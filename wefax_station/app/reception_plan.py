"""Plan de réception et résultats de scan.

* Fenêtre « Résultats du dernier scan » : toutes les stations (WEFAX, RTTY, NAVTEX) avec leur fréquence,
  la dernière qualité mesurée, son âge et sa source (scan complet, veille, réception). Un double-clic
  (ou « Accorder ») règle le poste sur la station choisie sans relancer de scan ; « Mesurer » relance une
  mesure rapide des seules lignes sélectionnées.
* Onglet Réglages « 4 · Plan de réception » : bulletins texte à recevoir (catégories, programmes RTTY,
  NAVTEX), veille de propagation, même tableau des stations et liste des prochains bulletins planifiés.
"""

import time
import tkinter as tk
from datetime import datetime, timedelta, timezone
from tkinter import messagebox, ttk

from wefax_station.core.stations import RTTY_WEATHER_STATIONS, WEFAX_STATIONS
from wefax_station.hybrid.scheduler import CATEGORIES, PROGRAM_LABEL, PROGRAM_STATIONS, RttyItem
from wefax_station.ui.placement import show_over_root
from wefax_station.ui.theme import UITheme

_COLUMNS = (
    ("mode", "Mode", 62),
    ("id", "Indicatif", 92),
    ("station", "Émetteur", 210),
    ("freq", "kHz", 70),
    ("prog", "Programme / période", 165),
    ("qual", "Qualité", 60),
    ("state", "État", 200),
    ("age", "Mesure", 150),
    ("spec", "Vu sur le spectre", 150),
)


def _program_of(sid):
    for p, ids in PROGRAM_STATIONS.items():
        if sid in ids:
            return PROGRAM_LABEL[p]
    return ""


