"""Affichage de la carte : rendu, pied de page, zoom / déplacement, repère QTH, zone d'analyse."""

import math
from datetime import datetime, timezone
from tkinter import messagebox
import numpy as np
import cv2
from PIL import Image, ImageTk
from wefax_station.version import SOFTWARE_BRAND
from wefax_station.ui.theme import UITheme


class CanvasViewMixin:
    # ----------------------------------------------------------- rendu
    def _refresh_canvas(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 20 or ch < 20:
            return
        vis = self._compose_display_image_with_footer()
        h, w = vis.shape[:2]
        self._last_vis_hw = (h, w)
        eff_scale = min(cw / w, ch / h) * self.zoom_scale
        disp_w = max(10, int(round(w * eff_scale)))
        disp_h = max(10, int(round(h * eff_scale)))

        interp = cv2.INTER_AREA if eff_scale < 1.0 else cv2.INTER_LINEAR
        resized = cv2.resize(vis, (disp_w, disp_h), interpolation=interp)

        self.tk_img_ref = ImageTk.PhotoImage(Image.fromarray(resized))
        self.canvas.delete("all")
        self.canvas.create_image(
            cw / 2.0 + self.pan_offset_x, ch / 2.0 + self.pan_offset_y, image=self.tk_img_ref, anchor="center"
        )

    def _compose_display_image_with_footer(self):
        if self.pin_completed and self.completed_rgb is not None:
            return self.completed_rgb.copy()
        image = self._compose_display_image_base()
        footer = int(round(56 * max(1.0, image.shape[1] / 1400.0)))
        body = image[:-footer]
        if self.rotation_quarters:
            body = np.rot90(body, k=-self.rotation_quarters)
        return self._signed(body, datetime.now(timezone.utc), "Réception en direct")

    def _compose_display_image_base(self) -> np.ndarray:
        raw_g = self.raw_wefax_img
        proc_g = self.processed_wefax_img
        h, w = proc_g.shape[:2]
        if raw_g.shape[:2] != (h, w):
            raw_g = cv2.resize(raw_g, (w, h), interpolation=cv2.INTER_NEAREST)

        sf = max(1.0, w / 1400.0)
        th_line = max(2, int(round(2.5 * sf)))

        if self.display_mode == "RAW":
            vis = cv2.cvtColor(raw_g, cv2.COLOR_GRAY2RGB)
            # 2.8.3 : le cartouche « MODE : IMAGE BRUTE » n'est plus dessiné sur la carte (il masquait le titre
            # de la carte, en haut à gauche) ; le mode est déjà indiqué par les boutons Traitée / Décodée / Comparer.

        elif self.display_mode == "SPLIT":
            split_x = max(20, min(w - 20, int(round(w * self.split_ratio))))
            comp = np.zeros_like(proc_g)
            comp[:, :split_x] = raw_g[:, :split_x]
            comp[:, split_x:] = proc_g[:, split_x:]
            vis = cv2.cvtColor(comp, cv2.COLOR_GRAY2RGB)

            cv2.line(vis, (split_x, 0), (split_x, h - 1), (16, 185, 129), max(3, int(3 * sf)))
            cv2.rectangle(
                vis,
                (max(0, split_x - int(220 * sf)), int(14 * sf)),
                (split_x - int(8 * sf), int(52 * sf)),
                (15, 23, 42),
                -1,
            )
            cv2.putText(
                vis,
                "AVANT (BRUTE)",
                (max(8, split_x - int(200 * sf)), int(40 * sf)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62 * sf,
                (248, 113, 113),
                th_line,
            )
            cv2.rectangle(
                vis,
                (min(w - 10, split_x + int(8 * sf)), int(14 * sf)),
                (min(w - 4, split_x + int(250 * sf)), int(52 * sf)),
                (15, 23, 42),
                -1,
            )
            cv2.putText(
                vis,
                "APRES (RETRAITEE)",
                (min(w - int(240 * sf), split_x + int(16 * sf)), int(40 * sf)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62 * sf,
                (52, 211, 153),
                th_line,
            )
        else:
            vis = cv2.cvtColor(proc_g, cv2.COLOR_GRAY2RGB)

        if self.rx_decoding_active and 0 < self.rx_current_line < h:
            ry = self.rx_current_line
            cv2.line(vis, (0, ry), (w - 1, ry), (0, 255, 210), max(3, int(3 * sf)))
            # 2.8.3 : étiquette placée SOUS la ligne de tracé (papier encore vierge) et non plus sur les
            # dernières lignes reçues, qu'elle masquait.
            ly = min(h - int(40 * sf), ry + int(8 * sf)) if ry + int(44 * sf) < h else ry - int(38 * sf)
            cv2.rectangle(
                vis,
                (int(20 * sf), max(4, ly)),
                (int(440 * sf), max(30, ly + int(30 * sf))),
                (15, 23, 42),
                -1,
            )
            cv2.putText(
                vis,
                f"DECODAGE WEFAX EN DIRECT : L.{ry} ({'TRACE' if self.current_wefax_stage == 'IMAGE' else self.current_wefax_stage})",
                (int(28 * sf), max(22, ly + int(22 * sf))),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.54 * sf,
                (0, 255, 210),
                th_line,
            )

        if self.pending_margin_x is not None:
            mx = max(0, min(w - 1, int(self.pending_margin_x)))
            cv2.line(vis, (mx, 0), (mx, h - 1), (255, 60, 60), max(3, int(3 * sf)))
            cv2.putText(
                vis,
                f"MARGE X={mx} (Clic-Droit = Valider)",
                (max(10, mx - int(170 * sf)), int(80 * sf)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.68 * sf,
                (255, 60, 60),
                th_line,
            )

        # zone d'analyse affichée seulement quand elle sert (outil ZONE actif ou fenêtre météo ouverte)
        if self.weather_roi_box is not None and (
            self.canvas_tool_mode in ("ROI", "GEOREF") or self._is_weather_or_settings_dialog_open()
        ):
            x0, y0, x1, y1 = self.weather_roi_box
            cv2.rectangle(vis, (x0, y0), (x1, y1), (56, 189, 248), th_line)
            cv2.rectangle(vis, (x0, max(0, y0 - int(28 * sf))), (x0 + int(430 * sf), y0), (15, 23, 42), -1)
            cv2.putText(
                vis,
                self._zone_box_caption() if hasattr(self, "_zone_box_caption") else "ZONE MANUELLE",
                (x0 + int(6 * sf), max(int(18 * sf), y0 - int(6 * sf))),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52 * sf,
                (56, 189, 248),
                th_line,
            )

        # points de repérage en cours de saisie
        for k, (gx, gy, glat, glon) in enumerate(getattr(self, "_georef_pts", []) or []):
            cv2.drawMarker(
                vis, (int(gx), int(gy)), (250, 204, 21), cv2.MARKER_CROSS, int(30 * sf), th_line + 1
            )
            cv2.putText(
                vis,
                f"{k + 1}: {glat:.1f} {glon:.1f}",
                (int(gx) + int(8 * sf), int(gy) - int(8 * sf)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6 * sf,
                (250, 204, 21),
                th_line,
            )

        if self.dept_overlay_var.get():
            cx_se = int(round(w * self.qth_rel_pos[0]))
            cy_se = int(round(h * self.qth_rel_pos[1]))
            is_moving = self.canvas_tool_mode == "MOVE_QTH" or self.dragging_target == "QTH"
            col_qth = (250, 204, 21) if is_moving else (16, 185, 129)

            rad = int(round(34 * sf))
            cv2.circle(vis, (cx_se, cy_se), rad, col_qth, th_line, cv2.LINE_AA)
            cv2.circle(vis, (cx_se, cy_se), max(4, int(5 * sf)), col_qth, -1, cv2.LINE_AA)
            cv2.drawMarker(vis, (cx_se, cy_se), col_qth, cv2.MARKER_CROSS, int(24 * sf), th_line)

            lbl_qth = "Position manuelle non validee"
            box_w = int(365 * sf)
            box_h = int(26 * sf)
            bx0 = min(w - box_w - 5, cx_se + int(12 * sf))
            by0 = max(5, cy_se - box_h - int(4 * sf))
            cv2.rectangle(vis, (bx0, by0), (bx0 + box_w, by0 + box_h), (15, 23, 42), -1)
            cv2.rectangle(vis, (bx0, by0), (bx0 + box_w, by0 + box_h), col_qth, max(1, int(sf)))
            cv2.putText(
                vis,
                lbl_qth,
                (bx0 + int(6 * sf), by0 + int(19 * sf)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50 * sf,
                col_qth,
                th_line,
                cv2.LINE_AA,
            )

        footer_h = int(round(56 * sf))
        footer = np.full((footer_h, w, 3), (15, 23, 42), dtype=np.uint8)
        cv2.line(footer, (0, 0), (w, 0), (56, 189, 248), max(2, int(2 * sf)))

        text_x_start = int(16 * sf)
        if self.custom_logo_pil is not None:
            try:
                logo_rgb = np.array(self.custom_logo_pil.convert("RGB"))
                lh, lw = logo_rgb.shape[:2]
                target_lh = int(round(42 * sf))
                target_lw = max(24, int(round(lw * (target_lh / max(1, lh)))))
                logo_res = cv2.resize(logo_rgb, (target_lw, target_lh), interpolation=cv2.INTER_AREA)
                y_off = (footer_h - target_lh) // 2
                x_off = int(14 * sf)
                footer[y_off : y_off + target_lh, x_off : x_off + target_lw] = logo_res
                text_x_start = x_off + target_lw + int(14 * sf)
            except Exception:
                pass

        op_call = self.operator_callsign_var.get().strip().upper()
        id_str = f"{SOFTWARE_BRAND}  |  Operateur : {op_call}" if op_call else SOFTWARE_BRAND
        utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        right_str = (
            f"{self.radio.active_station_id} ({self.radio.actual_freq_khz:.1f} kHz {self.radio.actual_filter_str}) | "
            f"SNR: {float(getattr(self, 'raw_snr_db', self.current_snr_db)):+.1f}dB | {utc_str} | Meteo: non validee"
        )

        cv2.putText(
            footer,
            id_str,
            (text_x_start, int(36 * sf)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68 * sf,
            (56, 189, 248),
            th_line,
            cv2.LINE_AA,
        )
        cv2.putText(
            footer,
            right_str,
            (max(text_x_start + int(370 * sf), w - int(740 * sf)), int(36 * sf)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52 * sf,
            (226, 232, 240),
            max(1, int(round(1.5 * sf))),
            cv2.LINE_AA,
        )

        return np.vstack([vis, footer])

    def _get_effective_scale_and_origin(self):
        # mêmes dimensions que l'image réellement affichée (corps + pied de page)
        if self.pin_completed and self.completed_rgb is not None:
            total_h, w = self.completed_rgb.shape[:2]
            body = getattr(self, "completed_raw", None)
            h = body.shape[0] if body is not None and body.shape[0] < total_h else max(1, total_h - 92)
        else:
            h, w = self.processed_wefax_img.shape[:2]
            if self.rotation_quarters % 2:
                h, w = w, h
            last = getattr(self, "_last_vis_hw", None)
            total_h = last[0] if last is not None and last[1] == w and last[0] > h else h + 92
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        scale = min(cw / w, ch / total_h) * self.zoom_scale
        return (
            scale,
            (cw - w * scale) / 2 + self.pan_offset_x,
            (ch - total_h * scale) / 2 + self.pan_offset_y,
            w,
            h,
        )

    def _canvas_to_image_coords(self, cx: int, cy: int) -> tuple:
        eff_scale, ox, oy, w, h = self._get_effective_scale_and_origin()
        ix = max(0, min(w - 1, int(round((cx - ox) / eff_scale))))
        iy = max(0, min(h - 1, int(round((cy - oy) / eff_scale))))
        return ix, iy

    def _image_to_canvas_coords(self, ix: int, iy: int) -> tuple:
        eff_scale, ox, oy, _, _ = self._get_effective_scale_and_origin()
        return ox + ix * eff_scale, oy + iy * eff_scale

    def _is_weather_or_settings_dialog_open(self) -> bool:
        for attr_name in ("weather_window", "meteo_window", "settings_window", "analysis_window"):
            w = getattr(self, attr_name, None)
            try:
                if w is not None and w.winfo_exists() and w.winfo_viewable():
                    return True
            except Exception:
                pass
        return False

    def _hide_main_canvas_roi_overlays(self):
        if self._is_weather_or_settings_dialog_open():
            return
        cv = getattr(self, "canvas", None)
        if cv is None:
            return
        try:
            for item_id in list(cv.find_all()):
                itype = cv.type(item_id)
                if itype == "image":
                    continue
                if itype in ("rectangle", "text", "line"):
                    cv.delete(item_id)
        except Exception:
            pass

    def _show_completed(self):
        if self.completed_rgb is None:
            messagebox.showinfo("Dernière carte", "Aucune carte en mémoire ; ouvrir l'historique.")
            return
        self.pin_completed = True
        # 2.9.2 — « Dernière carte » est aussi une consultation : bandeau visible et retour automatique au
        # direct (le 19/11 vers 07:18, la carte en réception est restée masquée sans aucune indication)
        self._begin_consultation("dernière carte reçue")
        self._reset_zoom_pan()
        self._refresh_canvas()

    def _show_live(self):
        self.pin_completed = False
        self.viewing_archived_file = None
        self._live_return_pending = False
        self._update_consult_banner(force=True)
        self._reset_zoom_pan()
        self._refresh_canvas()

    # ------------------------------------------------------------------ 2.9.2 consultation pendant une réception
    CONSULT_IDLE_RETURN_S = 90

    def _live_chart_in_progress(self):
        return (
            bool(getattr(self, "rx_image_armed", False))
            and int(getattr(self, "rx_current_line", 0) or 0) >= 5
            and not getattr(self, "waiting_after_stop", False)
        )

    def _begin_consultation(self, name):
        import time as _time

        self.viewing_archived_file = str(name)
        self._consult_touch_mono = _time.monotonic()
        cv = getattr(self, "canvas", None)
        if cv is not None and not getattr(self, "_consult_binds_done", False):
            try:
                for ev in ("<ButtonPress>", "<MouseWheel>", "<B1-Motion>"):
                    cv.bind(ev, self._touch_consultation, add="+")
                self._consult_binds_done = True
            except Exception:
                pass
        self._update_consult_banner(force=True)

    def _touch_consultation(self, _event=None):
        import time as _time

        self._consult_touch_mono = _time.monotonic()

    def _consultation_idle_check(self, mono_now=None):
        """Appelée par la boucle de réception : après 90 s sans action sur l'image consultée, si une carte
        est en cours de réception, retour automatique à la vue en direct. Renvoie True si retour."""
        import time as _time

        if not getattr(self, "viewing_archived_file", None) or not getattr(self, "pin_completed", False):
            self._update_consult_banner()
            return False
        now = _time.monotonic() if mono_now is None else mono_now
        idle = now - float(getattr(self, "_consult_touch_mono", now) or now)
        if self._live_chart_in_progress() and idle >= self.CONSULT_IDLE_RETURN_S:
            self.log_event(
                f"📡 Consultation sans action depuis {int(idle)} s pendant une réception (L.{int(getattr(self, 'rx_current_line', 0))}) : "
                "retour automatique à la vue en direct."
            )
            self._return_to_live_rx_view(log=False)
            return True
        self._update_consult_banner(idle_s=idle)
        return False

    def _update_consult_banner(self, idle_s=None, force=False):
        """Bandeau posé sur l'image : « Consultation : … » et bouton « Revenir au direct ». Visible dès qu'une
        image autre que la réception en direct est affichée (l'étiquette d'état est masquée depuis la 2.8)."""
        import tkinter as tk

        cv = getattr(self, "canvas", None)
        if cv is None:
            return
        name = getattr(self, "viewing_archived_file", None) if getattr(self, "pin_completed", False) else None
        bar = getattr(self, "_consult_banner", None)
        if not name:
            if bar is not None:
                try:
                    bar.place_forget()
                except Exception:
                    pass
            return
        try:
            if bar is None:
                bar = tk.Frame(cv.master, bg="#7c2d12")
                # 2.10.0 — bouton placé d'abord : il reste entier quelle que soit la longueur du texte
                # (le 19/11, un chemin complet repoussait « Revenir au direct » hors de la fenêtre)
                tk.Button(bar, text="⟲ Revenir au direct", command=lambda: self._return_to_live_rx_view(log=False),
                          bg="#fdba74", fg="#1c1917", relief="flat", padx=8,
                          font=("Segoe UI", 9, "bold")).pack(side="right", padx=4, pady=2)
                self._consult_banner_lbl = tk.Label(bar, text="", bg="#7c2d12", fg="#ffedd5", anchor="w",
                                                    font=("Segoe UI", 9, "bold"), width=1)
                self._consult_banner_lbl.pack(side="left", fill="x", expand=True, padx=6, pady=2)
                self._consult_banner = bar
            if self._live_chart_in_progress():
                left = None if idle_s is None else max(0, int(self.CONSULT_IDLE_RETURN_S - idle_s))
                extra = (f" — carte en réception (L.{int(getattr(self, 'rx_current_line', 0))}), retour au direct"
                         + (f" dans {left} s sans action" if left is not None else " après 90 s sans action"))
            else:
                extra = " — la réception continue en arrière-plan"
            shown = str(name)
            if ("/" in shown or "\\" in shown) and not shown.startswith("Carte Internet"):
                shown = shown.replace("\\", "/").rsplit("/", 1)[-1]  # nom du fichier seulement
            self._consult_banner_lbl.configure(text=f"👁 Consultation : {shown}{extra}")
            bar.place(in_=cv, relx=0, rely=0, relwidth=1)
            bar.lift()
        except Exception:
            pass

    def _return_to_live_rx_view(self, log=True):
        """2.9.0 — une carte archivée était affichée et une nouvelle carte arrive : retour à la vue en direct.

        (Méthode appelée par la boucle de réception depuis la 2.8.x mais absente du code : la branche était
        inactive, faute de mémoriser l'archive consultée.)"""
        name = getattr(self, "viewing_archived_file", None)
        self.viewing_archived_file = None
        self._live_return_pending = False
        if hasattr(self, "lbl_archive_state"):
            try:
                self.lbl_archive_state.configure(text="Réception en direct", fg=UITheme.TEXT_MUTED)
            except Exception:
                pass
        self._show_live()
        if name and log:
            self.log_event("📡 Nouvelle carte en réception : retour automatique à la vue en direct.")

    def _on_display_mode_changed(self, new_mode: str):
        self.display_mode = new_mode
        if new_mode in ("PROCESSED", "SPLIT"):
            self._apply_full_restoration()
        else:
            self._refresh_canvas()

    def _on_split_slider_changed(self, val):
        self.split_ratio = float(val) / 100.0
        if self.display_mode != "SPLIT":
            self.grp_display_mode.set_value("SPLIT", trigger_callback=True)
        else:
            self._refresh_canvas()

    # -------------------------------------------------------------- souris
    def _on_left_down(self, event):
        if getattr(self, "canvas_tool_mode", "") == "GEOREF" and not self.rotation_quarters:
            self._georef_click(event)  # repérage possible aussi sur une carte archivée
            return
        if self.pin_completed or self.rotation_quarters:
            self.lbl_status.configure(
                text="Image archivée ou tournée : cliquez sur Cartes -> Réception directe ou Corriger marge / slant."
            )
            return
        self._on_left_down_base(event)

    def _on_left_down_base(self, event):
        self.left_btn_down = True
        if self.right_btn_down:
            self.pan_start_mouse = (event.x, event.y)
            self.pan_start_offset = (self.pan_offset_x, self.pan_offset_y)
            return

        ix, iy = self._canvas_to_image_coords(event.x, event.y)
        h, w = self.processed_wefax_img.shape[:2]
        qx, qy = int(w * self.qth_rel_pos[0]), int(h * self.qth_rel_pos[1])
        q_screen_x, q_screen_y = self._image_to_canvas_coords(qx, qy)

        if self.canvas_tool_mode == "MOVE_QTH":
            self._move_qth_and_roi_to(ix, iy)
            self.lbl_status.config(
                text=f"📍 Repère 06/83 placé en X={ix}, Y={iy} — CLIC DROIT pour verrouiller et analyser.",
                fg="#38bdf8",
            )
            self._refresh_canvas()
            return

        if self.canvas_tool_mode == "MARGIN":
            self.pending_margin_x = ix
            self.lbl_status.config(
                text=f"📏 Marge placée à X={ix} px — CLIC DROIT pour valider.", fg="#38bdf8"
            )
            self._refresh_canvas()
            return

        if self.canvas_tool_mode == "ROI":
            self.roi_drag_start = (ix, iy)
            self.weather_roi_box = (ix, iy, ix + 20, iy + 20)
            self._refresh_canvas()
            return

        screen_dist = math.hypot(event.x - q_screen_x, event.y - q_screen_y)
        if self.dept_overlay_var.get() and screen_dist <= 42:
            self.dragging_target = "QTH"
            self._move_qth_and_roi_to(ix, iy)
            self.canvas.config(cursor="hand2")
            self.lbl_status.config(
                text="📍 Glissez la mire verte 06/83 jusqu'à votre QTH puis relâchez.", fg="#38bdf8"
            )
            self._refresh_canvas()
            return

        self.pan_start_mouse = (event.x, event.y)
        self.pan_start_offset = (self.pan_offset_x, self.pan_offset_y)

    def _on_left_up(self, event):
        self.left_btn_down = False
        if self.canvas_tool_mode == "ROI" and self.roi_drag_start and self.weather_roi_box is not None:
            # la case dessinée devient la zone mémorisée (centre + demi-largeur), reprise au prochain lancement
            x0, y0, x1, y1 = self.weather_roi_box
            h, w = self.processed_wefax_img.shape[:2]
            self.qth_rel_pos = [
                max(0.02, min(0.98, (x0 + x1) / 2.0 / w)),
                max(0.02, min(0.98, (y0 + y1) / 2.0 / h)),
            ]
            self.roi_rel_radius = max(0.01, (x1 - x0) / 2.0 / w)
        self.roi_drag_start = None
        if self.dragging_target == "QTH":
            self.dragging_target = None
            self.canvas.config(cursor="fleur")
            self._refresh_canvas()
            self._run_expert_weather_analysis()

    def _on_right_down(self, event):
        self.right_btn_down = True
        if self.left_btn_down:
            self.pan_start_mouse = (event.x, event.y)
            self.pan_start_offset = (self.pan_offset_x, self.pan_offset_y)
            return

        if self.canvas_tool_mode == "MARGIN" and self.pending_margin_x is not None:
            self._validate_margin_shift(self.pending_margin_x)
        elif self.canvas_tool_mode == "MOVE_QTH":
            self.canvas_tool_mode = "NONE"
            self.btn_move_qth.set_state(False)
            self.canvas.config(cursor="fleur")
            self._run_expert_weather_analysis()
        elif self.canvas_tool_mode == "ROI" and self.weather_roi_box is not None:
            self.canvas_tool_mode = "NONE"
            self.btn_roi_mode.set_state(False)
            self.canvas.config(cursor="fleur")
            self._run_expert_weather_analysis()

    def _on_right_up(self, event):
        self.right_btn_down = False

    def _on_middle_down(self, event):
        self.pan_start_mouse = (event.x, event.y)
        self.pan_start_offset = (self.pan_offset_x, self.pan_offset_y)

    def _on_middle_drag(self, event):
        if self.pan_start_mouse and self.pan_start_offset:
            self.pan_offset_x = self.pan_start_offset[0] + (event.x - self.pan_start_mouse[0])
            self.pan_offset_y = self.pan_start_offset[1] + (event.y - self.pan_start_mouse[1])
            self._refresh_canvas()

    def _on_middle_up(self, event):
        self.pan_start_mouse = None

    def _on_mouse_wheel(self, event):
        self._zoom_at_point(event.x, event.y, 1.18 if event.delta > 0 else (1.0 / 1.18))

    def _on_double_click_zoom(self, event):
        if self.zoom_scale < 1.8:
            self._zoom_at_point(event.x, event.y, 2.5 / self.zoom_scale)
        else:
            self._reset_zoom_pan()

    def _on_canvas_motion(self, event):
        ix, iy = self._canvas_to_image_coords(event.x, event.y)
        self.lbl_mouse_coords.config(text=f"Zoom: {int(self.zoom_scale*100)}% | X: {ix}, Y: {iy}")

        if self.left_btn_down and self.right_btn_down and self.pan_start_mouse:
            self.pan_offset_x = self.pan_start_offset[0] + (event.x - self.pan_start_mouse[0])
            self.pan_offset_y = self.pan_start_offset[1] + (event.y - self.pan_start_mouse[1])
            self._refresh_canvas()
            return

        if self.left_btn_down and (self.dragging_target == "QTH" or self.canvas_tool_mode == "MOVE_QTH"):
            self._move_qth_and_roi_to(ix, iy)
            self._refresh_canvas()
            return

        if self.left_btn_down and self.canvas_tool_mode == "MARGIN":
            self.pending_margin_x = ix
            self._refresh_canvas()
        elif self.left_btn_down and self.canvas_tool_mode == "ROI" and self.roi_drag_start:
            x0, y0 = self.roi_drag_start
            self.weather_roi_box = (min(x0, ix), min(y0, iy), max(x0, ix), max(y0, iy))
            self._refresh_canvas()
        elif self.left_btn_down and self.canvas_tool_mode == "NONE" and self.pan_start_mouse:
            self.pan_offset_x = self.pan_start_offset[0] + (event.x - self.pan_start_mouse[0])
            self.pan_offset_y = self.pan_start_offset[1] + (event.y - self.pan_start_mouse[1])
            self._refresh_canvas()

    def _zoom_at_point(self, cx: int, cy: int, factor: float):
        new_z = max(0.35, min(8.0, self.zoom_scale * factor))
        act = new_z / self.zoom_scale
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        self.pan_offset_x -= (cx - (cw / 2.0 + self.pan_offset_x)) * (act - 1.0)
        self.pan_offset_y -= (cy - (ch / 2.0 + self.pan_offset_y)) * (act - 1.0)
        self.zoom_scale = new_z
        self._refresh_canvas()

    def _reset_zoom_pan(self):
        self.zoom_scale = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self._refresh_canvas()

    # ------------------------------------------------------- QTH et ROI
    def _recompute_roi_from_qth(self):
        ih, iw = self.raw_wefax_img.shape[:2]
        qx, qy = int(iw * self.qth_rel_pos[0]), int(ih * self.qth_rel_pos[1])
        hw = hh = int(iw * self.roi_rel_radius)  # case carrée en pixels (même échelle que le repérage)
        self.weather_roi_box = (max(0, qx - hw), max(0, qy - hh), min(iw - 1, qx + hw), min(ih - 1, qy + hh))

    def _move_qth_and_roi_to(self, ix: int, iy: int):
        h, w = self.processed_wefax_img.shape[:2]
        self.qth_rel_pos = [max(0.02, min(0.98, ix / float(w))), max(0.02, min(0.98, iy / float(h)))]
        self._recompute_roi_from_qth()

    def _nudge_qth_position(self, dx_rel: float, dy_rel: float):
        self.qth_rel_pos[0] = max(0.02, min(0.98, self.qth_rel_pos[0] + dx_rel))
        self.qth_rel_pos[1] = max(0.02, min(0.98, self.qth_rel_pos[1] + dy_rel))
        self._recompute_roi_from_qth()
        self._refresh_canvas()
        self._run_expert_weather_analysis()

    def _on_roi_size_slider_changed(self, val):
        self.roi_rel_radius = float(val) / 100.0
        self._recompute_roi_from_qth()
        self._refresh_canvas()

    def _toggle_move_qth_mode(self):
        self.canvas_tool_mode = "NONE" if self.canvas_tool_mode == "MOVE_QTH" else "MOVE_QTH"
        self.btn_move_qth.set_state(self.canvas_tool_mode == "MOVE_QTH")
        self.btn_mode_margin.set_state(False)
        self.btn_roi_mode.set_state(False)
        self.canvas.config(cursor="crosshair" if self.canvas_tool_mode == "MOVE_QTH" else "fleur")
        self._refresh_canvas()

    def _toggle_roi_mode(self):
        self.canvas_tool_mode = "NONE" if self.canvas_tool_mode == "ROI" else "ROI"
        self.btn_roi_mode.set_state(self.canvas_tool_mode == "ROI")
        self.btn_mode_margin.set_state(False)
        self.btn_move_qth.set_state(False)

    def _toggle_dept_overlay(self):
        self.dept_overlay_var.set(not self.dept_overlay_var.get())
        self.btn_overlay_dept.set_state(self.dept_overlay_var.get())
        self._refresh_canvas()
