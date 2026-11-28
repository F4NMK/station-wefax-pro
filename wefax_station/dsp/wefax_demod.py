"""Démodulateur WEFAX continu (flux), conçu pour la HF perturbée.

Spécification (OMM, IOC 576, 120 lignes/min) : porteuse audio 1900 Hz, noir 1500 Hz, blanc 2300 Hz
(±400 Hz ; DWD ±425 Hz) ; START 5 s à 300 Hz (675 Hz en IOC 288) ; phasage 60 lignes
« 25 ms blanc + 475 ms noir » ; chaque ligne commence par 25 ms de blanc ; STOP 5 s à 450 Hz
puis 10 s de noir ; stabilité de ligne 5 ppm à l'émission.

Chaîne de traitement, appliquée en continu d'une ligne à l'autre (aucune rupture de filtre) :
1. Suppresseur d'impulsions (QRN) : le signal FM a une enveloppe constante ; tout échantillon qui
   dépasse nettement le niveau robuste est neutralisé (zéro) avec une garde de 0,5 ms.
2. Transposition en bande de base complexe autour de 1900 Hz (+ correction d'accord AFC) et filtre
   passe-bas RIF à phase linéaire : seul le canal WEFAX est conservé, le bruit hors canal est rejeté.
3. Discriminateur de fréquence par différence de phase, continu entre les lignes.
4. Pondération de confiance par échantillon : (enveloppe / référence)², nulle sur les impulsions
   neutralisées et hors excursion. Le bruit du discriminateur explose dans les creux de fading ;
   ces échantillons ne doivent pas peser.
5. Filtre vidéo par convolution normalisée : les échantillons peu fiables sont remplacés par la
   moyenne pondérée de leurs voisins immédiats (≤ 1 ms) ; au-delà, la zone est déclarée non fiable.
6. Intégration par pixel (moyenne sur la durée du pixel, pas un simple échantillonnage).
7. Détection START / STOP sur le signal vidéo (tonalité dominante + signal carré noir/blanc
   bimodal : un brouilleur ou un battement ne peut pas l'imiter) et du phasage (impulsion blanche
   de 5 %), avec mesure de l'erreur d'horloge de la carte son (ppm) pendant le phasage.
"""

import numpy as np
from scipy import signal as sp_signal

LINE_S = 0.5  # 120 lignes / min


