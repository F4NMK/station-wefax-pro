"""Démodulateur FSK continu pour RTTY (ITA2) et NAVTEX (SITOR-B).

* Deux filtres adaptés (un par tonalité) : transposition en bande de base et moyenne glissante
  sur exactement une durée de bit (filtre optimal pour des bits rectangulaires dans du bruit blanc).
* Décimation fractionnaire à 16 échantillons par bit.
* Correction automatique de seuil (ATC) : les niveaux de crête et le plancher de bruit de chaque
  tonalité sont suivis séparément. Le fading sélectif HF peut éteindre une tonalité pendant que
  l'autre reste forte ; l'ATC replace alors le seuil de décision au bon endroit.
* Sortie : décision souple d ∈ [-1, +1] (+ = mark / « B »), et rapport signal/bruit par tonalité.
"""

import numpy as np
from scipy import signal as sp_signal

SPS = 16  # échantillons par bit après décimation


class FSKDemodulator:
    PEAK_DECAY_BITS = 5.0  # durée d'oubli d'une crête, en bits
    def __init__(self, fs, baud, shift_hz, center_hz):
        self.configure(fs, baud, shift_hz, center_hz)

    def configure(self, fs, baud, shift_hz, center_hz):
        self.fs = int(fs)
        self.baud = float(baud)
        self.shift_hz = float(shift_hz)
        self.center_hz = float(center_hz)
        self.L = max(4, int(round(self.fs / self.baud)))
        self.h = np.ones(self.L) / self.L
        self.reset()

    def reset(self):
        self.ph_m = 0.0
        self.ph_s = 0.0
        self.zi_m = np.zeros(self.L - 1, dtype=np.complex128)
        self.zi_s = np.zeros(self.L - 1, dtype=np.complex128)
        self.t_next = 0.0  # position (en échantillons d'entrée) du prochain échantillon décimé
        self.prev_m = 0.0
        self.prev_s = 0.0
        self.m_pk = self.s_pk = None
        self.m_fl = self.s_fl = None
        self.snr_m_db = 0.0
        self.snr_s_db = 0.0
        self.hist_m = np.zeros(0)
        self.hist_s = np.zeros(0)

    @property
    def f_mark(self):
        return self.center_hz + 0.5 * self.shift_hz

    @property
    def f_space(self):
        return self.center_hz - 0.5 * self.shift_hz

    def process(self, x):
        x = np.asarray(x, dtype=np.float64)
        n = len(x)
        if n == 0:
            return np.zeros(0), np.zeros(0)
        k = np.arange(n, dtype=np.float64)
        wm = 2 * np.pi * self.f_mark / self.fs
        ws = 2 * np.pi * self.f_space / self.fs
        lo_m = np.exp(-1j * (self.ph_m + wm * k))
        lo_s = np.exp(-1j * (self.ph_s + ws * k))
        self.ph_m = (self.ph_m + wm * n) % (2 * np.pi)
        self.ph_s = (self.ph_s + ws * n) % (2 * np.pi)
        zm, self.zi_m = sp_signal.lfilter(self.h, 1.0, x * lo_m, zi=self.zi_m)
        zs, self.zi_s = sp_signal.lfilter(self.h, 1.0, x * lo_s, zi=self.zi_s)
        em = np.abs(zm)
        es = np.abs(zs)
        # décimation fractionnaire (interpolation linéaire, l'enveloppe est déjà filtrée)
        step = self.fs / (SPS * self.baud)
        pos = np.arange(self.t_next, n, step)
        self.t_next = (pos[-1] + step - n) if len(pos) else self.t_next - n
        em_ext = np.concatenate([[self.prev_m], em])
        es_ext = np.concatenate([[self.prev_s], es])
        self.prev_m = em[-1]
        self.prev_s = es[-1]
        m = np.interp(pos + 1.0, np.arange(n + 1), em_ext)
        s = np.interp(pos + 1.0, np.arange(n + 1), es_ext)
        keep = int(2.0 * SPS * self.baud)
        self.hist_m = np.concatenate([self.hist_m, m])[-keep:]
        self.hist_s = np.concatenate([self.hist_s, s])[-keep:]
        return self._atc(m, s), np.maximum(m, s)

    def contrast_db(self):
        """Contraste marche/arrêt de chaque tonalité sur 2 s : 20·log10(P90 / P25) de l'enveloppe.

        Bruit seul (enveloppe de Rayleigh) : ≈ 9 dB, très stable. Tonalité FSK manipulée : bien plus.
        """
        out = []
        for h in (self.hist_m, self.hist_s):
            if len(h) < SPS * 20:
                out.append(0.0)
                continue
            p90, p25 = np.percentile(h, [90, 25])
            out.append(float(20 * np.log10(max(p90, 1e-12) / max(p25, 1e-12))))
        return out

    def _atc(self, m, s):
        """Correction automatique de seuil (méthode « optimal ATC » de K. Chen / fldigi)."""
        out = np.empty(len(m))
        if self.m_pk is None and len(m):
            self.m_pk = self.s_pk = float(max(np.max(m), np.max(s)))
            self.m_fl = self.s_fl = float(min(np.min(m), np.min(s)))
        att = 0.25
        # 2.8.4 (audit D3) : une crête est oubliée en ~5 bits (16 auparavant). Sous fading rapide le niveau
        # d'une tonalité change en une dizaine de bits ; le seuil restait mal placé.
        dec = 1.0 / (SPS * self.PEAK_DECAY_BITS)
        fl_att = 0.25
        fl_dec = 1.0 / (SPS * 16.0)
        mp, sp, fl = self.m_pk, self.s_pk, min(self.m_fl, self.s_fl)
        mf = sf = fl
        for i in range(len(m)):
            mi, si = m[i], s[i]
            mp += (att if mi > mp else dec) * (mi - mp)
            sp += (att if si > sp else dec) * (si - sp)
            # 2.8.4 (audit D2) : plancher de bruit COMMUN aux deux voies, suivi sur la voie éteinte (en FSK
            # une seule tonalité est émise à la fois). Avec un plancher par voie, celui de la voie mark
            # remontait jusqu'à la crête pendant un repos sur mark : la voie mark ne pesait plus rien et le
            # bruit de la voie space déclenchait de faux bits de start (caractères fantômes).
            lo = mi if mi < si else si
            fl += (fl_att if lo < fl else fl_dec) * (lo - fl)
            mf = sf = fl
            mc = min(max(mi, mf), max(mp, mf))
            sc = min(max(si, sf), max(sp, sf))
            span = 0.5 * (max(mp - mf, 0.0) + max(sp - sf, 0.0)) + 1e-12
            out[i] = ((mc - mf) - (sc - sf) - 0.5 * ((mp - mf) - (sp - sf))) / span
        self.m_pk, self.s_pk, self.m_fl, self.s_fl = mp, sp, mf, sf
        self.snr_m_db = float(20 * np.log10(max(mp, 1e-12) / max(mf, 1e-12)))
        self.snr_s_db = float(20 * np.log10(max(sp, 1e-12) / max(sf, 1e-12)))
        return np.clip(out, -1.5, 1.5)
