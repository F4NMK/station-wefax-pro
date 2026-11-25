"""Traitement d'image : slant, marge, rotation, filtres de restauration, correction non destructive."""

from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image, ImageTk
from wefax_station.storage.atomic import atomic_json, atomic_png
from wefax_station.ui.placement import show_over_root


class ImageToolsMixin:
    def _apply_slant_and_filters(self, slope: float, show_busy=True):
        if self.pin_completed and self.completed_raw is not None:
            self.raw_wefax_img = self.completed_raw.copy()
        self._apply_slant_and_filters_base(slope, show_busy=show_busy)
        if self.pin_completed and self.completed_raw is not None:
            body = (
                np.rot90(self.processed_wefax_img, k=-self.rotation_quarters)
                if self.rotation_quarters
                else self.processed_wefax_img
            )
            self.completed_rgb = self._signed(body, datetime.now(timezone.utc), "Retraitement en direct")
            self._refresh_canvas()
        self._draw_three_quality_bargraphs()

    def _apply_slant_and_filters_base(self, slope: float, show_busy=True):
        if show_busy:
            self.set_busy_state(True, "RESTAURATION & AUTO-CONTRÔLE...")
        try:
            img = self.raw_wefax_img.copy()
            h, w = img.shape
            conf = getattr(self, "rx_confidence_img", None)
            conf = conf[:h].copy() if conf is not None and conf.shape[1] == w and len(conf) >= h else None
            if abs(slope) > 1e-6:
                shifts = np.round(np.arange(h) * slope * 25.0).astype(int)
                for r in range(h):
                    if shifts[r] != 0:
                        img[r, :] = np.roll(img[r, :], -shifts[r])
                        if conf is not None:
                            conf[r, :] = np.roll(conf[r, :], -shifts[r])
            self.processed_wefax_img = self.dsp.restore_image_v1_9(
                img,
                use_fft_notch=self.fft_notch_var.get(),
                use_structure_tensor=self.tensor_var.get(),
                use_adaptive_bin=self.adapt_bin_var.get(),
                conf=conf,
            )
            self._refresh_canvas()
        finally:
            if show_busy:
                self.set_busy_state(False)

    def _apply_full_restoration(self):
        self._apply_slant_and_filters(float(self.sld_slant.get()), show_busy=True)

    def _on_manual_slant_slider(self, val):
        if self.pin_completed:
            self._slant_label()
            return
        self._apply_slant_and_filters(float(val), show_busy=False)
        self._slant_label()

    def _accept_auto_slant(self, pixels_per_line, confidence):
        self.sld_slant.configure(resolution=0.000001)
        if confidence < 55.0 or not np.isfinite(pixels_per_line) or abs(pixels_per_line) > 0.12:
            return
        value = float(pixels_per_line) / 25.0
        self.sld_slant.set(value)
        self.log_event(f"Slant estime : {pixels_per_line:+.5f} px/ligne ; commande={value:+.6f}")
        self._slant_label()

    def _run_auto_margin_and_slant(self):
        if self.pin_completed:
            self._geometry_dialog()
            return
        n = self.rx_current_line if self.rx_current_line >= 40 else self.raw_wefax_img.shape[0]
        margin, slope, confidence = self.dsp.auto_detect_margin_and_slant(self.raw_wefax_img[:n])
        self.last_margin_confidence_pct = confidence
        if confidence < 55.0:
            self.log_event(
                f"Geometrie automatique refusee : score {confidence:.1f}/100 ; utiliser la correction manuelle"
            )
            return
        if margin > 4:
            self.raw_wefax_img = np.roll(self.raw_wefax_img, -margin, axis=1)
            self._roll_confidence(-margin)
            self.processed_wefax_img = np.roll(self.processed_wefax_img, -margin, axis=1)
            self.line_phase_offset_px = (self.line_phase_offset_px + margin) % self.raw_wefax_img.shape[1]
        self.auto_margin_locked_for_chart = True
        self._accept_auto_slant(slope, confidence)
        self._apply_full_restoration()
        self._slant_label()

    def _slant_label(self):
        if hasattr(self, "lbl_slant_state"):
            self.lbl_slant_state.configure(
                text=f"Slant : {float(self.sld_slant.get())*25:+.5f} px/ligne · marge {self.line_phase_offset_px}px · rotation {self.rotation_quarters*90}°"
            )

    def _rotate(self, steps):
        if self.pin_completed:
            self._geometry_dialog(initial_rotation=steps)
            return
        self.rotation_quarters = (self.rotation_quarters + steps) % 4
        self._slant_label()
        self._refresh_canvas()

    def _geometry_dialog(self, *args, **kwargs):
        self._geometry_window(*args, **kwargs)
        self._polish_new_toplevels25()

    def _geometry_window(self, initial_rotation=0):
        if self.pin_completed:
            if self.completed_raw is None:
                messagebox.showinfo(
                    "Géométrie",
                    "Ouvrir l'image décodée associée pour éviter de tourner ou déformer le pied de page.",
                )
                return
            original = self.completed_raw.copy()
        else:
            original = self.raw_wefax_img[: self.rx_current_line or len(self.raw_wefax_img)].copy()
        win = tk.Toplevel(self.root)
        win.title("Marge / slant / orientation — copie non destructive")
        show_over_root(win, self.root)
        controls = tk.Frame(win)
        controls.pack(fill="x", padx=12, pady=8)
        margin = tk.IntVar(value=0)
        slant = tk.DoubleVar(value=0)
        rotation = tk.IntVar(value=initial_rotation % 4)
        for title, var, lo, hi, res in (
            ("Marge horizontale (px)", margin, -original.shape[1], original.shape[1], 1),
            ("Slant (px / ligne)", slant, -0.15, 0.15, 0.0005),
        ):
            tk.Label(controls, text=title).pack(anchor="w")
            tk.Scale(
                controls, variable=var, from_=lo, to=hi, resolution=res, orient="horizontal", length=750
            ).pack(fill="x")
        line = tk.Frame(controls)
        line.pack(fill="x")
        for label, val in (("0°", 0), ("90° droite", 1), ("180°", 2), ("90° gauche", 3)):
            tk.Radiobutton(line, text=label, value=val, variable=rotation).pack(side="left", padx=10)
        preview = tk.Label(win, bg="#091322")
        preview.pack(fill="both", expand=True, padx=12, pady=8)

        def corrected():
            work = original.copy()
            for i in range(len(work)):
                work[i] = np.roll(work[i], -int(margin.get() + round(i * slant.get())))
            return np.rot90(work, k=-rotation.get())

        def show():
            img = Image.fromarray(corrected())
            img.thumbnail((850, 450))
            photo = ImageTk.PhotoImage(img)
            preview.configure(image=photo)
            preview.image = photo

        def save():
            path = filedialog.asksaveasfilename(
                parent=win,
                initialdir=self.archive_dir,
                defaultextension=".png",
                initialfile="carte_corrigee_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ".png",
                filetypes=[("PNG", "*.png")],
            )
            if not path:
                return
            try:
                image = self._signed(corrected(), datetime.now(timezone.utc), "Correction manuelle")
                atomic_png(path, image)
                atomic_json(
                    str(Path(path).with_suffix(".json")),
                    {
                        "manual_geometry": True,
                        "margin_px": margin.get(),
                        "slant_px_per_line": slant.get(),
                        "rotation_quarters": rotation.get(),
                        "source_metadata": str(self.current_metadata_path or ""),
                        "annotations": {},
                    },
                )
                self.completed_rgb = image
                self.pin_completed = True
                self._refresh_canvas()
                self.log_event("CORRECTION VERIFIEE : " + path)
            except Exception as exc:
                messagebox.showerror("Correction", str(exc))

        buttons = tk.Frame(win)
        buttons.pack(fill="x", padx=12, pady=8)

        def estimate():
            mx, slope, confidence = self.dsp.auto_detect_margin_and_slant(original)
            if confidence < 55.0:
                messagebox.showinfo(
                    "Géométrie",
                    "Estimation insuffisamment certaine : régler manuellement. Score interne "
                    + f"{confidence:.1f}/100",
                )
                return
            margin.set(mx)
            slant.set(slope)
            show()

        tk.Button(buttons, text="Estimer marge / slant", command=estimate).pack(side="left", padx=4)
        tk.Button(buttons, text="Prévisualiser", command=show).pack(side="left", padx=4)
        tk.Button(buttons, text="Enregistrer une copie", command=save).pack(side="left", padx=4)
        show()
        self._install_help(win)

    def _toggle_fft_filter(self):
        self.fft_notch_var.set(not self.fft_notch_var.get())
        self.btn_fft2d.set_state(self.fft_notch_var.get())
        if not self.fft_notch_var.get():
            self._warn_suboptimal_user_action(
                "Filtre Anti-Stries & FFT 2D désactivé : les fines lignes parasites horizontales resteront visibles."
            )
        self._apply_full_restoration()

    def _toggle_tensor_filter(self):
        self.tensor_var.set(not self.tensor_var.get())
        self.btn_tensor.set_state(self.tensor_var.get())
        if not self.tensor_var.get():
            self._warn_suboptimal_user_action(
                "Blanchiment du fond papier désactivé : le contraste documentaire des isobares sera moins net."
            )
        self._apply_full_restoration()

    def _toggle_bin_filter(self):
        self.adapt_bin_var.set(not self.adapt_bin_var.get())
        self.btn_bin.set_state(self.adapt_bin_var.get())
        if self.adapt_bin_var.get() and self.current_snr_db < 10.0:
            self._warn_suboptimal_user_action(
                "Seuillage Binaire Fort activé sur un signal bruité (<10 dB) : risque de granulosité noire !"
            )
        self._apply_full_restoration()

    def _toggle_margin_tool_mode(self):
        self.canvas_tool_mode = "NONE" if self.canvas_tool_mode == "MARGIN" else "MARGIN"
        self.btn_mode_margin.set_state(self.canvas_tool_mode == "MARGIN")
        self.btn_move_qth.set_state(False)
        self.btn_roi_mode.set_state(False)
        self.pending_margin_x = None
        self._refresh_canvas()
