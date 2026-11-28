"""Indices de qualité / fiabilité estimés (WEFAX image et RTTY texte)."""

from datetime import datetime, timezone
import numpy as np


class WeatherReliabilityEstimator:
    HELP_TEXT_FR = (
        "=== COMPRENDRE LES INDICES DE QUALITÉ & FIABILITÉ (WEFAX & RTTY) ===\n\n"
        "Les deux bargraphes 'Qual.WEFAX' et 'Qual.RTTY' situés dans le bloc "
        "'TÉLÉMÉTRIE RF & TRAITEMENT' (en haut à gauche) mesurent en direct la capacité "
        "du canal radio HF à produire une carte nette ou un bulletin texte sans erreurs :\n\n"
        "• GRADE A (80% à 100% — Vert Émeraude) : EXCELLENT\n"
        "  Porteuse blanche WEFAX (2300 Hz) très forte (SNR >= +15 dB), très peu de bruit.\n"
        "  -> Image WEFAX nette sans neige ; décodage RTTY/NAVTEX à ~99% sans fautes.\n\n"
        "• GRADE B (62% à 79% — Vert Clair) : BON\n"
        "  Signal bien lisible (SNR +10 à +14 dB) avec léger fading HF.\n"
        "  -> Carte météo parfaitement exploitable ; texte RTTY lisible.\n\n"
        "• GRADE C (42% à 61% — Ambre) : PARTIEL / BRUITÉ\n"
        "  Signal faible ou affecté par du QRM/QSB sélectif (SNR +6 à +9 dB).\n"
        "  -> Carte WEFAX bruitée mais isobares visibles ; texte RTTY partiel.\n\n"
        "• GRADE D (< 42% — Gris Ardoise) : ATTENTE / TROP BRUITÉ\n"
        "  Pas d'émission active ou simple raie parasite à 1900 Hz sans porteuse blanche 2300 Hz.\n"
        "  -> Le squelch RTTY bloque l'affichage du bruit aléatoire.\n\n"
        "=== SÉLECTION AUTOMATIQUE DE LA MEILLEURE FRÉQUENCE (SCAN INTELLIGENT) ===\n"
        "Lors d'un scan WEFAX, l'application distingue :\n"
        "  1. Les VRAIES cartes WEFAX (présence du pic de blanc à 2300 Hz ± 45 Hz avec peak >= 13.5 dB, "
        "ex: GYA2 4610 kHz la nuit ou DDK6 13882.5 kHz le jour) qui reçoivent la priorité maximale (Tier 2) ;\n"
        "  2. Les fausses porteuses fixes à 1896 Hz sans modulation 2300 Hz (ex: GYA3 8040 kHz en veille "
        "avec center_fraction > 0.45 et proxy < 6.5 dB) qui sont rétrogradées pour éviter les images neigeuses."
    )

    @staticmethod
    def propagation_bonus_db(freq_khz: float, utc_hour: int = None) -> float:
        h = datetime.now(timezone.utc).hour if utc_hour is None else int(utc_hour)
        is_day = 7 <= h <= 17
        f = float(freq_khz)
        if is_day:
            if f >= 11000.0:
                return 5.0  # DDK6 (13882.5), GYA4 (11086.5) privilégiées le jour
            if 7500.0 <= f < 11000.0:
                return 2.0
            return -3.0
        else:
            if 3500.0 <= f <= 8500.0:
                return 4.5  # GYA2 (4610), DDK3 (7880), DDH3 (3855), GYA3 (8040) privilégiées la nuit
            if f > 11000.0:
                return -2.5
            return 1.0

    @staticmethod
    def evaluate_wefax_scan_candidate(samples: list, st_dict: dict) -> dict:
        """
        Distingue une VRAIE émission WEFAX (porteuse blanche 2300 Hz active) d'une
        porteuse parasite fixe à 1896 Hz (comme sur GYA3 à 19:06 UTC).
        """
        if not samples:
            return {"quality_pct": 0, "effective_db": -99.0, "tier": 0, "white_carrier_windows": 0}

        med_proxy = float(np.median([float(x.get("proxy_db", 0.0)) for x in samples]))
        med_peak_db = float(np.median([float(x.get("peak_db", 0.0)) for x in samples]))
        med_span = float(np.median([float(x.get("span_hz", 1400.0)) for x in samples]))
        med_cfrac = float(np.median([float(x.get("center_fraction", 0.0)) for x in samples]))

        # Compte les fenêtres où le pic principal est le BLANC WEFAX (2245..2355 Hz) ou NOIR (1450..1550 Hz)
        white_or_black_windows = sum(
            1
            for x in samples
            if (
                (2245.0 <= float(x.get("peak_hz", 0.0)) <= 2355.0)
                or (1450.0 <= float(x.get("peak_hz", 0.0)) <= 1550.0)
            )
            and (float(x.get("peak_db", 0.0)) >= 13.0 or float(x.get("proxy_db", 0.0)) >= 4.0)
        )

        # Détecte le piège de la raie parasite fixe sur 1896 Hz (ex: GYA3 19:06 UTC : peak_hz=1896, cfrac=0.51, proxy=5.4 dB)
        stuck_on_1900_only = white_or_black_windows == 0 and med_cfrac >= 0.35 and med_proxy < 7.2

        prop_bonus = WeatherReliabilityEstimator.propagation_bonus_db(st_dict.get("freq", 7880.0))
        purity_bonus = max(-3.0, min(5.0, (1150.0 - med_span) / 150.0))

        if white_or_black_windows >= 3:
            # Vraie porteuse blanche WEFAX détectée (ex: GYA2 à 19:06 UTC ou DDK6 à 09:12 UTC) !
            tier = 2
            effective_db = max(med_proxy * 1.8, med_peak_db * 0.75) + purity_bonus + prop_bonus + 8.0
            quality_pct = int(round(max(48.0, min(100.0, effective_db * 2.6))))
        elif stuck_on_1900_only:
            # Raie fixe à 1896 Hz sans porteuse blanche 2300 Hz -> rétrogradée en Tier 0 !
            tier = 0
            effective_db = med_proxy - 8.0 + prop_bonus
            quality_pct = int(round(max(8.0, min(28.0, med_proxy * 3.0))))
        elif med_proxy >= 7.5:
            tier = 2
            effective_db = med_proxy + purity_bonus + prop_bonus
            quality_pct = int(round(max(42.0, min(95.0, (effective_db + 4.0) * 2.8))))
        else:
            tier = 0
            effective_db = med_proxy - 10.0 + prop_bonus
            quality_pct = int(round(max(5.0, min(25.0, max(1.0, med_proxy) * 2.5))))

        return {
            "quality_pct": quality_pct,
            "effective_db": round(effective_db, 2),
            "tier": int(tier),
            "white_carrier_windows": int(white_or_black_windows),
            "stuck_on_1900_only": bool(stuck_on_1900_only),
            "med_proxy_db": round(med_proxy, 1),
            "med_peak_db": round(med_peak_db, 1),
            "med_span_hz": round(med_span, 0),
        }

    @staticmethod
    def compute_wefax_reliability(app) -> dict:
        snr_db = float(getattr(app, "current_snr_db", 0.0))
        lines = int(getattr(app, "rx_current_line", 0))
        fading = float(getattr(getattr(app, "dsp", None), "last_fading_penalty", 5.0))
        afc_hz = float(getattr(getattr(app, "dsp", None), "current_white_hz", 2300.0))
        phase_ok = bool(getattr(getattr(app, "dsp", None), "phase_locked", False) or lines >= 40)

        # 2.8.3 — Carte en cours ou tout juste terminée : la fiabilité est celle de la CARTE (moyenne sur
        # toutes ses lignes), plus celle de l'instant de l'archivage, où le signal a déjà disparu (les
        # cartes lisibles du 15/11 étaient toutes notées 8 % [D]).
        quality = getattr(app, "chart_quality", None)
        if callable(quality):
            try:
                snr_avg, valid_frac, measured = quality()
            except Exception:
                measured = 0
            if measured >= 20:
                snr_score = max(0.0, min(50.0, (snr_avg - 8.0) * 2.5))
                lines_score = 30.0 * max(0.0, min(1.0, valid_frac))
                sync_score = 12.0 if getattr(app, "phase_locked_from_header", False) else 5.0
                start_score = 8.0 if getattr(app, "rx_sheet_had_start", False) else 0.0
                total = int(round(max(5.0, min(100.0, snr_score + lines_score + sync_score + start_score))))
                return WeatherReliabilityEstimator._format_grade(
                    total, f"SNR moyen {snr_avg:+.1f}dB · lignes exploitables {valid_frac * 100:.0f}%"
                )

        # Si le SNR bande est très faible (< 4 dB) et fading élevé (> 4.5), l'image est neigeuse -> Grade D
        if snr_db < 4.2 and fading >= 4.2:
            total = int(round(max(8.0, min(32.0, snr_db * 5.0 + (8.0 - min(8.0, fading)) * 2.0))))
            return WeatherReliabilityEstimator._format_grade(total, f"SNR {snr_db:+.1f}dB · QSB {fading:.1f}")

        snr_score = max(0.0, min(55.0, (snr_db + 1.0) * 2.8))
        fading_score = max(0.0, min(25.0, (8.5 - min(8.5, fading)) * 2.9))
        sync_score = 12.0 if phase_ok else (6.0 if snr_db >= 8.0 else 0.0)
        afc_ok = 8.0 if (2282.0 <= afc_hz <= 2325.0) else 0.0

        total = int(round(max(5.0, min(100.0, snr_score + fading_score + sync_score + afc_ok))))
        return WeatherReliabilityEstimator._format_grade(total, f"SNR {snr_db:+.1f}dB · QSB {fading:.1f}")

    @staticmethod
    def compute_rtty_reliability(rtty_decoder, raw_text: str = "") -> dict:
        m = getattr(rtty_decoder, "last_metrics", {})
        m_snr = float(m.get("mark_snr_db", 0.0))
        s_snr = float(m.get("space_snr_db", 0.0))
        best_snr = max(m_snr, s_snr)
        sig_ok = bool(m.get("signal_compatible", False))
        sync_r = float(m.get("frame_sync_ratio", 0.0))
        lex_q = float(m.get("lexical_quality", 0.0))
        n_chars = len((raw_text or "").strip())

        # mark_snr_db / space_snr_db = contraste marche/arrêt des tonalités (bruit seul ≈ 9 dB)
        if not sig_ok or best_snr < 11.5:
            total = int(round(max(5.0, min(25.0, best_snr * 2.0))))
            return WeatherReliabilityEstimator._format_grade(total, f"M:{m_snr:+.0f}/S:{s_snr:+.0f}dB")

        snr_score = max(0.0, min(45.0, (best_snr - 10.0) * 3.0))
        sync_score = max(0.0, min(25.0, sync_r * 25.0))
        lex_score = max(0.0, min(20.0, lex_q * 20.0))
        len_score = min(10.0, (n_chars / 100.0) * 10.0)

        total = int(round(max(5.0, min(100.0, snr_score + sync_score + lex_score + len_score))))
        return WeatherReliabilityEstimator._format_grade(total, f"M:{m_snr:+.0f}/S:{s_snr:+.0f}dB")

    @staticmethod
    def _format_grade(score_pct: int, detail: str) -> dict:
        if score_pct >= 80:
            grade, label, bg, fg, bar = "A", "EXCELLENTE", "#065f46", "#dcfce7", "#10b981"
        elif score_pct >= 62:
            grade, label, bg, fg, bar = "B", "BONNE", "#15803d", "#ffffff", "#22c55e"
        elif score_pct >= 42:
            grade, label, bg, fg, bar = "C", "MOYENNE", "#b45309", "#fef3c7", "#f59e0b"
        else:
            grade, label, bg, fg, bar = "D", "ATTENTE", "#334155", "#cbd5e1", "#64748b"
        return {
            "score_pct": score_pct,
            "grade": grade,
            "label": label,
            "detail": detail,
            "short_bar_text": f"{score_pct}% [{grade}]",
            "badge_text": f"FIABILITÉ {score_pct}% [{grade} · {label}]",
            "bg": bg,
            "fg": fg,
            "bar_color": bar,
        }
