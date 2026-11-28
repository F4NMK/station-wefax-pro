"""Façade de réception texte : RTTY ITA2 (DWD) et NAVTEX SITOR-B.

Interface inchangée pour le reste du programme (configure / reset / feed_audio / last_metrics).
Chaîne : rtty/fsk.py (filtres adaptés + ATC) puis rtty/ita2_async.py ou rtty/sitorb.py.

Squelch : il ne repose plus sur un filtre « lexical » (qui rejetait les groupes chiffrés SYNOP/SHIP
des bulletins DWD) mais sur la validité des trames : bits de start/stop corrects (RTTY) ou contrôle
4B/3Y (NAVTEX). Les caractères décodés juste avant l'ouverture sont conservés (pré-roulage).
"""

import math
import re
import numpy as np
from scipy import signal as sp_signal
from wefax_station.rtty.codes import CCIR476_FIGS, CCIR476_LTRS, ITA2_FIGS, ITA2_LTRS
from wefax_station.rtty.fsk import FSKDemodulator
from wefax_station.rtty.ita2_async import ITA2AsyncDecoder
from wefax_station.rtty.sitorb import SitorBDecoder


class RTTYITA2Decoder:
    ITA2_LTRS = ITA2_LTRS
    ITA2_FIGS = ITA2_FIGS
    CCIR476_LTRS = CCIR476_LTRS
    CCIR476_FIGS = CCIR476_FIGS

    WEATHER_KEYWORDS = (
        "ZCZC",
        "NNNN",
        "EDZW",
        "DWD",
        "PINNEBERG",
        "GALE",
        "WARNING",
        "STORM",
        "FORECAST",
        "SYNOPSIS",
        "PRESSURE",
        "HPA",
        "WIND",
        "KT",
        "BFT",
        "SEA",
        "VISIBILITY",
        "MODERATE",
        "GOOD",
        "POOR",
        "ROUGH",
        "SLIGHT",
        "SWELL",
        "NORTH",
        "SOUTH",
        "EAST",
        "WEST",
        "GERMAN",
        "BIGHT",
        "DOGGER",
        "FISHER",
        "FORTIES",
        "VIKING",
        "UTSIRA",
        "BISCAY",
        "FINISTERRE",
        "MEDITERRANEAN",
        "LION",
        "GENOA",
        "CORSICA",
        "BALEARES",
        "VORHERSAGE",
        "WETTER",
        "TIEF",
        "HOCH",
        "STURM",
        "RYRY",
        "CQ ",
        "DE ",
        "UTC",
    )
    VOWELS = set("AEIOUY")
    RARE_NOISE_CHARS = set("JQZX()$#&!+?;='")

    SQUELCH_OPEN = 0.60
    SQUELCH_CLOSE = 0.40
    PREROLL_CHARS = 12

    def __init__(
        self,
        sample_rate=44100,
        baud=50.0,
        shift_hz=450.0,
        center_hz=1900.0,
        protocol="RTTY_ITA2",
        inverted=False,
        auto_polarity=True,
        unshift_on_space=False,
    ):
        self.fs = int(sample_rate)
        self.baud = float(baud)
        self.shift_hz = float(shift_hz)
        self.nominal_center_hz = float(center_hz)
        self.center_hz = float(center_hz)
        self.protocol = str(protocol)
        self.inverted = bool(inverted)
        self.auto_polarity = bool(auto_polarity)
        self.unshift_on_space = bool(unshift_on_space)
        self.spectral_eval_decim = 0
        self.cached_q_eval = None
        self.reset()

    @property
    def is_navtex(self):
        return "NAVTEX" in self.protocol or "SITOR" in self.protocol

    def configure(
        self,
        sample_rate=None,
        baud=None,
        shift_hz=None,
        center_hz=None,
        protocol=None,
        inverted=None,
        auto_polarity=None,
    ):
        changed = False
        if sample_rate is not None and int(sample_rate) != self.fs:
            self.fs = max(8000, int(sample_rate))
            changed = True
        if baud is not None and float(baud) != self.baud:
            self.baud = float(baud)
            changed = True
        if shift_hz is not None and float(shift_hz) != self.shift_hz:
            self.shift_hz = float(shift_hz)
            changed = True
        if center_hz is not None and abs(float(center_hz) - self.nominal_center_hz) > 1.0:
            self.nominal_center_hz = float(center_hz)
            self.center_hz = float(center_hz)
            changed = True
        if protocol is not None and str(protocol) != self.protocol:
            self.protocol = str(protocol)
            changed = True
        if inverted is not None:
            self.inverted = bool(inverted)
        if auto_polarity is not None:
            self.auto_polarity = bool(auto_polarity)
        if changed:
            self.reset()

    def reset(self):
        self.center_hz = self.nominal_center_hz
        self.fsk = FSKDemodulator(self.fs, self.baud, self.shift_hz, self.center_hz)
        if self.is_navtex:
            self.branches = {"SITOR": SitorBDecoder()}
        elif self.auto_polarity:
            self.branches = {
                "NORM": ITA2AsyncDecoder(1.0, self.unshift_on_space),
                "INV": ITA2AsyncDecoder(-1.0, self.unshift_on_space),
            }
        else:
            key = "INV" if self.inverted else "NORM"
            self.branches = {key: ITA2AsyncDecoder(-1.0 if self.inverted else 1.0, self.unshift_on_space)}
        self.selected = next(iter(self.branches))
        self.preroll = {k: [] for k in self.branches}
        self.squelch_open = False
        self.effective_polarity = self.selected
        self.total_frames = 0
        self.valid_stop_frames = 0
        self.accepted_chars = 0
        self.uncertain_chars = 0
        self.navtex_messages = []
        self.spectral_eval_decim = 0
        self.cached_q_eval = None
        self.last_metrics = self._metrics(None)

    @classmethod
    def _score_lexical_plausibility(cls, text: str) -> float:
        """
        Rejette strictement le charabia aléatoire (`MKMPGBMLH HGOAT NAB025236PS6...`) :
        Exige des mots courts séparés par des espaces, un ratio de voyelles naturel (28%-52%)
        et pénalise toute suite de > 9 consonnes ou mélange chiffres/lettres aléatoires.
        """
        if not text:
            return -10.0
        clean = text.strip()
        if len(clean) < 3:
            return -5.0
        n = len(text)
        up = text.upper()
        letters = [c for c in up if c.isalpha()]
        vowels = [c for c in letters if c in cls.VOWELS]
        spaces = sum(1 for c in up if c in (" ", "\n", "\r"))
        rare_noise = sum(1 for c in up if c in cls.RARE_NOISE_CHARS)
        mixed_alnum_junk = len(re.findall(r"[A-Z]\d[A-Z]|\d[A-Z]\d", up))
        long_consonant_runs = len(re.findall(r"[BCDFGHJKLMNPQRSTVWXZ]{5,}", up))

        score = 0.0
        for kw in cls.WEATHER_KEYWORDS:
            if kw in up:
                score += 25.0

        sp_ratio = spaces / float(n)
        if 0.10 <= sp_ratio <= 0.28:
            score += n * 1.2
        else:
            score -= n * 1.5

        if len(letters) >= 4:
            v_ratio = len(vowels) / float(len(letters))
            if 0.28 <= v_ratio <= 0.52:
                score += len(letters) * 1.0
            else:
                score -= len(letters) * 2.0
        else:
            score -= 6.0

        score -= rare_noise * 3.0
        score -= mixed_alnum_junk * 8.0
        score -= long_consonant_runs * 10.0
        return score

    @classmethod
    def evaluate_rtty_quality_on_chunk(
        cls, audio_chunk: np.ndarray, fs: int, center_hz: float = 1900.0, shift_hz: float = 450.0
    ) -> dict:
        x = np.asarray(audio_chunk, dtype=np.float64)
        if x.ndim != 1 or len(x) < 1024 or not np.isfinite(x).all():
            return {
                "score_db": -99.0,
                "mark_snr_db": 0.0,
                "space_snr_db": 0.0,
                "valid_fsk": False,
                "best_center_hz": center_hz,
            }
        x = x - np.mean(x)
        if float(np.sqrt(np.mean(x * x))) < 1e-5:
            return {
                "score_db": -99.0,
                "mark_snr_db": 0.0,
                "space_snr_db": 0.0,
                "valid_fsk": False,
                "best_center_hz": center_hz,
            }

        ff, pp = sp_signal.welch(x, fs=fs, nperseg=min(4096, len(x)))
        noise_ref = float(np.median(pp[(ff >= 650) & (ff <= 1300)])) + 1e-20
        tol_hz = max(18.0, min(48.0, shift_hz * 0.28))

        best_m_snr = 0.0
        best_s_snr = 0.0
        best_c = center_hz
        for c_try in (
            center_hz,
            center_hz - 15.0,
            center_hz + 15.0,
            center_hz - 30.0,
            center_hz + 30.0,
            center_hz - 50.0,
            center_hz + 50.0,
        ):
            f_mark = c_try + 0.5 * shift_hz
            f_space = c_try - 0.5 * shift_hz
            m_pk = (
                float(np.max(pp[np.abs(ff - f_mark) <= tol_hz]))
                if np.any(np.abs(ff - f_mark) <= tol_hz)
                else noise_ref
            )
            s_pk = (
                float(np.max(pp[np.abs(ff - f_space) <= tol_hz]))
                if np.any(np.abs(ff - f_space) <= tol_hz)
                else noise_ref
            )
            m_s = 10.0 * math.log10(max(m_pk / noise_ref, 1.0))
            s_s = 10.0 * math.log10(max(s_pk / noise_ref, 1.0))
            if (m_s + s_s) > (best_m_snr + best_s_snr):
                best_m_snr, best_s_snr = m_s, s_s
                best_c = c_try

        # SQUELCH FSK STRICT : exige au moins +9.5 dB sur la raie principale et +4.5 dB sur la seconde
        valid_fsk = (max(best_m_snr, best_s_snr) >= 9.5) and (min(best_m_snr, best_s_snr) >= 4.5)
        score = (
            (0.55 * max(best_m_snr, best_s_snr) + 0.45 * min(best_m_snr, best_s_snr))
            if valid_fsk
            else (0.5 * max(best_m_snr, best_s_snr) - 12.0)
        )
        return {
            "score_db": round(score, 1),
            "mark_snr_db": round(best_m_snr, 1),
            "space_snr_db": round(best_s_snr, 1),
            "valid_fsk": bool(valid_fsk),
            "best_center_hz": float(best_c),
        }

    def _quality(self, ring_buffer):
        """Évaluation spectrale (≈ 1 fois sur 3 appels) : SNR des raies et correction d'accord (AFC).

        AFC : les deux tonalités sont localisées par interpolation parabolique de leur pic ; la correction
        n'est appliquée que si l'écart mesuré entre elles correspond au shift attendu (±25 %).
        """
        self.spectral_eval_decim = (self.spectral_eval_decim + 1) % 3
        if ring_buffer is None or len(ring_buffer) < 4096:
            return self.cached_q_eval
        if self.cached_q_eval is None or self.spectral_eval_decim == 1:
            x = np.asarray(ring_buffer, dtype=np.float64)
            self.cached_q_eval = self.evaluate_rtty_quality_on_chunk(
                x, self.fs, center_hz=self.nominal_center_hz, shift_hz=self.shift_hz
            )
            est = self._estimate_center(x)
            if est is not None and self.squelch_open:
                step = float(np.clip(0.3 * (est - self.center_hz), -10.0, 10.0))
                self.center_hz = float(
                    np.clip(
                        self.center_hz + step, self.nominal_center_hz - 60.0, self.nominal_center_hz + 60.0
                    )
                )
                self.fsk.center_hz = self.center_hz
        return self.cached_q_eval

    def _estimate_center(self, x):
        f, p = sp_signal.welch(x - np.mean(x), fs=self.fs, nperseg=min(len(x), 16384))
        win = min(60.0, 0.45 * self.shift_hz)
        tones = []
        floor = float(np.median(p[(f > 300) & (f < 3500)])) + 1e-30
        for f0 in (self.center_hz + 0.5 * self.shift_hz, self.center_hz - 0.5 * self.shift_hz):
            m = np.abs(f - f0) <= win
            if np.sum(m) < 3:
                return None
            pw = np.clip(p[m] - 2.0 * floor, 0.0, None)
            if float(np.max(p[m])) < 8.0 * floor or float(np.sum(pw)) <= 0:
                return None
            # barycentre de puissance : insensible aux raies fines d'un motif de bits répétitif (phasage)
            tones.append(float(np.sum(f[m] * pw) / np.sum(pw)))
        measured_shift = tones[0] - tones[1]
        if abs(measured_shift - self.shift_hz) > 0.25 * self.shift_hz:
            return None
        return 0.5 * (tones[0] + tones[1])

    def feed_audio(self, audio_samples, ring_buffer_2s=None):
        x = np.asarray(audio_samples, dtype=np.float64)
        if x.ndim != 1 or len(x) < 16 or not np.isfinite(x).all():
            return "", self.last_metrics
        q = self._quality(ring_buffer_2s)
        d, _amp = self.fsk.process(x - np.mean(x))
        decoded = {k: br.feed(d) for k, br in self.branches.items()}
        # sélection de branche (polarité) par taux de trames valides, avec hystérésis
        if len(self.branches) > 1:
            best = max(self.branches, key=lambda k: self.branches[k].valid_ema)
            if (
                best != self.selected
                and self.branches[best].valid_ema > self.branches[self.selected].valid_ema + 0.15
            ):
                self.selected = best
        self.effective_polarity = self.selected + (" (Auto)" if len(self.branches) > 1 else "")
        br = self.branches[self.selected]
        validity = br.valid_ema
        if not self.is_navtex:
            # RTTY : des trames valides ET enchaînées au rythme d'un télétype (le bruit n'enchaîne pas)
            validity = min(br.valid_ema, br.chain_ema + 0.2)
        if not self.squelch_open and self._may_open(validity):
            self.squelch_open = True
            decoded[self.selected] = self.preroll[self.selected] + decoded[self.selected]
        elif self.squelch_open and (
            validity < self.SQUELCH_CLOSE
            or (not self.is_navtex and max(self.fsk.contrast_db()) < self.CONTRAST_CLOSE_DB)
        ):  # NAVTEX : le contrôle 4B/3Y suffit à reconnaître le bruit (27 % de mots valides au hasard)
            self.squelch_open = False
        out = ""
        for k, chars in decoded.items():
            if k == self.selected and self.squelch_open:
                for c, conf in chars:
                    out += c
                    self.accepted_chars += 1
                    if conf < 0.25:
                        self.uncertain_chars += 1
                self.preroll[k] = []
            else:
                self.preroll[k] = (self.preroll[k] + chars)[-self.PREROLL_CHARS :]
        if hasattr(br, "frames"):
            self.total_frames, self.valid_stop_frames = br.frames, br.valid_frames
        if self.is_navtex:
            self.total_frames, self.valid_stop_frames = br.total_chars, br.total_chars - br.error_chars
            self.navtex_messages = br.messages
        self.last_metrics = self._metrics(q)
        return out, self.last_metrics

    CONTRAST_OPEN_DB = 11.5  # bruit seul : 8,4 à 10,2 dB ; signal FSK à 0 dB de SNR : ≥ 12,2 dB (banc HF)
    CONTRAST_CLOSE_DB = 10.5

    def _may_open(self, validity):
        """Ouverture du squelch : trames valides ET contraste marche/arrêt des tonalités (sur 2 s)."""
        return validity >= self.SQUELCH_OPEN and max(self.fsk.contrast_db()) >= self.CONTRAST_OPEN_DB

    def _metrics(self, q):
        br = self.branches[self.selected] if hasattr(self, "branches") else None
        validity = float(br.valid_ema) if br is not None else 0.0
        if self.is_navtex and br is not None:
            acc = 1.0 - br.error_chars / max(1, br.total_chars)
        else:
            acc = 1.0 - self.uncertain_chars / max(1, self.accepted_chars)
        m_snr, s_snr = self.fsk.contrast_db() if hasattr(self, "fsk") else (0.0, 0.0)
        return {
            "protocol": "NAVTEX / SITOR-B (CCIR 476)" if self.is_navtex else "RTTY FSK / ITA2",
            "baud": self.baud,
            "shift_hz": self.shift_hz,
            "center_hz": round(self.center_hz, 1),
            "f_mark_hz": round(self.center_hz + 0.5 * self.shift_hz, 1),
            "f_space_hz": round(self.center_hz - 0.5 * self.shift_hz, 1),
            "inverted": self.selected == "INV",
            "polarity_used": getattr(self, "effective_polarity", "Auto"),
            "signal_compatible": bool(getattr(self, "squelch_open", False)),
            "bit_clock_locked": bool(getattr(self, "squelch_open", False) and validity >= 0.7),
            "frame_sync_ratio": round(validity, 2),
            "accepted_char_ratio": round(acc, 2),
            "lexical_quality": round(0.5 + 0.5 * acc, 2) if getattr(self, "squelch_open", False) else 0.0,
            "shift_state": getattr(br, "shift", "LTRS") if br is not None else "LTRS",
            "mark_snr_db": round(m_snr, 1),
            "space_snr_db": round(s_snr, 1),
            "spectral_snr_db": None if not q else q.get("score_db"),
        }
