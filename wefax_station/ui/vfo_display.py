"""Afficheur de poste façon façade de transceiver : fréquence en chiffres 7 segments, indicatif de la
station, puces de réglage (mode, filtre, AGC, préampli), horloge UTC et S-mètre à segments.

2.10.0 — horloge UTC en 7 segments, plus petite et plus pâle que la fréquence (les programmes WEFAX,
RTTY et NAVTEX sont tous en UTC). Elle est redessinée seule chaque seconde (étiquette « clock »), sans
redessiner le reste de l'afficheur.

Entièrement dessiné sur un Canvas (aucune police spéciale à installer) et redessiné à chaque
redimensionnement : il se compacte sur les petits écrans (nom de la station, puis puces masqués).
"""

import tkinter as tk
from datetime import datetime, timezone

from wefax_station.ui.text_fit import fit_text

# segments : a b c d e f g
_DIGITS = {
    "0": "abcdef",
    "1": "bc",
    "2": "abdeg",
    "3": "abcdg",
    "4": "bcfg",
    "5": "acdfg",
    "6": "acdefg",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg",
    "-": "g",
    " ": "",
}

BG = "#0a0f16"
BEZEL = "#2b3a4f"
LCD = "#ffb000"  # ambre, comme les afficheurs des postes
LCD_OFF = "#1a1409"
CLOCK = "#7fb4cf"  # 2.10.0 : bleu acier pâle, plus discret que l'ambre de la fréquence
CLOCK_OFF = "#0f1b25"
CHIP_BG = "#16263a"
CHIP_FG = "#cbd5e1"


