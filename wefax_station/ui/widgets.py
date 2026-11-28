"""Widgets Tk personnalisés : infobulles, interrupteurs, groupes segmentés."""

import tkinter as tk
from wefax_station.ui.theme import UITheme


class FlyoverToolTip:
    """Bulle d'aide contextuelle sobre au survol de la souris."""

    def __init__(self, widget, text, status_callback=None):
        self.widget = widget
        self.text = text
        self.status_callback = status_callback
        self.tip_window = None
        self.after_id = None
        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        if self.status_callback:
            self.status_callback(f"Aide : {self.text.replace(chr(10), ' — ')}")
        self._schedule()

    def _on_leave(self, event=None):
        self._unschedule()
        self._hide()

    def _schedule(self):
        self._unschedule()
        self.after_id = self.widget.after(320, self._show)

    def _unschedule(self):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def _show(self):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        frame = tk.Frame(
            tw, bg=UITheme.BG_PANEL, highlightbackground=UITheme.BORDER_ACTIVE, highlightthickness=1
        )
        frame.pack(fill="both", expand=True)
        lbl = tk.Label(
            frame,
            text=self.text,
            justify="left",
            bg=UITheme.BG_PANEL,
            fg=UITheme.TEXT_PRIMARY,
            font=("Segoe UI", 9),
            padx=10,
            pady=6,
            wraplength=380,
        )
        lbl.pack()

    def _hide(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class SwitchCheckButton(tk.Button):
    """
    Interrupteur d'état sobre (● Actif / ○ Inactif) sans tramage Windows.
    Conserve strictement l'API existante (set_state, set_warning).
    """

    def __init__(
        self, master, text, command=None, initial=False, active_color="#15803d", active_fg="#ffffff", **kwargs
    ):
        self.base_text = text
        self.active_color = active_color if active_color != "#059669" else UITheme.OK_BG
        self.active_fg = active_fg
        self.is_active = bool(initial)
        self.user_command = command

        super().__init__(
            master,
            command=self._on_click,
            font=("Segoe UI", 9),
            bd=0,
            relief="flat",
            overrelief="flat",
            highlightthickness=1,
            cursor="hand2",
            padx=8,
            pady=3,
            anchor="w",
            **kwargs,
        )
        self.set_state(initial)

    def _on_click(self):
        if self.user_command:
            self.user_command()

    def set_state(self, active: bool, custom_label: str = None):
        self.is_active = bool(active)
        lbl = custom_label if custom_label else self.base_text
        if self.is_active:
            self.config(
                text=f"●  {lbl}",
                bg=self.active_color,
                fg=self.active_fg,
                activebackground=self.active_color,
                activeforeground=self.active_fg,
                highlightbackground="#22c55e",
                highlightcolor="#22c55e",
                font=("Segoe UI", 9, "bold"),
                relief="flat",
            )
        else:
            self.config(
                text=f"○  {lbl}",
                bg=UITheme.BG_SURFACE,
                fg=UITheme.TEXT_MUTED,
                activebackground="#2d3b4e",
                activeforeground=UITheme.TEXT_PRIMARY,
                highlightbackground=UITheme.BORDER,
                highlightcolor=UITheme.BORDER,
                font=("Segoe UI", 9),
                relief="flat",
            )

    def set_warning(self, warn_text: str):
        self.is_active = False
        self.config(
            text=f"▲  {warn_text}",
            bg=UITheme.WARN_BG,
            fg="#ffffff",
            activebackground="#92400e",
            activeforeground="#ffffff",
            highlightbackground="#f59e0b",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )


class SegmentedRadioGroup(tk.Frame):
    """Groupe de sélection segmenté sobre (1 seul choix actif à la fois)."""

    def __init__(
        self,
        master,
        options: list,
        command=None,
        default_value=None,
        group_title=None,
        active_bg="#2563eb",
        active_fg="#ffffff",
    ):
        super().__init__(
            master,
            bg=UITheme.BG_PANEL,
            highlightbackground=UITheme.BORDER,
            highlightthickness=1,
            padx=2,
            pady=1,
        )
        self.options = options
        self.command = command
        self.active_bg = UITheme.ACCENT if active_bg in ("#0284c7", "#059669") else active_bg
        self.active_fg = active_fg
        self.buttons = {}
        self.current_value = default_value if default_value is not None else options[0][0]

        if group_title:
            hdr = tk.Label(
                self,
                text=group_title,
                bg=UITheme.BG_PANEL,
                fg=UITheme.TEXT_MUTED,
                font=("Segoe UI", 8, "bold"),
                anchor="w",
                padx=6,
                pady=1,
            )
            hdr.pack(fill="x")

        inner = tk.Frame(self, bg=UITheme.BG_ROOT)
        inner.pack(fill="both", expand=True)

        for idx, item in enumerate(options):
            val, lbl = item[0], item[1]
            btn = tk.Button(
                inner,
                command=lambda v=val: self._on_select(v),
                font=("Segoe UI", 9),
                bd=0,
                relief="flat",
                overrelief="flat",
                padx=7,
                pady=2,
                cursor="hand2",
            )
            btn.pack(side="left", fill="both", expand=True, padx=(0 if idx == 0 else 1, 0))
            self.buttons[val] = (btn, lbl)

        self.set_value(self.current_value, trigger_callback=False)

    def _on_select(self, value):
        self.set_value(value, trigger_callback=True)

    def set_value(self, value, trigger_callback=False):
        self.current_value = value
        for val, (btn, lbl) in self.buttons.items():
            if val == value:
                btn.config(
                    text=lbl,
                    bg=self.active_bg,
                    fg=self.active_fg,
                    activebackground=self.active_bg,
                    activeforeground=self.active_fg,
                    font=("Segoe UI", 9, "bold"),
                )
            else:
                btn.config(
                    text=lbl,
                    bg=UITheme.BG_SURFACE,
                    fg=UITheme.TEXT_MUTED,
                    activebackground="#2d3b4e",
                    activeforeground=UITheme.TEXT_PRIMARY,
                    font=("Segoe UI", 9),
                )
        if trigger_callback and self.command:
            self.command(value)