class WefaxStreamDemodulator:
    BB_CUT_HZ = 650.0  # canal : 1250 .. 2550 Hz (réglé au banc HF)
    VID_CUT_HZ = 800.0
    BAD_PIXEL_CONF = 0.15
    CAL_MIN_COVERAGE = 0.60  # couverture minimale d'une ligne de phasage pour la mesure d'horloge
    LONG_GAP_PREV_ROW = True  # vidéo : compromis bruit / finesse des chiffres de la carte

    def __init__(self, fs):
        self.fs = int(fs)
        self.clock_ppm = 0.0  # erreur d'horloge de la carte son (persistante entre cartes)
        self._design()
        self.reset()

    # ------------------------------------------------------------------ état
    # 2.8.4 (audit D1) — largeur des filtres adaptée au signal. (coupure bande de base, coupure vidéo) en Hz.
    # Le profil étroit (réglé au banc pour 3–10 dB) coupait les traits fins quand le signal est bon : à
    # 120 lignes/min et 1809 px, un trait de 2 px a une fondamentale de 905 Hz. Mêmes longueurs de filtre
    # pour tous les profils : le changement se fait sans à-coup (l'état des filtres est conservé).
    BW_PROFILES = ((650.0, 800.0), (900.0, 1200.0), (1100.0, 1500.0))
    # Seuils mesurés au banc (corrélation et PSNR carte émise / carte décodée) : le profil 1 ne gagne
    # qu'à partir de 18–20 dB, le profil 2 à partir de 25 dB ; en dessous, et sous fading, l'étroit reste meilleur.
    BW_UP_DB = (19.0, 24.0)  # SNR estimé (dans 3 kHz) pour passer au profil 1, puis 2
    BW_MAX_FADE_CV = 0.15  # niveau stable exigé pour élargir (variation du niveau le long de la ligne)
    BW_HYST_DB = 2.0
    BW_UP_LINES = 8  # lignes consécutives au-dessus du seuil avant d'élargir ; le rétrécissement est immédiat
    BW_ADAPTIVE = True
    # 2.8.5 — choix de l'opérateur (Réglages › Image › Netteté des cartes), commun à toutes les réceptions :
    #   AUTO     seuils ci-dessus (le meilleur compromis mesuré au banc) ;
    #   DETAIL   élargit 10 dB plus tôt et sans la garde de fading : traits et textes plus nets, grain plus
    #            visible. À préférer quand le signal est fort mais bruité (S9 avec un bruit de bande élevé) ;
    #   ROBUSTE  toujours le filtre étroit.
    SHARPNESS = "AUTO"
    DETAIL_BIAS_DB = 10.0
    # 2.14.1 — filtre passe-bande « anti-brouilleur » (Réglages › Image), désactivé par défaut, appliqué
    # APRÈS le suppresseur d'impulsions. Banc HF (outils/banc_hf.py, filtre FI FIL2 du poste simulé,
    # corrélation carte décodée / émise) :
    #                         sans     avec           sans     avec
    #   brouilleur 2 kHz     0,720 → 0,781   QRN 15 dB 0,895 → 0,860
    #   brouilleur 700 Hz    0,876 → 0,925   propre    0,962 → 0,952
    # Utile contre une station voisine ; à laisser coupé par temps orageux (QRN). Placé AVANT le
    # suppresseur, il étale chaque parasite dans le temps : QRN 0,895 → 0,816 (essayé, écarté ; c'était
    # le choix de la version Qt du 27/11, en ordre 6, encore plus pénalisant).
    # Bande fixe autour du centre 1900 Hz : noir 1475 / blanc 2325 Hz au shift 850 Hz, marge pour l'AFC
    # ±40 Hz et les bandes latérales des signaux START / STOP.
    PREFILTER = False
    PREFILTER_BAND_HZ = (1250.0, 2550.0)
    PREFILTER_ORDER = 4

    def _design(self):
        fs = self.fs
        nb = int(round(0.0040 * fs)) | 1
        nv = int(round(0.0016 * fs)) | 1
        self._h_bb_set = [
            sp_signal.firwin(nb, bb, fs=fs, window=("kaiser", 6.0)) for bb, _ in self.BW_PROFILES
        ]
        self._h_vid_set = [sp_signal.firwin(nv, vid, fs=fs, window="hann") for _, vid in self.BW_PROFILES]
        self.bw_index = 0
        self.h_bb = self._h_bb_set[0]
        self.h_vid = self._h_vid_set[0]
        self.guard = max(1, int(round(0.0005 * fs)))
        lo, hi = self.PREFILTER_BAND_HZ
        self._sos_pre = sp_signal.butter(
            self.PREFILTER_ORDER, [lo, min(hi, 0.45 * fs)], btype="band", fs=fs, output="sos"
        )

    def _set_bandwidth(self, index):
        self.bw_index = int(index)
        self.h_bb = self._h_bb_set[self.bw_index]
        self.h_vid = self._h_vid_set[self.bw_index]

    def _adapt_bandwidth(self, env, bmask, ref):
        """Estime le SNR par la fluctuation rapide de l'enveloppe et choisit le profil de filtres.

        Le signal WEFAX est à enveloppe constante : sur quelques millisecondes, toute fluctuation de
        l'enveloppe est du bruit (le fading, lui, est lent). Écart-type / moyenne par bloc de 4 ms, médiane
        sur la ligne, blocs en creux de fading ou touchés par un parasite exclus ; ramené à 3 kHz.
        """
        blk = max(16, int(0.004 * self.fs))
        nblk = len(env) // blk
        if nblk < 20:
            return
        e = env[: nblk * blk].reshape(nblk, blk)
        clean = bmask[: nblk * blk].reshape(nblk, blk).max(axis=1) < 0.05
        means = e.mean(axis=1)
        ok = clean & (means > 0.5 * ref)
        fade_cv = float(np.std(means[clean]) / (np.mean(means[clean]) + 1e-12)) if np.sum(clean) > 15 else 1.0
        self.fade_cv = fade_cv if self.fade_cv is None else 0.7 * self.fade_cv + 0.3 * fade_cv
        if np.sum(ok) < 15:
            snr = 0.0
        else:
            cv = float(np.median(e[ok].std(axis=1) / (e[ok].mean(axis=1) + 1e-12)))
            bb = self.BW_PROFILES[self.bw_index][0]
            snr = -20.0 * np.log10(max(cv, 1e-4)) - 3.0 + 10.0 * np.log10(2.0 * bb / 3000.0) + self.BW_SNR_CAL_DB
        self.snr_env_db = snr if self.snr_env_db is None else 0.7 * self.snr_env_db + 0.3 * snr
        if not self.BW_ADAPTIVE:
            return
        mode = str(self.SHARPNESS).upper()
        if mode == "ROBUSTE":
            if self.bw_index:
                self._set_bandwidth(0)
            return
        detail = mode == "DETAIL"
        s = self.snr_env_db + (self.DETAIL_BIAS_DB if detail else 0.0)
        target = 2 if s >= self.BW_UP_DB[1] else (1 if s >= self.BW_UP_DB[0] else 0)
        fading = self.fade_cv > self.BW_MAX_FADE_CV and not detail
        if fading:
            target = 0  # fading : le profil étroit reste le meilleur même à SNR moyen élevé
        if target < self.bw_index:
            # rétrécissement immédiat, avec hystérésis sur le seuil qui avait permis d'élargir
            if fading or s < self.BW_UP_DB[self.bw_index - 1] - self.BW_HYST_DB:
                self._set_bandwidth(target)
            self._bw_up_count = 0
        elif target > self.bw_index:
            self._bw_up_count += 1
            if self._bw_up_count >= self.BW_UP_LINES:
                self._set_bandwidth(self.bw_index + 1)
                self._bw_up_count = 0
        else:
            self._bw_up_count = 0

    BW_SNR_CAL_DB = -1.2  # étalonnage de l'estimateur sur le canal simulé (banc)

    def reset(self):
        """Réinitialise les filtres (nouvelle feuille, changement de fréquence). Conserve clock_ppm."""
        self.n = 0
        self.zi_bb = np.zeros(len(self.h_bb) - 1, dtype=np.complex128)
        self.zi_num = np.zeros(len(self.h_vid) - 1)
        self.zi_den = np.zeros(len(self.h_vid) - 1)
        self.zi_mask = np.zeros(len(self.h_bb) - 1)
        self.zi_pre = np.zeros((self._sos_pre.shape[0], 2))
        self.prev_z = None
        self.snr_env_db = None
        self.fade_cv = None
        self._bw_up_count = 0
        self._set_bandwidth(0)
        self.amp_ref = None
        self.in_level = None
        self.afc_hz = 0.0
        self.prev_row = None
        self.phase_history = []  # (index de ligne, position du front)
        self.lock_edge = None
        self.lock_line = 0
        self.cal_points = []
        self.line_index = 0
        self._ppm_lines = []

    def samples_per_line(self, fs=None):
        return LINE_S * float(fs or self.fs) * (1.0 + self.clock_ppm * 1e-6)

    # ------------------------------------------------------------- traitement
    def process_line(
        self, x, center=1900.0, shift=800.0, line_width=1809, qrn_blanker=True, conditioner=True
    ):
        x = np.asarray(x, dtype=np.float64)
        n = len(x)
        obs = dict(
            valid=False,
            apt=None,
            apt_modulation_hz=None,
            apt_peak_ratio=0.0,
            phase_stable=False,
            phase_position=None,
            synchronized=False,
            center_hz=center,
            shift_hz=shift,
            coverage=0.0,
            afc_hz=self.afc_hz,
            ioc=None,
            clock_ppm=self.clock_ppm,
        )
        if x.ndim != 1 or n < 256 or not np.isfinite(x).all():
            return np.full(line_width, 128, np.uint8), None, np.zeros(line_width), obs
        x = x - np.mean(x)
        afc = self.afc_hz if conditioner else 0.0
        center = center + afc  # niveaux noir / blanc corrigés de l'erreur d'accord estimée
        black = center - shift / 2.0
        white = center + shift / 2.0

        # 1. suppresseur d'impulsions
        med = float(np.median(np.abs(x))) + 1e-12
        self.in_level = med if self.in_level is None else 0.8 * self.in_level + 0.2 * med
        blank = np.zeros(n, dtype=bool)
        if qrn_blanker:
            thr = 4.5 * min(self.in_level, med * 1.5)
            hit = np.abs(x) > thr
            if np.any(hit):
                blank = np.convolve(hit.astype(np.float64), np.ones(2 * self.guard + 1), mode="same") > 0
                x = np.where(blank, 0.0, x)

        # 1 bis. filtre passe-bande optionnel (après le suppresseur d'impulsions, voir PREFILTER)
        if self.PREFILTER:
            x, self.zi_pre = sp_signal.sosfilt(self._sos_pre, x, zi=self.zi_pre)

        # 2. bande de base
        f0 = center
        k = np.arange(self.n, self.n + n, dtype=np.float64)
        self.n = (self.n + n) % (self.fs * 3600)
        lo = np.exp(-2j * np.pi * f0 * k / self.fs)
        z, self.zi_bb = sp_signal.lfilter(self.h_bb, 1.0, x * lo, zi=self.zi_bb)
        bmask, self.zi_mask = sp_signal.lfilter(
            np.abs(self.h_bb) / np.sum(np.abs(self.h_bb)), 1.0, blank.astype(np.float64), zi=self.zi_mask
        )

        # 3. discriminateur continu
        zz = np.concatenate([[self.prev_z if self.prev_z is not None else z[0]], z])
        self.prev_z = z[-1]
        freq = np.angle(zz[1:] * np.conj(zz[:-1])) * self.fs / (2 * np.pi) + f0

        # 4. confiance
        env = np.abs(z)
        good_env = env[bmask < 0.05]
        if len(good_env) > n // 10:
            ref_now = float(np.percentile(good_env, 75))
            self.amp_ref = ref_now if self.amp_ref is None else 0.85 * self.amp_ref + 0.15 * ref_now
        ref = self.amp_ref or float(np.percentile(env, 75)) + 1e-12
        self._adapt_bandwidth(env, bmask, ref)  # agit sur la ligne suivante
        r = env / (ref + 1e-12)
        w = np.clip(r, 0.0, 1.3) ** 2
        w[r < 0.22] = 0.0
        w[bmask > 0.15] = 0.0
        w[(freq < black - 350.0) | (freq > white + 350.0)] = 0.0

        # 5. filtre vidéo normalisé
        fc = np.clip(freq, black - 250.0, white + 250.0)
        num, self.zi_num = sp_signal.lfilter(self.h_vid, 1.0, w * fc, zi=self.zi_num)
        den, self.zi_den = sp_signal.lfilter(self.h_vid, 1.0, w, zi=self.zi_den)
        valid = den > 0.12
        fv = np.where(valid, num / np.maximum(den, 1e-9), center)
        grey = np.clip((fv - black) / shift * 255.0, 0.0, 255.0)
        conf = np.clip(den, 0.0, 1.0)
        coverage = float(np.mean(conf))
        obs["coverage"] = round(coverage, 3)
        obs["valid"] = coverage >= 0.35

        # 6. intégration par pixel
        edges = np.linspace(0, n, line_width + 1)
        cs = np.concatenate([[0.0], np.cumsum(grey * conf)])
        cw = np.concatenate([[0.0], np.cumsum(conf)])
        num_p = np.interp(edges[1:], np.arange(n + 1), cs) - np.interp(edges[:-1], np.arange(n + 1), cs)
        den_p = np.interp(edges[1:], np.arange(n + 1), cw) - np.interp(edges[:-1], np.arange(n + 1), cw)
        span = np.diff(edges)
        pix_conf = np.clip(den_p / span, 0.0, 1.0)
        row = np.where(den_p > 1e-6, num_p / np.maximum(den_p, 1e-9), np.nan)

        # 7a. START / STOP : tonalité de commutation noir/blanc pleine excursion.
        # Amplitude complexe de la composante à f (moyenne pondérée par la confiance) ; un signal carré
        # noir/blanc a une fondamentale d'amplitude 2·shift/π. Un battement avec un brouilleur ou le
        # bruit ne produisent ni cette amplitude ni cette pureté.
        flag = None
        if coverage >= 0.25 and n >= int(0.2 * self.fs):
            flag = self._detect_apt(fv, conf, shift, obs)

        # 7b. phasage : impulsion blanche de 5 % (25 ms) sur fond noir
        phase_edge = None
        if flag is None and abs(n / self.fs - LINE_S) < 0.03 and float(np.mean(pix_conf)) > 0.35:
            okp = pix_conf > 0.3
            rv = np.where(okp, np.nan_to_num(row, nan=0.0), 0.0)
            whitepx = (rv > 127.5) & okp
            share = float(np.sum(whitepx) / max(1, np.sum(okp)))
            # spécification : impulsion BLANCHE sur fond noir ; la variante inversée est tolérée
            inverted = share > 0.5
            minority = (~whitepx & okp) if inverted else whitepx
            share = 1.0 - share if inverted else share
            if 0.02 <= share <= 0.10:
                ang = 2 * np.pi * np.arange(line_width) / line_width
                mom = np.mean(np.exp(1j * ang[minority]))
                if abs(mom) > 0.90:
                    centre = float(np.angle(mom) % (2 * np.pi) / (2 * np.pi))
                    g_for_edge = 255.0 - grey if inverted else grey
                    phase_edge = self._precise_edge(g_for_edge, conf, (centre - share / 2.0) % 1.0)
                    # référence d'accord : le fond noir du phasage est exactement à la fréquence du noir.
                    # Sélection par POSITION (hors impulsion), jamais par valeur : pas de biais de sélection.
                    if conditioner and coverage > 0.75 and not inverted:
                        e0 = int(phase_edge * n)
                        idx = (np.arange(int(0.10 * n), int(0.95 * n)) + e0) % n
                        selb = conf[idx] > 0.6
                        if np.mean(selb) > 0.8:
                            self._afc_step(float(np.median(freq[idx][selb])) - black)
        self.line_index += 1
        if phase_edge is not None:
            self.phase_history.append((self.line_index, phase_edge))
            # 2.8.3 : seuil 0,60 (0,85 auparavant). La couverture est une amplitude relative au 75e centile :
            # sur un signal réel S9 elle vaut 0,69 à 0,85 pendant le phasage (GYA3, 15/11), si bien que la
            # mesure d'horloge ne démarrait jamais. La robustesse reste assurée par _update_clock (30 points,
            # accord des deux moitiés, dispersion < 1,5 px).
            if coverage > self.CAL_MIN_COVERAGE:
                self.cal_points.append((self.line_index, phase_edge))
        elif self.phase_history and self.line_index - self.phase_history[-1][0] > 3:
            self.phase_history = []
        self.phase_history = self.phase_history[-80:]
        recent = [p for (i, p) in self.phase_history if self.line_index - i < 6]
        if len(recent) >= 3:
            vec = np.mean(np.exp(2j * np.pi * np.asarray(recent)))
            if abs(vec) > 0.985:
                flag = "PHASE"
                obs["phase_stable"] = True
                obs["synchronized"] = True
                obs["phase_position"] = float(np.angle(vec) % (2 * np.pi) / (2 * np.pi))
                self.lock_edge = obs["phase_position"]
                self.lock_line = self.line_index
                self._update_clock()
        obs["clock_ppm"] = round(self.clock_ppm, 2)

        # AFC sur l'image : la marge de début de ligne (25 ms) est du blanc par spécification
        if conditioner and flag is None and self.lock_edge is not None and coverage > 0.75:
            idx = (np.arange(int(0.010 * n), int(0.040 * n)) + int(self.lock_edge * n)) % n
            selw = conf[idx] > 0.6
            if np.mean(selw) > 0.8:
                vals = freq[idx][selw]
                # la marge n'est exploitable que si elle est réellement blanche (pas un bord d'image)
                if np.mean(fv[idx][selw] > center + 0.3 * shift) > 0.9:
                    self._afc_step(float(np.median(vals)) - white)
        obs["afc_hz"] = round(self.afc_hz, 1)

        # 8. pixels non fiables
        bad = ~np.isfinite(row) | (pix_conf < self.BAD_PIXEL_CONF)
        if np.any(bad):
            good_idx = np.flatnonzero(~bad)
            if conditioner and len(good_idx) > line_width // 3:
                filled = np.interp(np.arange(line_width), good_idx, row[good_idx])
                # trous courts (≤ 12 px ≈ 3 ms) : interpolation ; trous longs : ligne précédente si disponible
                lab, nlab = _runs(bad)
                for s, e in lab:
                    if e - s > 12 and self.LONG_GAP_PREV_ROW:
                        filled[s:e] = self.prev_row[s:e] if self.prev_row is not None else 255.0
                row = filled
            else:
                row = np.where(bad, self.prev_row if self.prev_row is not None else 128.0, row)
        out = np.clip(np.nan_to_num(row, nan=128.0), 0, 255).astype(np.uint8)
        self.prev_row = out.astype(np.float64)
        return out, flag, pix_conf, obs

    # (drapeau, fréquence de commutation, IOC, amplitude relative mesurée sur signal propre après filtrage)
    APT_TONES = (
        ("START_576", 300.0, 576, 0.72),
        ("STOP", 450.0, None, 0.54),
        ("START_576", 675.0, 288, 0.29),
    )
    APT_MIN_FRACTION = (
        0.40  # fraction de l'amplitude « propre » exigée (fading : la moitié de la ligne peut manquer)
    )

    APT_FADED_FRACTION = 0.20
    APT_FADED_PEAK_RATIO = 20.0

    def _detect_apt(self, fv, conf, shift, obs):
        n = len(fv)
        wsum = float(np.sum(conf))
        if wsum < 0.2 * n:
            return None
        dec = 4  # le signal vidéo est limité à ~800 Hz : on peut décimer pour l'analyse
        t = np.arange(0, n, dec) / self.fs
        dev = ((fv - np.sum(conf * fv) / wsum) * conf)[::dec]
        wsum = wsum / dec

        # 2.10.0 — les 38 fréquences testées (3 tonalités × 11 + 5 de fond) en un seul produit matriciel,
        # avec la table d'exponentielles gardée pour la longueur de ligne courante (calculée une fois)
        freqs, basis = self._apt_basis(len(t))
        amps = 2.0 * np.abs(basis @ dev) / wsum
        best = None
        k = 0
        for name, f_nom, ioc, ref in self.APT_TONES:
            vals = amps[k : k + 11]
            i = int(np.argmax(vals))
            score = vals[i] / ref
            if best is None or score > best[0]:
                best = (score, float(freqs[k + i]), name, ioc, float(vals[i]))
            k += 11
        rel, f_best, name, ioc, a_best = best
        background = float(np.median(amps[k:])) + 1e-9
        expected = 2.0 * shift / np.pi
        obs["apt_modulation_hz"] = f_best
        obs["apt_peak_ratio"] = round(a_best / background, 1)
        obs["apt_amplitude_ratio"] = round(rel / expected, 2)
        strong = rel >= self.APT_MIN_FRACTION * expected and a_best >= 4.0 * background
        # 2.8.4 (audit D5) : sous fading sélectif l'amplitude de la tonalité tombe à 20–40 % du nominal alors
        # que la raie reste très au-dessus du fond. Second critère : amplitude ≥ 20 % ET raie ≥ 20 fois le fond.
        pure = rel >= self.APT_FADED_FRACTION * expected and a_best >= self.APT_FADED_PEAK_RATIO * background
        if strong or pure:
            if ioc:
                obs["ioc"] = ioc
            return name
        return None

    APT_BACKGROUND_HZ = (240.0, 375.0, 525.0, 600.0, 750.0)

    def _apt_basis(self, m):
        cache = getattr(self, "_apt_basis_cache", None)
        if cache is not None and cache[0] == (m, self.fs):
            return cache[1], cache[2]
        freqs = np.concatenate(
            [f_nom + np.arange(-5.0, 5.01, 1.0) for _, f_nom, _, _ in self.APT_TONES] + [np.array(self.APT_BACKGROUND_HZ)]
        )
        t = np.arange(0, 4 * m, 4)[:m] / self.fs
        basis = np.exp(-2j * np.pi * np.outer(freqs, t))
        self._apt_basis_cache = ((m, self.fs), freqs, basis)
        return freqs, basis

    def _afc_step(self, residual_hz):
        if abs(residual_hz) < 120.0:
            self.afc_hz = float(np.clip(self.afc_hz + 0.2 * residual_hz, -100.0, 100.0))

    def _precise_edge(self, grey, conf, coarse_frac):
        """Front montant (noir -> blanc) de l'impulsion de phasage, à l'échantillon près (fraction de ligne)."""
        n = len(grey)
        c = int(coarse_frac * n)
        half = int(0.03 * n)
        idx = (np.arange(c - half, c + half)) % n
        g = grey[idx]
        ok = conf[idx] > 0.3
        if np.mean(ok) < 0.7:
            return coarse_frac
        up = np.flatnonzero((g[:-1] < 127.5) & (g[1:] >= 127.5) & ok[:-1] & ok[1:])
        if len(up) == 0:
            return coarse_frac
        k = up[np.argmin(np.abs(up - half))]
        frac = (127.5 - g[k]) / max(g[k + 1] - g[k], 1e-6)
        return float(((c - half + k + frac) / n) % 1.0)

    def _update_clock(self):
        """Erreur d'horloge = dérive du front de l'impulsion de phasage d'une ligne à l'autre.

        Une erreur ε de la carte son décale le front de ε ligne à chaque ligne. Mesure robuste
        (pente de Theil-Sen) sur au moins 30 lignes de phasage de bonne qualité ; la correction n'est
        appliquée que si les deux moitiés de la série donnent la même pente et si la dispersion est
        inférieure à 1,5 pixel. Sinon, la valeur précédente (mémorisée) est conservée.
        """
        pts = self.cal_points[-60:]
        if len(pts) < 30:
            return
        idx = np.array([i for i, _ in pts], dtype=np.float64)
        if np.max(np.diff(idx)) > 3:
            self.cal_points = self.cal_points[-1:]
            return
        pos = np.unwrap(2 * np.pi * np.array([p for _, p in pts])) / (2 * np.pi)

        def theil_sen(i, p):
            d = (p[None, :] - p[:, None]) / np.where(
                i[None, :] != i[:, None], i[None, :] - i[:, None], np.nan
            )
            return float(np.nanmedian(d))

        slope = theil_sen(idx, pos)
        resid = pos - (pos[0] + slope * (idx - idx[0]))
        resid -= np.median(resid)
        half = len(idx) // 2
        s1 = theil_sen(idx[:half], pos[:half])
        s2 = theil_sen(idx[half:], pos[half:])
        spread_ok = float(np.median(np.abs(resid))) < 0.0008
        agree = abs(s1 - s2) <= max(0.35 * abs(slope), 4e-6)
        if spread_ok and agree and 2e-6 < abs(slope) < 800e-6:
            self.clock_ppm = float(np.clip(self.clock_ppm + slope * 1e6, -1000.0, 1000.0))
            self.cal_points = []
            self.phase_history = self.phase_history[-1:]


def _runs(mask):
    """Plages [début, fin) des valeurs True."""
    m = np.concatenate([[False], mask, [False]]).astype(np.int8)
    d = np.diff(m)
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return list(zip(starts, ends)), len(starts)