class VfoDisplay(tk.Canvas):
    def __init__(self, master, height=66, **kw):
        super().__init__(master, height=height, bg=BG, highlightthickness=1, highlightbackground=BEZEL, **kw)
        self.state = {
            "freq_khz": 7880.0,
            "dial_khz": 7878.1,
            "station": "DDK3",
            "name": "DWD Pinneberg",
            "mode": "USB-D",
            "filter": "FIL1",
            "agc": "FAST",
            "preamp": 1,
            "att": False,
            "s_raw": None,
            "s_label": "",
            "service": "WEFAX",
            "service_detail": "120 lpm · IOC 576",
            "quality": "",
            "cat": False,
        }
        self._tag = ()  # étiquette des éléments en cours de dessin (« clock » pour l'horloge)
        self._clock_box = None  # (x, y, hauteur, avec_secondes) calculé par redraw()
        self._clock_job = None
        self.clock_now = lambda: datetime.now(timezone.utc)  # remplaçable par les tests
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Destroy>", self._stop_clock, add="+")
        self._tick_clock()

    def update_state(self, **kw):
        changed = any(self.state.get(k) != v for k, v in kw.items())
        self.state.update(kw)
        if changed:
            self.redraw()

    # ------------------------------------------------------------------ dessin
    def _seg_digit(self, x, y, w, h, ch, color, off_color, t):
        on = _DIGITS.get(ch, "")
        hh = h / 2.0
        g = max(1.0, t * 0.18)  # petit jour entre segments
        b = t / 2.0  # biseau
        horiz = {"a": y + b, "g": y + hh, "d": y + h - b}  # axe des segments horizontaux
        vert = {
            "f": (x + b, y + b, y + hh),
            "b": (x + w - b, y + b, y + hh),
            "e": (x + b, y + hh, y + h - b),
            "c": (x + w - b, y + hh, y + h - b),
        }
        for name, cy in horiz.items():
            x0, x1 = x + b + g, x + w - b - g
            col = color if name in on else off_color
            self.create_polygon(
                x0,
                cy,
                x0 + b,
                cy - b,
                x1 - b,
                cy - b,
                x1,
                cy,
                x1 - b,
                cy + b,
                x0 + b,
                cy + b,
                fill=col,
                outline="",
                tags=self._tag,
            )
        for name, (cx, y0, y1) in vert.items():
            y0, y1 = y0 + g, y1 - g
            col = color if name in on else off_color
            self.create_polygon(
                cx,
                y0,
                cx + b,
                y0 + b,
                cx + b,
                y1 - b,
                cx,
                y1,
                cx - b,
                y1 - b,
                cx - b,
                y0 + b,
                fill=col,
                outline="",
                tags=self._tag,
            )

    def _seg_text(self, x, y, h, text, color=LCD, off_color=LCD_OFF):
        w = h * 0.56
        t = max(2.0, h * 0.13)
        gap = h * 0.17
        for ch in text:
            if ch == ":":  # 2.10.0 : deux points de l'horloge
                r = t * 0.55
                cx = x + gap * 0.2
                for cy in (y + h * 0.3, y + h * 0.72):
                    self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="", tags=self._tag)
                x += gap * 1.4
                continue
            if ch == ".":
                r = t * 0.7
                self.create_oval(
                    x - gap * 0.6 - r, y + h - 2 * r, x - gap * 0.6 + r, y + h, fill=color, outline=""
                )
                x += gap * 0.4
                continue
            if ch == " ":
                x += w * 0.45
                continue
            self._seg_digit(x, y, w, h, ch, color, off_color, t)
            x += w + gap
        return x

    @staticmethod
    def seg_text_width(h, text):
        """Largeur (px) de `text` en 7 segments de hauteur h, même calcul que _seg_text."""
        w, gap, x = h * 0.56, h * 0.17, 0.0
        for ch in text:
            x += gap * 1.4 if ch == ":" else gap * 0.4 if ch == "." else w * 0.45 if ch == " " else w + gap
        return x

    # ------------------------------------------------------------------ horloge UTC (2.10.0)
    def _tick_clock(self):
        try:
            self._draw_clock()
            now = self.clock_now()
            self._clock_job = self.after(max(50, 1000 - now.microsecond // 1000), self._tick_clock)
        except tk.TclError:
            self._clock_job = None

    def _stop_clock(self, event=None):
        if event is not None and event.widget is not self:
            return
        if self._clock_job is not None:
            try:
                self.after_cancel(self._clock_job)
            except tk.TclError:
                pass
            self._clock_job = None

    def clock_text(self):
        box = self._clock_box
        now = self.clock_now()
        return now.strftime("%H:%M:%S" if (box is None or box[3]) else "%H:%M")

    def _draw_clock(self):
        self.delete("clock")
        box = self._clock_box
        if box is None:
            return
        x, y, h, _secs = box
        self._tag = ("clock",)
        try:
            self.create_text(
                x, y - 2, text="UTC", anchor="sw", fill="#5b7f95", font=("Segoe UI", 7, "bold"), tags=self._tag
            )
            self._seg_text(x, y, h, self.clock_text(), CLOCK, CLOCK_OFF)
        finally:
            self._tag = ()

    @staticmethod
    def _freq_text(khz):
        s = f"{khz:,.2f}".replace(",", " ")
        return s

    def _text_width(self, text, font):
        tid = self.create_text(-1000, -1000, text=text, anchor="w", font=font)
        x0, _, x1, _ = self.bbox(tid) or (0, 0, 0, 0)
        self.delete(tid)
        return x1 - x0

    def _chip(self, x, y, text, bg=CHIP_BG, fg=CHIP_FG, font=("Segoe UI", 8, "bold")):
        tid = self.create_text(x + 6, y, text=text, anchor="w", fill=fg, font=font)
        x0, y0, x1, y1 = self.bbox(tid)
        rid = self.create_rectangle(x0 - 5, y0 - 2, x1 + 5, y1 + 2, fill=bg, outline="")
        self.tag_lower(rid, tid)
        return x1 + 10

    def _smeter(self, x, y, w, h):
        st = self.state
        n = 15  # S1..S9 puis +10..+60
        segw = w / n
        raw = st.get("s_raw")
        lit = -1 if raw is None else int(round(min(1.0, max(0.0, raw / 241.0)) * n))
        for i in range(n):
            on = i < lit
            col = ("#22c55e" if i < 9 else "#ef4444") if on else ("#12301d" if i < 9 else "#3b1414")
            self.create_rectangle(x + i * segw + 1, y, x + (i + 1) * segw - 1, y + h, fill=col, outline="")
        for i, lab in (
            (0, "1"),
            (2, "3"),
            (4, "5"),
            (6, "7"),
            (8, "9"),
            (10, "+20"),
            (12, "+40"),
            (14, "+60"),
        ):
            self.create_text(x + (i + 0.5) * segw, y + h + 6, text=lab, fill="#64748b", font=("Segoe UI", 7))
        self.create_text(x - 4, y + h / 2, text="S", anchor="e", fill="#94a3b8", font=("Segoe UI", 8, "bold"))
        label = st.get("s_label") if raw is not None else "S —"
        self.create_text(x + w, y - 8, text=label, anchor="e", fill="#e2e8f0", font=("Segoe UI", 8, "bold"))

    def redraw(self):
        self.delete("all")
        st = self.state
        W = max(200, self.winfo_width())
        H = max(40, self.winfo_height())
        pad = 10
        # 1. service (WEFAX / RTTY / NAVTEX) en pastille colorée
        svc_col = {"WEFAX": "#0e7490", "RTTY": "#b45309", "NAVTEX": "#7c3aed"}.get(st["service"], "#334155")
        x = self._chip(pad - 4, 13, f" {st['service']} ", bg=svc_col, fg="#ffffff")
        did = self.create_text(
            x, 13, text=st.get("service_detail", ""), anchor="w", fill="#94a3b8", font=("Segoe UI", 8)
        )
        detail_end = (self.bbox(did) or (0, 0, x, 0))[2]
        # 2. fréquence (fréquence publiée de la station) en 7 segments
        dh = max(18, min(38, H - 27))
        fx = self._seg_text(
            pad, H - dh - 5, dh, self._freq_text(st["freq_khz"]), LCD if st.get("cat") else "#c58f1c"
        )
        self.create_text(
            fx + 2, H - 9, text="kHz", anchor="sw", fill="#c9a66b", font=("Segoe UI", 10, "bold")
        )
        # 2.9.0 — l'indicatif commence après la fréquence ET après le texte de service : en NAVTEX,
        # « SITOR-B 100 Bd · 170 Hz » (plus long que « 120 lpm · IOC 576 ») chevauchait « NAVTEX-INT ».
        x0 = max(fx + 46, detail_end + 14)
        compact = W < 900
        tiny = W < 640
        cx = x0
        # 3. indicatif + nom + puces
        if tiny and W - 150 - x0 > 70:
            self.create_text(
                x0 - 20,
                H / 2 + 4,
                text=st["station"],
                anchor="w",
                fill="#fef3c7",
                font=("Segoe UI", 15, "bold"),
            )
        if not tiny:
            self.create_text(
                x0, 18, text=st["station"], anchor="w", fill="#fef3c7", font=("Segoe UI", 17, "bold")
            )
            if not compact:
                cid = self.create_text(x0, 18, text=st["station"], anchor="w", font=("Segoe UI", 17, "bold"))
                bx = self.bbox(cid)[2] + 12
                self.delete(cid)
                # 2.9.0 — nom raccourci pour ne pas passer sous le S-mètre
                room = (W - (200 if not compact else 130) - pad - 16) - bx
                name = fit_text(st.get("name", ""), room, lambda t: self._text_width(t, ("Segoe UI", 9)))
                if name:
                    self.create_text(bx, 19, text=name, anchor="w", fill="#94a3b8", font=("Segoe UI", 9))
            cx = x0
            chips = [
                f"VFO {st['dial_khz']:,.2f}".replace(",", " "),
                st["mode"],
                st["filter"],
                f"AGC {st['agc']}",
                "P.AMP " + (str(st["preamp"]) if st["preamp"] else "OFF"),
            ]
            if st.get("att"):
                chips.append("ATT")
            for c in chips if not compact else chips[1:4]:
                cx = self._chip(cx - 6, H - 16, c)
        # 4. S-mètre + qualité à droite
        sm_w = 200 if not compact else 130
        sx = W - sm_w - pad
        # 5. horloge UTC (2.10.0) entre les puces et le S-mètre, sinon au-dessus des puces
        self._clock_box = None
        right = sx - 18
        left = (cx + 12) if not tiny else (x0 + 90)
        for ch_h, secs in ((min(24, dh * 0.62), True), (min(20, dh * 0.55), False)):
            need = self.seg_text_width(ch_h, "00:00:00" if secs else "00:00")
            if right - left >= need:
                self._clock_box = (right - need, H - ch_h - 7, ch_h, secs)
                break
        self._draw_clock()
        if sx > x0 + 120 or tiny:
            self._smeter(sx, 20, sm_w, 11)
            bottom = st.get("quality", "")
            color = "#a7f3d0"
            if not st.get("cat"):
                bottom, color = "CAT non connecté", "#fca5a5"
            if bottom:
                self.create_text(
                    W - pad, H - 10, text=bottom, anchor="e", fill=color, font=("Segoe UI", 8, "bold")
                )
