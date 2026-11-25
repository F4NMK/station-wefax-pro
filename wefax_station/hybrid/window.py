"""Fenêtre téléscripteur RTTY, rapport ADRASEC et aide qualité."""

from datetime import datetime, timezone
from pathlib import Path
from wefax_station.weather.plain_language import clean_raw
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from wefax_station.core.stations import RTTY_WEATHER_STATIONS
from wefax_station.rtty.segmenter import find_marker
from wefax_station.hybrid.arbiter import HybridModeArbiter
from wefax_station.ui.theme import UITheme
from wefax_station.version import SOFTWARE_BRAND
from wefax_station.weather.reliability import WeatherReliabilityEstimator


class BulletinsAndHybridWindow:
    def __init__(self, app, arbiter: HybridModeArbiter):
        self.app = app
        self.arbiter = arbiter
        self.window = None
        self.adv_visible = False

    def _tip(self, widget, topic: str, text: str):
        self.app._register_tip25(widget, topic, text)

    def show_reliability_help_dialog(self):
        parent_win = self.window if (self.window and self.window.winfo_exists()) else self.app.root
        messagebox.showinfo(
            "Guide : Indices de Qualité & Sélection de la Meilleure Fréquence HF",
            WeatherReliabilityEstimator.HELP_TEXT_FR,
            parent=parent_win,
        )

    def sync_station_combo(self):
        if self.window is not None and self.window.winfo_exists() and hasattr(self, "cmb_rtty_st"):
            st_labels = [
                f"{s['id']} ({s['freq']} kHz) · {s['station']} [{self.arbiter.rtty_snr_map.get(s['id'], s['period'])}]"
                for s in RTTY_WEATHER_STATIONS
            ]
            self.cmb_rtty_st["values"] = st_labels
            cur_idx = next(
                (
                    i
                    for i, s in enumerate(RTTY_WEATHER_STATIONS)
                    if s["id"] == self.arbiter.active_rtty_station["id"]
                ),
                0,
            )
            self.cmb_rtty_st.current(cur_idx)

    # ================================================================== fenêtre (2.8.8)
    #
    # Une seule question par zone :
    #   en haut     — QUOI j'écoute (émetteur, état du signal, programme) ; deux actions : scanner, revenir aux cartes
    #   à gauche    — LES BULLETINS REÇUS, classés par jour (« En direct » tout en haut)
    #   au centre   — le bulletin choisi : texte reçu | lecture en français
    #   en bas      — ce qu'on fait de CE bulletin (enregistrer, retraduire, ouvrir le fichier)
    # Les commandes générales (rapport, horaires Internet, résultats de scan, aide) restent dans les menus.

    PERIODS = (("24 heures", 24), ("3 jours", 72), ("7 jours", 168))

    def show(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self.sync_station_combo()
            self.refresh_archive()
            self.refresh_status()
            return

        P, R = UITheme.BG_PANEL, UITheme.BG_ROOT
        win = self.window = tk.Toplevel(self.app.root)
        win.title(f"Téléscripteur — bulletins RTTY / NAVTEX — {SOFTWARE_BRAND}")
        win.configure(bg=R)
        self.app._fit_window(win, 1240, 780)
        win.minsize(900, 560)
        self.viewing = None  # None = direct ; sinon document archivé affiché
        self._text_cache = {}

        # ---------------------------------------------------------------- en haut : ce que j'écoute
        top = tk.Frame(win, bg=P, padx=10, pady=8)
        top.pack(fill="x", padx=8, pady=(8, 4))
        row = tk.Frame(top, bg=P)
        row.pack(fill="x")
        tk.Label(row, text="Émetteur :", bg=P, fg=UITheme.TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.cmb_rtty_st = ttk.Combobox(row, state="readonly")
        self.cmb_rtty_st.pack(side="left", fill="x", expand=True, padx=(6, 8))
        self.cmb_rtty_st.bind("<<ComboboxSelected>>", self._on_rtty_station_selected)
        self._tip(
            self.cmb_rtty_st,
            "interface",
            "Choisir un émetteur règle le poste dessus pendant 15 min (écoute manuelle), puis l'automatisme reprend.",
        )
        b = tk.Button(
            row,
            text="🔍 Chercher la meilleure fréquence",
            command=lambda: self.arbiter.trigger_rtty_frequency_scan(family_filter="DWD_RTTY"),
            bg="#1d4ed8",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
        )
        b.pack(side="left", padx=(0, 6))
        self._tip(b, "interface", "Mesure les fréquences RTTY du DWD et se règle sur la meilleure.")
        tk.Button(
            row,
            text="🗺️ Revenir aux cartes WEFAX",
            command=self._quit_rtty_and_return_wefax,
            bg="#059669",
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side="left")
        self.sync_station_combo()

        self.lbl_big_status = tk.Label(
            top, text="Initialisation…", bg="#174f68", fg="#ffffff", font=("Segoe UI", 10, "bold"),
            anchor="w", justify="left", padx=10, pady=6,
        )
        self.lbl_big_status.pack(fill="x", pady=(8, 2))
        self.lbl_sched_bulletin = tk.Label(
            top, text="", bg=P, fg="#bae6fd", font=("Segoe UI", 9), anchor="w", justify="left"
        )
        self.lbl_sched_bulletin.pack(fill="x")
        trow = tk.Frame(top, bg=P)
        trow.pack(fill="x")
        self.lbl_tech_summary = tk.Label(
            trow, text="", bg=P, fg=UITheme.TEXT_MUTED, font=("Consolas", 8), anchor="w", justify="left"
        )
        self.lbl_tech_summary.pack(side="left", fill="x", expand=True)
        tk.Button(
            trow, text="?", command=self.show_reliability_help_dialog, bg=P, fg="#fde68a",
            relief="flat", font=("Segoe UI", 8, "bold"), padx=6, cursor="hand2",
        ).pack(side="right")
        for w in (self.lbl_big_status, self.lbl_sched_bulletin, self.lbl_tech_summary):
            w.bind("<Configure>", lambda e, w=w: w.configure(wraplength=max(300, e.width - 20)))

        # ---------------------------------------------------------------- corps : liste | bulletin
        body = tk.PanedWindow(win, orient="horizontal", sashwidth=5, bg=UITheme.BORDER)
        body.pack(fill="both", expand=True, padx=8, pady=4)

        side = tk.Frame(body, bg=P, padx=6, pady=6)
        body.add(side, minsize=260, width=390, stretch="never")
        tk.Label(side, text="📚 BULLETINS REÇUS", bg=P, fg="#fef3c7", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        frow = tk.Frame(side, bg=P)
        frow.pack(fill="x", pady=(4, 4))
        self.period_var = tk.StringVar(master=self.app.root, value=self.PERIODS[0][0])
        cmb_p = ttk.Combobox(frow, textvariable=self.period_var, values=[p[0] for p in self.PERIODS], state="readonly", width=10)
        cmb_p.pack(side="left")
        cmb_p.bind("<<ComboboxSelected>>", lambda e: self.refresh_archive())
        self.search_var = tk.StringVar(master=self.app.root)
        ent = tk.Entry(frow, textvariable=self.search_var, bg=R, fg=UITheme.TEXT_PRIMARY, insertbackground="white")
        ent.pack(side="left", fill="x", expand=True, padx=(6, 0))
        ent.bind("<KeyRelease>", lambda e: self._schedule_archive_refresh())
        self._tip(ent, "interface", "Rechercher : station (DDH7), produit (FQME), ou un mot du texte (GALE, LION…).")
        tk.Label(side, text="🔎 station, produit ou mot du texte", bg=P, fg=UITheme.TEXT_MUTED, font=("Segoe UI", 7), anchor="e").pack(fill="x")

        tv_box = tk.Frame(side, bg=P)
        tv_box.pack(fill="both", expand=True)
        style = ttk.Style(win)
        style.configure("Arch.Treeview", rowheight=22, font=("Segoe UI", 9))
        self.tv_arch = ttk.Treeview(tv_box, columns=("rel",), show="tree headings", style="Arch.Treeview", selectmode="browse")
        self.tv_arch.heading("#0", text="Heure UTC · station · contenu")
        self.tv_arch.heading("rel", text="Fiab.")
        self.tv_arch.column("#0", width=300, stretch=True)
        self.tv_arch.column("rel", width=52, anchor="center", stretch=False)
        sb_a = ttk.Scrollbar(tv_box, orient="vertical", command=self.tv_arch.yview)
        self.tv_arch.configure(yscrollcommand=sb_a.set)
        sb_a.pack(side="right", fill="y")
        self.tv_arch.pack(side="left", fill="both", expand=True)
        for tag, col in (("live", "#4ade80"), ("day", "#fde68a"), ("warn", "#f87171"), ("poor", "#94a3b8")):
            self.tv_arch.tag_configure(tag, foreground=col)
        self.tv_arch.tag_configure("day", font=("Segoe UI", 9, "bold"))
        self.tv_arch.bind("<<TreeviewSelect>>", self._on_archive_selected)
        self.tv_arch.bind("<Double-1>", lambda e: self._open_viewed_file())
        self._arch_docs = {}
        self.lbl_arch_count = tk.Label(side, text="", bg=P, fg=UITheme.TEXT_MUTED, font=("Segoe UI", 8), anchor="w")
        self.lbl_arch_count.pack(fill="x", pady=(4, 0))

        main = tk.Frame(body, bg=P, padx=6, pady=6)
        body.add(main, minsize=520, stretch="always")
        hrow = tk.Frame(main, bg=P)
        hrow.pack(fill="x", pady=(0, 4))
        self.lbl_view = tk.Label(hrow, text="", bg=P, fg="#4ade80", font=("Segoe UI", 10, "bold"), anchor="w")
        self.lbl_view.pack(side="left", fill="x", expand=True)
        self.btn_back_live = tk.Button(
            hrow, text="● Revenir au direct", command=self.show_live, bg="#065f46", fg="#dcfce7",
            relief="flat", font=("Segoe UI", 9, "bold"), padx=10, cursor="hand2",
        )
        pane = tk.PanedWindow(main, orient="horizontal", sashwidth=5, bg=UITheme.BORDER)
        pane.pack(fill="both", expand=True)
        self.txt_orig = self._text_column(pane, "TEXTE REÇU (tel que diffusé)", "#e6edf3")
        self.txt_trad = self._text_column(pane, "EN FRANÇAIS : ce qu'il faut retenir, puis la traduction complète", "#dcfce7")

        # ---------------------------------------------------------------- en bas : ce bulletin
        bot = tk.Frame(win, bg=P, padx=10, pady=6)
        bot.pack(fill="x", padx=8, pady=(0, 6))
        self.btn_save = self._bot_button(bot, "💾 Enregistrer maintenant", self._save_bulletin_now, "#059669")
        self.btn_retrad = self._bot_button(bot, "🔄 Retraduire", self._translate_now)
        self.btn_clear = self._bot_button(bot, "🧹 Effacer le direct", self._clear_rtty)
        self.btn_open_file = self._bot_button(bot, "📄 Ouvrir le fichier", self._open_viewed_file)
        self._bot_button(bot, "📂 Dossier des bulletins", self._open_bulletins_dir)
        self.btn_toggle_adv = tk.Button(
            bot, text="⚙️ Réglages du décodeur ▸", command=self._toggle_advanced_panel, bg=UITheme.BG_SURFACE,
            fg=UITheme.TEXT_MUTED, font=("Segoe UI", 8), relief="flat", padx=8, pady=4, cursor="hand2",
        )
        self.btn_toggle_adv.pack(side="right")
        self._build_advanced_panel(win)

        self.show_live()
        self.refresh_archive()
        self.refresh_status()

    def _text_column(self, pane, title, fg):
        P, R = UITheme.BG_PANEL, UITheme.BG_ROOT
        f = tk.Frame(pane, bg=P, padx=2)
        pane.add(f, minsize=240, stretch="always")
        tk.Label(f, text=title, bg=P, fg=UITheme.TEXT_PRIMARY, font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x", pady=(0, 3))
        box = tk.Frame(f, bg=R)
        box.pack(fill="both", expand=True)
        t = tk.Text(box, wrap="word", bg=R, fg=fg, font=("Consolas", 10), padx=8, pady=6, relief="flat")
        sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
        return t

    def _bot_button(self, parent, text, cmd, bg=None):
        b = tk.Button(
            parent, text=text, command=cmd, bg=bg or UITheme.BG_SURFACE, fg="#ffffff" if bg else UITheme.TEXT_PRIMARY,
            font=("Segoe UI", 9, "bold" if bg else "normal"), relief="flat", padx=10, pady=4, cursor="hand2",
        )
        b.pack(side="left", padx=(0, 6))
        return b

    def _build_advanced_panel(self, win):
        P = UITheme.BG_PANEL
        self.adv_frame = tk.Frame(win, bg=P, padx=10, pady=6)
        tk.Label(self.adv_frame, text="Bauds :", bg=P, fg=UITheme.TEXT_MUTED).pack(side="left")
        self.cmb_rtty_baud = ttk.Combobox(self.adv_frame, values=["45.45", "50.0", "75.0", "100.0"], state="readonly", width=6)
        self.cmb_rtty_baud.set(str(self.arbiter.rtty.baud))
        self.cmb_rtty_baud.pack(side="left", padx=2)
        self.cmb_rtty_baud.bind("<<ComboboxSelected>>", self._apply_rtty_params)
        tk.Label(self.adv_frame, text="Shift (Hz) :", bg=P, fg=UITheme.TEXT_MUTED).pack(side="left", padx=(8, 2))
        self.cmb_rtty_shift = ttk.Combobox(self.adv_frame, values=["85.0", "170.0", "450.0", "850.0"], state="readonly", width=6)
        self.cmb_rtty_shift.set(str(self.arbiter.rtty.shift_hz))
        self.cmb_rtty_shift.pack(side="left", padx=2)
        self.cmb_rtty_shift.bind("<<ComboboxSelected>>", self._apply_rtty_params)
        self.auto_pol_var = tk.BooleanVar(value=self.arbiter.rtty.auto_polarity)
        tk.Checkbutton(
            self.adv_frame, text="Polarité automatique", variable=self.auto_pol_var, command=self._apply_rtty_params,
            bg=P, fg="#4ade80", selectcolor=UITheme.BG_SURFACE,
        ).pack(side="left", padx=6)
        self.inv_var = tk.BooleanVar(value=self.arbiter.rtty.inverted)
        tk.Checkbutton(
            self.adv_frame, text="Forcer inversée", variable=self.inv_var, command=self._apply_rtty_params,
            bg=P, fg=UITheme.TEXT_PRIMARY, selectcolor=UITheme.BG_SURFACE,
        ).pack(side="left", padx=4)
        tk.Label(self.adv_frame, text="Scan WEFAX avant carte (s) :", bg=P, fg=UITheme.TEXT_MUTED).pack(side="left", padx=(12, 2))
        self.spn_margin = tk.Spinbox(
            self.adv_frame, from_=60, to=600, increment=15, width=5, bg=UITheme.BG_SURFACE, fg=UITheme.TEXT_PRIMARY,
            font=("Consolas", 9), command=self._on_margin_changed,
        )
        self.spn_margin.delete(0, "end")
        self.spn_margin.insert(0, str(self.arbiter.return_margin_sec))
        self.spn_margin.pack(side="left", padx=4)
        tk.Button(
            self.adv_frame, text="🧪 Bulletin d'essai", command=self._inject_test_bulletin, bg=UITheme.BG_SURFACE,
            fg=UITheme.TEXT_MUTED, font=("Segoe UI", 8), relief="flat", padx=8,
        ).pack(side="right")

    # ------------------------------------------------------------------ direct / archive
    def show_live(self):
        """Affiche le texte en cours de réception (le direct)."""
        self.viewing = None
        if not (self.window and self.window.winfo_exists()):
            return
        self.btn_back_live.pack_forget()
        st = self.arbiter.active_rtty_station
        self.lbl_view.configure(
            text=f"● EN DIRECT — {st['id']} · {st['freq']:.1f} kHz", fg="#4ade80"
        )
        for b in (self.btn_save, self.btn_clear):
            b.configure(state="normal")
        self.txt_orig.configure(state="normal")
        self.txt_orig.delete("1.0", "end")
        if self.arbiter.rtty_raw_buffer:
            self.txt_orig.insert("1.0", self.arbiter.rtty_raw_buffer.replace("\r", ""))
            self.txt_orig.see("end")
        else:
            self.txt_orig.insert("1.0", "")
        self._translate_now()
        try:
            if self.tv_arch.exists("live"):
                self.tv_arch.selection_set("live")
        except tk.TclError:
            pass

    def show_document(self, doc_id):
        """Ouvre le téléscripteur sur un bulletin archivé (depuis « Météo & bulletin » par exemple)."""
        self.show()
        iid = "doc_" + str(doc_id)
        if not self.tv_arch.exists(iid):
            self.period_var.set(self.PERIODS[-1][0])
            self.search_var.set("")
            self.refresh_archive()
        if self.tv_arch.exists(iid):
            parent = self.tv_arch.parent(iid)
            if parent:
                self.tv_arch.item(parent, open=True)
            self.tv_arch.selection_set(iid)
            self.tv_arch.see(iid)
            self._on_archive_selected()

    def _period_hours(self):
        return dict(self.PERIODS).get(self.period_var.get(), 24) if hasattr(self, "period_var") else 24

    def _schedule_archive_refresh(self):
        w = self.window
        if not (w and w.winfo_exists()):
            return
        if getattr(self, "_arch_after", None):
            try:
                w.after_cancel(self._arch_after)
            except tk.TclError:
                pass
        self._arch_after = w.after(350, self.refresh_archive)

    # en-têtes OMM (TTAAii) → nom en clair
    _WMO_KIND = (
        ("WO", "Avis de vent fort"),
        ("WW", "Avis de tempête"),
        ("FQ", "Prévision marine"),
        ("FE", "Prévision longue"),
        ("FP", "Prévision"),
        ("FX", "Prévision"),
        ("AX", "Situation générale"),
        ("SM", "Observations (SYNOP)"),
        ("SI", "Observations (SYNOP)"),
        ("SN", "Observations (SYNOP)"),
        ("SX", "Observations"),
        ("NO", "Message de service"),
    )

    def _doc_label(self, d):
        import re

        prod = (d.get("product") or "").strip()
        m = re.search(r"\b([A-Z]{4}\d{2})\s+[A-Z]{4}\b", prod.upper())
        if m:
            code = m.group(1)
            name = next((n for p, n in self._WMO_KIND if code.startswith(p)), "Bulletin")
            prod = f"{name} ({code})"
        elif not prod or prod.upper().startswith("FLUX"):
            prod = d.get("status") or "bulletin"
        if "NAVTEX" in str(d.get("station", "")).upper() or d.get("kind") == "NAVTEX":
            prod = "NAVTEX · " + prod
        return f"{d['start']:%H:%M}  {d['station']}  ·  {prod}"[:80]

    def refresh_archive(self):
        """Liste des bulletins archivés (RTTY / NAVTEX), regroupés par jour UTC, le plus récent en haut."""
        if not (self.window and self.window.winfo_exists()) or not hasattr(self, "tv_arch"):
            return
        self._arch_after = None
        try:
            docs = [d for d in self.app._desk_documents(hours=self._period_hours()) if d["kind"] != "Carte WEFAX"]
        except Exception:
            docs = []
        q = (self.search_var.get() or "").strip().upper()
        if q:
            def match(d):
                hay = f"{d['station']} {d.get('product', '')} {d.get('status', '')}".upper()
                if q in hay:
                    return True
                if len(q) < 3:
                    return False
                key = d["id"]
                if key not in self._text_cache:
                    self._text_cache[key] = self.app._doc_text(d).upper()
                return q in self._text_cache[key]
            docs = [d for d in docs if match(d)]
        tv = self.tv_arch
        keep = tv.selection()[0] if tv.selection() else "live"
        tv.delete(*tv.get_children())
        st = self.arbiter.active_rtty_station
        tv.insert("", "end", iid="live", text=f"● En direct — {st['id']} {st['freq']:.1f} kHz", values=("",), tags=("live",))
        self._arch_docs = {}
        today = datetime.now(timezone.utc).date()
        days = {}
        for d in docs:
            day = d["start"].date()
            if day not in days:
                delta = (today - day).days
                name = "Aujourd'hui" if delta == 0 else ("Hier" if delta == 1 else f"{day:%A}".capitalize())
                days[day] = tv.insert("", "end", iid=f"day{day:%Y%m%d}", text=f"{name}  {day:%d/%m}", open=delta <= 1 or bool(q), tags=("day",))
            iid = "doc_" + str(d["id"])
            if tv.exists(iid):
                continue
            rel = d.get("rel")
            label = self._doc_label(d)
            txt_u = f"{d.get('product', '')} {d.get('status', '')} {label}".upper()
            tag = "warn" if ("GALE" in txt_u or "WARN" in txt_u or "STORM" in txt_u or "AVIS" in txt_u) else ("poor" if rel is not None and rel < 40 else "")
            tv.insert(days[day], "end", iid=iid, text=label, values=(f"{rel:.0f} %" if rel is not None else "—",), tags=(tag,) if tag else ())
            self._arch_docs[iid] = d
        self.lbl_arch_count.configure(
            text=f"{len(docs)} bulletin(s) sur {self.period_var.get()}" + (f" contenant « {q.lower()} »" if q else "")
            + " · double-clic : ouvrir le fichier"
        )
        if tv.exists(keep):
            tv.selection_set(keep)
            tv.see(keep)

    def _on_archive_selected(self, event=None):
        sel = self.tv_arch.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "live":
            if self.viewing is not None:
                self.show_live()
            return
        d = self._arch_docs.get(iid)
        if d is None:  # ligne « jour »
            return
        self.viewing = d
        text = self.app._doc_text(d)
        rel = d.get("rel")
        self.lbl_view.configure(
            text=f"📄 ARCHIVE — {d['start']:%d/%m %H:%M} UTC · {d['station']} · {d.get('product') or ''}"
            + (f" · fiabilité {rel:.0f} %" if rel is not None else ""),
            fg="#fde68a",
        )
        self.btn_back_live.pack(side="right")
        for b in (self.btn_save, self.btn_clear):
            b.configure(state="disabled")
        self.txt_orig.configure(state="normal")
        self.txt_orig.delete("1.0", "end")
        self.txt_orig.insert("1.0", text.strip("\n"))
        self.txt_orig.configure(state="disabled")
        plain, _ = self.arbiter.interpret_text(clean_raw(text), f"{d['station']} {d['start']:%d/%m %H:%M} UTC", live=False)
        res = self.arbiter.translator.translate_preserve_critical(text)
        self._fill_translation(plain, res["translated"], keep_position=False)

    def _viewed_file(self):
        d = self.viewing
        if d is None:
            return None
        return next((f for f in d["files"] if f.name.endswith("_original.txt")), None)

    def _open_viewed_file(self):
        f = self._viewed_file()
        if f is None:
            sel = self.tv_arch.selection() if hasattr(self, "tv_arch") else ()
            d = self._arch_docs.get(sel[0]) if sel else None
            f = next((x for x in d["files"] if x.name.endswith("_original.txt")), None) if d else None
        if f is not None and f.exists():
            self.app._open_path(f) if hasattr(self.app, "_open_path") else self._os_open(f)

    def _open_bulletins_dir(self):
        f = self._viewed_file()
        target = f.parent if f is not None else None
        if target is None:
            try:
                target = self.arbiter.workspace.reception_day_dir() / "bulletins"
            except Exception:
                target = None
        if target is not None:
            self._os_open(target)

    @staticmethod
    def _os_open(path):
        import os
        import subprocess
        import sys

        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError:
            pass


    def _generate_orsec_bulletin_dialog(self):
        out_path = self.arbiter.generate_adrasec_orsec_report_1click()
        parent_win = self.window if (self.window and self.window.winfo_exists()) else self.app.root
        messagebox.showinfo(
            (self.app.report_label() if hasattr(self.app, "report_label") else "Rapport") + " généré",
            f"Le Bulletin de Situation Météorologique avec Indice de Fiabilité a été enregistré dans :\n\n{out_path}",
            parent=parent_win,
        )

    def _toggle_advanced_panel(self):
        self.adv_visible = not self.adv_visible
        if self.adv_visible:
            self.adv_frame.pack(fill="x", padx=8, pady=(0, 6), before=self.btn_toggle_adv.master)
            self.btn_toggle_adv.configure(text="⚙️ Réglages du décodeur ▾")
        else:
            self.adv_frame.pack_forget()
            self.btn_toggle_adv.configure(text="⚙️ Réglages du décodeur ▸")

    def _quit_rtty_and_return_wefax(self):
        # 2.8.9 — même chemin que le retour automatique : le bulletin en cours est marqué « fait » (sinon,
        # avant la fin de son créneau, l'automatisme repartait aussitôt en RTTY)
        if self.arbiter.active_pipeline == "RTTY":
            self.arbiter.end_rtty_and_return("Retour manuel aux cartes WEFAX")
        else:
            self.arbiter.switch_to_wefax_pipeline(reason="Retour manuel aux cartes WEFAX", launch_prescan=False)
        if self.window and self.window.winfo_exists():
            self.window.withdraw()


    def _on_rtty_station_selected(self, event=None):
        idx = self.cmb_rtty_st.current()
        if 0 <= idx < len(RTTY_WEATHER_STATIONS):
            st = RTTY_WEATHER_STATIONS[idx]
            self.arbiter.active_rtty_station = st
            if hasattr(self, "cmb_rtty_baud"):
                self.cmb_rtty_baud.set(str(st["baud"]))
                self.cmb_rtty_shift.set(str(st["shift_hz"]))
            # 2.8.6 — choix manuel : créneau d'écoute de 15 min (abandonné après 6 s le 16/11 sur NAVTEX)
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            from wefax_station.hybrid.scheduler import RttyItem

            now = _dt.now(_tz.utc)
            self.arbiter.current_item = RttyItem(now, now + _td(minutes=15), "OPERATEUR", "OPERATEUR", "choix opérateur")
            self.arbiter._reset_rtty_tracking()
            self.arbiter.switch_to_rtty_pipeline(
                st, reason=f"Sélection manuelle de {st['id']} ({st['freq']} kHz)"
            )
            self.refresh_status()

    def _on_margin_changed(self):
        try:
            self.arbiter.return_margin_sec = max(60, min(900, int(self.spn_margin.get())))
        except ValueError:
            pass

    def _apply_rtty_params(self, event=None):
        try:
            b = float(self.cmb_rtty_baud.get())
            s = float(self.cmb_rtty_shift.get())
            inv = bool(self.inv_var.get())
            apol = bool(self.auto_pol_var.get())
            self.arbiter.rtty.configure(baud=b, shift_hz=s, inverted=inv, auto_polarity=apol)
            self.refresh_status()
        except ValueError:
            pass

    def _inject_test_bulletin(self):
        sample = (
            "ZCZCFQXX60 EDZW 140830\n"
            "DWD PINNEBERG SHIPPING FORECAST AND GALE WARNING\n"
            "ISSUED AT 140830 UTC\n"
            "GALE WARNING IN EFFECT FOR GERMAN BIGHT AND DOGGER.\n"
            "GENERAL SYNOPSIS: LOW PRESSURE 986 HPA OVER NORTH SEA MOVING NE RAPIDLY AND DEEPENING.\n"
            "HIGH PRESSURE 1024 HPA WEST OF BISCAY STATIONARY.\n"
            "FORECAST FOR GERMAN BIGHT AND FISHER:\n"
            "WIND SW TO W 28 TO 34 KT (7 TO 8 BFT), VEERING NW LATER, GUSTS 45 KT.\n"
            "COLD FRONT PASSING EASTWARD WITH SQUALLS AND SHOWERS. VISIBILITY MODERATE OR POOR IN RAIN.\n"
            "SEA STATE ROUGH TO VERY ROUGH, SWELL 4.0 M.\n"
            "OUTLOOK NEXT 24 HOURS: WIND DECREASING 18 KT, NO STORM WARNING.\n"
            "NNNN\n"
        )
        if not self.arbiter.rtty_session_start_utc:
            self.arbiter.rtty_session_start_utc = self.arbiter.workspace.begin_document_reception()
        self.arbiter.rtty_raw_buffer += sample
        self.arbiter.rtty.accepted_chars += len(sample)
        self.arbiter.rtty.valid_stop_frames += len(sample)
        self.arbiter.rtty.total_frames += len(sample)
        self.arbiter.rtty.last_metrics.update(
            {
                "signal_compatible": True,
                "bit_clock_locked": True,
                "accepted_char_ratio": 0.99,
                "frame_sync_ratio": 0.98,
                "lexical_quality": 0.95,
                "mark_snr_db": 18.5,
                "space_snr_db": 17.8,
            }
        )
        if self.window and self.window.winfo_exists():
            self.show_live()
            self.refresh_status()

    def _translate_now(self):
        if getattr(self, "viewing", None) is not None:
            self._on_archive_selected()  # « Retraduire » sur une archive : relit le fichier
            return
        live_ui = bool(self.window and self.window.winfo_exists())
        raw = self.txt_orig.get("1.0", "end-1c") if live_ui else self.arbiter.rtty_raw_buffer
        self.arbiter.rtty_raw_buffer = raw
        res = self.arbiter.translator.translate_preserve_critical(raw)
        if live_ui:
            st = self.arbiter.active_rtty_station
            plain, it = self.arbiter.interpret_text(clean_raw(raw), f"{st['id']} {st['freq']:.1f} kHz", live=True)
            self._fill_translation(plain, res["translated"], keep_position=True)

    def _fill_translation(self, plain, translated, keep_position=True):
        t = self.txt_trad
        t.configure(state="normal")
        # 2.8.5 — la position de lecture est conservée : le panneau revenait en haut à chaque ligne reçue
        top = t.yview()[0] if keep_position else 0.0
        t.delete("1.0", "end")
        t.insert(
            "1.0",
            plain + "\n\n" + "─" * 60 + "\nTRADUCTION DU BULLETIN REÇU (texte complet, dans l'ordre de réception)\n" + translated,
        )
        self._colorize_levels(t)
        t.yview_moveto(top)

    _LEVEL_TAGS = (
        ("■□□□ 1/4", "lvl1", "#4ade80"),
        ("■■□□ 2/4", "lvl2", "#facc15"),
        ("■■■□ 3/4", "lvl3", "#fb923c"),
        ("■■■■ 4/4", "lvl4", "#f87171"),
    )

    def _colorize_levels(self, widget):
        """Colore les jauges de niveau (vert, jaune, orange, rouge) et les titres de la lecture en clair."""
        widget.tag_configure("head", foreground="#ffffff", font=("Consolas", 10, "bold"))
        for marker, tag, color in self._LEVEL_TAGS:
            widget.tag_configure(tag, foreground=color, font=("Consolas", 10, "bold"))
            pos = "1.0"
            while True:
                pos = widget.search(marker, pos, stopindex="end")
                if not pos:
                    break
                end = f"{pos}+{len(marker)}c"
                widget.tag_add(tag, pos, end)
                pos = end
        for title in (
            "CE QUI VOUS CONCERNE",
            "SITUATION GÉNÉRALE ANNONCÉE",
            "AILLEURS (",
            "COMMENT LIRE",
            "NIVEAUX —",
            "TRADUCTION DU BULLETIN REÇU",
            "… RÉCEPTION EN COURS",
        ):
            pos = "1.0"
            while True:
                pos = widget.search(title, pos, stopindex="end")
                if not pos:
                    break
                widget.tag_add("head", pos, f"{pos} lineend")
                pos = f"{pos} lineend"

    def _save_bulletin_now(self):
        if getattr(self, "viewing", None) is not None:
            return
        if self.window and self.window.winfo_exists():
            self.arbiter.rtty_raw_buffer = self.txt_orig.get("1.0", "end-1c")
        orig_p, trad_p = self.arbiter.save_current_rtty_bulletin(
            trigger_reason="Archivage manuel opérateur", manual=True
        )
        parent_win = self.window if (self.window and self.window.winfo_exists()) else self.app.root
        if orig_p:
            self.refresh_archive()
            messagebox.showinfo(
                "Bulletin archivé",
                f"Bulletin original et traduction hors-ligne enregistrés dans :\n{orig_p.parent}\n\n"
                f"• Original : {orig_p.name}\n• Traduction : {trad_p.name}",
                parent=parent_win,
            )

    def _clear_rtty(self):
        if getattr(self, "viewing", None) is not None:
            return
        self.arbiter.rtty_raw_buffer = ""
        self.arbiter.rtty_segment = ""
        self.arbiter.rtty.reset()
        if self.window and self.window.winfo_exists():
            self.txt_orig.delete("1.0", "end")
            self.txt_trad.configure(state="normal")
            self.txt_trad.delete("1.0", "end")
            self.refresh_status()

    def _run_retention_check(self):
        stats = self.arbiter.workspace.enforce_retention_and_quota()
        count = self.arbiter.workspace.rebuild_operator_index()
        parent_win = (
            self.app.settings_window
            if (hasattr(self.app, "settings_window") and self.app.settings_window.winfo_viewable())
            else self.app.root
        )
        messagebox.showinfo(
            "Stockage Portable & Rétention 7 jours",
            f"Racine portable active :\n{self.arbiter.workspace.root_dir}\n\n"
            f"• Documents indexés (chemins relatifs) : {count}\n"
            f"• Fichiers expirés (>7j UTC) ou hors quota purgés : {stats['purged_files']}\n"
            f"• Volume courant : {stats['total_mb']} Mo / Quota {self.arbiter.workspace.quota_mb} Mo",
            parent=parent_win,
        )

    def _export_autonomous_bundle(self):
        parent_win = (
            self.app.settings_window
            if (hasattr(self.app, "settings_window") and self.app.settings_window.winfo_viewable())
            else self.app.root
        )
        dest = filedialog.askdirectory(
            parent=parent_win,
            title="Choisir un dossier externe pour l'export autonome hors rétention 7 jours",
        )
        if not dest:
            return
        target = Path(dest) / f"Export_Autonome_WEFAX_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%SZ')}"
        out = self.arbiter.workspace.export_beyond_7days_bundle(target)
        messagebox.showinfo(
            "Export autonome terminé",
            f"Export autonome créé avec manifeste et sources :\n{out}",
            parent=parent_win,
        )

    def append_live_rtty_text(self, new_chars: str):
        if not new_chars:
            return
        self.arbiter.rtty_raw_buffer += new_chars
        self.arbiter.rtty_segment += new_chars
        if hasattr(self.app, "append_teleprinter"):
            self.app.append_teleprinter(new_chars)
        self.arbiter.on_rtty_text(new_chars)
        cur_len = len(self.arbiter.rtty_raw_buffer)
        if (cur_len - self.arbiter.rtty_last_logged_len) >= 40:
            snippet = self.arbiter.rtty_raw_buffer[-40:].replace("\n", " ").replace("\r", "")
            self.app.log_event(
                f"📠 [RTTY RX {self.arbiter.active_rtty_station['id']}] {cur_len} caractères reçus : « {snippet} »"
            )
            self.arbiter.rtty_last_logged_len = cur_len
        # 2.8.5 — un fichier par bulletin : le segment en cours est archivé à son NNNN puis vidé. Le texte de
        # la session (rtty_raw_buffer) n'est plus effacé : il reste affiché et sert à la synthèse. Auparavant
        # il était restauré depuis la zone de texte à chaque traduction, ce qui redéclenchait la sauvegarde.
        saved = False
        while True:
            seg = self.arbiter.rtty_segment
            # 2.8.6 — un nouveau « ZCZC » ferme aussi le bulletin précédent quand son NNNN a été perdu : le
            # 17/11, la fin du bulletin mer du Nord et toute la prévision Méditerranée (39 min) étaient dans
            # un seul fichier, intitulé « Flux RTTY en cours de réception ».
            z = find_marker(seg[40:], "ZCZC")
            n = find_marker(seg, "NNNN")
            if z is not None and (n is None or n[0] > z[0] + 40) and z[1] + 40 < len(seg):
                cut = z[0] + 40
                if len(seg[:cut].strip()) >= 45:
                    self.arbiter.save_current_rtty_bulletin(
                        trigger_reason="Nouveau ZCZC (fin du bulletin précédent perdue)", text=seg[:cut]
                    )
                    self.arbiter.rtty_segment = seg[cut:]
                    saved = True
                    continue
            mark = find_marker(seg, "NNNN")
            if mark is None or not (seg[mark[0] : mark[1]].upper() == "NNNN" or mark[1] < len(seg)):
                break  # pas de fin de bulletin, ou mot « à un caractère près » encore en cours de réception
            self.arbiter.save_current_rtty_bulletin(
                trigger_reason="Séquence NNNN détectée", text=seg[: mark[1]]
            )
            self.arbiter.rtty_segment = seg[mark[1] :].lstrip("\r\n ")
            saved = True
        if self.window is not None and self.window.winfo_exists():
            if getattr(self, "viewing", None) is None:  # pendant la lecture d'une archive, le direct continue en fond
                at_end = self.txt_orig.yview()[1] > 0.98
                self.txt_orig.insert("end", new_chars.replace("\r", ""))
                if at_end:
                    self.txt_orig.see("end")
                if "\n" in new_chars or cur_len % 25 < len(new_chars):
                    self._translate_now()
            if saved:
                self.refresh_archive()
            self.refresh_status()

    def refresh_status(self, scanning_station: dict = None):
        if self.window is None or not self.window.winfo_exists():
            return
        delay_sec, code, desc, when_str, wf_fam, _ = self.arbiter.get_next_wefax_countdown()

        cur_line, later = self.arbiter.plan_summary(n=3)
        why = getattr(self.arbiter, "last_decision", "")
        if why:
            later = f"{later}\n🤖 Automatisme : {why}"
        if self.arbiter.current_item is not None and self.arbiter.active_pipeline == "RTTY":
            self.lbl_sched_bulletin.configure(
                text=f"🟢 Bulletin en cours : {self.arbiter.current_item.describe()}   ·   Ensuite : {later}",
                fg="#86efac",
            )
        else:
            self.lbl_sched_bulletin.configure(
                text=f"📅 {cur_line}   ·   Prochains bulletins : {later}", fg="#bae6fd"
            )

        st = scanning_station or self.arbiter.active_rtty_station
        m = self.arbiter.rtty.last_metrics
        sig_ok = bool(m.get("signal_compatible"))
        clk_ok = bool(m.get("bit_clock_locked"))
        rel_rt = WeatherReliabilityEstimator.compute_rtty_reliability(
            self.arbiter.rtty, self.arbiter.rtty_raw_buffer
        )

        if scanning_station is not None:
            self.lbl_big_status.configure(
                text=f"🔍 SCAN RTTY QUALITÉ EN COURS — Mesure de {st['id']} ({st['freq']:.1f} kHz · {st['station']})...",
                bg="#1d4ed8",
                fg="#ffffff",
            )
        elif self.arbiter.active_pipeline == "RTTY":
            if sig_ok and clk_ok:
                self.lbl_big_status.configure(
                    text=(
                        f"🟢 SIGNAL {m.get('protocol', 'RTTY')} ACTIF SUR {st['id']} ({st['freq']:.1f} kHz) — "
                        f"DÉCODAGE ({self.arbiter.rtty.accepted_chars} car. | {rel_rt['badge_text']})"
                    ),
                    bg="#15803d",
                    fg="#ffffff",
                )
            elif sig_ok:
                self.lbl_big_status.configure(
                    text=f"🟠 PORTEUSE FSK DÉTECTÉE SUR {st['id']} ({st['freq']:.1f} kHz) — Validation lexicale Baudot...",
                    bg="#b45309",
                    fg="#ffffff",
                )
            else:
                self.lbl_big_status.configure(
                    text=(
                        f"⏳ SQUELCH FSK FERMÉ SUR {st['id']} ({st['freq']:.1f} kHz · {st['baud']:.0f} Bd / shift {st['shift_hz']:.0f} Hz) — "
                        "En attente d'un signal RTTY valide (SNR >= 9.5 dB)."
                    ),
                    bg="#174f68",
                    fg="#d5f5ff",
                )
        else:
            self.lbl_big_status.configure(
                text=(
                    f"🗺️ POSTE EN VEILLE CARTES WEFAX ({self.app.radio.active_station_id} · {self.app.radio.actual_freq_khz:.1f} kHz) — "
                    "Bascule automatique au prochain bulletin choisi dans le plan de réception."
                ),
                bg="#065f46",
                fg="#dcfce7",
            )

        if getattr(self, "viewing", None) is None and hasattr(self, "lbl_view"):
            live_txt = f"● EN DIRECT — {self.arbiter.active_rtty_station['id']} · {self.arbiter.active_rtty_station['freq']:.1f} kHz"
            if self.lbl_view.cget("text") != live_txt:
                self.lbl_view.configure(text=live_txt)
            try:
                if self.tv_arch.exists("live"):
                    self.tv_arch.item("live", text=live_txt.replace("● EN DIRECT", "● En direct"))
            except tk.TclError:
                pass
        self.lbl_tech_summary.configure(
            text=(
                f"{m.get('protocol', 'RTTY')} ({st['baud']:.0f}Bd/{st['shift_hz']:.0f}Hz · {m.get('polarity_used', 'Auto')}) | "
                f"Mark {m.get('f_mark_hz', 2125):.0f}Hz={m.get('mark_snr_db', 0):+.1f}dB · "
                f"Space {m.get('f_space_hz', 1675):.0f}Hz={m.get('space_snr_db', 0):+.1f}dB | "
                f"{rel_rt['badge_text']} | Prochaine carte {wf_fam} [{code}] ({when_str})"
            )
        )