class ReceptionPlanMixin:
    # ------------------------------------------------------------- tableau commun
    def _make_station_tree(self, parent, height=12):
        frame = tk.Frame(parent, bg=UITheme.BG_PANEL)
        tree = ttk.Treeview(frame, columns=[c[0] for c in _COLUMNS], show="headings", height=height)
        for key, title, width in _COLUMNS:
            tree.heading(key, text=title)
            tree.column(key, width=width, stretch=key in ("station", "state"), anchor="w")
        ys = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xs = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        tree.tag_configure("good", foreground="#86efac")
        tree.tag_configure("mid", foreground="#fde68a")
        tree.tag_configure("bad", foreground="#fca5a5")
        tree.tag_configure("none", foreground="#94a3b8")
        tree.tag_configure("current", background="#155e75")
        tree.bind("<Double-1>", lambda e, t=tree: self._tune_from_tree(t))
        if not hasattr(self, "_station_trees"):
            self._station_trees = []
        self._station_trees.append(tree)
        self._fill_station_tree(tree)
        return frame, tree

    def _station_rows(self):
        arb = getattr(self, "hybrid_arbiter", None)
        prop = arb.prop if arb is not None else None
        rows = []
        for st in WEFAX_STATIONS:
            rows.append(("WEFAX", st, st.get("period", "")))
        for st in RTTY_WEATHER_STATIONS:
            mode = "NAVTEX" if "NAVTEX" in st.get("protocol", "") else "RTTY"
            prog = _program_of(st["id"]) or st.get("period", "")
            rows.append((mode, st, prog))
        out = []
        for mode, st, prog in rows:
            e = prop.get(st["id"]) if prop is not None else None
            out.append((mode, st, prog, e))
        order = {"WEFAX": 0, "RTTY": 1, "NAVTEX": 2}
        out.sort(key=lambda r: (order[r[0]], -(r[3].quality if r[3] else -1)))
        return out

    def _fill_station_tree(self, tree):
        try:
            sel = tree.selection()
            tree.delete(*tree.get_children())
        except tk.TclError:
            return
        cur_freq = float(getattr(self.radio, "actual_freq_khz", 0.0))
        now = time.time()
        for mode, st, prog, e in self._station_rows():
            if e is None:
                qual, state, age, tag = "—", "jamais mesurée", "—", "none"
            else:
                qual = f"{e.quality} %"
                state = ("✓ émission reconnue · " if e.active else "") + (e.detail or "")
                mins = int((now - e.measured) // 60)
                age = (f"il y a {mins} min" if mins < 120 else f"il y a {mins // 60} h") + f" ({e.source})"
                tag = "good" if e.quality >= 70 and e.active else ("mid" if e.quality >= 40 else "bad")
            tags = [tag]
            if abs(cur_freq - st["freq"]) < 0.8:
                tags.append("current")
            tree.insert(
                "",
                "end",
                iid=st["id"],
                tags=tags,
                values=(
                    mode, st["id"], st["station"], f"{st['freq']:.1f}", prog, qual, state, age,
                    self.spectral_cell(st["id"]) if hasattr(self, "spectral_cell") else "—",
                ),
            )
        for s in sel:
            if tree.exists(s):
                tree.selection_add(s)

    def _refresh_propagation_views(self):
        for tree in list(getattr(self, "_station_trees", [])):
            try:
                if tree.winfo_exists():
                    self._fill_station_tree(tree)
                else:
                    self._station_trees.remove(tree)
            except tk.TclError:
                self._station_trees.remove(tree)

    # ------------------------------------------------------------- choix manuel (2.11.0)
    def _release_manual_hold(self):
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None and hasattr(arb, "release_manual_hold"):
            arb.release_manual_hold()
        self._on_manual_hold_changed()

    def _on_manual_hold_changed(self):
        """Bouton « Stations » de l'écran principal : montre le choix opérateur en cours.

        Synchronise aussi le bouton ⟳ Auto (2.13.0) : un choix de station active
        operator_choice sans changer requested_mode, donc _update_auto_btn doit être
        appelé ici pour que le bouton orange apparaisse / disparaisse correctement.
        """
        btn = getattr(self, "btn_stations", None)
        if btn is None:
            return
        arb = getattr(self, "hybrid_arbiter", None)
        hold = getattr(arb, "operator_choice", None) if arb is not None else None
        try:
            if hold:
                btn.configure(text=f"🔒 {hold['station']} (forcé par opérateur)", bg="#b45309", fg="white")
            else:
                btn.configure(text="Stations", bg=getattr(self, "_btn_stations_bg", "SystemButtonFace"), fg="black")
        except Exception:
            pass
        # Synchroniser le bouton ⟳ Auto avec l'état du choix de station
        if hasattr(self, "_update_auto_btn"):
            self._update_auto_btn()

    # ------------------------------------------------------------- actions
    def _tune_from_tree(self, tree):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("Accorder", "Choisissez d'abord une station dans le tableau.", parent=tree)
            return
        sid = sel[0]
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is None or self.carrier_scan_active or self.connection_busy:
            return
        if not self.radio.handshake_ok:
            messagebox.showwarning("Accorder", "La radio n'est pas connectée.", parent=tree)
            return
        wf = next((s for s in WEFAX_STATIONS if s["id"] == sid), None)
        if wf is not None:
            if self.rx_current_line > 25 and not self.waiting_after_stop:
                if not messagebox.askyesno(
                    "Carte en cours",
                    "Une carte est en cours : l'archiver et changer de fréquence ?",
                    parent=tree,
                ):
                    return
                self._finalize_completed_wefax_chart("QSY opérateur")
            arb.wefax_return_freq_khz, arb.wefax_return_station = float(wf["freq"]), wf["id"]
            # 2.11.0 — le choix est gardé jusqu'à la fin de la carte suivante
            if hasattr(arb, "set_manual_hold"):
                arb.set_manual_hold(wf["id"])
                self._on_manual_hold_changed()
            if arb.active_pipeline == "RTTY":
                arb.end_rtty_and_return(f"Choix opérateur : {wf['id']} ({wf['freq']:.1f} kHz)")
            else:
                self.radio.set_wefax_frequency(wf["freq"], self.apply_usb_offset.get())
                self._sync_ui_from_hardware()
                self.log_event(f"📻 Choix opérateur : {wf['id']} ({wf['freq']:.1f} kHz), sans nouveau scan.")
            self._refresh_propagation_views()
            return
        st = next((s for s in RTTY_WEATHER_STATIONS if s["id"] == sid), None)
        if st is None:
            return
        now = datetime.now(timezone.utc)
        # créneau « opérateur » de 15 min : les règles de fin de bulletin s'appliquent ensuite normalement
        arb.current_item = RttyItem(
            now, now + timedelta(minutes=15), "OPERATEUR", "OPERATEUR", "choix opérateur"
        )
        arb._reset_rtty_tracking()
        arb.switch_to_rtty_pipeline(st, reason=f"Choix opérateur depuis les résultats de scan : {sid}")
        if hasattr(self, "bulletins_ui"):
            self.bulletins_ui.sync_station_combo()
            self.bulletins_ui.refresh_status()
        self._refresh_propagation_views()

    def _measure_from_tree(self, tree):
        arb = getattr(self, "hybrid_arbiter", None)
        sel = list(tree.selection())
        if arb is None or not sel:
            messagebox.showinfo("Mesurer", "Sélectionnez une ou plusieurs stations (Ctrl+clic).", parent=tree)
            return
        if self.rx_current_line > 25 and not self.waiting_after_stop:
            if not messagebox.askyesno(
                "Carte en cours",
                "Une carte est en cours : la mesure va l'interrompre. Continuer ?",
                parent=tree,
            ):
                return
            self._finalize_completed_wefax_chart("Mesure opérateur")
        if not self.radio.handshake_ok or not self.audio_live_connected:
            messagebox.showwarning("Mesurer", "Radio et audio nécessaires.", parent=tree)
            return
        arb.run_veille(sel, reason="Mesure demandée par l'opérateur", max_stations=8)

    def _station_buttons(self, parent, tree):
        bar = tk.Frame(parent, bg=UITheme.BG_PANEL)
        spec = (
            ("📻 Accorder sur la sélection", lambda: self._tune_from_tree(tree), "#047857"),
            ("🤖 Rendre la main à l'automatique", self._release_manual_hold, "#7c2d12"),
            ("📏 Mesurer la sélection", lambda: self._measure_from_tree(tree), "#1d4ed8"),
            ("🔍 Scan complet WEFAX", self._trigger_carrier_scan, "#334155"),
            (
                "🔍 Scan RTTY",
                lambda: self.hybrid_arbiter.trigger_rtty_frequency_scan(family_filter="DWD_RTTY"),
                "#334155",
            ),
        )
        for text, cmd, bg in spec:
            tk.Button(
                bar,
                text=text,
                command=cmd,
                bg=bg,
                fg="#ffffff",
                relief="flat",
                padx=8,
                pady=3,
                cursor="hand2",
            ).pack(side="left", padx=(0, 6), pady=4)
        return bar

    # ------------------------------------------------------------- fenêtre résultats
    def _open_scan_results(self):
        win = getattr(self, "_scan_results_win", None)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            self._refresh_propagation_views()
            return
        win = tk.Toplevel(self.root)
        win.title("Résultats du dernier scan — choix de la fréquence")
        win.configure(bg=UITheme.BG_PANEL)
        win.geometry("1330x500")
        show_over_root(win, self.root)
        win.minsize(640, 300)
        self._scan_results_win = win
        tk.Label(
            win,
            text=(
                "Dernière mesure de chaque fréquence (scan complet, veille automatique ou réception). Double-clic "
                "ou « Accorder » : le poste passe sur la station choisie sans nouveau scan. « Mesurer » : mesure "
                "rapide des seules lignes sélectionnées. « Vu sur le spectre » : niveau lu sur l'écran de spectre "
                "du poste (±250 kHz autour de la fréquence écoutée), sans interrompre la réception."
            ),
            bg=UITheme.BG_PANEL,
            fg=UITheme.TEXT_MUTED,
            justify="left",
            anchor="w",
            wraplength=1000,
        ).pack(fill="x", padx=10, pady=(8, 2))
        frame, tree = self._make_station_tree(win, height=14)
        frame.pack(fill="both", expand=True, padx=10, pady=4)
        self._station_buttons(win, tree).pack(fill="x", padx=10)
        win.bind(
            "<Configure>",
            lambda e: e.widget is win
            and win.winfo_children()[0].configure(wraplength=max(300, e.width - 30)),
        )

        def tick():
            if win.winfo_exists():
                self._refresh_propagation_views()
                win.after(5000, tick)

        win.after(5000, tick)

    # ------------------------------------------------------------- onglet Réglages
    def _build_tab_plan(self, parent):
        arb = getattr(self, "hybrid_arbiter", None)
        plan = (
            arb.plan
            if arb is not None
            else {"categories": [], "programs": [1], "rtty_enabled": True, "veille_enabled": True}
        )
        bg = "#0f172a"
        g0 = tk.LabelFrame(
            parent, text="Position de repli (si la carte n'est pas repérée)", bg=bg, fg="#a6ddef"
        )
        g0.pack(fill="x", padx=5, pady=(4, 10))
        qth = plan.get("qth", [43.58, 7.02])
        self._plan_lat = tk.StringVar(master=self.root, value=f"{float(qth[0]):.2f}")
        self._plan_lon = tk.StringVar(master=self.root, value=f"{float(qth[1]):.2f}")
        self._plan_radius = tk.StringVar(master=self.root, value=str(int(plan.get("radius_km", 500))))
        row0 = tk.Frame(g0, bg=bg)
        row0.pack(fill="x")
        for label, var, w in (
            ("Latitude (° N)", self._plan_lat, 8),
            ("Longitude (° E, négatif = ouest)", self._plan_lon, 8),
            ("Rayon d'intérêt (km)", self._plan_radius, 6),
        ):
            tk.Label(row0, text=label, bg=bg, fg="#cbd5e1").pack(side="left", padx=(0, 4))
            tk.Entry(row0, textvariable=var, width=w).pack(side="left", padx=(0, 14))
        tk.Label(
            g0,
            text=(
                "La zone d'analyse est la CASE placée sur la carte (Réception › Placer la zone d'analyse). Une fois la "
                "carte repérée (Réception › Repérer la carte : 3 croisements méridien / parallèle), le centre et le "
                "rayon de la case sont calculés automatiquement. Cette position ne sert que tant que la carte n'est "
                "pas repérée. Le Cannet : 43,58 N / 7,02 E."
            ),
            bg=bg,
            fg=UITheme.TEXT_MUTED,
            justify="left",
            anchor="w",
            wraplength=520,
        ).pack(fill="x", pady=(4, 0))

        g1 = tk.LabelFrame(
            parent, text="Bulletins texte reçus automatiquement entre les cartes", bg=bg, fg="#a6ddef"
        )
        g1.pack(fill="x", padx=5, pady=(4, 10))
        self._plan_rtty_var = tk.BooleanVar(master=self.root, value=bool(plan["rtty_enabled"]))
        tk.Checkbutton(
            g1,
            text="Recevoir les bulletins RTTY / NAVTEX choisis ci-dessous (mode hybride)",
            variable=self._plan_rtty_var,
            bg=bg,
            fg="#e2e8f0",
            selectcolor="#1e293b",
            activebackground=bg,
            anchor="w",
        ).pack(fill="x")
        self._plan_cat_vars = {}
        for key, label in CATEGORIES.items():
            v = tk.BooleanVar(master=self.root, value=key in plan["categories"])
            self._plan_cat_vars[key] = v
            tk.Checkbutton(
                g1,
                text=label,
                variable=v,
                bg=bg,
                fg="#cbd5e1",
                selectcolor="#1e293b",
                activebackground=bg,
                anchor="w",
                padx=18,
            ).pack(fill="x")
        row = tk.Frame(g1, bg=bg)
        row.pack(fill="x", pady=(6, 0))
        tk.Label(row, text="Programmes RTTY du DWD :", bg=bg, fg="#cbd5e1").pack(side="left")
        self._plan_prog_vars = {}
        for p in (1, 2):
            v = tk.BooleanVar(master=self.root, value=p in plan["programs"])
            self._plan_prog_vars[p] = v
            ids = ", ".join(PROGRAM_STATIONS[p])
            tk.Checkbutton(
                row,
                text=f"{PROGRAM_LABEL[p]} — {ids}",
                variable=v,
                bg=bg,
                fg="#cbd5e1",
                selectcolor="#1e293b",
                activebackground=bg,
            ).pack(side="left", padx=6)
        tk.Label(
            g1,
            text=(
                "Règles : les cartes WEFAX sont prioritaires. Une carte en cours n'est jamais interrompue ; un "
                "bulletin n'est pris que s'il tient avant la carte suivante (≈ 5 min, NAVTEX 10 min) et une carte "
                "qui commence l'interrompt, avis compris. Retour aux cartes dès la fin du bulletin (NNNN ou "
                "boucle « RYRY / CQ »). L'ordre des catégories ci-dessus fixe la priorité."
            ),
            bg=bg,
            fg=UITheme.TEXT_MUTED,
            justify="left",
            anchor="w",
            wraplength=520,
        ).pack(fill="x", pady=(6, 0))

        self._build_text_station_frame(parent, arb, bg)

        g3 = tk.LabelFrame(parent, text="Cartes de la Méditerranée (Athènes)", bg=bg, fg="#a6ddef")
        g3.pack(fill="x", padx=5, pady=(0, 10))
        self._plan_athens_var = tk.BooleanVar(master=self.root, value=bool(plan.get("athens_enabled", True)))
        tk.Checkbutton(
            g3,
            text="Écouter Athènes chaque jour de 08:45 à 10:45 UTC (8105 kHz le jour, 4481 kHz)",
            variable=self._plan_athens_var,
            bg=bg,
            fg="#e2e8f0",
            selectcolor="#1e293b",
            activebackground=bg,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            g3,
            text="Seul émetteur de cartes centrées sur la Méditerranée. Prévu pour la Grèce : la réception au "
            "Cannet reste à confirmer. Une carte en cours n'est jamais interrompue pour y aller.",
            bg=bg,
            fg="#94a3b8",
            justify="left",
            wraplength=520,
        ).pack(fill="x", pady=(4, 0))

        g2 = tk.LabelFrame(parent, text="Veille de propagation", bg=bg, fg="#a6ddef")
        g2.pack(fill="x", padx=5, pady=(0, 10))
        self._plan_veille_var = tk.BooleanVar(master=self.root, value=bool(plan.get("veille_enabled", True)))
        tk.Checkbutton(
            g2,
            text="Mesurer régulièrement les autres fréquences (30 min le jour, 45 min la nuit)",
            variable=self._plan_veille_var,
            bg=bg,
            fg="#e2e8f0",
            selectcolor="#1e293b",
            activebackground=bg,
            anchor="w",
        ).pack(fill="x")
        self._plan_spectral_var = tk.BooleanVar(master=self.root, value=bool(plan.get("spectral_watch", True)))
        tk.Checkbutton(
            g2,
            text="Veille spectrale : lire le spectre du poste toutes les 2 min (autres stations de la bande, sans coupure)",
            variable=self._plan_spectral_var,
            bg=bg,
            fg="#e2e8f0",
            selectcolor="#1e293b",
            activebackground=bg,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            g2,
            text=(
                "Uniquement dans le temps mort qui suit la fin d'une carte, au plus 4 fréquences de 3 s "
                "chacune, puis retour sur la fréquence de départ : la radio est peu sollicitée et la table "
                "ci-dessous reste à jour pour choisir directement la meilleure fréquence."
            ),
            bg=bg,
            fg=UITheme.TEXT_MUTED,
            justify="left",
            anchor="w",
            wraplength=520,
        ).pack(fill="x")
        tk.Button(
            g2,
            text="💾 Enregistrer le plan de réception",
            command=self._save_plan_from_ui,
            bg="#047857",
            fg="#ffffff",
            relief="flat",
            padx=10,
            pady=4,
        ).pack(anchor="w", pady=(8, 2))

        g3 = tk.LabelFrame(parent, text="Stations, fréquences et dernier scan", bg=bg, fg="#a6ddef")
        g3.pack(fill="both", expand=True, padx=5, pady=(0, 10))
        frame, tree = self._make_station_tree(g3, height=10)
        frame.pack(fill="both", expand=True)
        self._station_buttons(g3, tree).pack(fill="x")

        g4 = tk.LabelFrame(parent, text="Prochains bulletins planifiés", bg=bg, fg="#a6ddef")
        g4.pack(fill="x", padx=5, pady=(0, 10))
        self.lbl_plan_next = tk.Label(
            g4, text="", bg=bg, fg="#cbd5e1", justify="left", anchor="w", font=("Consolas", 9), wraplength=520
        )
        self.lbl_plan_next.pack(fill="x")
        self._refresh_plan_next()

    def _build_text_station_frame(self, parent, arb, bg):
        """2.9.2 — stations NAVTEX / RTTY : activation, état (sommeil automatique), réactivation."""
        from wefax_station.hybrid.text_station_health import STATION_NAMES

        health = getattr(arb, "text_health", None) if arb is not None else None
        g = tk.LabelFrame(parent, text="Stations texte (NAVTEX / RTTY) : écoute et mise en sommeil", bg=bg, fg="#a6ddef")
        g.pack(fill="x", padx=5, pady=(0, 10))
        self._plan_station_vars = {}
        self._plan_station_labels = {}
        if health is None:
            tk.Label(g, text="Indisponible (ordonnanceur non démarré).", bg=bg, fg="#94a3b8").pack(anchor="w")
            return g
        for key, name in STATION_NAMES.items():
            row = tk.Frame(g, bg=bg)
            row.pack(fill="x")
            v = tk.BooleanVar(master=self.root, value=health.is_enabled(key))
            self._plan_station_vars[key] = v
            tk.Checkbutton(row, text=name, variable=v, bg=bg, fg="#e2e8f0", selectcolor="#1e293b",
                           activebackground=bg, anchor="w", width=40).pack(side="left")
            tk.Button(row, text="Réactiver", relief="flat", bg="#334155", fg="#ffffff", padx=6,
                      command=lambda k=key: self._reactivate_text_station(k)).pack(side="right")
            lbl = tk.Label(g, text="", bg=bg, fg="#94a3b8", justify="left", anchor="w", wraplength=520, padx=24)
            lbl.pack(fill="x")
            self._plan_station_labels[key] = lbl
        tk.Label(
            g,
            text=(
                "Une station écoutée jusqu'au bout de son créneau sans texte décodé compte un échec ; après 3 échecs "
                "de suite (NAVTEX) ou 5 (RTTY DWD), elle est mise en sommeil puis réessayée une fois par jour "
                "(NAVTEX) ou toutes les 6 h (RTTY). Une réception la réactive. Le temps gagné va aux cartes."
            ),
            bg=bg, fg=UITheme.TEXT_MUTED, justify="left", anchor="w", wraplength=520,
        ).pack(fill="x", pady=(4, 0))
        self._refresh_text_station_labels()
        return g

    def _refresh_text_station_labels(self):
        arb = getattr(self, "hybrid_arbiter", None)
        health = getattr(arb, "text_health", None)
        for key, lbl in (getattr(self, "_plan_station_labels", None) or {}).items():
            try:
                lbl.configure(text=health.status_text(key) if health else "")
            except tk.TclError:
                pass

    def _reactivate_text_station(self, key):
        arb = getattr(self, "hybrid_arbiter", None)
        health = getattr(arb, "text_health", None)
        if health is None:
            return
        health.reset(key)
        v = (getattr(self, "_plan_station_vars", None) or {}).get(key)
        if v is not None:
            v.set(True)
        self.log_event(f"✅ [STATIONS TEXTE] {key} réactivée par l'opérateur (compteur remis à zéro).")
        self._refresh_text_station_labels()
        self._refresh_plan_next()

    def _refresh_plan_next(self):
        arb = getattr(self, "hybrid_arbiter", None)
        lbl = getattr(self, "lbl_plan_next", None)
        if arb is None or lbl is None:
            return
        try:
            items = arb.scheduler.next_items(datetime.now(timezone.utc), n=8)
            text = "\n".join(it.describe() for it in items) or "Aucun bulletin d'intérêt dans les 4 h."
            lbl.configure(text=text)
            lbl.after(60000, self._refresh_plan_next)
        except tk.TclError:
            pass

    def _save_plan_from_ui(self):
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is None:
            return
        cats = [k for k in CATEGORIES if self._plan_cat_vars[k].get()]
        progs = [p for p in (1, 2) if self._plan_prog_vars[p].get()]
        if not progs:
            progs = [1]
            self._plan_prog_vars[1].set(True)
        try:
            float(self._plan_lat.get().replace(",", "."))
            float(self._plan_lon.get().replace(",", "."))
            float(self._plan_radius.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Position", "Latitude, longitude et rayon doivent être des nombres.")
            return
        health = getattr(arb, "text_health", None)
        if health is not None:
            for key, v in (getattr(self, "_plan_station_vars", None) or {}).items():
                if bool(v.get()) != health.is_enabled(key):
                    health.set_enabled(key, bool(v.get()))
                    self.log_event(
                        f"🗓️ [STATIONS TEXTE] {key} {'activée' if v.get() else 'désactivée'} par l'opérateur."
                    )
            self._refresh_text_station_labels()
        arb.save_plan(
            {
                "categories": cats,
                "programs": progs,
                "rtty_enabled": bool(self._plan_rtty_var.get()),
                "veille_enabled": bool(self._plan_veille_var.get()),
                "athens_enabled": bool(self._plan_athens_var.get()),
                "spectral_watch": bool(self._plan_spectral_var.get()),
                "qth": [
                    float(self._plan_lat.get().replace(",", ".")),
                    float(self._plan_lon.get().replace(",", ".")),
                ],
                "radius_km": max(50, min(3000, int(float(self._plan_radius.get().replace(",", "."))))),
            }
        )
        self._refresh_plan_next()
