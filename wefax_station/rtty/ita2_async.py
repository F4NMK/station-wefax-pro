"""Décodeur RTTY asynchrone ITA2 (1 start, 5 bits LSB d'abord, 1 à 2 stops) sur décisions souples.

* Recherche du front mark -> space avec interpolation sous-échantillon.
* Chaque bit est intégré sur la moitié centrale de sa durée (insensible aux transitions bruitées).
* Validation de trame : bit de start « space » ET bit de stop « mark » ; une trame invalide n'émet
  aucun caractère et la recherche reprend un bit plus loin (resynchronisation rapide).
* Confiance par caractère = marge la plus faible parmi ses 7 bits.
* Inversions LTRS/FIGS conformes à l'ITA2 : l'état est conservé jusqu'au code suivant. L'option
  « unshift on space » (usage radioamateur) est désactivable car les émissions météo DWD alternent
  groupes chiffrés et espaces.
"""

import numpy as np

from wefax_station.rtty.codes import ITA2_LTRS, ITA2_FIGS
from wefax_station.rtty.fsk import SPS


class ITA2AsyncDecoder:
    def __init__(self, polarity=1.0, unshift_on_space=False):
        self.polarity = float(polarity)
        self.unshift_on_space = bool(unshift_on_space)
        self.reset()

    def reset(self):
        self.buf = np.zeros(0)
        self.pos = 1
        self.shift = "LTRS"
        self.valid_ema = 0.0
        self.chain_ema = 0.0  # trames valides enchaînées au rythme exact d'un télétype (7 à 8,2 bits)
        self.last_valid_start = None
        self.abs_offset = 0  # position absolue du début de self.buf
        self.frames = 0
        self.valid_frames = 0

    def _mid(self, start, bit):
        a = int(round(start + bit * SPS + 0.25 * SPS))
        b = int(round(start + bit * SPS + 0.75 * SPS))
        return float(np.mean(self.buf[a:b])) if b > a else 0.0

    def feed(self, d):
        """d : décisions souples (+ = mark). Renvoie [(caractère, confiance), ...]."""
        self.buf = np.concatenate([self.buf, self.polarity * np.asarray(d, dtype=np.float64)])
        out = []
        need = int(7.6 * SPS)
        i = max(1, self.pos)
        buf = self.buf
        while i + need < len(buf):
            if buf[i - 1] > 0.0 >= buf[i]:
                frac = buf[i - 1] / (buf[i - 1] - buf[i] + 1e-12)
                start = i - 1 + frac
                st = self._mid(start, 0)
                if st < -0.15:
                    bits = [self._mid(start, 1 + b) for b in range(5)]
                    stop = self._mid(start, 6)
                    self.frames += 1
                    if stop > 0.15:
                        self.valid_frames += 1
                        self.valid_ema = 0.9 * self.valid_ema + 0.1
                        abs_start = self.abs_offset + start
                        if self.last_valid_start is not None:
                            gap = (abs_start - self.last_valid_start) / SPS
                            chained = 7.0 <= gap <= 8.2
                            self.chain_ema = 0.9 * self.chain_ema + (0.1 if chained else 0.0)
                        self.last_valid_start = abs_start
                        code = sum(1 << b for b, v in enumerate(bits) if v > 0)
                        conf = min([abs(st), abs(stop)] + [abs(v) for v in bits])
                        tok = self._token(code)
                        if tok:
                            out.append((tok, conf))
                        i = int(start + 6.9 * SPS)
                        continue
                    self.valid_ema = 0.9 * self.valid_ema
                    i += SPS // 2
                    continue
            i += 1
        keep = max(0, i - 2 * SPS)
        self.buf = self.buf[keep:]
        self.abs_offset += keep
        self.pos = i - keep
        return out

    def _token(self, code):
        table = ITA2_LTRS if self.shift == "LTRS" else ITA2_FIGS
        tok = table.get(code, "")
        if tok == "<LTRS>":
            self.shift = "LTRS"
            return ""
        if tok == "<FIGS>":
            self.shift = "FIGS"
            return ""
        if tok == " " and self.unshift_on_space:
            self.shift = "LTRS"
        if tok == "\a":
            return ""
        return tok
