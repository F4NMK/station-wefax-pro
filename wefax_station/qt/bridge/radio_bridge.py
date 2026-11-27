"""Pont PyQt6 ↔ UnifiedRadioController (CI-V IC-705).

Ce QObject expose le contrôleur radio existant au moteur QML via des
propriétés Q_PROPERTY et des signaux Qt. Aucun code CI-V n'est dupliqué :
tout est délégué à radio.controller.UnifiedRadioController.

Règle : ce fichier n'importe jamais tkinter.
"""

from __future__ import annotations

import time
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot, pyqtProperty
from wefax_station.radio.controller import UnifiedRadioController
from wefax_station.radio.auto_rf_gain import AutoRFGain

# Paramètres IC-705 par défaut (port surchargeable depuis QML)
_DEFAULT_PORT    = "COM14"
_DEFAULT_BAUD    = 19200
_DEFAULT_PROTO   = "ICOM CI-V"
_DEFAULT_CIV_HEX = "A4"

# Plage normalisée S-mètre IC-705 : 0–241
_SMETER_MAX = 241.0

# Protocoles supportés
PROTOCOLS = ["ICOM CI-V", "YAESU CAT", "AUTO"]


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
    # Signaux étendus
    preampChanged    = pyqtSignal(int,   arguments=["level"])
    attChanged       = pyqtSignal(bool,  arguments=["on"])
    filterChanged    = pyqtSignal(int,   arguments=["filtNo"])
    scanProgress     = pyqtSignal(str, float, arguments=["stationId", "snr"])  # scan en cours
    scanCompleted    = pyqtSignal("QVariantList", arguments=["results"])        # résultats scan
    portsRefreshed   = pyqtSignal("QVariantList", arguments=["ports"])          # liste ports COM
    audioDevicesReady= pyqtSignal("QVariantList", arguments=["devices"])        # liste entrées audio
    # AGC-RF
    rfGainChanged    = pyqtSignal(int,  arguments=["value"])     # valeur CI-V 0–255
    agcRfStatusChanged = pyqtSignal(str, arguments=["msg"])      # dernier message de l'AGC-RF

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = UnifiedRadioController(
            log_callback=lambda msg: self.logMessage.emit(msg)
        )
        self._freq_hz:   float = 0.0
        self._mode:      str   = ""
        self._handshake: bool  = False
        self._smeter:    float = 0.0
        self._preamp:    int   = 1
        self._att:       bool  = False
        self._filter:    int   = 2
        self._scan_results: list = []
        self._scanning: bool = False
        # AGC-RF — boucle de contre-réaction gain RF
        self._agc_rf = AutoRFGain()
        self._agc_rf_rms:  float | None = None   # dernier RMS audio reçu (dBFS)
        self._agc_rf_snr:  float | None = None   # dernier SNR reçu (dB)
        # Timer AGC-RF : tick toutes les 2 s
        self._agc_rf_timer = QTimer()
        self._agc_rf_timer.setInterval(2000)
        self._agc_rf_timer.timeout.connect(self._agc_rf_tick)
        self._agc_rf_timer.start()

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
            self._emit_freq()
            self._emit_mode()
        return ok

    @pyqtSlot(str, int, str, str, result=bool)
    def connectFull(self, port: str, baud: int, protocol: str, civ_hex: str) -> bool:
        """Connexion avec tous les paramètres configurables."""
        ok = self._controller.connect(port, baud, protocol=protocol, civ_hex=civ_hex)
        self._handshake = ok
        self.handshakeChanged.emit(ok)
        if ok:
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

    @pyqtSlot(float)
    def tuneStation(self, freq_khz: float) -> None:
        """Accordage sur une station WEFAX (fréquence porteuse en kHz)."""
        self._controller.set_wefax_frequency(freq_khz, apply_usb_offset=True)
        self.logMessage.emit(f"QSY → {freq_khz:.1f} kHz (porteuse)")

    @pyqtSlot(int)
    def setPreamp(self, level: int) -> None:
        """Préampli HF : 0=IPO, 1=PAMP1, 2=PAMP2 — garde-fou CI-V inclus."""
        try:
            self._controller.set_preamp(level)
            self._preamp = level
            self.preampChanged.emit(level)
        except Exception as exc:
            self.logMessage.emit(f"⚠️ Préampli : {exc}")

    @pyqtSlot(bool)
    def setAttenuator(self, on: bool) -> None:
        """Atténuateur RF ±20 dB — garde-fou CI-V inclus."""
        try:
            self._controller.set_attenuator(on)
            self._att = on
            self.attChanged.emit(on)
        except Exception as exc:
            self.logMessage.emit(f"⚠️ Atténuateur : {exc}")

    @pyqtSlot(int)
    def setIFFilter(self, filt_no: int) -> None:
        """Filtre FI IC-705 : 1=Large, 2=WEFAX optimal, 3=Étroit."""
        try:
            self._controller.set_if_filter(filt_no)
            self._filter = filt_no
            self.filterChanged.emit(filt_no)
        except Exception as exc:
            self.logMessage.emit(f"⚠️ Filtre FI : {exc}")

    @pyqtSlot()
    def refreshPorts(self) -> None:
        """Rafraîchit la liste des ports série et émet portsRefreshed."""
        try:
            from wefax_station.deps import HAS_SERIAL, serial
            if HAS_SERIAL:
                ports = [p.device for p in serial.tools.list_ports.comports()]
            else:
                ports = ["COM14", "COM5", "COM3"]
        except Exception:
            ports = ["COM14"]
        if not ports:
            ports = ["COM14"]
        self.portsRefreshed.emit(ports)

    @pyqtSlot()
    def refreshAudioDevices(self) -> None:
        """Rafraîchit la liste des entrées audio et émet audioDevicesReady."""
        devices = []
        try:
            import sounddevice as sd
            for dev in sd.query_devices():
                if dev.get("max_input_channels", 0) > 0:
                    devices.append(dev.get("name", ""))
        except Exception:
            pass
        if not devices:
            devices = ["IC-705 USB Audio", "Microphone", "Line In"]
        self.audioDevicesReady.emit(devices)

    @pyqtSlot()
    def autoDetect(self) -> None:
        """Tente l'auto-détection IC-705 / Yaesu sur tous les ports disponibles."""
        import threading
        threading.Thread(target=self._run_autodetect, daemon=True).start()

    def _run_autodetect(self) -> None:
        self.logMessage.emit("▶ Auto-détection CAT + audio…")
        try:
            from wefax_station.deps import HAS_SERIAL, serial
            ports = [p.device for p in serial.tools.list_ports.comports()] if HAS_SERIAL else []
            for port in ports:
                for baud in [19200, 9600, 4800]:
                    try:
                        ok = self._controller.connect(port, baud, protocol="AUTO", civ_hex=_DEFAULT_CIV_HEX)
                        if ok:
                            self._handshake = True
                            self.handshakeChanged.emit(True)
                            self.logMessage.emit(f"✅ IC-705 trouvé sur {port} @ {baud}")
                            self._emit_freq()
                            self._emit_mode()
                            return
                    except Exception:
                        pass
            self.logMessage.emit("⚠️ Aucun transceiver détecté automatiquement.")
        except Exception as exc:
            self.logMessage.emit(f"⚠️ Auto-détection échouée : {exc}")

    @pyqtSlot()
    def scanFrequencies(self) -> None:
        """Lance le scan des 7 fréquences WEFAX et émet scanCompleted."""
        if self._scanning:
            return
        import threading
        threading.Thread(target=self._run_scan, daemon=True).start()

    def _run_scan(self) -> None:
        from wefax_station.core.stations import WEFAX_STATIONS
        import time
        self._scanning = True
        self.logMessage.emit("▶ Scan des fréquences WEFAX…")
        results = []
        for sta in WEFAX_STATIONS:
            try:
                self.logMessage.emit(f"  → {sta['id']} {sta['freq']} kHz…")
                self.scanProgress.emit(sta['id'], 0.0)
                # QSY vers la station
                self._controller.set_wefax_frequency(sta['freq'], apply_usb_offset=True)
                time.sleep(1.5)
                self._controller.poll_hardware_state()
                raw = self._controller.s_meter_raw if self._controller.s_meter_valid else 0
                snr = round(raw / 241.0 * 30.0, 1)  # approximation 0–30 dB
                results.append({
                    "id":      sta['id'],
                    "station": sta['station'],
                    "freq":    sta['freq'],
                    "period":  sta['period'],
                    "snr":     snr,
                    "snrText": f"{snr:+.1f} dB",
                })
                self.scanProgress.emit(sta['id'], snr)
            except Exception as exc:
                results.append({"id": sta['id'], "station": sta['station'],
                                 "freq": sta['freq'], "period": sta['period'],
                                 "snr": -99.0, "snrText": "N/M"})
        self._scan_results = results
        self._scanning = False
        self.scanCompleted.emit(results)
        self.logMessage.emit("✅ Scan terminé.")

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
            self._emit_rf_gain()
        except Exception:
            pass

    # ---------------------------------------------------------------- AGC-RF

    @pyqtSlot(bool)
    def setAgcRfEnabled(self, enabled: bool) -> None:
        """Active ou désactive la boucle AGC-RF depuis l'UI."""
        self._agc_rf.enabled = enabled
        state = "activé" if enabled else "désactivé"
        self.agcRfStatusChanged.emit(f"AGC-RF {state}")
        self.logMessage.emit(f"ℹ️ AGC-RF {state}")

    @pyqtSlot(int)
    def setRfGain(self, value: int) -> None:
        """Réglage manuel du gain RF (0–255) depuis l'UI — suspend l'AGC-RF 15 min."""
        value = max(0, min(255, int(value)))
        now = time.monotonic()
        self._agc_rf.notify_manual_change(now, value)
        try:
            self._controller.set_rf_gain(value)
            self.rfGainChanged.emit(value)
        except Exception as exc:
            self.logMessage.emit(f"⚠️ Gain RF : {exc}")

    @pyqtSlot(float)
    def setAgcRfTarget(self, target_dbfs: float) -> None:
        """Ajuste le niveau RMS cible de l'AGC-RF (dBFS) depuis l'UI."""
        self._agc_rf.target_dbfs = float(target_dbfs)
        self.logMessage.emit(f"ℹ️ AGC-RF cible → {target_dbfs:+.1f} dBFS")

    @pyqtProperty(bool)
    def agcRfEnabled(self) -> bool:
        return self._agc_rf.enabled

    @pyqtProperty(int)
    def rfGain(self) -> int:
        return self._agc_rf.current_gain

    @pyqtProperty(int)
    def rfGainPct(self) -> int:
        return self._agc_rf.current_gain_pct

    def update_audio_metrics(self, rms_dbfs: float | None, snr_db: float | None) -> None:
        """Appelé par DspBridge (ou tout autre pont DSP) à chaque bloc audio analysé.

        Met à jour les métriques DSP utilisées par la boucle AGC-RF pour sa décision.
        Cette méthode est thread-safe car elle ne fait que stocker des floats.
        """
        self._agc_rf_rms = rms_dbfs
        self._agc_rf_snr = snr_db

    def _agc_rf_tick(self) -> None:
        """Tick AGC-RF toutes les 2 s — appelé par QTimer dans le thread Qt."""
        now = time.monotonic()
        actual_gain = getattr(self._controller, "actual_rf_gain", 255)
        new_gain = self._agc_rf.step(
            now,
            rms_dbfs=self._agc_rf_rms,
            snr_db=self._agc_rf_snr,
            actual_gain=actual_gain,
        )
        if new_gain is not None:
            try:
                self._controller.set_rf_gain(new_gain)
                self.rfGainChanged.emit(new_gain)
                # émettre le dernier message journalisé
                evts = self._agc_rf.events
                if evts:
                    self.agcRfStatusChanged.emit(evts[-1][1])
            except Exception as exc:
                self.logMessage.emit(f"⚠️ AGC-RF tick : {exc}")

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

    def _emit_rf_gain(self) -> None:
        """Émet rfGainChanged si le gain RF a changé (p. ex. modification manuelle sur le rig)."""
        actual = getattr(self._controller, "actual_rf_gain", 255)
        if actual != self._agc_rf.current_gain:
            # Modification externe détectée → notifier l'AGC-RF
            self._agc_rf.notify_manual_change(time.monotonic(), actual)
            self.rfGainChanged.emit(actual)

    # ---------------------------------------------------------------- accès brut (ponts internes)

    @property
    def controller(self) -> UnifiedRadioController:
        """Accès direct au contrôleur pour les ponts internes Python (non exposé QML)."""
        return self._controller
