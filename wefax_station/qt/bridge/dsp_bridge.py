"""Pont PyQt6 ↔ WefaxSignalAndImageEngine (moteur DSP WEFAX).

Alimente le moteur DSP avec l'audio reçu (sounddevice) et publie les
résultats vers QML via signaux Qt. La chaîne audio elle-même tourne dans
un thread séparé ; ce pont assure le passage thread-safe vers le thread Qt.

Règle : ce fichier n'importe jamais tkinter.
"""

from __future__ import annotations

import threading
import numpy as np
from scipy import signal as sp_signal

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty, QTimer
from wefax_station.dsp.engine import WefaxSignalAndImageEngine


class DspBridge(QObject):
    """Expose le moteur DSP WEFAX au QML.

    Signaux émis → QML :
      spectrumReady(list)        Spectre BF : liste de 128 flottants 0–1
      signalLevelChanged(float)  Niveau RMS 0–1
      lineReceived(int, bytes)   Numéro de ligne + données pixel brutes
      imageCompleted(str)        Chemin du fichier image sauvegardé
      snrChanged(float)          SNR estimé dB
      phaseDetected(str)         "START" | "PHASING" | "IMAGE" | "STOP" | "IDLE"
    """

    spectrumReady      = pyqtSignal("QVariantList",  arguments=["spectrum"])
    signalLevelChanged = pyqtSignal(float,           arguments=["level"])
    lineReceived       = pyqtSignal(int, float,      arguments=["lineNo", "fraction"])
    imageCompleted     = pyqtSignal(str,             arguments=["path"])
    snrChanged         = pyqtSignal(float,           arguments=["snr"])
    phaseDetected      = pyqtSignal(str,             arguments=["phase"])

    def __init__(self, sample_rate: int = 44100, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = WefaxSignalAndImageEngine(sample_rate=sample_rate)
        self._sample_rate = sample_rate
        self._lock = threading.Lock()
        # Référence vers RadioBridge pour alimenter l'AGC-RF en métriques DSP
        self._radio_bridge = None

        # Filtre passe-bande WEFAX optionnel (1400–2400 Hz)
        # Appliqué avant analyse et démodulation pour supprimer le bruit hors-bande
        self._wefax_filter_enabled: bool = False
        self._build_wefax_filter(sample_rate)

        # Buffer circulaire audio partagé entre le callback sounddevice et pollAudio()
        self._ring: np.ndarray = np.zeros(sample_rate * 2, dtype=np.float32)
        self._ring_write = 0
        self._ring_read = 0

        self._phase = "IDLE"
        self._snr: float = 0.0
        self._level: float = 0.0

        # Buffer RTTY (pour sauvegarde)
        self._rtty_lines: list[str] = []
        self._rtty_baud: int = 50
        self._rtty_shift_hz: int = 450
        self._lines_received: int = 0

    # ---------------------------------------------------------------- propriétés

    @pyqtProperty(str, notify=phaseDetected)
    def phase(self) -> str:
        return self._phase

    @pyqtProperty(float, notify=snrChanged)
    def snr(self) -> float:
        return self._snr

    @pyqtProperty(float, notify=signalLevelChanged)
    def signalLevel(self) -> float:
        return self._level

    # ---------------------------------------------------------------- alimentation audio (thread sounddevice)

    def feed_audio(self, chunk: np.ndarray) -> None:
        """Appelé depuis le callback sounddevice (thread audio). Thread-safe."""
        # Filtre passe-bande WEFAX appliqué ici, avant mise en buffer
        # (hors du lock pour minimiser la durée de verrouillage)
        chunk = self._apply_wefax_filter(chunk)
        with self._lock:
            n = len(chunk)
            ring_len = len(self._ring)
            end = self._ring_write + n
            if end <= ring_len:
                self._ring[self._ring_write:end] = chunk
            else:
                split = ring_len - self._ring_write
                self._ring[self._ring_write:] = chunk[:split]
                self._ring[:end - ring_len] = chunk[split:]
            self._ring_write = end % ring_len

    # ---------------------------------------------------------------- slots QML

    @pyqtSlot()
    def pollAudio(self) -> None:
        """À appeler depuis un QTimer (thread Qt). Consomme le buffer audio et publie les résultats."""
        with self._lock:
            w = self._ring_write
            r = self._ring_read
            if w == r:
                return
            ring_len = len(self._ring)
            if w > r:
                chunk = self._ring[r:w].copy()
            else:
                chunk = np.concatenate([self._ring[r:], self._ring[:w]])
            self._ring_read = w

        if len(chunk) < 512:
            return

        try:
            result = self._engine.analyze_live_audio_spectrum(chunk)
            if result:
                spectrum = result.get("spectrum_normalized", [])
                if spectrum is not None and len(spectrum) > 0:
                    # Sous-échantillonner à 128 points pour QML
                    s = np.asarray(spectrum, dtype=float)
                    idx = np.linspace(0, len(s) - 1, 128).astype(int)
                    self.spectrumReady.emit(s[idx].tolist())

                rms_dbfs = float(result.get("rms_dbfs", -90.0))
                # Normaliser dBFS [-90..0] → niveau linéaire [0..1] pour l'UI
                rms_linear = max(0.0, min(1.0, (rms_dbfs + 90.0) / 90.0))
                if abs(rms_linear - self._level) > 0.01:
                    self._level = rms_linear
                    self.signalLevelChanged.emit(rms_linear)

                snr = float(result.get("snr_db", 0.0))
                if abs(snr - self._snr) > 0.1:
                    self._snr = snr
                    self.snrChanged.emit(snr)

                # Alimenter la boucle AGC-RF avec les métriques DSP réelles
                if self._radio_bridge is not None:
                    self._radio_bridge.update_audio_metrics(rms_dbfs, snr)

            sig = self._engine.assess_wefax_signal(chunk)
            if sig:
                phase = str(sig.get("phase", "IDLE"))
                if phase != self._phase:
                    self._phase = phase
                    self.phaseDetected.emit(phase)

                # Lignes reçues (progression image)
                n_lines = int(sig.get("lines_received", 0))
                if n_lines != self._lines_received:
                    self._lines_received = n_lines
                    total_expected = int(sig.get("total_lines", 800)) or 800
                    fraction = min(1.0, n_lines / total_expected)
                    self.lineReceived.emit(n_lines, fraction)

                # Chemin image complète
                img_path = sig.get("image_path", "")
                if img_path and phase == "STOP":
                    self.imageCompleted.emit(str(img_path))

        except Exception:
            pass

    @pyqtSlot()
    def reset(self) -> None:
        """Réinitialise le moteur DSP (entre deux réceptions)."""
        self._engine.reset_filter_states()
        self._phase = "IDLE"
        self._lines_received = 0
        self.phaseDetected.emit("IDLE")

    @pyqtSlot(str, "QVariant")
    def setDspParam(self, param: str, value) -> None:
        """Applique un paramètre DSP (notch FFT, tenseur, binarisation, offset USB)."""
        try:
            if hasattr(self._engine, "set_param"):
                self._engine.set_param(param, value)
            elif hasattr(self._engine, param):
                setattr(self._engine, param, value)
        except Exception:
            pass

    def set_rtty_baud(self, baud: int) -> None:
        self._rtty_baud = baud

    def set_rtty_shift(self, shift_hz: int) -> None:
        self._rtty_shift_hz = shift_hz

    # ---------------------------------------------------------------- filtre WEFAX passe-bande

    def _build_wefax_filter(self, sample_rate: int) -> None:
        """Construit le filtre Butterworth passe-bande WEFAX [1400–2400 Hz].

        Plage choisie :
          • 1500 Hz = tonalité noire (niveau référence, phasing, sync)
          • 2300 Hz = tonalité blanche (niveau maximal)
          • ± 100 Hz de garde → 1400–2400 Hz
        Le filtre coupe tout le bruit hors de cette bande (QRM, QRN, 50/100 Hz,
        bruit de fond HF) avant analyse et démodulation.
        """
        fs = max(8000, int(sample_rate))
        nyq = 0.5 * fs
        low  = 1400.0 / nyq
        high = min(0.95, 2400.0 / nyq)
        self._sos_wefax = sp_signal.butter(6, [low, high], btype="band", output="sos")
        self._zi_wefax  = sp_signal.sosfilt_zi(self._sos_wefax) * 0.0

    def _apply_wefax_filter(self, chunk: np.ndarray) -> np.ndarray:
        """Applique le filtre passe-bande WEFAX si activé. Thread audio → utilise état zi persistant."""
        if not self._wefax_filter_enabled:
            return chunk
        filtered, self._zi_wefax = sp_signal.sosfilt(
            self._sos_wefax, chunk.astype(np.float64), zi=self._zi_wefax
        )
        return filtered.astype(np.float32)

    @pyqtSlot(bool)
    def setWefaxFilterEnabled(self, enabled: bool) -> None:
        """Active ou désactive le filtre passe-bande WEFAX (slot QML)."""
        self._wefax_filter_enabled = bool(enabled)
        if not enabled:
            # Réinitialiser l'état du filtre pour éviter les artefacts à la réactivation
            self._zi_wefax = sp_signal.sosfilt_zi(self._sos_wefax) * 0.0

    @pyqtProperty(bool)
    def wefaxFilterEnabled(self) -> bool:
        return self._wefax_filter_enabled

    # ---------------------------------------------------------------- accès brut (ponts internes)

    def set_radio_bridge(self, radio_bridge) -> None:
        """Câble RadioBridge pour alimenter sa boucle AGC-RF en métriques DSP.

        Appelé par AppBridge après création des deux sous-ponts.
        """
        self._radio_bridge = radio_bridge

    @property
    def engine(self) -> WefaxSignalAndImageEngine:
        return self._engine
