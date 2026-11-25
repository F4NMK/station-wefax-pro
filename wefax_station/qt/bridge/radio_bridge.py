"""Pont PyQt6 ↔ UnifiedRadioController (CI-V IC-705).

Ce QObject expose le contrôleur radio existant au moteur QML via des
propriétés Q_PROPERTY et des signaux Qt. Aucun code CI-V n'est dupliqué :
tout est délégué à radio.controller.UnifiedRadioController.

Règle : ce fichier n'importe jamais tkinter.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty, Q_ARG
from wefax_station.radio.controller import UnifiedRadioController


class RadioBridge(QObject):
    """Expose UnifiedRadioController au QML.

    Signaux émis → QML :
      freqChanged(float)        Fréquence affichée (Hz)
      modeChanged(str)          Mode CI-V actuel (p. ex. "USB", "FM")
      handshakeChanged(bool)    Liaison CAT vérifiée ou non
      smeterChanged(float)      Niveau S-mètre 0–9+ (linéaire)
      logMessage(str)           Message de journal à afficher
    """

    freqChanged     = pyqtSignal(float,  arguments=["hz"])
    modeChanged     = pyqtSignal(str,    arguments=["mode"])
    handshakeChanged = pyqtSignal(bool,  arguments=["ok"])
    smeterChanged   = pyqtSignal(float,  arguments=["level"])
    logMessage      = pyqtSignal(str,    arguments=["text"])

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = UnifiedRadioController(
            log_callback=lambda msg: self.logMessage.emit(msg)
        )
        self._freq_hz: float = 0.0
        self._mode: str = ""
        self._handshake: bool = False
        self._smeter: float = 0.0

    # ---------------------------------------------------------------- propriétés Q_PROPERTY

    @pyqtProperty(float, notify=freqChanged)
    def freqHz(self) -> float:
        return self._freq_hz

    @pyqtProperty(str, notify=modeChanged)
    def mode(self) -> str:
        return self._mode

    @pyqtProperty(bool, notify=handshakeChanged)
    def handshakeOk(self) -> bool:
        return self._handshake

    @pyqtProperty(float, notify=smeterChanged)
    def smeter(self) -> float:
        return self._smeter

    # ---------------------------------------------------------------- slots appelables depuis QML

    @pyqtSlot(str, int, result=bool)
    def connect(self, port: str, baud: int) -> bool:
        """Ouvre la liaison CI-V sur `port` à `baud` bauds. Renvoie True si OK."""
        ok = self._controller.connect(port, baud)
        self._handshake = ok
        self.handshakeChanged.emit(ok)
        return ok

    @pyqtSlot()
    def disconnect(self) -> None:
        """Ferme la liaison CI-V."""
        self._controller.disconnect()
        self._handshake = False
        self.handshakeChanged.emit(False)

    @pyqtSlot(float)
    def setFrequency(self, hz: float) -> None:
        """Commande QSY vers `hz` hertz (lecture seule d'abord : vérifie RX-safe)."""
        self._controller.set_frequency(int(hz))

    @pyqtSlot()
    def pollStatus(self) -> None:
        """Interroge le rig et met à jour les propriétés (à appeler périodiquement)."""
        try:
            freq = self._controller.read_frequency()
            if freq and freq != self._freq_hz:
                self._freq_hz = float(freq)
                self.freqChanged.emit(self._freq_hz)

            mode = self._controller.read_mode()
            if mode and mode != self._mode:
                self._mode = str(mode)
                self.modeChanged.emit(self._mode)

            sm = self._controller.read_smeter()
            if sm is not None:
                val = float(sm)
                if abs(val - self._smeter) > 0.05:
                    self._smeter = val
                    self.smeterChanged.emit(val)
        except Exception:
            pass

    # ---------------------------------------------------------------- accès au contrôleur brut (ponts internes)

    @property
    def controller(self) -> UnifiedRadioController:
        """Accès direct au contrôleur pour les ponts internes Python (non exposé QML)."""
        return self._controller
