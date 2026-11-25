"""Pont PyQt6 ↔ WefaxSignalAndImageEngine (moteur DSP WEFAX).

Alimente le moteur DSP avec l'audio reçu (sounddevice) et publie les
résultats vers QML via signaux Qt. La chaîne audio elle-même tourne dans
un thread séparé ; ce pont assure le passage thread-safe vers le thread Qt.

Règle : ce fichier n'importe jamais tkinter.
"""

from __future__ import annotations

import threading
import numpy as np

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
    lineReceived       = pyqtSignal(int, "QByteArray", arguments=["lineNo", "pixels"])
    imageCompleted     = pyqtSignal(str,             arguments=["path"])
    snrChanged         = pyqtSignal(float,           arguments=["snr"])
    phaseDetected      = pyqtSignal(str,             arguments=["phase"])

    def __init__(self, sample_rate: int = 44100, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = WefaxSignalAndImageEngine(sample_rate=sample_rate)
        self._sample_rate = sample_rate
        self._lock = threading.Lock()

        # Buffer circulaire audio partagé entre le callback sounddevice et pollAudio()
        self._ring: np.ndarray = np.zeros(sample_rate * 2, dtype=np.float32)
        self._ring_write = 0
        self._ring_read = 0

        self._phase = "IDLE"
        self._snr: float = 0.0
        self._level: float = 0.0

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

                rms = float(result.get("rms", 0.0))
                if abs(rms - self._level) > 0.01:
                    self._level = rms
                    self.signalLevelChanged.emit(rms)

                snr = float(result.get("snr_db", 0.0))
                if abs(snr - self._snr) > 0.1:
                    self._snr = snr
                    self.snrChanged.emit(snr)

            sig = self._engine.assess_wefax_signal(chunk)
            if sig:
                phase = str(sig.get("phase", "IDLE"))
                if phase != self._phase:
                    self._phase = phase
                    self.phaseDetected.emit(phase)
        except Exception:
            pass

    @pyqtSlot()
    def reset(self) -> None:
        """Réinitialise le moteur DSP (entre deux réceptions)."""
        self._engine.reset_filter_states()
        self._phase = "IDLE"
        self.phaseDetected.emit("IDLE")

    # ---------------------------------------------------------------- accès brut (ponts internes)

    @property
    def engine(self) -> WefaxSignalAndImageEngine:
        return self._engine
