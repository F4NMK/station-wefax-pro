"""Moteur de démodulation FM WEFAX 120 RPM et de restauration d'image."""

import math
import numpy as np
from wefax_station.dsp.chart_restore import restore_chart
import cv2
from scipy import signal as sp_signal
from wefax_station.dsp.wefax_demod import WefaxStreamDemodulator
from wefax_station.weather.geometry import estimate_geometry


class WefaxSignalAndImageEngine:
    """
    Moteur DSP :
    1. Conditionneur Audio HF en amont (AGC, Soft-Limiter QRN, AFC centrage auto 2300 Hz,
       Anti-fading QSB 2D par suivi d'enveloppe Hilbert + cohérence verticale L-1).
    2. Détection sélective START (300.0 ± 3.5 Hz), STOP (450.0 ± 4.5 Hz) et PHASE
       avec contrôle de pureté spectrale (zéro faux déclenchement sur les traits d'isobares).
    3. Restauration Documentaire Non-Destructive avec rehaussement net des isobares.
    """

    def __init__(self, sample_rate=44100):
        self.last_clarity_score = 92.0
        self.afc_white_freq_hz = 2300.0
        self.last_fading_penalty_db = 0.0
        self.qsb_env_threshold_ratio = 0.28
        self.prev_valid_freq = 2300.0
        self.prev_decoded_row = None
        self.kept_raw_fallback = False
        self._phase_positions = []
        self.set_sample_rate(sample_rate)

    def set_sample_rate(self, sample_rate: int):
        self.fs = max(8000, int(sample_rate))
        nyq = 0.5 * self.fs
        self.sos_bp = sp_signal.butter(4, [1320.0 / nyq, min(0.95, 2480.0 / nyq)], btype="band", output="sos")
        self.zi_bp = sp_signal.sosfilt_zi(self.sos_bp) * 0.0
        self.sos_lp = sp_signal.butter(3, min(0.92, 1250.0 / nyq), btype="low", output="sos")
        self.zi_lp = sp_signal.sosfilt_zi(self.sos_lp) * 0.0
        old_ppm = getattr(getattr(self, "stream", None), "clock_ppm", 0.0)
        self.stream = WefaxStreamDemodulator(self.fs)
        self.stream.clock_ppm = old_ppm
        self.last_row_confidence = np.ones(0)

    def reset_filter_states(self):
        self.zi_bp = sp_signal.sosfilt_zi(self.sos_bp) * 0.0
        self.zi_lp = sp_signal.sosfilt_zi(self.sos_lp) * 0.0
        self.prev_valid_freq = 2300.0
        self.afc_white_freq_hz = 2300.0
        self.prev_decoded_row = None
        self._phase_positions = []
        self.stream.reset()

    def analyze_live_audio_spectrum(self, audio_chunk: np.ndarray, auto_afc_enabled: bool = True) -> dict:
        if audio_chunk is None or len(audio_chunk) < 512:
            return {
                "snr_db": 0.0,
                "snr_raw_db": 0.0,
                "rms_dbfs": -90.0,
                "locked": False,
                "carrier_2300": False,
                "carrier_1500": False,
                "freqs": None,
                "psd_db": None,
            }

        x = audio_chunk.astype(np.float64)
        x = x - np.mean(x)
        rms = float(np.sqrt(np.mean(x * x)) + 1e-12)
        rms_dbfs = 20.0 * math.log10(rms)

        nperseg = min(4096, len(x))
        freqs, psd = sp_signal.welch(x, fs=self.fs, window="hann", nperseg=nperseg)
        psd_db = 10.0 * np.log10(psd + 1e-16)

        mask_2300 = (freqs >= 2240) & (freqs <= 2360)
        mask_1500 = (freqs >= 1440) & (freqs <= 1560)
        mask_wefax = (freqs >= 1500) & (freqs <= 2340)
        mask_inband_noise = (freqs >= 650) & (freqs <= 1380)

        peak_2300 = float(np.max(psd_db[mask_2300])) if np.any(mask_2300) else -95.0
        peak_1500 = float(np.max(psd_db[mask_1500])) if np.any(mask_1500) else -95.0
        band_wefax = float(np.percentile(psd_db[mask_wefax], 85)) if np.any(mask_wefax) else -95.0
        inband_noise = (
            float(np.percentile(psd_db[mask_inband_noise], 60)) if np.any(mask_inband_noise) else -80.0
        )

        if auto_afc_enabled and np.any(mask_2300) and (peak_2300 - inband_noise) >= 6.0:
            f_sub = freqs[mask_2300]
            p_sub = psd_db[mask_2300]
            detected_white_hz = float(f_sub[int(np.argmax(p_sub))])
            if 2265.0 <= detected_white_hz <= 2335.0:
                self.afc_white_freq_hz = 0.85 * self.afc_white_freq_hz + 0.15 * detected_white_hz

        raw_snr = max(0.0, max(peak_2300, band_wefax, peak_1500) - inband_noise)
        effective_snr_db = max(0.0, raw_snr - self.last_fading_penalty_db)

        carrier_2300 = ((peak_2300 - inband_noise) >= 7.0) and ((peak_2300 - peak_1500) >= 6.0)
        carrier_1500 = ((peak_1500 - inband_noise) >= 7.0) and ((peak_1500 - peak_2300) >= 6.0)

        mask_3k = freqs <= 3000.0
        return {
            "snr_db": round(effective_snr_db, 1),
            # 2.8.3 : SNR spectral mesuré, sans la pénalité de fading. « snr_db » (pénalisé) ne sert plus
            # qu'aux décisions d'attente / fin de carte ; l'affichage et les statistiques utilisent celui-ci.
            "snr_raw_db": round(raw_snr, 1),
            "rms_dbfs": round(rms_dbfs, 1),
            "locked": (effective_snr_db >= 4.5),
            "carrier_2300": carrier_2300,
            "carrier_1500": carrier_1500,
            "freqs": freqs[mask_3k],
            "psd_db": psd_db[mask_3k],
        }

    def assess_wefax_signal(self, audio_chunk: np.ndarray) -> dict:
        info = self.analyze_live_audio_spectrum(audio_chunk, auto_afc_enabled=False)
        present = bool(info.get("rms_dbfs", -120) > -100 and info.get("snr_db", 0) > 4.5)
        return dict(
            verdict="candidate_unconfirmed" if present else "not_established",
            signal_present=present,
            fm_structure_ok=False,
            deviation_ok=False,
            apt_start_detected=False,
            apt_stop_detected=False,
            synchronized=False,
        )

    def demodulate_line_fm(
        self,
        audio_samples: np.ndarray,
        line_width: int = 1809,
        qrn_blanker: bool = True,
        upstream_conditioner: bool = True,
    ) -> tuple:
        """Démodule une ligne (0,5 s) ; les lignes successives doivent être contiguës.

        Renvoie (ligne_uint8, drapeau) avec drapeau ∈ {None, "START_576", "PHASE", "STOP"}.
        Détails dans self.protocol_observation ; confiance par pixel dans self.last_row_confidence.
        Voir dsp/wefax_demod.py pour la chaîne de traitement.
        """
        center = float(getattr(self, "fm_center_hz", 1900.0))
        shift = float(getattr(self, "fm_shift_hz", 800.0))
        if not 700 <= shift <= 1000:
            shift = 800.0
        row, flag, conf, obs = self.stream.process_line(
            audio_samples,
            center=center,
            shift=shift,
            line_width=line_width,
            qrn_blanker=qrn_blanker,
            conditioner=upstream_conditioner,
        )
        self.protocol_observation = obs
        self.last_row_confidence = conf
        self.last_invalid_fraction = float(np.mean(conf < 0.5)) if len(conf) else 1.0
        self.last_fading_penalty_db = min(14.0, self.last_invalid_fraction * 42.0)
        self.prev_decoded_row = row.copy()
        return row, flag

    def samples_per_line(self) -> float:
        """Durée exacte d'une ligne en échantillons, corrigée de l'erreur d'horloge mesurée (ppm)."""
        return self.stream.samples_per_line()

    @property
    def clock_ppm(self) -> float:
        return self.stream.clock_ppm

    @clock_ppm.setter
    def clock_ppm(self, value):
        self.stream.clock_ppm = float(value)

    @staticmethod
    def evaluate_document_legibility(img_gray: np.ndarray) -> float:
        if img_gray is None or img_gray.size == 0:
            return 0.0
        f = img_gray.astype(np.float32)
        p85 = float(np.percentile(f, 85))
        p05 = float(np.percentile(f, 5))
        dynamic_contrast = max(0.0, p85 - p05)

        white_mask = f >= np.percentile(f, 55)
        if np.any(white_mask):
            blur = cv2.GaussianBlur(f, (5, 5), 1.0)
            paper_noise_std = float(np.std(f[white_mask] - blur[white_mask]))
        else:
            paper_noise_std = 20.0

        score = (dynamic_contrast * 0.38) + (p85 * 0.14) - (paper_noise_std * 2.0)
        return float(np.clip(score, 10.0, 99.0))

    def restore_image_v1_9(
        self, img_gray, use_fft_notch=True, use_structure_tensor=True, use_adaptive_bin=False, conf=None
    ):
        """Restauration de la carte (voir dsp/chart_restore.py).

        use_fft_notch : réparation des lignes abîmées (guidée par la confiance) et des stries ;
        use_structure_tensor : fond papier uniformisé et netteté ; use_adaptive_bin : noir et blanc.
        """
        if img_gray is None or img_gray.size == 0:
            return img_gray
        original = np.asarray(img_gray, dtype=np.uint8)
        raw_score = float(self.evaluate_document_legibility(original))
        if not (use_fft_notch or use_structure_tensor or use_adaptive_bin):
            self.kept_raw_fallback = True
            self.last_clarity_score = raw_score
            return original.copy()
        result = restore_chart(
            original,
            conf=conf,
            repair=bool(use_fft_notch),
            flatten=bool(use_structure_tensor),
            binarize=bool(use_adaptive_bin),
        )
        proc_score = float(self.evaluate_document_legibility(result))
        self.kept_raw_fallback = False
        self.last_clarity_score = max(proc_score, raw_score)
        return result

    @staticmethod
    def auto_detect_margin_and_slant(img_gray):
        return estimate_geometry(img_gray)

    def synthesize_wefax_fm_line(self, pixel_row_u8: np.ndarray, n_samples: int) -> np.ndarray:
        t_idx = np.linspace(0, len(pixel_row_u8) - 1, n_samples)
        px_interp = np.interp(t_idx, np.arange(len(pixel_row_u8)), pixel_row_u8.astype(np.float64))
        inst_freq = 1500.0 + (px_interp / 255.0) * 800.0
        phase = 2.0 * np.pi * np.cumsum(inst_freq) / float(self.fs)
        carrier = 0.65 * np.cos(phase)
        noise = np.random.normal(0.0, 0.04, size=n_samples)
        return (carrier + noise).astype(np.float32)
