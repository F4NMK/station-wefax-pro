"""Indicateurs du bandeau : spectre BF, bargraphes de qualité, horaires UTC."""

import json
import math
import time
from datetime import datetime, timezone
import numpy as np
from wefax_station.core.schedules import (
    BROADCAST_SCHEDULES_UTC,
    SCHEDULE_REV,
    merge_saved_schedules,
    next_schedule25,
    schedule_pair,
)
from wefax_station.dsp.scan_diagnostics import assess_scan_audio
from wefax_station.ui.theme import UITheme
from wefax_station.weather.reliability import WeatherReliabilityEstimator
import tkinter.font as tkfont


class TelemetryMixin:
    def _draw_permanent_top_signal_curve(self):
        self._draw_wefax_spectrum()
        if not hasattr(self, "top_signal_canvas"):
            return
        c = self.top_signal_canvas
        w = max(140, c.winfo_width())
        h = max(40, c.winfo_height())
        arb = getattr(self, "hybrid_arbiter", None)
        is_rtty = bool(arb is not None and arb.active_pipeline == "RTTY")
        sel_aud = (
            self.cmb_audio.get()[:16]
            if (hasattr(self, "cmb_audio") and self.audio_live_connected)
            else "SIMU"
        )

        if is_rtty:
            f_center = float(self.rtty_decoder.center_hz)
            f_shift = float(self.rtty_decoder.shift_hz)
            f_space = f_center - 0.5 * f_shift
            f_mark = f_center + 0.5 * f_shift

            if hasattr(self, "lbl_spectrum_header"):
                self.lbl_spectrum_header.configure(
                    text=f"SPECTRE BF [RTTY {self.rtty_decoder.baud:.0f}Bd · {f_space:.0f}S/{f_mark:.0f}M] ({sel_aud})"
                )
            c.delete("all")
            for frac in (0.25, 0.50, 0.75):
                gy = int(h * frac)
                c.create_line(0, gy, w, gy, fill="#18222f")

            spec_pts = []
            freqs = self.last_spectrum_info.get("freqs")
            psd_db = self.last_spectrum_info.get("psd_db")
            if freqs is not None and psd_db is not None and len(freqs) > 8:
                p_min = float(np.percentile(psd_db, 10))
                p_max = max(p_min + 20.0, float(np.max(psd_db)))
                for x in range(0, w, 3):
                    f_target = (x / float(w)) * 3000.0
                    val_db = float(np.interp(f_target, freqs, psd_db))
                    norm_y = (val_db - p_min) / (p_max - p_min)
                    ys = max(14, min(h - 3, int(h - norm_y * (h - 17))))
                    spec_pts.extend([x, ys])
            if len(spec_pts) >= 4:
                c.create_line(*spec_pts, fill="#38bdf8", width=1.5)

            x_space = int(w * (f_space / 3000.0))
            x_center = int(w * (f_center / 3000.0))
            x_mark = int(w * (f_mark / 3000.0))

            c.create_line(x_space, 12, x_space, h, fill="#22c55e", dash=(2, 2))
            c.create_line(x_center, 12, x_center, h, fill="#64748b", dash=(1, 3))
            c.create_line(x_mark, 12, x_mark, h, fill="#f59e0b", dash=(2, 2))

            c.create_text(
                max(90, x_space - 4),
                1,
                text=f"{f_space:.0f} S",
                fill="#22c55e",
                anchor="ne",
                font=("Consolas", 7, "bold"),
            )
            c.create_text(
                min(w - 4, x_mark + 4),
                1,
                text=f"{f_mark:.0f} M",
                fill="#f59e0b",
                anchor="nw",
                font=("Consolas", 7, "bold"),
            )

            c.create_rectangle(4, 2, 86, 15, fill="#b45309", outline="#fde68a")
            c.create_text(
                45,
                8,
                text=f"RTTY {self.rtty_decoder.baud:.0f} Bd",
                fill="#ffffff",
                font=("Segoe UI", 7, "bold"),
            )
        else:
            if hasattr(self, "lbl_spectrum_header"):
                self.lbl_spectrum_header.configure(
                    text=f"SPECTRE BF [WEFAX 120 RPM · 1500N / 2300B] ({sel_aud})"
                )
            c.create_rectangle(4, 2, 86, 15, fill="#92400e", outline="#fde68a")
            c.create_text(45, 8, text="WEFAX 120", fill="#ffffff", font=("Segoe UI", 7, "bold"))

    def _draw_wefax_spectrum(self):
        if not hasattr(self, "top_signal_canvas"):
            return
        c = self.top_signal_canvas
        w = max(140, c.winfo_width())
        h = max(40, c.winfo_height())
        c.delete("all")
        for frac in (0.25, 0.50, 0.75):
            gy = int(h * frac)
            c.create_line(0, gy, w, gy, fill="#18222f")

        x1500 = int(w * (1500.0 / 3000.0))
        x1900 = int(w * (1900.0 / 3000.0))
        x2300 = int(w * (self.dsp.afc_white_freq_hz / 3000.0))

        spec_pts = []
        freqs = self.last_spectrum_info.get("freqs")
        psd_db = self.last_spectrum_info.get("psd_db")

        if freqs is not None and psd_db is not None and len(freqs) > 8:
            p_min = float(np.percentile(psd_db, 10))
            p_max = max(p_min + 20.0, float(np.max(psd_db)))
            for x in range(0, w, 3):
                f_target = (x / float(w)) * 3000.0
                val_db = float(np.interp(f_target, freqs, psd_db))
                norm_y = (val_db - p_min) / (p_max - p_min)
                ys = max(13, min(h - 3, int(h - norm_y * (h - 16))))
                spec_pts.extend([x, ys])
        else:
            for x in range(0, w, 3):
                freq = (x / float(w)) * 3000.0
                noise = np.random.uniform(2, 4)
                sig = 22.0 * math.exp(-(((freq - 2300.0) / 40.0) ** 2))
                if 1500 <= freq <= 2300:
                    sig += 9.0 * math.exp(-(((freq - 1900.0) / 210.0) ** 2))
                ys = max(13, int(h - (noise + sig)))
                spec_pts.extend([x, ys])

        if len(spec_pts) >= 4:
            c.create_line(*spec_pts, fill="#38bdf8", width=1.5)

        for xpos, lbl, col in [
            (x1500, "1500", "#64748b"),
            (x1900, "1900", "#64748b"),
            (x2300, f"{self.dsp.afc_white_freq_hz:.0f} B", "#f59e0b"),
        ]:
            c.create_line(xpos, 12, xpos, h, fill=col, dash=(2, 2))
            c.create_text(xpos + 3, 1, text=lbl, fill=col, anchor="nw", font=("Consolas", 7))

    def _draw_three_quality_bargraphs(self, *args, **kwargs):
        """Panneau télémétrie : 5 barres (RF, bande, pic, qualité WEFAX, qualité RTTY).

        Le dessin s'adapte à la taille réelle du panneau (hauteur de ligne, police, largeur des barres).
        """
        if not hasattr(self, "bargraph_canvas"):
            return
        c = self.bargraph_canvas
        cb = getattr(self, "last_audio_callback", 0)
        fresh = bool(self.audio_live_connected and cb and 0 <= time.monotonic() - cb < 1)
        now = time.monotonic()
        if fresh and now - getattr(self, "_candidate_dashboard_ts", 0) > 0.7:
            self._candidate_dashboard_info = assess_scan_audio(self.audio_ring.copy(), self.audio_fs)
            self._candidate_dashboard_ts = now
        info = getattr(self, "_candidate_dashboard_info", {}) if fresh else {}
        rf = bool(self.radio.port_open and self.radio.handshake_ok and self.radio.s_meter_valid)
        band = info.get("proxy_db")
        peak = info.get("peak_contrast_db")
        hz = info.get("peak_hz")
        try:
            rel_wf = WeatherReliabilityEstimator.compute_wefax_reliability(self)
            arb = getattr(self, "hybrid_arbiter", None)
            rel_rt = (
                WeatherReliabilityEstimator.compute_rtty_reliability(self.rtty_decoder, arb.rtty_raw_buffer)
                if (hasattr(self, "rtty_decoder") and arb is not None)
                else WeatherReliabilityEstimator._format_grade(10, "Attente")
            )
        except Exception:
            rel_wf = rel_rt = None
        rows = [
            (
                "RF brut",
                min(1, max(0, self.radio.s_meter_raw / 200)) if rf else 0,
                self.radio.s_meter_label if rf else "n/d",
                "#22c55e",
                UITheme.TEXT_MUTED,
            ),
            (
                "Bande / réf.",
                min(1, max(0, (band + 5) / 25)) if band is not None else 0,
                f"{band:+.1f} dB" if band is not None else "n/d",
                "#38bdf8",
                UITheme.TEXT_MUTED,
            ),
            (
                "Pic / réf.",
                min(1, max(0, peak / 40)) if peak is not None else 0,
                f"{peak:+.1f} dB · {hz:.0f} Hz" if peak is not None else "n/d",
                "#f59e0b",
                UITheme.TEXT_MUTED,
            ),
        ]
        for title, rel in (("Qualité WEFAX", rel_wf), ("Qualité RTTY", rel_rt)):
            if rel is not None:
                pct = max(0, min(100, int(rel["score_pct"])))
                rows.append(
                    (
                        title,
                        pct / 100.0,
                        f"{pct} % [{rel.get('grade', '')}]",
                        rel.get("bar_color", "#a3e635"),
                        "#fde68a",
                    )
                )
            else:
                rows.append((title, 0, "n/d", "#a3e635", "#fde68a"))
        width = max(200, c.winfo_width())
        height = max(60, c.winfo_height())
        # 2.10.0 — rien à redessiner si rien n'a changé (appelé ≈ 4 fois par seconde) ; polices de mesure
        # gardées en cache au lieu d'en créer deux nouvelles à chaque appel
        sig = (width, height, tuple((r[0], round(r[1], 3), r[2], r[3]) for r in rows))
        if getattr(self, "_bargraph_sig", None) == sig:
            return
        self._bargraph_sig = sig
        c.delete("all")
        row_h = height / len(rows)
        fsize = int(max(7, min(10, row_h * 0.55)))
        fonts = getattr(self, "_bargraph_fonts", None)
        if fonts is None or fonts[0] != fsize:
            fonts = (
                fsize,
                tkfont.Font(root=c, family="Segoe UI", size=fsize),
                tkfont.Font(root=c, family="Consolas", size=fsize),
            )
            self._bargraph_fonts = fonts
        _, f_lab, f_val = fonts
        label_w = max(f_lab.measure(r[0]) for r in rows) + 6
        value_w = max(f_val.measure(r[2]) for r in rows) + 8
        bar_x0 = label_w + 4
        bar_w = max(30, width - bar_x0 - value_w - 6)
        bar_h = max(6, min(12, row_h * 0.45))
        for i, (title, ratio, value, color, title_color) in enumerate(rows):
            yc = row_h * (i + 0.5)
            c.create_text(2, yc, text=title, anchor="w", fill=title_color, font=("Segoe UI", fsize))
            c.create_rectangle(
                bar_x0,
                yc - bar_h / 2,
                bar_x0 + bar_w,
                yc + bar_h / 2,
                fill=UITheme.BG_SURFACE,
                outline=UITheme.BORDER,
            )
            if ratio:
                c.create_rectangle(
                    bar_x0, yc - bar_h / 2, bar_x0 + bar_w * ratio, yc + bar_h / 2, fill=color, outline=""
                )
            c.create_text(
                bar_x0 + bar_w + 5,
                yc,
                text=value,
                anchor="w",
                fill=UITheme.TEXT_PRIMARY,
                font=("Consolas", fsize),
            )
        if not getattr(self, "_bargraph_resize_bound", False):
            self._bargraph_resize_bound = True
            c.bind("<Configure>", lambda e: self._draw_three_quality_bargraphs(), add="+")

    def _update_programme(self):
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is None or not hasattr(self, "lbl_sched_current") or not hasattr(self, "lbl_sched_next"):
            self._update_programme_local()
            return
        self._update_programme_slots()
        cur, later = arb.plan_summary()
        self.lbl_sched_current.configure(
            text="▶ " + cur, fg="#fde68a" if arb.active_pipeline == "RTTY" else "#a7f3d0"
        )
        # 2.9.0 — éléments entiers, sur deux lignes au plus, dans la largeur réelle du libellé (avant :
        # retour à la ligne au milieu d'un bulletin, « · 21:30 Bulletin / Atlantique Nord »)
        entries = arb.upcoming_entries(n=6)
        if not entries:
            self.lbl_sched_next.configure(text="Ensuite : " + later)
            return
        self.lbl_sched_next.configure(text=self._fit_programme_text(self.lbl_sched_next, entries))

    def _fit_programme_text(self, label, entries):
        import tkinter.font as tkfont

        from wefax_station.ui.text_fit import fit_items

        try:
            font = tkfont.Font(font=label.cget("font"))
            measure = font.measure
            width = int(float(str(label.cget("wraplength")) or 0)) or label.winfo_width()
        except Exception:
            measure, width = (lambda t: 6 * len(t)), 0
        if width <= 50:
            width = 600
        return fit_items(entries, width - 4, measure, prefix="Ensuite : ", max_lines=2)

    def _update_programme_local(self):
        self._update_programme_slots()
        data = getattr(self, "schedule_data", None)
        if data is None:
            return
        family = self.radio.active_station_family
        try:
            result = next_schedule25(data.get(family, []), datetime.now(timezone.utc))
            if result is None:
                self.lbl_sched_next.configure(text="Prochaine carte : aucune entrée")
                return
            event, seconds = result
            minutes, seconds = divmod(seconds, 60)
            hours, minutes = divmod(minutes, 60)
            when = f"{event[0]//60:02d}:{event[0]%60:02d} UTC"
            delay = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            self.lbl_sched_next.configure(text=f"Suivante : {when} (dans {delay}) · {event[2]}")
        except (ValueError, TypeError, KeyError) as exc:
            self.lbl_sched_next.configure(text="Programme local invalide")
            self.log_event("Programme : " + repr(exc))

    def _update_programme_slots(self):
        if not hasattr(self, "lbl_sched_current"):
            return
        family = self.radio.active_station_family
        data = getattr(self, "schedule_data", BROADCAST_SCHEDULES_UTC)
        current, next_ = schedule_pair(data.get(family, []), datetime.now(timezone.utc))

        def desc(event):
            return (
                f"{event[0]//60:02}:{event[0]%60:02} UTC · {event[2]}" if event else "Aucun programme local"
            )

        self.lbl_sched_current.configure(text="Créneau théorique : " + desc(current))
        self.lbl_sched_next.configure(text="À suivre : " + desc(next_) + " · à confirmer sur la carte")

    def _reload_schedules(self):
        try:
            value = json.loads(self.schedule_path.read_text(encoding="utf-8"))
            candidate = value.get("stations", {})
            for slots in candidate.values():
                for h, m, code, desc in slots:
                    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
                        raise ValueError("Horaire invalide")
            # 2.9.0 — programme DWD intégré prioritaire sur une copie locale d'une autre révision
            rev = value.get("schedule_rev")
            candidate = merge_saved_schedules(candidate, rev)
            if rev != SCHEDULE_REV:
                value["stations"], value["schedule_rev"] = candidate, SCHEDULE_REV
                try:
                    from wefax_station.storage.atomic import atomic_json

                    atomic_json(self.schedule_path, value)
                except Exception:
                    pass
                if not getattr(self, "_schedule_rev_logged", False):
                    self._schedule_rev_logged = True
                    self.log_event(
                        "🗓️ Programmes des cartes DWD et Northwood remplacés par les programmes publiés (NOAA, "
                        "information du 24/07/2024 pour le DWD, du 05/01/2022 pour Northwood) ; les anciennes "
                        "tables locales ne correspondaient pas aux émissions."
                    )
            self.schedule_data = candidate
            self._update_programme()
        except Exception as exc:
            self.log_event("Programme local non recharge : " + repr(exc))
