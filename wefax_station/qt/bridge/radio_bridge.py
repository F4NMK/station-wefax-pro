"""Pont PyQt6 ↔ UnifiedRadioController (CI-V IC-705).

Ce QObject expose le contrôleur radio existant au moteur QML via des
propriétés Q_PROPERTY et des signaux Qt. Aucun code CI-V n'est dupliqué :
tout est délégué à radio.controller.UnifiedRadioController.

Règle : ce fichier n'importe jamais tkinter.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty
from wefax_station.radio.controller import UnifiedRadioController

# Paramètres IC-705 par défaut (port surchargeable depuis QML)
_DEFAULT_PORT    = "COM14"
_DEFAULT_BAUD    = 19200
_DEFAULT_PROTO   = "ICOM CI-V"
_DEFAULT_CIV_HEX = "A4"

# Plage normalisée S-mètre IC-705 : 0–241
_SMETER_MAX = 241.0


class RadioBridge(QObject):
    """Expose UnifiedRadioController au QML.

    Signaux émis → QML :
      freqChanged(float)        Fréquence affichée (Hz)
      modeChanged(str)          Mode CI-V actuel (p. ex. "USB-D")
      handshakeChanged(bool)    Liaison CAT vérifiée ou non
      smeterChanged(float)      Niveau S-mètre 0.0–1.0 (normalisé)
      logMessage(str)           Message de journal à afficher
    """

    freqChanged      = pyqtSignal(float, arguments=["hz"])
    modeChanged      = pyqtSignal(str,   arguments=["mode"])
    handshakeChanged = pyqtSignal(bool,  arguments=["ok"])
    smeterChanged    = pyqtSignal(float, arguments=["level"])
    logMessage       = pyqtSignal(str,   arguments=["text"])

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = UnifiedRadioController(
            log_callback=lambda msg: self.logMessage.emit(msg)
        )
        self._freq_hz:   float = 0.0
        self._mode:      str   = ""
        self._handshake: bool  = False
        self._smeter:    float = 0.0

    # ---------------------------------------------------------------- Q_PROPERTY

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

    # ---------------------------------------------------------------- slots QML

    @pyqtSlot(str, int, result=bool)
    def connect(self, port: str, baud: int) -> bool:
        """Ouvre la liaison CI-V sur `port` à `baud` bauds. Renvoie True si OK."""
        ok = self._controller.connect(
            port, baud,
            protocol=_DEFAULT_PROTO,
            civ_hex=_DEFAULT_CIV_HEX,
        )
        self._handshake = ok
        self.handshakeChanged.emit(ok)
        if ok:
            # Émet les valeurs initiales après connexion
            self._emit_freq()
            self._emit_mode()
        return ok

    @pyqtSlot()
    def disconnect(self) -> None:
        """Ferme la liaison CI-V."""
        self._controller.disconnect()
        self._handshake = False
        self.handshakeChanged.emit(False)

    @pyqtSlot(float)
    def setFrequency(self, hz: float) -> None:
        """Commande QSY vers `hz` hertz via set_wefax_frequency (garde-fou RX-safe inclus)."""
        self._controller.set_wefax_frequency(hz / 1000.0, apply_usb_offset=True)

    @pyqtSlot()
    def pollStatus(self) -> None:
        """Interroge le rig et met à jour les propriétés (appelé par QTimer 500 ms)."""
        if not self._controller.port_open:
            return
        try:
            self._controller.poll_hardware_state()
            self._emit_freq()
            self._emit_mode()
            self._emit_smeter()
        except Exception:
            pass

    # ---------------------------------------------------------------- internes

    def _emit_freq(self) -> None:
        hz = self._controller.actual_dial_khz * 1000.0
        if abs(hz - self._freq_hz) > 1.0:
            self._freq_hz = hz
            self.freqChanged.emit(hz)

    def _emit_mode(self) -> None:
        mode = self._controller.actual_mode_str or "---"
        if mode != self._mode:
            self._mode = mode
            self.modeChanged.emit(mode)

    def _emit_smeter(self) -> None:
        if not self._controller.s_meter_valid:
            return
        level = min(self._controller.s_meter_raw / _SMETER_MAX, 1.0)
        if abs(level - self._smeter) > 0.01:
            self._smeter = level
            self.smeterChanged.emit(level)

    # ---------------------------------------------------------------- accès brut (ponts internes)

    @property
    def controller(self) -> UnifiedRadioController:
        """Accès direct au contrôleur pour les ponts internes Python (non exposé QML)."""
        return self._controller
