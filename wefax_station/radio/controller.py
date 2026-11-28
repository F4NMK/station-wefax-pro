"""Contrôleur radio unifié (IC-705 CI-V et autres protocoles)."""

import threading

from wefax_station.radio import scope as _scope
import time
from wefax_station.core.stations import RTTY_WEATHER_STATIONS, WEFAX_STATIONS
from wefax_station.deps import HAS_SERIAL, serial
from wefax_station.radio.profiles import CIV_RX_PROFILE
from wefax_station.radio.yaesu import (
    ASCII_RX_PROFILE,
    LEGACY_READ_FREQ,
    LEGACY_READ_RX,
    ascii_freq_cmd,
    ascii_is_safe,
    legacy_freq_frame,
    legacy_mode_frame,
    legacy_smeter_label,
    parse_ascii_freq,
    parse_ascii_id,
    parse_legacy_freq,
)


class _UnifiedRadioControllerBase:
    PROTOCOLS = [
        "ICOM CI-V (IC-705 / IC-7300)",
        "YAESU CAT ASCII (FT-891 / FT-991A / FT-DX10 / FT-710)",
        "YAESU CAT LEGACY (FT-817 / FT-857 / FT-897)",
        "AUTO (Icom puis Yaesu)",
    ]
    BAUDS = {
        "ICOM": [19200, 115200, 9600, 38400],
        "YAESU CAT ASCII": [38400, 4800, 9600, 19200],
        "YAESU CAT LEGACY": [9600, 38400, 4800, 19200],
    }

    def __init__(self, log_callback=None):
        self.ser = None
        self.lock = threading.RLock()
        self.port_open = False
        self.handshake_ok = False
        self.protocol = self.PROTOCOLS[0]
        self.civ_addr = 0xA4
        self.usb_dial_offset_khz = -1.90
        self.log_cb = log_callback

        self.active_station_id = "DDK3"
        self.active_station_name = "DWD Pinneberg (All.)"
        self.active_station_family = "DWD"
        self.actual_freq_khz = 7880.0
        self.actual_dial_khz = 7878.10
        self.actual_preamp = 1
        self.actual_att = False
        self.actual_mode_str = "USB-D"
        self.actual_filter_str = "FIL1"
        self.actual_agc_str = "FAST"
        self.s_meter_raw = 95
        self.s_meter_valid = False
        self.s_meter_label = "S8"
        self.s_meter_dbm = -79.0
        self.ovf_active = False
        self.last_auto_rf_action_ts = 0.0
        self.param_status = {}
        self.tx_guard_enabled = True
        self.cat_fail_count = 0
        self.model_name = ""
        self._poll_count = 0

    @property
    def cat_label(self):
        """Libellé court de la liaison CAT pour l'interface."""
        if "ICOM" in self.protocol:
            return f"Icom CI-V 0x{self.civ_addr:02X}"
        return self.model_name or "Yaesu CAT"

    def log(self, msg: str):
        if self.log_cb:
            self.log_cb(msg)

    def update_station_metadata_by_freq(self, freq_khz: float):
        for st in WEFAX_STATIONS:
            if abs(st["freq"] - freq_khz) < 1.0:
                self.active_station_id = st["id"]
                self.active_station_name = st["station"]
                self.active_station_family = st["family"]
                return
        self.active_station_id = "MANUEL"
        self.active_station_name = "Fréquence Personnalisée"

    def apply_optimal_wefax_rx_profile(self, filter_idx: int = 1) -> bool:
        """
        Configure automatiquement le récepteur (IC-705 / Yaesu) avec les réglages
        les plus optimaux pour la réception de cartes météo WEFAX :
        - Mode USB-D (Data : coupe le micro et route l'audio USB sans coloration)
        - Filtre FI optimal FIL1 (2.4 kHz : englobe 1500..2300 Hz et coupe le bruit hors-bande)
        - AGC FAST (empêche un craquement QRN d'assourdir le récepteur sur plusieurs lignes)
        - NR OFF, notch automatique OFF, notch manuel OFF ; NB conservé (choix opérateur).
        Détail et justification : radio/profiles.py.
        """
        filter_idx = max(1, min(3, int(filter_idx)))
        self.actual_mode_str = "USB-D"
        self.actual_filter_str = f"FIL{filter_idx}"
        self.actual_agc_str = "FAST"

        if not self.port_open:
            self.log(
                f"ℹ️ [SIMU] Profil Optimal WEFAX appliqué : Mode=USB-D | Filtre={self.actual_filter_str} | AGC=FAST | NR/notch OFF | NB conservé"
            )
            return True

        if "ICOM" in self.protocol:
            # 1. Passage en mode USB + filtre FILx (0x06 : 0x01=USB, 0x02=FIL1)
            self._civ_transaction([0x06, 0x01, filter_idx])
            time.sleep(0.03)
            # 2. Activation du mode DATA (USB-D) + Filtre FILx sur IC-705 / IC-7300 (0x1A 0x06 [Data=01] [Fil=02])
            self._civ_transaction([0x1A, 0x06, 0x01, filter_idx])
            time.sleep(0.03)
            # 3. Forçage AGC FAST (0x16 0x12 : 0x01=FAST, 0x02=MID, 0x03=SLOW)
            self._civ_transaction([0x16, 0x12, 0x01])
            time.sleep(0.02)
            # 4. NR OFF, notch automatique OFF, notch manuel OFF (NB laissé au choix de l'opérateur)
            for _name, cmd in CIV_RX_PROFILE[1:]:
                self._civ_transaction(cmd)
                time.sleep(0.02)
            self.log(
                f"✅ [IC-705] Profil Optimal WEFAX actif : USB-D | {self.actual_filter_str} | AGC FAST | NR/notch OFF | NB conservé"
            )
            return True

        elif "YAESU CAT ASCII" in self.protocol:
            for _name, cmd in ASCII_RX_PROFILE:
                self._yaesu_ascii_cmd(cmd, read_reply=False)
                time.sleep(0.03)
            self.log(
                f"✅ [{self.model_name or 'YAESU'}] Profil WEFAX actif : DATA-USB | AGC FAST | NR OFF | "
                "notch auto OFF | NB conservé"
            )
            return True

        elif "YAESU CAT LEGACY" in self.protocol:
            self._legacy_cmd(legacy_mode_frame("DIG"))
            self.log(f"✅ [{self.model_name or 'YAESU'}] Mode DIG (menu DIG MODE = USER-U conseillé)")
            return True

        return False

    def auto_detect_port_and_connect(self, preferred_protocol: str, civ_hex: str = "A4") -> tuple:
        with self.lock:
            if not HAS_SERIAL:
                self.log("❌ pyserial non installé.")
                return False, "", 19200, "pyserial absent"

            ports_info = list(serial.tools.list_ports.comports())
            if not ports_info:
                self.log("⚠️ Aucun port COM détecté.")
                return False, "", 19200, "Aucun port COM"

            def _port_priority(p):
                desc = f"{p.device} {p.description} {p.manufacturer or ''}".upper()
                score = 0
                if "ENHANCED" in desc:  # port CAT des Yaesu à double port USB (FT-991A, FTDX10, FT-710)
                    score += 80
                if "STANDARD" in desc:
                    score -= 20
                if getattr(p, "vid", None) == 0x0C26 or "IC-705" in desc or "ICOM" in desc:
                    score += 100
                if "CI-V" in desc or "SERIAL PORT A" in desc:
                    score += 50
                if "GPS" in desc or "SERIAL PORT B" in desc:
                    score -= 40
                if "USB" in desc or "ACM" in desc or "CP210" in desc:
                    score += 20
                return -score

            ports_info.sort(key=_port_priority)
            self.log(f"🔍 Scan Auto Ports COM : {[p.device for p in ports_info]}")

            target_civ = int(civ_hex.replace("0x", "").strip() or "A4", 16)
            if "AUTO" in preferred_protocol:
                protocols = [p for p in self.PROTOCOLS if "AUTO" not in p]
            else:
                protocols = [preferred_protocol]
            for proto in protocols:
                key = next(k for k in self.BAUDS if k in proto)
                for p in ports_info:
                    for baud in self.BAUDS[key]:
                        ok, det_civ = self._probe_single_port(p.device, baud, proto, target_civ)
                        if not ok:
                            continue
                        hex_civ = f"{det_civ:02X}"
                        if self.connect(p.device, baud, proto, hex_civ) and self.handshake_ok:
                            self.set_attenuator(False)
                            self.set_preamp(1)
                            self.apply_optimal_wefax_rx_profile(filter_idx=1)
                            self.set_wefax_frequency(self.actual_freq_khz, apply_usb_offset=True)
                            what = f"CI-V 0x{hex_civ}" if "ICOM" in proto else (self.model_name or "Yaesu")
                            return (True, p.device, baud, f"Connecté sur {p.device} ({baud} bps, {what})")
            bauds = self.BAUDS["ICOM"]
            self.log("⚠️ Aucune connexion verifiee ; consulter CAT_PROBE et les erreurs de connexion.")
            return False, ports_info[0].device, bauds[0], "Aucune réponse radio"

    def _probe_single_port(self, port_name: str, baud: int, protocol: str, civ_addr: int) -> tuple:
        temp = None
        stage = "open"
        with self.lock:
            try:
                self.log(f"CAT_PROBE port={port_name} baud={baud} stage=open")
                temp = serial.Serial(port=port_name, baudrate=baud, timeout=0.25, write_timeout=0.25)
                stage = "control_lines"
                temp.dtr = True
                temp.rts = False
                time.sleep(0.08)
                temp.reset_input_buffer()
                stage = "query"
                if "ICOM" in protocol:
                    temp.write(bytes([0xFE, 0xFE, civ_addr, 0xE0, 0x03, 0xFD]))
                    temp.flush()
                    time.sleep(0.12)
                    raw = temp.read(64)
                    reply, addr = self._extract_civ_reply(raw, civ_addr)
                    if reply is not None:
                        self.log(f"CAT_PROBE port={port_name} baud={baud} reply=frequency")
                        return True, addr
                    temp.reset_input_buffer()
                    temp.write(bytes([0xFE, 0xFE, 0, 0xE0, 0x19, 0, 0xFD]))
                    temp.flush()
                    time.sleep(0.14)
                    raw = temp.read(64)
                    reply, addr = self._extract_civ_reply(raw, None)
                    if reply is not None and addr is not None:
                        return True, addr
                    self.log(f"CAT_PROBE port={port_name} baud={baud} no_matching_reply raw={raw.hex(' ')}")
                    return False, civ_addr
                if "YAESU CAT ASCII" in protocol:
                    temp.write(b"FA;")
                    temp.flush()
                    time.sleep(0.15)
                    response = temp.read(32).decode("ascii", errors="ignore")
                    ok = parse_ascii_freq(response) is not None
                    self.log(f"CAT_PROBE port={port_name} baud={baud} yaesu_ascii={'ok' if ok else 'non'}")
                    return ok, civ_addr
                if "YAESU CAT LEGACY" in protocol:
                    temp.write(LEGACY_READ_FREQ)
                    temp.flush()
                    time.sleep(0.15)
                    raw = temp.read(5)
                    ok = parse_legacy_freq(raw) is not None
                    self.log(f"CAT_PROBE port={port_name} baud={baud} yaesu_legacy={'ok' if ok else 'non'}")
                    return ok, civ_addr
                return False, civ_addr
            except Exception as exc:
                self.log(f"CAT_PROBE_ERROR port={port_name} baud={baud} stage={stage} error={exc!r}")
                return False, civ_addr
            finally:
                if temp is not None:
                    try:
                        temp.close()
                        self.log(f"CAT_PROBE_CLOSED port={port_name} baud={baud}")
                    except Exception as exc:
                        self.log(f"CAT_CLOSE_ERROR port={port_name} error={exc!r}")

    def connect(self, port: str, baud: int, protocol: str, civ_hex: str = "A4") -> bool:
        if not HAS_SERIAL:
            return False
        with self.lock:
            self.disconnect()
            try:
                self.protocol = protocol
                self.civ_addr = int(civ_hex.replace("0x", "").strip() or "A4", 16)
                self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.35, write_timeout=0.35)
                self.ser.dtr = True
                self.ser.rts = False
                time.sleep(0.25)
                self.ser.reset_input_buffer()
                self.port_open = True
                self.handshake_ok = self.verify_radio_handshake()
                if self.handshake_ok:
                    if "ICOM" in protocol:
                        self.model_name = "IC-705 / Icom"
                        self.log(
                            f"✅ Liaison CAT vérifiée sur {port} ({baud} bps | CI-V 0x{self.civ_addr:02X})"
                        )
                    else:
                        self.log(
                            f"✅ Liaison CAT vérifiée sur {port} ({baud} bps | {self.model_name or 'Yaesu'})"
                        )
                    self.apply_optimal_wefax_rx_profile(filter_idx=1)
                    self.poll_hardware_state()
                else:
                    self.log(f"⚠️ Port {port} ouvert mais sans réponse CAT. Connexion refusée.")
                    self.disconnect()
                    return False
                return True
            except Exception as exc:
                if self.ser is not None:
                    try:
                        self.ser.close()
                    except Exception as close_exc:
                        self.log(f"CAT_CLOSE_ERROR connect : {close_exc!r}")
                self.ser = None
                self.port_open = False
                self.handshake_ok = False
                self.log(f"❌ Erreur port {port} : {exc}")
                return False

    def disconnect(self):
        with self.lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            self.port_open = False
            self.handshake_ok = False
            self.s_meter_valid = False

    def _extract_civ_reply(self, raw: bytes, expected_src_addr=None) -> tuple:
        if not raw:
            return None, expected_src_addr
        for ch in raw.split(b"\xfd"):
            pos = ch.find(b"\xfe\xfe")
            if pos == -1 or len(ch) < pos + 5:
                continue
            frame = list(ch[pos + 2 :])
            dst, src, payload = frame[0], frame[1], frame[2:]
            if src == 0xE0:
                continue
            if dst in (0xE0, 0x00):
                if expected_src_addr is None or src == expected_src_addr:
                    return payload, src
        return None, expected_src_addr

    def _set_param_status(self, name, status, requested=None, readback=None, critical=False):
        self.param_status[name] = {
            "status": status,
            "requested": requested,
            "readback": readback,
            "critical": critical,
        }

    def _ensure_rx_safe(self, cmd_bytes):
        if not self.tx_guard_enabled:
            return True
        if cmd_bytes and cmd_bytes[0] in (0x1C, 0x17):
            self.log("⛔ Commande TX bloquée par le garde-fou de sécurité.")
            return False
        return True

    def _civ_transaction(self, cmd_bytes: list, wait_s: float = 0.10) -> list:
        if not self.port_open or not self.ser:
            return None
        if not self._ensure_rx_safe(cmd_bytes):
            return None
        frame = bytes([0xFE, 0xFE, self.civ_addr, 0xE0] + cmd_bytes + [0xFD])
        with self.lock:
            try:
                self.ser.reset_input_buffer()
                self.ser.write(frame)
                self.ser.flush()
                self._set_param_status(f"cmd_{cmd_bytes[0]:02X}", "envoyé")
                deadline = time.time() + max(0.28, wait_s * 3.0)
                buf = bytearray()
                while time.time() < deadline:
                    w = self.ser.in_waiting
                    chunk = self.ser.read(w if w > 0 else 1)
                    if chunk:
                        buf.extend(chunk)
                        reply, src_addr = self._extract_civ_reply(bytes(buf), None)
                        if reply is not None:
                            if src_addr and src_addr != self.civ_addr:
                                self.civ_addr = src_addr
                            self.handshake_ok = True
                            self.cat_fail_count = 0
                            self._set_param_status(f"cmd_{cmd_bytes[0]:02X}", "acquitté")
                            return reply
                    else:
                        time.sleep(0.015)
                self.cat_fail_count += 1
                self.log(
                    f"⚠️ Pas de réponse CI-V à la commande {bytes(cmd_bytes).hex(' ')} ({self.cat_fail_count} échec(s))"
                )
                if self.cat_fail_count >= 3:
                    self.log("⛔ Liaison CAT déclarée hors service après 3 absences de réponse.")
                    self.handshake_ok = False
                return None
            except Exception as exc:
                self.log(f"❌ Erreur CAT : {exc}")
                self.handshake_ok = False
                self.port_open = False
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
                return None

    def _yaesu_ascii_cmd(self, cmd_str: str, read_reply=True) -> str:
        if not self.port_open or not self.ser:
            return ""
        if not cmd_str.endswith(";"):
            cmd_str += ";"
        if self.tx_guard_enabled and not ascii_is_safe(cmd_str):
            self.log(f"⛔ Commande Yaesu {cmd_str} bloquée par le garde-fou réception.")
            return ""
        with self.lock:
            try:
                self.ser.reset_input_buffer()
                self.ser.write(cmd_str.encode("ascii"))
                self.ser.flush()
                if not read_reply:
                    return "OK"
                time.sleep(0.08)
                resp = self.ser.read_until(b";").decode("ascii", errors="ignore").strip()
                if resp:
                    self.handshake_ok = True
                return resp
            except Exception:
                return ""

    def _legacy_cmd(self, frame: bytes, reply_len: int = 0) -> bytes:
        """Trame CAT 5 octets FT-817/857/897 (réception uniquement : fréquence, mode, lectures)."""
        if not self.port_open or not self.ser:
            return b""
        if frame[4] in (0x08, 0x88, 0x0F, 0x8F, 0x2F) and self.tx_guard_enabled:  # PTT, marche/arrêt
            self.log("⛔ Trame Yaesu d'émission bloquée par le garde-fou réception.")
            return b""
        with self.lock:
            try:
                self.ser.reset_input_buffer()
                self.ser.write(frame)
                self.ser.flush()
                if not reply_len:
                    time.sleep(0.05)
                    return b"OK"
                time.sleep(0.08)
                return self.ser.read(reply_len)
            except Exception:
                return b""

    def verify_radio_handshake(self) -> bool:
        if not self.port_open:
            return False
        if "ICOM" in self.protocol:
            # jusqu'à 3 essais : juste après l'ouverture du port USB, l'IC-705 peut ne pas encore répondre
            rep = None
            for attempt in range(3):
                rep = self._civ_transaction([0x03], wait_s=0.12)
                if rep is not None and len(rep) >= 1 and rep != [0xFA]:
                    self.cat_fail_count = 0
                    self.handshake_ok = True
                    return True
                time.sleep(0.25)
            self.log(f"CAT_HANDSHAKE réponse invalide à la lecture de fréquence : {rep!r}")
            self.handshake_ok = False
            return False
        elif "YAESU CAT ASCII" in self.protocol:
            for attempt in range(3):
                resp = self._yaesu_ascii_cmd("FA;", read_reply=True)
                if parse_ascii_freq(resp) is not None:
                    self.handshake_ok = True
                    self.model_name = parse_ascii_id(self._yaesu_ascii_cmd("ID;", read_reply=True)) or "Yaesu"
                    return True
                time.sleep(0.25)
            self.handshake_ok = False
            return False
        elif "YAESU CAT LEGACY" in self.protocol:
            for attempt in range(3):
                if parse_legacy_freq(self._legacy_cmd(LEGACY_READ_FREQ, 5)) is not None:
                    self.handshake_ok = True
                    self.model_name = "FT-817/818/857/897"
                    return True
                time.sleep(0.25)
            self.handshake_ok = False
            return False
        self.handshake_ok = False
        return False

    def set_wefax_frequency(self, carrier_freq_khz: float, apply_usb_offset: bool = True) -> bool:
        self.actual_freq_khz = float(carrier_freq_khz)
        self.update_station_metadata_by_freq(self.actual_freq_khz)
        dial_khz = carrier_freq_khz + (self.usb_dial_offset_khz if apply_usb_offset else 0.0)
        self.actual_dial_khz = round(dial_khz, 3)
        freq_hz = int(round(self.actual_dial_khz * 1000.0))

        if not self.port_open:
            self.log(
                f"ℹ️ [SIMU] QSY {self.active_station_id} ({carrier_freq_khz:.1f} kHz | "
                f"Dial USB-D {self.actual_dial_khz:.2f} kHz | {self.actual_filter_str} | AGC FAST)"
            )
            return True

        if "ICOM" in self.protocol:
            s = f"{freq_hz:010d}"
            bcd = [int(s[8:10], 16), int(s[6:8], 16), int(s[4:6], 16), int(s[2:4], 16), int(s[0:2], 16)]
            rep = self._civ_transaction([0x05] + bcd)
            readback = self._civ_transaction([0x03], wait_s=0.12)
            if readback is not None:
                self._set_param_status(
                    "frequence", "confirmé", requested=carrier_freq_khz, readback=readback, critical=True
                )
            else:
                self._set_param_status("frequence", "acquitté", requested=carrier_freq_khz, critical=True)
            # Bascule systématiquement en USB-D + FIL + profil RX (AGC FAST, NR/notch OFF) à chaque QSY
            fil_num = 2 if "2" in self.actual_filter_str else (1 if "1" in self.actual_filter_str else 3)
            self._civ_transaction([0x06, 0x01, fil_num])
            self._civ_transaction([0x1A, 0x06, 0x01, fil_num])
            for _name, cmd in CIV_RX_PROFILE:
                self._civ_transaction(cmd)
            if rep is not None:
                self.log(
                    f"✅ [IC-705] QSY confirmé : {self.active_station_id} {carrier_freq_khz:.1f} kHz "
                    f"(USB-D {self.actual_dial_khz:.2f} kHz | {self.actual_filter_str} | AGC FAST)"
                )
                return True
            else:
                self._set_param_status("frequence", "écart", requested=carrier_freq_khz, critical=True)
            return False

        elif "YAESU CAT ASCII" in self.protocol:
            self._yaesu_ascii_cmd(ascii_freq_cmd(freq_hz), read_reply=False)
            time.sleep(0.05)
            for _name, cmd in ASCII_RX_PROFILE:
                self._yaesu_ascii_cmd(cmd, read_reply=False)
            got = parse_ascii_freq(self._yaesu_ascii_cmd("FA;", read_reply=True))
            ok = got is not None and abs(got - freq_hz) <= 20
            self._set_param_status(
                "frequence",
                "confirmé" if ok else "écart",
                requested=carrier_freq_khz,
                readback=got,
                critical=True,
            )
            self.log(
                f"{'✅' if ok else '⚠️'} [{self.model_name or 'YAESU'}] QSY {self.active_station_id} "
                f"{carrier_freq_khz:.1f} kHz (DATA-USB {self.actual_dial_khz:.2f} kHz | AGC FAST | relu {got})"
            )
            return ok

        elif "YAESU CAT LEGACY" in self.protocol:
            self._legacy_cmd(legacy_freq_frame(freq_hz))
            self._legacy_cmd(legacy_mode_frame("DIG"))
            got = parse_legacy_freq(self._legacy_cmd(LEGACY_READ_FREQ, 5))
            ok = got is not None and abs(got - freq_hz) <= 20
            self.log(
                f"{'✅' if ok else '⚠️'} [{self.model_name or 'YAESU'}] QSY {self.active_station_id} "
                f"{carrier_freq_khz:.1f} kHz (DIG {self.actual_dial_khz:.2f} kHz | relu {got})"
            )
            return ok
        return False

    def set_if_filter(self, fil_idx: int):
        fil_idx = max(1, min(3, int(fil_idx)))
        self.actual_filter_str = f"FIL{fil_idx}"
        if not self.port_open:
            self.log(f"ℹ️ [SIMU] Filtre FI réglé sur {self.actual_filter_str} (USB-D)")
            return
        if "ICOM" in self.protocol:
            self._civ_transaction([0x06, 0x01, fil_idx])
            self._civ_transaction([0x1A, 0x06, 0x01, fil_idx])
            self.log(f"✅ [IC-705] Filtre FI configuré sur {self.actual_filter_str} en mode USB-D.")

    def set_preamp(self, level: int) -> int:
        level = max(0, min(2, int(level)))
        if not self.port_open:
            self.actual_preamp = level
            if level > 0:
                self.actual_att = False
            self.log(f"ℹ️ [SIMU] Préampli réglé sur P.AMP {level}")
            return self.actual_preamp

        if "ICOM" in self.protocol:
            if level > 0 and self.actual_att:
                self._civ_transaction([0x11, 0x00])
                self.actual_att = False
            rep_set = self._civ_transaction([0x16, 0x02, level])
            time.sleep(0.04)
            rep_read = self._civ_transaction([0x16, 0x02])
            if rep_read and len(rep_read) >= 3 and rep_read[0] == 0x16 and rep_read[1] == 0x02:
                self.actual_preamp = int(rep_read[2])
                self.log(
                    f"🔄 [Contre-Réaction IC-705] P.AMP demandé={level} -> État matériel lu={self.actual_preamp}"
                )
            elif rep_set == [0xFB]:
                self.actual_preamp = level
                self.log(f"✅ [ACK IC-705] P.AMP={level} confirmé")
            return self.actual_preamp

        elif "YAESU CAT ASCII" in self.protocol:
            self._yaesu_ascii_cmd(f"PA0{level};", read_reply=False)
            resp = self._yaesu_ascii_cmd("PA0;", read_reply=True)
            if len(resp) >= 4 and resp.startswith("PA0") and resp[3].isdigit():
                self.actual_preamp = int(resp[3])
            else:
                self.actual_preamp = level
            return self.actual_preamp

        self.actual_preamp = level
        return self.actual_preamp

    # ------------------------------------------------------------ veille spectrale (2.8.9)
    def _scope_cmd(self, cmd, timeout=0.35):
        """Commande 27 xx : renvoie la charge de la réponse qui lui correspond (27 xx …), ou FB / FA.

        Pendant la lecture du spectre, des trames 27 00 arrivent sans arrêt : on ne garde que la réponse
        à NOTRE commande, contrairement à _civ_transaction qui prend la première trame venue."""
        # 2.9.0 — garde-fou : ce chemin ne contourne jamais la protection d'émission (seules les
        # commandes d'écran 27 xx passent ; 1C et 17 ne peuvent pas être envoyées d'ici)
        if not cmd or cmd[0] != 0x27:
            raise ValueError(f"_scope_cmd réservé aux commandes 27 xx (reçu {bytes(cmd).hex(' ')})")
        frame = bytes([0xFE, 0xFE, self.civ_addr, 0xE0] + list(cmd) + [0xFD])
        self.ser.write(frame)
        self.ser.flush()
        deadline = time.time() + timeout
        buf = bytearray()
        while time.time() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if not chunk:
                continue
            buf.extend(chunk)
            for fr in _scope.iter_frames(bytes(buf)):
                if len(fr) < 3 or fr[1] == 0xE0:
                    continue
                pl = fr[2:]
                if pl[:1] in ([0xFB], [0xFA]):
                    return pl
                if pl[:2] == list(cmd[:2]) and pl[:2] != [0x27, 0x00]:  # (on n'envoie jamais 27 00)
                    return pl
            if len(buf) > 4096:
                del buf[:-512]
        return None

    def read_scope_sweep(self, span_hz=250000, timeout_s=1.5):
        """Un balayage du spectre (centré sur la fréquence écoutée), puis remise en l'état de l'écran.

        Aucune émission, aucun changement de fréquence ni de réglage de réception. Renvoie
        {"center_hz", "span_hz", "points"} ou None (poste non Icom, non connecté ou sans réponse)."""
        if not self.port_open or not self.ser or "ICOM" not in self.protocol:
            return None
        with self.lock:
            saved = {}
            result = None
            try:
                self.ser.reset_input_buffer()
                for key, cmd in (("on", [0x27, 0x10]), ("out", [0x27, 0x11]), ("mode", [0x27, 0x14, 0x00]), ("span", [0x27, 0x15, 0x00])):
                    r = self._scope_cmd(cmd)
                    if r and r[:2] == cmd[:2] and len(r) > len(cmd):
                        saved[key] = r[len(cmd):] if key in ("mode", "span") else r[2:3]
                self._scope_cmd([0x27, 0x10, 0x01])
                self._scope_cmd([0x27, 0x14, 0x00, 0x00])
                self._scope_cmd([0x27, 0x15, 0x00] + _scope.bcd_freq(span_hz))
                self.ser.reset_input_buffer()
                self._scope_cmd([0x27, 0x11, 0x01])
                asm = _scope.SweepAssembler()
                deadline = time.time() + timeout_s
                first = bytearray()
                blank = None
                self.last_scope_stats = {"bytes": 0, "sweeps": 0, "blank": 0}
                while time.time() < deadline:
                    chunk = self.ser.read(self.ser.in_waiting or 1)
                    if not chunk:
                        continue
                    self.last_scope_stats["bytes"] += len(chunk)
                    if len(first) < 96:
                        first.extend(chunk[: 96 - len(first)])
                    # 2.9.0 — les octets sont recollés d'une lecture à l'autre (trames coupées)
                    if asm.feed_raw(chunk, None):
                        pts = asm.points()
                        if len(pts) < 200 or not asm.center_hz:
                            continue
                        self.last_scope_stats["sweeps"] += 1
                        sweep = {"center_hz": asm.center_hz, "span_hz": asm.span_hz or span_hz, "points": pts}
                        if _scope.is_blank_sweep(pts):
                            # premier balayage après le changement de largeur souvent vide : on attend le suivant
                            self.last_scope_stats["blank"] += 1
                            blank = dict(sweep, blank=True)
                            continue
                        result = sweep
                        break
                if result is None and blank is not None:
                    result = blank  # données bien reçues, mais spectre entièrement à zéro
                if result is None and not getattr(self, "_scope_diag_logged", False):
                    # une seule fois : de quoi comprendre un format de trame différent de celui attendu
                    self._scope_diag_logged = True
                    self.log(
                        f"🔭 Spectre : aucun balayage reconnu en {timeout_s:.1f} s ; réglages lus {saved} ; "
                        f"premiers octets reçus : {bytes(first).hex(' ') or '(rien)'}"
                    )
            except Exception as exc:
                self.log(f"Veille spectrale : erreur de lecture {exc!r}")
            finally:
                try:
                    self._scope_cmd([0x27, 0x11] + list(saved.get("out", [0x00]))[:1])
                    time.sleep(0.05)
                    self.ser.reset_input_buffer()
                    if "span" in saved and len(saved["span"]) >= 5:
                        self._scope_cmd([0x27, 0x15, 0x00] + list(saved["span"])[-5:])
                    if "mode" in saved and saved["mode"]:
                        self._scope_cmd([0x27, 0x14, 0x00] + list(saved["mode"])[-1:])
                    if "on" in saved:
                        self._scope_cmd([0x27, 0x10] + list(saved["on"])[:1])
                    self.ser.reset_input_buffer()
                except Exception:
                    pass
            return result

    def set_attenuator(self, enable: bool) -> bool:
        enable = bool(enable)
        if not self.port_open:
            self.actual_att = enable
            if enable:
                self.actual_preamp = 0
            self.log(f"ℹ️ [SIMU] Atténuateur réglé sur {'ON (-20dB)' if enable else 'OFF'}")
            return self.actual_att

        if "ICOM" in self.protocol:
            att_byte = 0x20 if enable else 0x00
            rep_set = self._civ_transaction([0x11, att_byte])
            time.sleep(0.04)
            rep_read = self._civ_transaction([0x11])
            if rep_read and len(rep_read) >= 2 and rep_read[0] == 0x11:
                self.actual_att = rep_read[1] > 0
                if self.actual_att:
                    self.actual_preamp = 0
                self.log(f"🔄 [Contre-Réaction IC-705] ATT={'ON' if self.actual_att else 'OFF'} confirmé")
            elif rep_set == [0xFB]:
                self.actual_att = enable
                if enable:
                    self.actual_preamp = 0
            return self.actual_att

        elif "YAESU CAT ASCII" in self.protocol:
            self._yaesu_ascii_cmd("RA01;" if enable else "RA00;", read_reply=False)
            resp = self._yaesu_ascii_cmd("RA0;", read_reply=True)
            if len(resp) >= 4 and resp.startswith("RA0") and resp[3].isdigit():
                self.actual_att = int(resp[3]) > 0
            else:
                self.actual_att = enable
            return self.actual_att

        self.actual_att = enable
        return self.actual_att

    def poll_hardware_state(self) -> bool:
        if not self.port_open:
            self.s_meter_valid = False
            return False

        if "ICOM" in self.protocol:
            self._poll_count += 1
            _ICOM_MODE_MAP = {
                0x00: "LSB",   0x01: "USB",   0x02: "AM",    0x03: "CW",
                0x04: "RTTY",  0x05: "FM",    0x06: "CW-R",  0x07: "CW-R",
                0x08: "RTTY-R", 0x11: "DV",   0x12: "USB-D", 0x17: "LSB-D",
            }
            # Priorité 1 : fréquence (0x03) — lue à chaque cycle
            rep_f = self._civ_transaction([0x03], wait_s=0.10)
            if rep_f and len(rep_f) >= 5 and rep_f[0] == 0x03:
                try:
                    bcd_bytes = rep_f[1:6] if len(rep_f) >= 6 else rep_f[1:]
                    hz = 0
                    mult = 1
                    for b in bcd_bytes:
                        lo = b & 0x0F
                        hi = (b >> 4) & 0x0F
                        hz += lo * mult; mult *= 10
                        hz += hi * mult; mult *= 10
                    if hz > 0:
                        new_khz = round(hz / 1000.0, 3)
                        if abs(new_khz - self.actual_dial_khz) > 0.1:
                            self.actual_dial_khz = new_khz
                except Exception:
                    pass

            # Priorité 2 : mode (0x04) — lu à chaque cycle
            rep_m = self._civ_transaction([0x04])
            if rep_m and len(rep_m) >= 2 and rep_m[0] == 0x04:
                mode_code = rep_m[1]
                new_mode = _ICOM_MODE_MAP.get(mode_code, f"M{mode_code:02X}")
                if new_mode != self.actual_mode_str:
                    self.actual_mode_str = new_mode

            # Priorité 3 : S-mètre (0x15,0x02) — lu à chaque cycle
            rep_s = self._civ_transaction([0x15, 0x02])
            if rep_s and len(rep_s) >= 4 and rep_s[0] == 0x15 and rep_s[1] == 0x02:
                bcd_str = f"{rep_s[2]:02x}{rep_s[3]:02x}"
                if bcd_str.isdigit():
                    self.s_meter_raw = int(bcd_str)
                    self.s_meter_valid = True
                    self._update_s_label(self.s_meter_raw, max_s9=120)
            else:
                self.s_meter_valid = False
                return False

            # Priorité 4 : lectures lentes — toutes les 5 itérations (~2.5 s)
            if self._poll_count % 5 == 0:
                rep_ovf = self._civ_transaction([0x15, 0x07])
                if rep_ovf and len(rep_ovf) >= 3 and rep_ovf[0] == 0x15 and rep_ovf[1] == 0x07:
                    self.ovf_active = rep_ovf[2] == 1

                rep_p = self._civ_transaction([0x16, 0x02])
                if rep_p and len(rep_p) >= 3 and rep_p[0] == 0x16 and rep_p[1] == 0x02:
                    self.actual_preamp = int(rep_p[2])

                rep_a = self._civ_transaction([0x11])
                if rep_a and len(rep_a) >= 2 and rep_a[0] == 0x11:
                    self.actual_att = rep_a[1] > 0
            return True

        elif "YAESU CAT ASCII" in self.protocol:
            resp_s = self._yaesu_ascii_cmd("SM0;", read_reply=True)
            if len(resp_s) >= 6 and resp_s.startswith("SM0") and resp_s[3:6].isdigit():
                self.s_meter_raw = int(resp_s[3:6])
                self.s_meter_valid = True
                self._update_s_label(self.s_meter_raw, max_s9=130)
                self.ovf_active = self.s_meter_raw > 235
                return True
            self.s_meter_valid = False
            return False

        elif "YAESU CAT LEGACY" in self.protocol:
            rep = self._legacy_cmd(LEGACY_READ_RX, 1)
            if rep:
                v, label = legacy_smeter_label(rep[0])
                self.s_meter_raw = int(v * 241 / 15)
                self.s_meter_label = label
                self.s_meter_valid = True
                return True
            self.s_meter_valid = False
            return False

        return False

    def _update_s_label(self, raw_val: int, max_s9: int = 120):
        if raw_val <= max_s9:
            s_unit = int(round((raw_val / max(1, max_s9)) * 9.0))
            self.s_meter_label = f"S{s_unit}"
            self.s_meter_dbm = -127.0 + s_unit * 6.0
        else:
            plus_db = int(round(((raw_val - max_s9) / max(1, (241 - max_s9))) * 60.0))
            self.s_meter_label = f"S9+{plus_db}dB"
            self.s_meter_dbm = -73.0 + plus_db


class UnifiedRadioController(_UnifiedRadioControllerBase):
    """Contrôleur radio avec reconnaissance des fréquences RTTY et limitation du polling CI-V.

    (Anciennement ajouté par patch dynamique dans hf_bulletins_and_portable_core.)
    """

    def update_station_metadata_by_freq(self, freq_khz: float):
        for st in RTTY_WEATHER_STATIONS:
            if abs(st["freq"] - freq_khz) < 0.8:
                self.active_station_id = st["id"]
                self.active_station_name = st["station"]
                self.active_station_family = st.get("family", "DWD")
                return
        return super().update_station_metadata_by_freq(freq_khz)

    def poll_hardware_state(self, *args, **kwargs):
        """Interroge le poste à chaque appel (cycle ~500 ms).
        Fréquence et mode sont lus à chaque cycle ; paramètres lents toutes les 5 itérations.
        """
        return super().poll_hardware_state(*args, **kwargs)
