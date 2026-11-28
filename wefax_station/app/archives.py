"""Archives : signature des cartes, sauvegardes, historique, consultation, logo opérateur."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk
from wefax_station.core.stations import is_rtty_frequency
from wefax_station.storage.atomic import atomic_png
from wefax_station.ui.logo import default_app_logo
from wefax_station.ui.placement import show_over_root
from wefax_station.version import SOFTWARE_BRAND, SOFTWARE_TITLE


_FONT_CACHE = {}


def _footer_font(size):
    """2.10.0 — police du cartouche chargée une fois par taille (avant : relue sur disque à chaque
    rafraîchissement de l'image, plusieurs fois par seconde pendant une réception)."""
    font = _FONT_CACHE.get(size)
    if font is None:
        try:
            font = ImageFont.truetype(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"), size)
        except OSError:
            font = ImageFont.load_default()
        _FONT_CACHE[size] = font
    return font


class ArchivesMixin:
    def _footer_logo(self):
        key = id(self.custom_logo_pil) if self.custom_logo_pil is not None else "défaut"
        cached = getattr(self, "_footer_logo_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        src = self.custom_logo_pil if self.custom_logo_pil is not None else default_app_logo()
        logo = src.copy().convert("RGBA")
        logo.thumbnail((58, 58))
        self._footer_logo_cache = (key, logo)
        return logo

    def _signed(self, array, stamp, reason):
        arb = getattr(self, "hybrid_arbiter", None)
        saved_id = self.radio.active_station_id
        saved_freq = self.radio.actual_freq_khz
        try:
            if arb is not None and is_rtty_frequency(saved_freq):
                self.radio.active_station_id = arb.wefax_return_station
                self.radio.actual_freq_khz = arb.wefax_return_freq_khz
            return self._render_signed_chart(array, stamp, reason)
        finally:
            self.radio.active_station_id = saved_id
            self.radio.actual_freq_khz = saved_freq

    def _render_signed_chart(self, array, stamp, reason):
        image = Image.fromarray(np.asarray(array, dtype=np.uint8)).convert("RGB")
        result = Image.new("RGB", (image.width, image.height + 92), (12, 23, 43))
        result.paste(image, (0, 0))
        d = ImageDraw.Draw(result)
        fontsize = max(11, min(18, int(image.width / 110)))
        font = _footer_font(fontsize)
        logo = self._footer_logo()
        result.paste(logo, (12, image.height + 16), logo)
        x = 80
        station = self.radio.active_station_id
        frequency = self.radio.actual_freq_khz
        if reason == "Correction manuelle" and getattr(self, "current_metadata_path", None):
            try:
                source = json.loads(Path(self.current_metadata_path).read_text(encoding="utf-8"))
                station = source.get("station", station)
                frequency = float(source.get("carrier_khz", frequency))
                if source.get("utc_reception_fin"):
                    stamp = datetime.fromisoformat(source["utc_reception_fin"].replace("Z", "+00:00"))
            except (OSError, ValueError, TypeError):
                pass
        texts = [
            SOFTWARE_BRAND
            + (
                " · Opérateur : " + self.operator_callsign_var.get().strip()
                if self.operator_callsign_var.get().strip()
                else ""
            ),
            f"{station} · {frequency:.1f} kHz · Réception : {stamp.strftime('%Y-%m-%d %H:%M UTC')}",
            "Validité météo : cartouche de la carte · " + reason,
        ]
        for i, text in enumerate(texts):
            d.text((x, image.height + 9 + i * 26), text, font=font, fill=(176, 194, 212))
        return np.asarray(result).copy()

    def _save_stamped_wefax(self):
        if self.pin_completed and self.completed_rgb is not None:
            image = self.completed_rgb
        else:
            body = self.processed_wefax_img[: self.rx_current_line or len(self.processed_wefax_img)]
            if self.rotation_quarters:
                body = np.rot90(body, k=-self.rotation_quarters)
            image = self._signed(body, datetime.now(timezone.utc), "Export manuel")
        path = filedialog.asksaveasfilename(
            initialdir=self.archive_dir, defaultextension=".png", filetypes=[("PNG", "*.png")]
        )
        if path:
            try:
                atomic_png(path, image)
                self.log_event("EXPORT VERIFIE : " + path)
            except Exception as exc:
                messagebox.showerror("Export", str(exc))

    def _view_archive(self, path):
        try:
            p = Path(path)
            stem = p.stem
            for ending in ("_carte", "_decodee", "_traitee"):
                if stem.endswith(ending):
                    stem = stem[: -len(ending)]
                    break
            candidate = p.with_name(stem + ".json")
            self.current_metadata_path = candidate if candidate.exists() else None
            with Image.open(p) as im:
                image = np.asarray(im.convert("RGB")).copy()
            self.completed_rgb = image
            self.completed_raw = None
            if candidate.exists():
                meta = json.loads(candidate.read_text(encoding="utf-8"))
                decoded = next(
                    (p.parent / name for name in meta.get("files", []) if "_decodee" in name), None
                )
                if decoded and decoded.exists():
                    with Image.open(decoded) as im:
                        self.completed_raw = np.asarray(im.convert("L")).copy()
            if self.completed_raw is None and "_decodee" in p.stem:
                with Image.open(p) as im:
                    self.completed_raw = np.asarray(im.convert("L")).copy()
            self.pin_completed = True
            # 2.9.0 — mémorisé : une nouvelle carte en réception ramène automatiquement à la vue en direct
            self.viewing_archived_file = str(p)
            self.lbl_archive_state.configure(text="Consultation : " + p.name)
            # 2.9.2 — bandeau visible sur l'image et retour automatique au direct pendant une réception
            if hasattr(self, "_begin_consultation"):
                self._begin_consultation(p.name)
                self.viewing_archived_file = str(p)
            self._reset_zoom_pan()
            self._refresh_canvas()
        except Exception as exc:
            messagebox.showerror("Archive", str(exc))

    def _history(self):
        self._history_window()
        self._polish_new_toplevels25()

    def _history_window(self):
        win = tk.Toplevel(self.root)
        win.title("Historique des cartes")
        show_over_root(win, self.root)
        tree = ttk.Treeview(win, columns=("name", "size"), show="headings")
        tree.heading("name", text="Carte (double-clic pour consulter)")
        tree.heading("size", text="Ko")
        tree.column("name", width=800)
        tree.column("size", width=90)
        scroll = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        # 2.11.0 — cartes du jour et cartes partielles (sous-dossier) ; les images techniques sont à part
        base = Path(self.archive_dir)
        files = sorted(
            (
                p
                for p in list(base.glob("*.png")) + list((base / "partielles").glob("*.png"))
                if p.name != "logo_personnalise.png" and not p.name.startswith("reception_en_cours")
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for i, p in enumerate(files):
            label = p.name + ("   (partielle)" if p.parent.name == "partielles" else "")
            tree.insert("", "end", iid=str(i), values=(label, round(p.stat().st_size / 1024)))

        def open_selected(event=None):
            selected = tree.selection()
            if selected:
                self._view_archive(files[int(selected[0])])

        tree.bind("<Double-1>", open_selected)
        tk.Button(win, text="Afficher", command=open_selected).pack(side="left", padx=8, pady=6)
        tk.Button(win, text="Dossier", command=self._open_archive).pack(side="left", padx=8)

    def _load_wefax_file(self):
        path = filedialog.askopenfilename(
            initialdir=self.archive_dir, filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tif")]
        )
        if path:
            self._view_archive(path)

    def _open_archive(self):
        if sys.platform == "win32":
            os.startfile(self.archive_dir)
        else:
            subprocess.Popen(["xdg-open", self.archive_dir])

    def _open_csv(self):
        if self.csv_path and self.csv_path.exists():
            self._open_local(self.csv_path)
        else:
            messagebox.showinfo("Journal", "Aucun CSV créé pour cette session.")

    def _open_local(self, path):
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Ouverture", str(exc))

    # ---------------------------------------------------------------- logo
    def _choose_custom_logo(self):
        path = filedialog.askopenfilename(filetypes=[("Logo", "*.png *.jpg *.jpeg *.bmp")])
        if not path:
            return
        try:
            with Image.open(path) as im:
                self.custom_logo_pil = im.convert("RGBA").copy()
            self.custom_logo_path = Path(path).name
            self._refresh_logo_preview()
            self._save_preferences()
            self._refresh_canvas()
        except Exception as exc:
            messagebox.showerror("Logo", str(exc))

    def _remove_logo(self):
        self.custom_logo_pil = None
        self.custom_logo_path = ""
        self._refresh_logo_preview()
        self._save_preferences()
        self._refresh_canvas()

    def _refresh_logo_preview(self):
        image = self.custom_logo_pil if self.custom_logo_pil is not None else default_app_logo()
        image = image.copy()
        image.thumbnail((38, 38))
        self.logo_photo = ImageTk.PhotoImage(image)
        self.logo_preview.configure(
            image=self.logo_photo,
            text="Logo personnel" if self.custom_logo_pil is not None else SOFTWARE_TITLE,
            compound="left",
        )
