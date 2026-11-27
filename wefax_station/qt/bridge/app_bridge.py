"""Pont principal PyQt6 ↔ moteurs métier (arbitre, cycle de vie, audio).

Orchestre RadioBridge et DspBridge, expose le statut global de l'application
au QML, et gère le thread audio (sounddevice).

Règle : ce fichier n'importe jamais tkinter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import logging
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import (
    QObject, pyqtSignal, pyqtSlot, pyqtProperty, QTimer
)

from wefax_station.qt.bridge.radio_bridge import RadioBridge
from wefax_station.qt.bridge.dsp_bridge import DspBridge

try:
    from wefax_station.version import SOFTWARE_VERSION
except ImportError:
    SOFTWARE_VERSION = "2.0-qt"

log = logging.getLogger("wefax.qt")

# Chemin par défaut des préférences
_PREFS_PATH = Path.home() / ".station_wefax_pro" / "preferences.json"


class AppBridge(QObject):
    """Pont principal : cycle de vie de l'application exposé au QML.

    Signaux → QML :
      statusChanged(str)         Message de statut (barre du bas)
      versionReady(str)          Numéro de version logicielle
      journalLine(str)           Ligne de journal
      modeChanged(str)           Mode courant : WEFAX | RTTY | NAVTEX | IDLE
      scheduleChanged(list)      Plan de réception mis à jour
      workspaceReady(str)        Chemin du dossier de travail ouvert
      audioConnected(bool)       Flux audio USB actif
      closingApp()               Fermeture confirmée
      weatherUpdated(dict)       Nouvelles données météo synoptique
      bulletinsUpdated(list)     Liste des bulletins RTTY/NAVTEX reçus
      rttyLine(str, str)         Ligne RTTY reçue (texte, station)
      navtexLine(str, str)       Ligne NAVTEX reçue (texte, station)
      prefsLoaded(dict)          Préférences chargées
      diagnosticLine(str)        Ligne de sortie diagnostic
    """

    # ── Signaux généraux ─────────────────────────────────────────────────────
    statusChanged    = pyqtSignal(str,            arguments=["msg"])
    versionReady     = pyqtSignal(str,            arguments=["version"])
    journalLine      = pyqtSignal(str,            arguments=["line"])
    modeChanged      = pyqtSignal(str,            arguments=["mode"])
    scheduleChanged  = pyqtSignal("QVariantList", arguments=["schedule"])
    workspaceReady   = pyqtSignal(str,            arguments=["path"])
    audioConnected   = pyqtSignal(bool,           arguments=["ok"])
    closingApp       = pyqtSignal()

    # ── Signaux météo / bulletins ────────────────────────────────────────────
    weatherUpdated   = pyqtSignal("QVariantMap",  arguments=["data"])
    bulletinsUpdated = pyqtSignal("QVariantList", arguments=["list"])

    # ── Signaux RTTY / NAVTEX ────────────────────────────────────────────────
    rttyLine         = pyqtSignal(str, str,       arguments=["text", "station"])
    navtexLine       = pyqtSignal(str, str,       arguments=["text", "station"])

    # ── Signaux paramètres / diagnostic ─────────────────────────────────────
    prefsLoaded      = pyqtSignal("QVariantMap",  arguments=["prefs"])
    diagnosticLine   = pyqtSignal(str,            arguments=["text"])

    # ────────────────────────────────────────────────────────────────────────
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._mode       = "IDLE"
        self._audio_ok   = False
        self._closing    = False
        self._prefs: dict[str, Any] = {}
        self._bulletins: list[dict] = []

        # Sous-ponts
        self.radio = RadioBridge(parent=self)
        self.dsp   = DspBridge(parent=self)

        # Moteurs métier (lazy)
        self._workspace = None
        self._arbiter   = None
        self._planner   = None

        # Timers
        self._radio_timer = QTimer(self)
        self._radio_timer.setInterval(500)
        self._radio_timer.timeout.connect(self.radio.pollStatus)

        self._dsp_timer = QTimer(self)
        self._dsp_timer.setInterval(80)
        self._dsp_timer.timeout.connect(self.dsp.pollAudio)

        self._sched_timer = QTimer(self)
        self._sched_timer.setInterval(60_000)
        self._sched_timer.timeout.connect(self._refresh_schedule)

        self._wx_timer = QTimer(self)
        self._wx_timer.setInterval(300_000)   # toutes les 5 min
        self._wx_timer.timeout.connect(self._refresh_weather)

        # Connexions inter-ponts
        self.radio.logMessage.connect(self.journalLine)
        self.dsp.phaseDetected.connect(self._on_phase)
        self.dsp.lineReceived.connect(self._on_dsp_line)
        self.dsp.imageCompleted.connect(self._on_image_completed)
        # Câblage DSP → AGC-RF : DspBridge alimente RadioBridge en métriques RMS/SNR
        self.dsp.set_radio_bridge(self.radio)

    # ── Propriétés ───────────────────────────────────────────────────────────

    @pyqtProperty(str, notify=modeChanged)
    def currentMode(self) -> str:
        return self._mode

    @pyqtProperty(bool, notify=audioConnected)
    def isAudioConnected(self) -> bool:
        return self._audio_ok

    @pyqtProperty(str, constant=True)
    def softwareVersion(self) -> str:
        return SOFTWARE_VERSION

    # ── Slots QML : cycle de vie ─────────────────────────────────────────────

    @pyqtSlot()
    def initialize(self) -> None:
        """Appelé par QML au chargement : démarre les moteurs, les timers."""
        self._load_prefs_internal()
        self.versionReady.emit(SOFTWARE_VERSION)
        self.statusChanged.emit("Station WEFAX PRO — prêt")
        self._start_arbiter()
        self._radio_timer.start()
        self._dsp_timer.start()
        self._sched_timer.start()
        self._wx_timer.start()
        self._refresh_schedule()
        self._refresh_weather()
        self.journalLine.emit(f"Station WEFAX PRO v{SOFTWARE_VERSION} démarrée.")

        # Auto-connexion radio si prefs l'indiquent
        if self._prefs.get("auto_connect_radio"):
            port     = self._prefs.get("serial_port", "COM14")
            baud     = int(self._prefs.get("baud_rate", 19200))
            protocol = self._prefs.get("protocol", "ICOM CI-V")
            civ_hex  = self._prefs.get("civ_address", "A4")
            self.radio.connectFull(port, baud, protocol, civ_hex)

        # Auto-démarrage audio
        if self._prefs.get("start_audio_auto"):
            dev  = self._prefs.get("audio_device", "")
            rate = int(self._prefs.get("sample_rate", 44100))
            self.startAudio(dev, rate)

    @pyqtSlot(str, int)
    def connectRadio(self, port: str, baud: int) -> None:
        ok  = self.radio.connect(port, baud)
        msg = f"CI-V {'établie' if ok else 'échouée'} sur {port} à {baud} bauds."
        self.statusChanged.emit(msg)
        self.journalLine.emit(msg)

    @pyqtSlot()
    def disconnectRadio(self) -> None:
        self.radio.disconnect()
        self.statusChanged.emit("Liaison CI-V fermée.")

    @pyqtSlot(str)
    def setMode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self.modeChanged.emit(mode)
        if self._arbiter:
            try:
                self._arbiter.set_requested_mode(mode, user_initiated=True)
            except Exception:
                pass
        self.journalLine.emit(f"Mode → {mode}")

    @pyqtSlot()
    def requestClose(self) -> None:
        if self._closing:
            return
        self._closing = True
        for t in (self._radio_timer, self._dsp_timer, self._sched_timer, self._wx_timer):
            t.stop()
        self._stop_audio()
        self.radio.disconnect()
        self.closingApp.emit()

    # ── Slots QML : audio ────────────────────────────────────────────────────

    @pyqtSlot(str, int)
    def startAudio(self, device: str, sample_rate: int) -> None:
        self._stop_audio()
        try:
            import sounddevice as sd
            self._sd_stream = sd.InputStream(
                device=device or None,
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=2048,
                callback=self._audio_callback,
            )
            self._sd_stream.start()
            self._audio_ok = True
            self.audioConnected.emit(True)
            self.journalLine.emit(f"Audio démarré : {device or 'défaut'} @ {sample_rate} Hz")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Audio : {exc}")
            self._audio_ok = False
            self.audioConnected.emit(False)

    @pyqtSlot()
    def stopAudio(self) -> None:
        self._stop_audio()

    # ── Slots QML : planning ─────────────────────────────────────────────────

    @pyqtSlot()
    def requestScheduleRefresh(self) -> None:
        self._refresh_schedule()

    @pyqtSlot(str, float)
    def launchScheduledReception(self, station_id: str, freq_khz: float) -> None:
        self.radio.tuneStation(freq_khz)
        self.setMode("WEFAX")
        self.journalLine.emit(f"▶ Lancement réception {station_id} @ {freq_khz} kHz")
        self.statusChanged.emit(f"Réception {station_id}")

    @pyqtSlot()
    def startNextScheduled(self) -> None:
        """Lance la prochaine émission prévue."""
        if self._planner:
            try:
                nxt = self._planner.next_emission()
                if nxt:
                    self.launchScheduledReception(nxt.get("station_id", "?"), nxt.get("freq_khz", 0))
            except Exception as exc:
                self.journalLine.emit(f"⚠️ Planificateur : {exc}")

    # ── Slots QML : météo ────────────────────────────────────────────────────

    @pyqtSlot()
    def refreshWeather(self) -> None:
        self._refresh_weather()

    # ── Slots QML : archives ─────────────────────────────────────────────────

    @pyqtSlot()
    def openArchives(self) -> None:
        path = Path(self._prefs.get("archive_dir", Path.home() / "Documents" / "WEFAX" / "archives"))
        path.mkdir(parents=True, exist_ok=True)
        self._open_folder(path)
        self.workspaceReady.emit(str(path))

    @pyqtSlot(str)
    def saveCurrentImage(self, src_path: str) -> None:
        """Copie l'image courante dans le dossier archives."""
        try:
            import shutil
            src = Path(src_path)
            dst_dir = Path(self._prefs.get("archive_dir", src.parent))
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            shutil.copy2(src, dst)
            self.journalLine.emit(f"Image archivée : {dst}")
            self.statusChanged.emit(f"Sauvegardé dans {dst_dir.name}")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Sauvegarde : {exc}")

    # ── Slots QML : RTTY / log ───────────────────────────────────────────────

    @pyqtSlot(int)
    def setRttyBaud(self, baud: int) -> None:
        if self.dsp and hasattr(self.dsp, "set_rtty_baud"):
            self.dsp.set_rtty_baud(baud)
        self.journalLine.emit(f"RTTY vitesse → {baud} Bd")

    @pyqtSlot(int)
    def setRttyShift(self, shift_hz: int) -> None:
        if self.dsp and hasattr(self.dsp, "set_rtty_shift"):
            self.dsp.set_rtty_shift(shift_hz)
        self.journalLine.emit(f"RTTY décalage → {shift_hz} Hz")

    @pyqtSlot()
    def saveRttyLog(self) -> None:
        try:
            from datetime import datetime
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = Path(self._prefs.get("workspace_dir", Path.home() / "Documents" / "WEFAX")) / f"rtty_{ts}.txt"
            dst.parent.mkdir(parents=True, exist_ok=True)
            # DspBridge accumule les lignes dans un buffer
            lines = getattr(self.dsp, "_rtty_lines", [])
            dst.write_text("\n".join(lines), encoding="utf-8")
            self.journalLine.emit(f"Log RTTY sauvegardé : {dst}")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Sauvegarde log RTTY : {exc}")

    @pyqtSlot(str)
    def openBulletin(self, bulletin_id: str) -> None:
        # Cherche dans le buffer et affiche le contenu complet
        for b in self._bulletins:
            if str(b.get("id")) == bulletin_id:
                self.journalLine.emit("─" * 60)
                self.journalLine.emit(b.get("full_text", "(pas de texte)"))
                self.journalLine.emit("─" * 60)
                break

    # ── Slots QML : workspace ────────────────────────────────────────────────

    @pyqtSlot()
    def openWorkspace(self) -> None:
        path = Path(self._prefs.get("workspace_dir", Path.home() / "Documents" / "WEFAX"))
        path.mkdir(parents=True, exist_ok=True)
        self._open_folder(path)
        self.workspaceReady.emit(str(path))

    @pyqtSlot()
    def chooseWorkspaceDir(self) -> None:
        # En Qt pur on passerait par QFileDialog — ici on émet juste un log
        self.journalLine.emit("ℹ️ Modifiez le chemin manuellement dans le champ texte.")

    @pyqtSlot()
    def chooseArchiveDir(self) -> None:
        self.journalLine.emit("ℹ️ Modifiez le chemin manuellement dans le champ texte.")

    # ── Slots QML : préférences ──────────────────────────────────────────────

    @pyqtSlot()
    def loadPrefs(self) -> None:
        self._load_prefs_internal()
        self.prefsLoaded.emit(self._prefs)

    @pyqtSlot("QVariantMap")
    def savePrefs(self, prefs: dict) -> None:
        self._prefs.update(prefs)
        try:
            _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _PREFS_PATH.write_text(json.dumps(self._prefs, indent=2, ensure_ascii=False), encoding="utf-8")
            self.statusChanged.emit("Préférences sauvegardées.")
            self.journalLine.emit("💾 Préférences enregistrées.")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Sauvegarde préfs : {exc}")

    @pyqtSlot(str)
    def switchUiMode(self, mode: str) -> None:
        """Redémarre l'application avec l'interface demandée (qt ou tk)."""
        self._prefs["ui_mode"] = mode
        try:
            _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _PREFS_PATH.write_text(json.dumps(self._prefs, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self.journalLine.emit(f"🔄 Redémarrage en mode {mode.upper()}…")
        self.statusChanged.emit(f"Redémarrage → {mode.upper()}")

        # Relancer le processus avec l'argument --ui approprié
        args = [sys.executable, "-m", "wefax_station", f"--ui={mode}"]
        try:
            subprocess.Popen(args)  # noqa: S603
            QTimer.singleShot(500, self.requestClose)
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Redémarrage impossible : {exc}")

    # ── Slots QML : téléchargement cartes web ────────────────────────────────

    @pyqtSlot()
    def downloadWebCharts(self) -> None:
        self.journalLine.emit("📥 Téléchargement des cartes web DWD…")
        threading.Thread(target=self._run_download_charts, daemon=True).start()

    # ── Slots QML : diagnostic ───────────────────────────────────────────────

    @pyqtSlot(str)
    def runDiagnostic(self, check: str) -> None:
        threading.Thread(target=self._run_diagnostic, args=(check,), daemon=True).start()

    # ── Méthodes internes ────────────────────────────────────────────────────

    def _load_prefs_internal(self) -> None:
        try:
            if _PREFS_PATH.exists():
                self._prefs = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Lecture préfs : %s", exc)

    def _start_arbiter(self) -> None:
        try:
            from wefax_station.hybrid.arbiter import HybridModeArbiter
            self._arbiter = HybridModeArbiter(app=self)  # type: ignore[arg-type]
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Arbitre non chargé : {exc}")

    def _on_phase(self, phase: str) -> None:
        status_map = {
            "START":   "Démarrage WEFAX détecté",
            "PHASING": "Alignement en cours…",
            "IMAGE":   "Réception image WEFAX",
            "STOP":    "Fin de carte reçue",
            "IDLE":    "En veille",
        }
        self.statusChanged.emit(status_map.get(phase, phase))

    def _on_dsp_line(self, n: int, frac: float) -> None:
        """Appelé à chaque ligne WEFAX reçue (progression)."""
        pass  # Transmis directement au QML via DspBridge.lineReceived

    def _on_image_completed(self, path: str) -> None:
        self.statusChanged.emit(f"Image reçue : {Path(path).name}")

    def _refresh_schedule(self) -> None:
        """Construit le programme d'émissions depuis schedules.py + planner."""
        try:
            from wefax_station.core.schedules import BROADCAST_SCHEDULES_UTC
            from datetime import datetime, timezone

            now_utc = datetime.now(timezone.utc)
            items: list[dict] = []

            for entry in BROADCAST_SCHEDULES_UTC:
                # Determine status
                try:
                    h, m = map(int, entry["time_utc"].split(":"))
                    emit_dt = now_utc.replace(hour=h, minute=m, second=0, microsecond=0)
                    delta   = (emit_dt - now_utc).total_seconds()
                    if -entry.get("duration_min", 20) * 60 < delta < 0:
                        status = "EN COURS"
                    elif 0 <= delta <= 3600:
                        status = "PROCHAIN"
                    elif delta < 0:
                        status = "PASSÉ"
                    else:
                        status = "PRÉVU"
                except Exception:
                    status = "---"

                items.append({
                    "time_utc":    entry.get("time_utc", "?"),
                    "duration_min": entry.get("duration_min", 20),
                    "station_id":  entry.get("station_id", "?"),
                    "station_name": entry.get("station_name", "?"),
                    "freq_khz":    entry.get("freq_khz", 0.0),
                    "mode":        entry.get("mode", "WEFAX"),
                    "status":      status,
                })

            self.scheduleChanged.emit(items)
        except Exception as exc:
            log.debug("Refresh schedule : %s", exc)

    def _refresh_weather(self) -> None:
        """Tente de charger les données météo depuis SynopticWeatherAnalysisEngine."""
        try:
            from wefax_station.meteo.synoptic import SynopticWeatherAnalysisEngine
            if not hasattr(self, "_wx_engine"):
                self._wx_engine = SynopticWeatherAnalysisEngine()
            data = self._wx_engine.get_latest_obs()
            if data:
                self.weatherUpdated.emit(data)
        except Exception:
            pass

    def _run_download_charts(self) -> None:
        try:
            from wefax_station.web.chart_fetcher import download_dwd_charts
            download_dwd_charts()
            self.journalLine.emit("✅ Cartes DWD téléchargées.")
            self.statusChanged.emit("Cartes web mises à jour.")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Téléchargement : {exc}")

    def _run_diagnostic(self, check: str) -> None:
        self.diagnosticLine.emit(f"▶ Diagnostic : {check}")
        try:
            if check == "civ":
                ok = self.radio._ctrl is not None and self.radio._ctrl.is_connected()
                self.diagnosticLine.emit(f"  CI-V : {'✅ connecté' if ok else '❌ non connecté'}")
            elif check == "audio":
                try:
                    import sounddevice as sd
                    devs = sd.query_devices()
                    self.diagnosticLine.emit(f"  Audio : {len(devs)} périphériques détectés.")
                except Exception as e:
                    self.diagnosticLine.emit(f"  Audio : ⚠️ {e}")
            elif check == "freq":
                if self.radio._ctrl and self.radio._ctrl.is_connected():
                    self.radio._ctrl.poll_hardware_state()
                    self.diagnosticLine.emit(f"  Fréquence : {self.radio._ctrl.actual_dial_khz:.3f} kHz")
                    self.diagnosticLine.emit(f"  Mode : {self.radio._ctrl.actual_mode_str}")
                else:
                    self.diagnosticLine.emit("  ❌ Radio non connectée.")
            self.diagnosticLine.emit(f"✅ Diagnostic {check} terminé.")
        except Exception as exc:
            self.diagnosticLine.emit(f"  ⚠️ Erreur : {exc}")

    def _open_folder(self, path: Path) -> None:
        """Ouvre un dossier dans l'explorateur système."""
        try:
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])  # noqa: S603, S607
            else:
                subprocess.Popen(["xdg-open", str(path)])  # noqa: S603, S607
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Ouverture dossier : {exc}")

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
        self.dsp.feed_audio(indata[:, 0])
