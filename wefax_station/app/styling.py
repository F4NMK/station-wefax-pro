"""Styles ttk, thème sombre appliqué aux widgets et fenêtres secondaires."""

import re
import tkinter as tk
from tkinter import ttk
from wefax_station.ui.theme import UITheme
from wefax_station.ui.widgets import SegmentedRadioGroup, SwitchCheckButton


class StylingMixin:
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        row_h = 21 if self.compact_screen else 24
        style.configure(
            "Treeview",
            background=UITheme.BG_ROOT,
            foreground=UITheme.TEXT_PRIMARY,
            fieldbackground=UITheme.BG_ROOT,
            borderwidth=1,
            relief="flat",
            rowheight=row_h,
            font=("Consolas", 9),
        )
        style.configure(
            "Treeview.Heading",
            background=UITheme.BG_SURFACE,
            foreground=UITheme.TEXT_PRIMARY,
            borderwidth=1,
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padding=(6, 4),
        )
        style.map("Treeview", background=[("selected", UITheme.ACCENT)], foreground=[("selected", "#ffffff")])
        style.map("Treeview.Heading", background=[("active", "#2d3b4e")])
        style.configure(
            "TCombobox",
            fieldbackground=UITheme.BG_SURFACE,
            background=UITheme.BG_PANEL,
            foreground=UITheme.TEXT_PRIMARY,
            arrowcolor=UITheme.TEXT_PRIMARY,
            bordercolor=UITheme.BORDER,
            lightcolor=UITheme.BORDER,
            darkcolor=UITheme.BORDER,
            padding=3,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", UITheme.BG_SURFACE), ("disabled", UITheme.BG_ROOT)],
            foreground=[("readonly", UITheme.TEXT_PRIMARY), ("disabled", UITheme.TEXT_MUTED)],
            selectbackground=[("readonly", UITheme.BG_SURFACE)],
            selectforeground=[("readonly", UITheme.TEXT_PRIMARY)],
        )
        style.configure("TNotebook", background=UITheme.BG_ROOT, borderwidth=0, tabmargins=(4, 4, 4, 0))
        style.configure(
            "TNotebook.Tab",
            background=UITheme.BG_SURFACE,
            foreground=UITheme.TEXT_MUTED,
            bordercolor=UITheme.BORDER,
            lightcolor=UITheme.BG_SURFACE,
            padding=(12, 5),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", UITheme.ACCENT), ("active", "#2d3b4e")],
            foreground=[("selected", "#ffffff"), ("active", UITheme.TEXT_PRIMARY)],
        )
        self._install_readability_guard25()
        style.configure(
            "Vertical.TScrollbar",
            background=UITheme.BG_SURFACE,
            troughcolor=UITheme.BG_ROOT,
            bordercolor=UITheme.BG_ROOT,
            arrowcolor=UITheme.TEXT_MUTED,
            relief="flat",
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=UITheme.BG_SURFACE,
            troughcolor=UITheme.BG_ROOT,
            bordercolor=UITheme.BG_ROOT,
            arrowcolor=UITheme.TEXT_MUTED,
            relief="flat",
        )

    def _polish_all_containers25(self):
        self._style_widget_tree25(self.root)
        if hasattr(self, "canvas"):
            self.canvas.configure(bg=UITheme.BG_CANVAS, highlightthickness=0)

        if hasattr(self, "settings_window"):
            self.settings_window.configure(bg=UITheme.BG_ROOT)
            self._style_widget_tree25(self.settings_window)
            for outer in getattr(self, "tab_frames", {}).values():
                for ch in outer.winfo_children():
                    if isinstance(ch, ttk.Scrollbar) and str(ch.cget("orient")) == "horizontal":
                        ch.pack_forget()
            self._select_navigation_tab("RADIO")

        if hasattr(self, "diagnostics_window"):
            self.diagnostics_window.configure(bg=UITheme.BG_ROOT)
            self._style_widget_tree25(self.diagnostics_window)
            for child in list(self.diagnostics_window.winfo_children()):
                if isinstance(child, tk.LabelFrame):
                    child.pack_configure(fill="both", expand=True, padx=10, pady=8)
                elif isinstance(child, tk.Frame):
                    child.pack_configure(fill="x", expand=False, padx=10, pady=(8, 0))
            if hasattr(self, "txt_logs"):
                self.txt_logs.configure(height=16)

    def _style_widget_tree25(self, parent):
        try:
            cls_name = parent.winfo_class()
            if cls_name in ("Frame", "Toplevel", "Tk"):
                cur_bg = str(parent.cget("bg")).lower()
                if cur_bg in (
                    "#090d16",
                    "#050811",
                    "#020617",
                    "#0b1424",
                    "systembuttonface",
                    "#f0f0f0",
                    "#d9d9d9",
                ):
                    parent.configure(bg=UITheme.BG_ROOT)
                elif cur_bg in ("#0f172a", "#101c30", "#172033", "#172338", "#1e293b", "#102035"):
                    parent.configure(bg=UITheme.BG_PANEL)
                if cls_name == "Frame" and int(parent.cget("bd") or 0) > 0:
                    parent.configure(
                        bd=0, relief="flat", highlightbackground=UITheme.BORDER, highlightthickness=1
                    )
        except tk.TclError:
            pass

        for child in parent.winfo_children():
            w_cls = child.winfo_class()
            try:
                if isinstance(child, (SwitchCheckButton, SegmentedRadioGroup)):
                    pass
                elif w_cls == "LabelFrame":
                    raw_t = self._clean_ui_label25(child.cget("text"))
                    child.configure(
                        text=f" {raw_t} " if raw_t else "",
                        bg=UITheme.BG_PANEL,
                        fg=UITheme.TEXT_PRIMARY,
                        font=("Segoe UI", 9, "bold"),
                        bd=1,
                        relief="solid",
                        padx=8,
                        pady=6,
                    )
                elif w_cls == "Frame":
                    cur_bg = str(child.cget("bg")).lower()
                    if cur_bg in ("#f59e0b", "#475569", "#334155"):
                        child.configure(bg=UITheme.BORDER)
                    elif cur_bg in (
                        "#090d16",
                        "#050811",
                        "#020617",
                        "systembuttonface",
                        "#f0f0f0",
                        "#d9d9d9",
                    ):
                        child.configure(bg=UITheme.BG_ROOT)
                    else:
                        child.configure(bg=UITheme.BG_PANEL)
                    if int(child.cget("bd") or 0) > 0:
                        child.configure(bd=0, relief="flat")
                elif w_cls == "Label":
                    raw_t = self._clean_ui_label25(child.cget("text"))
                    if raw_t != str(child.cget("text")):
                        child.configure(text=raw_t)
                    p_bg = str(child.master.cget("bg"))
                    cur_fg = str(child.cget("fg")).lower()
                    if cur_fg in ("#38bdf8", "#55cfea", "#a6ddef", "#9dd4e7", "#abddec", "#9bc9dc"):
                        new_fg = UITheme.TEXT_PRIMARY
                    elif cur_fg in (
                        "#94a3b8",
                        "#cbd5e1",
                        "#b3c4d8",
                        "#95a7bb",
                        "#a5b6ca",
                        "systemwindowtext",
                        "systembuttontext",
                        "black",
                        "#000000",
                    ):
                        new_fg = UITheme.TEXT_MUTED
                    elif cur_fg in ("#9a3412",):
                        new_fg = "#fbbf24"
                    else:
                        new_fg = child.cget("fg")
                    if str(child.cget("cursor")) == "hand2" and ("▾" in raw_t or "▸" in raw_t):
                        child.configure(
                            bg=UITheme.BG_SURFACE,
                            fg=UITheme.TEXT_PRIMARY,
                            font=("Segoe UI", 9, "bold"),
                            padx=8,
                            pady=5,
                        )
                    else:
                        child.configure(bg=p_bg, fg=new_fg)
                        self._fix_contrast25(child)
                elif w_cls == "Canvas":
                    # conteneur défilant laissé à la couleur système (pavé clair au milieu d'une fenêtre sombre)
                    if str(child.cget("bg")).lower() in ("systembuttonface", "#f0f0f0", "#d9d9d9", "white"):
                        child.configure(bg=UITheme.BG_ROOT, highlightthickness=0)
                elif w_cls in ("Button", "Menubutton"):
                    raw_t = self._clean_ui_label25(child.cget("text"))
                    if raw_t != str(child.cget("text")):
                        child.configure(text=raw_t)
                    cur_bg = str(child.cget("bg")).lower()
                    if cur_bg in ("#047857", "#059669"):
                        btn_bg, btn_act = UITheme.OK_BG, "#166534"
                    elif cur_bg in ("#1d4ed8", "#0284c7", "#0369a1"):
                        btn_bg, btn_act = UITheme.ACCENT, UITheme.ACCENT_HOVER
                    else:
                        btn_bg, btn_act = UITheme.BG_SURFACE, "#2d3b4e"
                    child.configure(
                        bg=btn_bg,
                        fg=UITheme.TEXT_PRIMARY,
                        activebackground=btn_act,
                        activeforeground="#ffffff",
                        font=("Segoe UI", 9),
                        bd=0,
                        relief="flat",
                        overrelief="flat",
                        highlightbackground=UITheme.BORDER,
                        highlightthickness=1,
                        padx=8,
                        pady=2,
                        cursor="hand2",
                    )
                elif w_cls == "Entry":
                    child.configure(
                        bg=UITheme.BG_SURFACE,
                        fg=UITheme.TEXT_PRIMARY,
                        insertbackground=UITheme.TEXT_PRIMARY,
                        selectbackground=UITheme.ACCENT,
                        selectforeground="#ffffff",
                        bd=0,
                        relief="flat",
                        highlightbackground=UITheme.BORDER,
                        highlightcolor=UITheme.BORDER_ACTIVE,
                        highlightthickness=1,
                        font=("Consolas", 9),
                    )
                elif w_cls == "Text":
                    child.configure(
                        bg=UITheme.BG_ROOT,
                        fg=UITheme.TEXT_PRIMARY,
                        insertbackground=UITheme.TEXT_PRIMARY,
                        selectbackground=UITheme.ACCENT,
                        selectforeground="#ffffff",
                        bd=0,
                        relief="flat",
                        highlightbackground=UITheme.BORDER,
                        highlightcolor=UITheme.BORDER_ACTIVE,
                        highlightthickness=1,
                        font=("Consolas", 9),
                        padx=10,
                        pady=8,
                    )
                elif w_cls == "Listbox":
                    child.configure(
                        bg=UITheme.BG_ROOT,
                        fg=UITheme.TEXT_PRIMARY,
                        selectbackground=UITheme.ACCENT,
                        selectforeground="#ffffff",
                        bd=0,
                        relief="flat",
                        highlightbackground=UITheme.BORDER,
                        highlightthickness=1,
                        font=("Segoe UI", 9),
                    )
                elif w_cls in ("Checkbutton", "Radiobutton"):
                    p_bg = str(child.master.cget("bg"))
                    child.configure(
                        bg=p_bg,
                        fg=UITheme.TEXT_PRIMARY,
                        selectcolor=UITheme.BG_SURFACE,
                        activebackground=p_bg,
                        activeforeground="#ffffff",
                        font=("Segoe UI", 9),
                        bd=0,
                        highlightthickness=0,
                    )
                elif w_cls == "Scale":
                    p_bg = str(child.master.cget("bg"))
                    child.configure(
                        bg=p_bg,
                        fg=UITheme.TEXT_MUTED,
                        troughcolor=UITheme.BG_ROOT,
                        activebackground=UITheme.ACCENT,
                        highlightthickness=0,
                        bd=0,
                        font=("Consolas", 8),
                    )
            except tk.TclError:
                pass
            self._style_widget_tree25(child)

    @staticmethod
    def _clean_ui_label25(text: str) -> str:
        if not text:
            return text
        cleaned = str(text)
        for token in (
            "📻",
            "⚪",
            "🟢",
            "🟠",
            "☀️",
            "🌙",
            "⏳",
            "📡",
            "📊",
            "📈",
            "🗂️",
            "📂",
            "📁",
            "📜",
            "🔌",
            "🔄",
            "🎙️",
            "🛡️",
            "🌐",
            "📍",
            "🆕",
            "⚡",
            "✨",
            "⭐",
            "🏷️",
            "🖼️",
            "🌡️",
            "💾",
            "🔍",
            "🛰️",
            "🖱️",
        ):
            cleaned = cleaned.replace(token, "")
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned

    def _wrap_schedule25(self, width):
        half = max(180, (width // 2) - 12)
        self.lbl_sched_current.configure(wraplength=half)
        self.lbl_sched_next.configure(wraplength=half)

    # ------------------------------------------------------------------ lisibilité (2.8.3)
    @staticmethod
    def _luminance25(widget, color) -> float:
        def lin(c):
            c = c / 65535.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        r, g, b = widget.winfo_rgb(color)
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    def _fix_contrast25(self, widget, minimum=4.0):
        """Texte illisible (noir sur gris foncé, gris sur gris…) : couleur de texte remplacée.

        Le rapport de contraste (définition WCAG) entre le texte et SON fond est calculé ; en dessous du
        minimum, le texte passe en clair sur fond sombre ou en foncé sur fond clair. Un texte déjà lisible
        n'est jamais modifié.
        """
        try:
            lf = self._luminance25(widget, widget.cget("fg"))
            lb = self._luminance25(widget, widget.cget("bg"))
            if (max(lf, lb) + 0.05) / (min(lf, lb) + 0.05) < minimum:
                widget.configure(fg=UITheme.TEXT_PRIMARY if lb < 0.30 else "#0f172a")
        except (tk.TclError, ValueError):
            pass

    _READABLE_CLASSES25 = (
        "Label",
        "Button",
        "Menubutton",
        "Checkbutton",
        "Radiobutton",
        "Entry",
        "Text",
        "Listbox",
        "Message",
        "Labelframe",
    )

    def _readable_tree25(self, parent):
        """Passe de lisibilité sur une fenêtre entière (ne change que les textes illisibles)."""
        try:
            children = parent.winfo_children()
        except tk.TclError:
            return
        for child in children:
            try:
                if child.winfo_class() in self._READABLE_CLASSES25 and not isinstance(
                    child, (SwitchCheckButton, SegmentedRadioGroup)
                ):
                    self._fix_contrast25(child)
            except tk.TclError:
                pass
            self._readable_tree25(child)

    def _install_readability_guard25(self):
        """Toute fenêtre secondaire qui s'ouvre reçoit la passe de lisibilité, quel que soit son module."""

        def on_map(event):
            w = event.widget
            if isinstance(w, tk.Toplevel):
                self.root.after(120, lambda: self._readable_tree25(w) if w.winfo_exists() else None)

        self.root.bind_class("Toplevel", "<Map>", on_map, add="+")
        self.root.after(1500, lambda: self._readable_tree25(self.root))

    def _polish_new_toplevels25(self):
        """Applique le thème et l'aide F1 aux fenêtres secondaires nouvellement ouvertes."""
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel) and w not in (
                self.settings_window,
                self.diagnostics_window,
                self.help_window25,
            ):
                self._style_widget_tree25(w)
                self._install_help(w)
