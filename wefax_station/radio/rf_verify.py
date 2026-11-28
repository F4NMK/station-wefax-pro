"""Préparation RF vérifiée de l'IC-705 (écriture + relecture CI-V, liste blanche RX uniquement)."""

import time


def rf_bcd(data):
    if any((b & 15) > 9 or (b >> 4) > 9 for b in data):
        raise ValueError("BCD invalide")
    return int("".join(f"{b:02x}" for b in data))


class RFVerified705:
    def __init__(self, radio):
        self.r = radio

    def transaction(self, query, data=None, size=None):
        # Whitelist RX uniquement. Ne touche jamais DTR/RTS/PTT.
        allowed = {
            (0x19, 0),
            (3,),
            (4,),
            (6,),
            (0x1A, 6),
            (0x1A, 3),
            (0x16, 2),
            (0x16, 0x12),
            (0x16, 0x22),
            (0x16, 0x40),
            (0x16, 0x41),
            (0x16, 0x48),
            (0x11,),
            (0x14, 2),
            (0x14, 7),
            (0x14, 8),
            (0x14, 1),
            (0x15, 2),
            (0x15, 7),
            (0x1A, 5, 1, 9),
            (0x1A, 5, 1, 0x10),
            (0x1A, 5, 1, 0x11),
        }
        if tuple(query) not in allowed:
            raise RuntimeError("Commande hors whitelist RX")
        r = self.r
        with r.lock:
            if not r.port_open or not r.ser:
                raise RuntimeError("Port ferme")
            r.ser.reset_input_buffer()
            r.ser.write(
                bytes(
                    [254, 254, r.civ_addr, 224]
                    + list(query)
                    + (list(data) if data is not None else [])
                    + [253]
                )
            )
            r.ser.flush()
            deadline = time.monotonic() + 0.65
            buf = bytearray()
            while time.monotonic() < deadline:
                chunk = r.ser.read(max(1, min(r.ser.in_waiting, 512)))
                buf.extend(chunk)
                while 253 in buf:
                    end = buf.index(253)
                    raw = bytes(buf[:end])
                    del buf[: end + 1]
                    pos = raw.rfind(bytes([254, 254]))
                    if pos < 0:
                        continue
                    frame = raw[pos + 2 :]
                    if len(frame) < 3 or frame[0] != 224 or frame[1] != r.civ_addr:
                        continue
                    payload = list(frame[2:])
                    if payload == [250]:
                        raise RuntimeError("CI-V NG")
                    if data is not None:
                        if payload == [251]:
                            return payload
                    elif payload[: len(query)] == list(query) and len(payload) == len(query) + size:
                        return payload[len(query) :]
            raise RuntimeError("Timeout ou reponse non correspondante")

    def read(self, q, n):
        return self.transaction(q, size=n)

    def ensure(self, name, q, value, n=None, write_q=None):
        n = len(value) if n is None else n
        before = self.read(q, n)
        if before == value:
            # 2.11.0 — déjà conforme : une seule lecture (la relecture identique doublait le trafic CI-V)
            self.r.log(f"RF_VERIFY {name} avant={before} demande={value} apres={before} status=relu_conforme")
            return before
        self.transaction(write_q or q, value)
        after = self.read(q, n)
        self.r.log(
            f"RF_VERIFY {name} avant={before} demande={value} apres={after} "
            f"status={'relu_conforme' if after==value else 'ECART'}"
        )
        if after != value:
            raise RuntimeError(name + " : relecture differente")
        return after

    def prepare(self, auto, reference_pamp=None):
        """Profil de réception écrit puis relu.

        2.9.0 — `reference_pamp` (1 pour les scans, choix F4NMK du 18/11/2026) : P.AMP imposé pendant les
        mesures pour que toutes les fréquences soient comparées dans les mêmes conditions. Jusqu'en 2.8.9 le
        scan gardait le P.AMP mémorisé par bande dans l'IC-705 (0 sur 2,6 / 3,8 / 4,5 / 4,6 MHz, 1 ailleurs
        le 18/11), ce qui avantageait les bandes en P.AMP 1. La protection contre la surcharge (OVF) reste
        prioritaire : P.AMP 0, puis atténuateur."""
        # 2.11.0 — profil déjà vérifié sur cette bande depuis moins de PROFILE_TTL_S : contrôle léger
        # (mode, surcharge, fréquence). Le 20/11, 88 vérifications complètes (≈ 40 échanges CI-V chacune)
        # en 10 h, une par changement de fréquence, pour un profil qui ne changeait jamais.
        band = int(float(getattr(self.r, "actual_dial_khz", 0.0) or 0.0) // 1000)
        cache = getattr(self.r, "_rf_profile_ok", None) or {}
        stamp = cache.get(band)
        if stamp is not None and time.monotonic() - stamp < self.PROFILE_TTL_S:
            try:
                if self._quick_check(auto, reference_pamp):
                    return
            except Exception:
                pass
        self._full_prepare(auto, reference_pamp)
        cache[band] = time.monotonic()
        self.r._rf_profile_ok = cache

    PROFILE_TTL_S = 1800

    def _quick_check(self, auto, reference_pamp=None):
        mode = self.read([4], 2)
        if reference_pamp is not None and self.read([0x16, 2], 1) != [int(reference_pamp)]:
            return False
        if mode[0] != 1 or self.read([0x1A, 6], 2)[0] != 1:
            return False  # mode changé (mémoire de bande, opérateur) : vérification complète
        if auto and self.read([0x15, 7], 1) == [1]:
            return False  # surcharge : la protection complète s'applique
        freq = self.read([3], 5)
        hz = rf_bcd(freq[::-1])
        if abs(hz - round(self.r.actual_dial_khz * 1000)) > 1:
            raise RuntimeError(f"Frequence lue={hz}")
        self.r.log(f"RF_READY freq_hz={hz} profil_deja_verifie_sur_la_bande (controle leger)")
        return True

    def _full_prepare(self, auto, reference_pamp=None):
        ident = self.read([0x19, 0], 1)
        if ident != [0xA4]:
            raise RuntimeError("Modele non IC-705 : " + repr(ident))
        mode = self.read([4], 2)
        fil = mode[1] if mode[1] in (1, 2, 3) else 1
        self.ensure("USB/FIL", [4], [1, fil], write_q=[6])
        self.ensure("DATA/FIL", [0x1A, 6], [1, fil])
        # 3.0 kHz : code BCD 34, profil reproductible, pas un optimum garanti.
        self.ensure("IF_WIDTH_3000Hz", [0x1A, 3], [0x34])
        self.ensure("PBT1_CENTER", [0x14, 7], [1, 0x28])
        self.ensure("PBT2_CENTER", [0x14, 8], [1, 0x28])
        self.ensure("AGC_FAST", [0x16, 0x12], [1])
        self.ensure("NR_OFF", [0x16, 0x40], [0])
        self.ensure("AUTO_NOTCH_OFF", [0x16, 0x41], [0])
        self.ensure("MANUAL_NOTCH_OFF", [0x16, 0x48], [0])
        # NB conserve : journalise et verifie, ne declare pas NB ON optimal.
        nb = self.read([0x16, 0x22], 1)
        self.ensure("NB_PRESERVE", [0x16, 0x22], nb)
        self.ensure("USB_OUTPUT_AF", [0x1A, 5, 1, 9], [0])
        self.ensure("USB_AF_SQL_OPEN", [0x1A, 5, 1, 0x11], [0])
        for name, q in [
            ("RF_GAIN", [0x14, 2]),
            ("AF_LEVEL", [0x14, 1]),
            ("USB_AF_LEVEL", [0x1A, 5, 1, 0x10]),
        ]:
            val = self.read(q, 2)
            self.r.log(f"RF_READ {name} valeur={rf_bcd(val)} conservee")
        pre = self.read([0x16, 2], 1)
        att = self.read([0x11], 1)
        if reference_pamp is not None and pre != [int(reference_pamp)]:
            pre = self.ensure("PAMP_REFERENCE_SCAN", [0x16, 2], [int(reference_pamp)])
            time.sleep(0.15)
        if auto:
            ovf = self.read([0x15, 7], 1)
            sm = rf_bcd(self.read([0x15, 2], 2))
            # Protection surcharge uniquement ; pas d'augmentation automatique du gain.
            if ovf == [1]:
                pre = self.ensure("PAMP_OVF", [0x16, 2], [0])
                time.sleep(0.25)
                if self.read([0x15, 7], 1) == [1]:
                    att = self.ensure("ATT_OVF", [0x11], [0x20])
                    time.sleep(0.25)
                if self.read([0x15, 7], 1) == [1]:
                    raise RuntimeError("OVF persistant : mesure annulee")
            else:
                self.r.log(
                    f"RF_AUTO aucune correction surcharge ; OVF=0 S_raw={sm}. "
                    "Gain faible non optimise automatiquement"
                )
        pre = self.ensure("PAMP", [0x16, 2], pre)
        att = self.ensure("ATT", [0x11], att)
        self.r.actual_preamp = pre[0]
        self.r.actual_att = att[0] != 0
        self.r.actual_mode_str = "USB-D"
        self.r.actual_filter_str = f"FIL{fil}"
        self.r.actual_agc_str = "FAST"
        # Verification frequence par lecture BCD little endian.
        freq = self.read([3], 5)
        hz = rf_bcd(freq[::-1])
        expected = round(self.r.actual_dial_khz * 1000)
        if abs(hz - expected) > 1:
            raise RuntimeError(f"Frequence lue={hz} attendue={expected}")
        self.r.log(
            f"RF_READY freq_hz={hz} FIL={fil} width=3000Hz NB={nb[0]} "
            f"PAMP={pre[0]} ATT={att[0]} profil_verifie_non_optimise"
        )
