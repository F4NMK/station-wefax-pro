"""Pont principal PyQt6 ↔ moteurs métier (arbitre, cycle de vie, audio).

Orchestre RadioBridge et DspBridge, expose le statut global de l'application
au QML, et gère le thread audio (sounddevice).

Règle : ce fichier n'importe jamais tkinter.
"""

from __future__ import annotations

import threading
import time
import logging
from pathlib import Path

import numpy as np
from PyQt6.QtCore import (
    QObject, pyqtSignal, pyqtSlot, pyqtProperty, QTimer
)

from wefax_station.qt.bridge.radio_bridge import RadioBridge
from wefax_station.qt.bridge.dsp_bridge import DspBridge
from wefax_station.hybrid.arbiter import HybridModeArbiter
from wefax_station.hybrid.planner import ScheduleSyncAndPlanner
from wefax_station.storage.portable import PortableWorkspaceManager
from wefax_station.version import SOFTWARE_VERSION

log = logging.getLogger("wefax.qt")


class AppBridge(QObject):
    """Pont principal : cycle de vie de l'application exposé au QML.

    Signaux → QML :
      statusChanged(str)        Message de statut (barre du bas)
      versionReady(str)         Numéro de version logicielle
      journalLine(str)          Ligne de journal à ajouter au log QML
      modeChanged(str)          Mode courant : "WEFAX" | "RTTY" | "NAVTEX" | "IDLE"
      scheduleChanged(list)     Plan de réception mis à jour (liste de dicts)
      workspaceReady(str)       Chemin du dossier de travail ouvert
      audioConnected(bool)      Flux audio USB actif ou non
      closingApp()              Demande de fermeture confirmée
    """

    statusChanged    = pyqtSignal(str,           arguments=["msg"])
    versionReady     = pyqtSignal(str,           arguments=["version"])
    journalLine      = pyqtSignal(str,           arguments=["line"])
    modeChanged      = pyqtSignal(str,           arguments=["mode"])
    scheduleChanged  = pyqtSignal("QVariantList", arguments=["schedule"])
    workspaceReady   = pyqtSignal(str,           arguments=["path"])
    audioConnected   = pyqtSignal(bool,          arguments=["ok"])
    closingApp       = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._mode = "IDLE"
        self._audio_ok = False
        self._closing = False

        # --- Sous-ponts ---
        self.radio = RadioBridge(parent=self)
        self.dsp = DspBridge(parent=self)

        # --- Moteurs métier (sans UI) ---
        self._workspace = PortableWorkspaceManager()
        self._arbiter: HybridModeArbiter | None = None
        self._planner: ScheduleSyncAndPlanner | None = None

        # --- Timer polling radio (500 ms) ---
        self._radio_timer = QTimer(self)
        self._radio_timer.setInterval(500)
        self._radio_timer.timeout.connect(self.radio.pollStatus)

        # --- Timer polling DSP (80 ms) ---
        self._dsp_timer = QTimer(self)
        self._dsp_timer.setInterval(80)
        self._dsp_timer.timeout.connect(self.dsp.pollAudio)

        # --- Timer schedule (60 s) ---
        self._sched_timer = QTimer(self)
        self._sched_timer.setInterval(60_000)
        self._sched_timer.timeout.connect(self._refresh_schedule)

        # --- Connexion journaux radio → journal unifié ---
        self.radio.logMessage.connect(self.journalLine)
        self.dsp.phaseDetected.connect(self._on_phase)

    # ---------------------------------------------------------------- propriétés

    @pyqtProperty(str, notify=modeChanged)
    def currentMode(self) -> str:
        return self._mode

    @pyqtProperty(bool, notify=audioConnected)
    def isAudioConnected(self) -> bool:
        return self._audio_ok

    @pyqtProperty(str, constant=True)
    def softwareVersion(self) -> str:
        return SOFTWARE_VERSION

    # ---------------------------------------------------------------- slots QML

    @pyqtSlot()
    def initialize(self) -> None:
        """Appelé par QML au chargement : démarre les moteurs, les timers, émet les états initiaux."""
        self.versionReady.emit(SOFTWARE_VERSION)
        self.statusChanged.emit("Station WEFAX PRO — prêt")
        self._start_arbiter()
        self._radio_timer.start()
        self._dsp_timer.start()
        self._sched_timer.start()
        self._refresh_schedule()
        self.journalLine.emit(f"Station WEFAX PRO v{SOFTWARE_VERSION} démarrée.")

    @pyqtSlot(str, int)
    def connectRadio(self, port: str, baud: int) -> None:
        """Ouvre la liaison CI-V."""
        ok = self.radio.connect(port, baud)
        msg = f"Liaison CI-V {'établie' if ok else 'échouée'} sur {port} à {baud} bauds."
        self.statusChanged.emit(msg)
        self.journalLine.emit(msg)

    @pyqtSlot()
    def disconnectRadio(self) -> None:
        self.radio.disconnect()
        self.statusChanged.emit("Liaison CI-V fermée.")

    @pyqtSlot(str)
    def setMode(self, mode: str) -> None:
        """Bascule le mode de réception : WEFAX | RTTY | NAVTEX | IDLE."""
        if mode == self._mode:
            return
        self._mode = mode
        self.modeChanged.emit(mode)
        if self._arbiter:
            self._arbiter.set_requested_mode(mode, user_initiated=True)
        self.journalLine.emit(f"Mode → {mode}")

    @pyqtSlot(str)
    def openWorkspace(self, path: str) -> None:
        """Ouvre un dossier de travail portable."""
        try:
            self._workspace.set_root(Path(path))
            self.workspaceReady.emit(path)
            self.statusChanged.emit(f"Dossier de travail : {path}")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Dossier inaccessible : {exc}")

    @pyqtSlot()
    def requestClose(self) -> None:
        """Demande de fermeture : arrête les timers, coupe l'audio, émet closingApp."""
        if self._closing:
            return
        self._closing = True
        self._radio_timer.stop()
        self._dsp_timer.stop()
        self._sched_timer.stop()
        self._stop_audio()
        self.radio.disconnect()
        self.closingApp.emit()

    # ---------------------------------------------------------------- audio (sounddevice)

    @pyqtSlot(str, int)
    def startAudio(self, device: str, sample_rate: int) -> None:
        """Démarre le flux audio USB. Appel QML."""
        self._stop_audio()
        try:
            import sounddevice as sd
            self._sd_stream = sd.InputStream(
                device=device,
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=2048,
                callback=self._audio_callback,
            )
            self._sd_stream.start()
            self._audio_ok = True
            self.audioConnected.emit(True)
            self.journalLine.emit(f"Audio USB démarré : {device} @ {sample_rate} Hz")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Audio : {exc}")
            self._audio_ok = False
            self.audioConnected.emit(False)

    @pyqtSlot()
    def stopAudio(self) -> None:
        self._stop_audio()

    def _stop_audio(self) -> None:
        stream = getattr(self, "_sd_stream", None)
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            self._sd_stream = None
        if self._audio_ok:
            self._audio_ok = False
            self.audioConnected.emit(False)

    def _audio_callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        """Callback sounddevice → alimente DspBridge (thread audio)."""
        self.dsp.feed_audio(indata[:, 0])

    # ---------------------------------------------------------------- internes

    def _start_arbiter(self) -> None:
        try:
            self._arbiter = HybridModeArbiter(app=self)  # type: ignore[arg-type]
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Arbitre : {exc}")

    def _on_phase(self, phase: str) -> None:
        status_map = {
            "START":   "Démarrage WEFAX détecté",
            "PHASING": "Alignement en cours…",
            "IMAGE":   "Réception image WEFAX",
            "STOP":    "Fin de carte reçue",
            "IDLE":    "En veille",
        }
        self.statusChanged.emit(status_map.get(phase, phase))

    def _refresh_schedule(self) -> None:
        try:
            if self._arbiter:
                summary = self._arbiter.plan_summary(n=6)
                # Convertir en liste de dicts sérialisables JSON pour QML
                items = []
                for entry in (summary or []):
                    items.append({
                        "label": str(entry.get("label", "")),
                        "time":  str(entry.get("time", "")),
                        "mode":  str(entry.get("mode", "")),
                        "freq":  str(entry.get("freq", "")),
                    })
                self.scheduleChanged.emit(items)
        except Exception:
            pass

    # ---------------------------------------------------------------- accès bruts (ponts internes Python)

    @property
    def arbiter(self) -> HybridModeArbiter | None:
        return self._arbiter
