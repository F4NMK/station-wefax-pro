"""Infobulle d'aide détaillée liée aux rubriques."""

import re
import tkinter as tk
from wefax_station.ui.help_content import HELP_TOPICS_25
from wefax_station.ui.placement import clamp_into, root_area
from wefax_station.ui.theme import UITheme


class DetailedHelpTip25:
    def __init__(self, app, widget, topic, extra=""):
        self.app = app
        self.widget = widget
        self.topic = topic
        self.extra = extra
        self.timer = None
        self.hide_timer = None
        self.window = None
        widget.bind("<Enter>", self.enter, add="+")
        widget.bind("<Leave>", self.leave, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")
        widget.bind("<F1>", self.open_help, add="+")

    def enter(self, event=None):
        self.hide()
        self.timer = self.widget.after(550, self.show)

    def leave(self, event=None):
        if self.timer:
            self.widget.after_cancel(self.timer)
            self.timer = None
        self.hide_timer = self.widget.after(220, self.maybe_hide)

    def maybe_hide(self):
        self.hide_timer = None
        if self.window is not None:
            try:
                x, y = self.widget.winfo_pointerxy()
                over = self.widget.winfo_containing(x, y)
                node = over
                while node is not None:
                    if node is self.window:
                        return
                    node = getattr(node, "master", None)
            except tk.TclError:
                pass
        self.hide()

    def show(self):
        self.timer = None
        try:
            title, body = HELP_TOPICS_25[self.topic]
            self.window = win = tk.Toplevel(self.widget)
            win.wm_overrideredirect(True)
            box = tk.Frame(
                win,
                bg=UITheme.BG_PANEL,
                highlightbackground=UITheme.BORDER_ACTIVE,
                highlightthickness=1,
                padx=12,
                pady=10,
            )
            box.pack()
            tk.Label(
                box,
                text=title,
                bg=UITheme.BG_PANEL,
                fg=UITheme.TEXT_PRIMARY,
                font=("Segoe UI", 10, "bold"),
                anchor="w",
                justify="left",
                wraplength=460,
            ).pack(fill="x")
            summary = ((self.extra + "\n\n") if self.extra else "") + "\n".join(body.split("\n")[:3])
            summary = re.sub(r"\[\[([^|]+)\|([^]]+)\]\]", r"\2", summary)
            if len(summary) > 720:
                summary = summary[:717] + "…"
            tk.Label(
                box,
                text=summary,
                bg=UITheme.BG_PANEL,
                fg=UITheme.TEXT_MUTED,
                font=("Segoe UI", 9),
                wraplength=460,
                justify="left",
            ).pack(fill="x", pady=6)
            link = tk.Label(
                box,
                text="Consulter cette rubrique dans l’aide  ·  F1",
                bg=UITheme.BG_PANEL,
                fg="#60a5fa",
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
                anchor="w",
            )
            link.pack(fill="x")
            link.bind("<Button-1>", self.open_help)
            win.bind("<Leave>", self.leave, add="+")
            win.update_idletasks()
            x = self.widget.winfo_rootx() + 10
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
            # 2.9.0 — bornée à la fenêtre principale (et non à l'écran principal) : sur un poste
            # multi-écran la bulle s'affichait sur un autre écran que l'application.
            top = self.widget.winfo_toplevel()
            x, y = clamp_into(x, y, win.winfo_reqwidth(), win.winfo_reqheight(), root_area(top))
            win.geometry(f"+{x}+{y}")
        except tk.TclError:
            self.hide()

    def open_help(self, event=None):
        self.hide()
        self.app._show_help25(self.topic)
        return "break"

    def hide(self, event=None):
        for key in ("timer", "hide_timer"):
            timer = getattr(self, key, None)
            if timer:
                try:
                    self.widget.after_cancel(timer)
                except tk.TclError:
                    pass
                setattr(self, key, None)
        if self.window is not None:
            win = self.window
            self.window = None
            try:
                win.destroy()
            except tk.TclError:
                pass
