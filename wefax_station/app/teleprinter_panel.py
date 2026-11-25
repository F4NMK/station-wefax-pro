"""Téléscripteur intégré à la fenêtre principale, et fenêtre « À propos ».

2.8.6 — pendant une écoute RTTY ou NAVTEX, la zone centrale continuait d'afficher la dernière carte WEFAX
avec « Réception WEFAX » et les étapes APT : rien n'indiquait que le poste écoutait du texte, ni jusqu'à
quand. La zone centrale devient un téléscripteur (papier sombre, caractères ambre, comme les
téléimprimeurs des stations radio) qui affiche le texte reçu en direct ; la carte revient automatiquement
au retour en WEFAX.
"""

import tkinter as tk
from pathlib import Path

from wefax_station.ui.placement import show_over_root
from wefax_station.version import SOFTWARE_VERSION

PAPER = "#14110b"
INK = "#f5c46b"
INK_DIM = "#a8875a"
RULE = "#3a2f1d"
ASSETS = Path(__file__).resolve().parent.parent / "assets"


class TeleprinterPanelMixin:
    def _tp_build(self):
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return None
        frame = tk.Frame(canvas.master, bg=PAPER, highlightthickness=1, highlightbackground=RULE)
        head = tk.Frame(frame, bg=PAPER)
        head.pack(fill="x", padx=14, pady=(10, 4))
        self._tp_title = tk.Label(
            head, text="", bg=PAPER, fg=INK, font=("Consolas", 12, "bold"), anchor="w", justify="left"
        )
        self._tp_title.pack(side="left", fill="x", expand=True)
        tk.Button(
            head,
            text="Revenir aux cartes",
            command=self._tp_back_to_charts,
            bg="#2a2216",
            fg=INK,
            activebackground="#3a2f1d",
            activeforeground=INK,
            relief="flat",
            padx=10,
        ).pack(side="right")
        tk.Frame(frame, bg=RULE, height=1).pack(fill="x", padx=14)
        self._tp_sub = tk.Label(frame, text="", bg=PAPER, fg=INK_DIM, font=("Segoe UI", 9), anchor="w")
        self._tp_sub.pack(fill="x", padx=14, pady=(4, 0))
        body = tk.Frame(frame, bg=PAPER)
        body.pack(fill="both", expand=True, padx=14, pady=8)
        sb = tk.Scrollbar(body, orient="vertical")
        txt = tk.Text(
            body,
            bg=PAPER,
            fg=INK,
            insertbackground=INK,
            font=("Consolas", 12),
            wrap="word",
            relief="flat",
            yscrollcommand=sb.set,
            padx=8,
            pady=6,
        )
        sb.configure(command=txt.yview)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("end", "En attente des premiers caractères…\n")
        txt.configure(state="disabled")
        self._tp_frame, self._tp_text = frame, txt
        self._tp_empty = True
        return frame

    def show_teleprinter(self, on, station=None, item=None):
        frame = getattr(self, "_tp_frame", None) or self._tp_build()
        if frame is None:
            return
        if not on:
            frame.place_forget()
            return
        st = station or {}
        proto = "NAVTEX SITOR-B" if "NAVTEX" in str(st.get("protocol", "")) else "RTTY ITA2"
        self._tp_title.configure(
            text=f"📠 TÉLÉSCRIPTEUR — {st.get('id', '?')} · {float(st.get('freq', 0.0)):.1f} kHz · {proto}"
        )
        until = f"écoute jusqu'à {item.end:%H:%M} UTC" if item is not None and getattr(item, "end", None) else ""
        what = item.label if item is not None and getattr(item, "label", "") not in ("", "OPERATEUR") else ""
        self._tp_sub.configure(
            text=" · ".join(x for x in (what, until) if x)
            + "   —   la carte reviendra automatiquement à la fin de l'écoute."
        )
        t = self._tp_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", "En attente des premiers caractères…\n")
        t.configure(state="disabled")
        self._tp_empty = True
        frame.place(in_=self.canvas, relx=0, rely=0, relwidth=1, relheight=1)
        frame.lift()

    def append_teleprinter(self, chars):
        t = getattr(self, "_tp_text", None)
        if t is None or not chars:
            return
        try:
            if not t.winfo_ismapped():
                return
        except tk.TclError:
            return
        t.configure(state="normal")
        if getattr(self, "_tp_empty", False):
            t.delete("1.0", "end")
            self._tp_empty = False
        at_end = t.yview()[1] > 0.98
        t.insert("end", chars.replace("\r", ""))
        if int(t.index("end-1c").split(".")[0]) > 3000:
            t.delete("1.0", "500.0")
        if at_end:
            t.see("end")
        t.configure(state="disabled")

    def _tp_back_to_charts(self):
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None and arb.active_pipeline == "RTTY":
            arb.end_rtty_and_return("Retour manuel aux cartes WEFAX")
        else:
            self.show_teleprinter(False)

    # ------------------------------------------------------------------ À propos
    def _show_about(self):
        win = tk.Toplevel(self.root)
        win.title("À propos")
        win.configure(bg="#0b1220")
        win.resizable(False, False)
        win.transient(self.root)
        try:
            img = tk.PhotoImage(file=str(ASSETS / "logo_f4nmk.png"))
            win._logo = img
            tk.Label(win, image=img, bg="#0b1220", bd=0).pack(padx=18, pady=(18, 10))
        except (tk.TclError, OSError):
            pass
        tk.Label(
            win, text=f"Station WEFAX PRO {SOFTWARE_VERSION}", bg="#0b1220", fg="#f5c46b", font=("Segoe UI", 15, "bold")
        ).pack()
        tk.Label(
            win,
            text="Cartes météo WEFAX · bulletins RTTY DWD · NAVTEX\npilotage de l'Icom IC-705 par CI-V",
            bg="#0b1220",
            fg="#cbd5e1",
            font=("Segoe UI", 10),
            justify="center",
        ).pack(pady=(4, 10))
        tk.Frame(win, bg="#334155", height=1).pack(fill="x", padx=40)
        tk.Label(
            win,
            text="Conception et développement : Marc — F4NMK\nLe Cannet · Alpes-Maritimes · Provence-Alpes-Côte d'Azur",
            bg="#0b1220",
            fg="#e2e8f0",
            font=("Segoe UI", 10),
            justify="center",
        ).pack(pady=10)
        tk.Label(
            win,
            text="Logiciel portable : tout est enregistré dans le dossier de l'application.\n"
            "Repères météo indicatifs : ils ne remplacent pas les bulletins officiels (Météo-France, CROSS).",
            bg="#0b1220",
            fg="#94a3b8",
            font=("Segoe UI", 9),
            justify="center",
        ).pack(padx=24)
        tk.Label(win, text="73 !", bg="#0b1220", fg="#f5c46b", font=("Consolas", 12, "bold")).pack(pady=(10, 4))
        tk.Button(win, text="Fermer", command=win.destroy, relief="flat", bg="#1e293b", fg="#e2e8f0", padx=16).pack(
            pady=(4, 16)
        )
        win.bind("<Escape>", lambda e: win.destroy())
        # 2.9.0 — placée sur la fenêtre principale, quel que soit l'écran (coordonnées négatives comprises) ;
        # en 2.8.9 la position était bornée à 0 et la fenêtre partait hors de l'écran sur un poste multi-écran.
        try:
            show_over_root(win, self.root)
        except tk.TclError:
            pass
        self._about_window = win
        return win
