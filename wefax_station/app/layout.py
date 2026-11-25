"""Construction et mise en forme de la fenêtre principale (onglets, bandeaux, styles, fenêtres annexes)."""

import sys
import tkinter as tk
from tkinter import ttk
from wefax_station.core.schedules import WEFAX_STAGES
from wefax_station.ui.theme import UITheme
from wefax_station.ui.widgets import SegmentedRadioGroup, SwitchCheckButton
from wefax_station.version import SOFTWARE_TITLE


class LayoutMixin:
    # ------------------------------------------------------------ structure
    def _build_ui(self):
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title(f"Réglages — {SOFTWARE_TITLE} (Radio / Image / Bulletin)")
        self.settings_window.geometry("620x700")
        self.settings_window.protocol("WM_DELETE_WINDOW", self.settings_window.withdraw)
        self.settings_window.withdraw()
        self.diagnostics_window = tk.Toplevel(self.root)
        self.diagnostics_window.title(f"Diagnostics — {SOFTWARE_TITLE} (Signal et journal)")
        self.diagnostics_window.geometry("760x500")
        self.diagnostics_window.protocol("WM_DELETE_WINDOW", self.diagnostics_window.withdraw)
        self.diagnostics_window.withdraw()
        self._build_permanent_top_bar(self.root)
        self._build_folder_navigation_bar(self.settings_window)
        self._build_permanent_log_dock(self.diagnostics_window)
        self._build_right_map_area(self.root)
        status = tk.Frame(self.root, bg="#0b1424")
        status.pack(fill="x", side="bottom")
        self.lbl_status = tk.Label(
            status, text="Prêt", bg="#0b1424", fg="#a6ddef", anchor="w", justify="left"
        )
        self.lbl_status.pack(fill="x", expand=True, side="left")
        self.lbl_mouse_coords = tk.Label(status, text="", bg="#0b1424", fg="#95a7bb")
        self.lbl_mouse_coords.pack(side="right")
        status.bind("<Configure>", lambda e: self.lbl_status.configure(wraplength=max(200, e.width - 190)))
        self.root.bind("<F1>", lambda e: self._general_help())

    def _build_folder_navigation_bar(self, parent):
        nav = tk.Frame(parent, bg="#090d16", padx=8, pady=6)
        nav.pack(fill="x", pady=(0, 9))
        self.tab_widgets = {}
        self.tab_frames = {}
        for key, title in (
            ("RADIO", "1 · Radio"),
            ("IMAGE", "2 · Image"),
            ("METEO", "3 · Opérateur & observations"),
            ("PLAN", "4 · Plan de réception"),
        ):
            frame = tk.Frame(nav, bg="#334155", padx=1, pady=1)
            frame.pack(side="left", fill="x", expand=True, padx=3)
            label = tk.Label(frame, text=title, font=("Segoe UI", 10, "bold"), padx=4, pady=7, cursor="hand2")
            label.pack(fill="x")
            label.bind("<Button-1>", lambda event, k=key: self._select_navigation_tab(k))
            self.tab_widgets[key] = (frame, label, title)
        self.pages_container = tk.Frame(parent, bg="#0f172a")
        self.pages_container.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self._page_canvases = {}
        for key in ("RADIO", "IMAGE", "METEO", "PLAN"):
            outer = tk.Frame(self.pages_container, bg="#0f172a")
            canvas = tk.Canvas(outer, bg="#0f172a", highlightthickness=0)
            scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            inner = tk.Frame(canvas, bg="#0f172a")
            window = canvas.create_window((0, 0), window=inner, anchor="nw")
            inner.bind("<Configure>", lambda event, c=canvas: c.configure(scrollregion=c.bbox("all")))
            horizontal = ttk.Scrollbar(outer, orient="horizontal", command=canvas.xview)
            horizontal.pack(side="bottom", fill="x", before=scroll)
            canvas.configure(xscrollcommand=horizontal.set)
            canvas.bind(
                "<Configure>",
                lambda event, c=canvas, w=window: c.itemconfigure(w, width=max(540, event.width)),
            )
            self.tab_frames[key] = outer
            self._page_canvases[key] = canvas
            setattr(
                self,
                "page_" + {"RADIO": "radio", "IMAGE": "image", "METEO": "meteo", "PLAN": "plan"}[key],
                inner,
            )
        self._build_tab_radio(self.page_radio)
        self._build_tab_image_and_operator(self.page_image)
        self._build_tab_weather(self.page_meteo)
        self._compact_groups(self.page_radio)
        self._compact_groups(self.page_image)
        self.root.bind_all("<MouseWheel>", self._scroll_left, add="+")
        self._select_navigation_tab("RADIO")

    def _select_navigation_tab(self, active_key: str):
        if active_key == "PLAN" and not getattr(self, "_plan_tab_built", False):
            self._plan_tab_built = True  # construit à la première ouverture (l'arbitre existe alors)
            self._build_tab_plan(self.page_plan)
            self._compact_groups(self.page_plan)
        for k, frame in self.tab_frames.items():
            frame.pack_forget()
        self.tab_frames[active_key].pack(fill="both", expand=True)

        for k, (outer, lbl, base_title) in self.tab_widgets.items():
            clean_title = self._clean_ui_label25(base_title)
            if k == active_key:
                outer.config(bg=UITheme.BORDER_ACTIVE)
                lbl.config(text=clean_title, bg=UITheme.ACCENT, fg="#ffffff", font=("Segoe UI", 9, "bold"))
            else:
                outer.config(bg=UITheme.BORDER)
                lbl.config(
                    text=clean_title, bg=UITheme.BG_SURFACE, fg=UITheme.TEXT_MUTED, font=("Segoe UI", 9)
                )

    def _scroll_left(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        for canvas in self._page_canvases.values():
            current = widget
            while current is not None:
                if current == canvas.master:
                    canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
                    return
                current = getattr(current, "master", None)

    def _compact_groups(self, parent):
        for frame in list(parent.winfo_children()):
            if not isinstance(frame, tk.LabelFrame) or not frame.winfo_manager():
                continue
            frame.pack_configure(padx=5, pady=(4, 14))
            frame.configure(padx=8, pady=8, bd=1, relief="groove")
            title = str(frame.cget("text")).strip()
            label = tk.Label(
                frame,
                text="▾  " + title,
                bg="#17263e",
                fg="#a6ddef",
                font=("Segoe UI", 9, "bold"),
                padx=7,
                pady=5,
                cursor="hand2",
                anchor="w",
                wraplength=425,
            )
            frame.configure(text="")
            children = list(frame.winfo_children())
            packed = [(w, w.pack_info()) for w in children if w is not label and w.winfo_manager() == "pack"]
            label.pack(fill="x", before=packed[0][0] if packed else None, pady=(0, 5))
            state = [True]

            def toggle(event=None, items=packed, status=state, head=label, text=title):
                status[0] = not status[0]
                for widget, info in items:
                    if status[0]:
                        widget.pack(**{k: v for k, v in info.items() if k != "in"})
                    else:
                        widget.pack_forget()
                head.configure(text=("▾  " if status[0] else "▸  ") + text)

            label.bind("<Button-1>", toggle)
            self.fold_sections.append((label, toggle))

    # Bandeau supérieur : construction 2.4 puis réorganisation « cockpit 3 colonnes » 2.5
    def _build_permanent_top_bar(self, parent):
        self._build_permanent_top_bar_base(parent)
        for name in (
            "bargraph_canvas",
            "top_signal_canvas",
            "lbl_spectrum_header",
            "lbl_sched_current",
            "lbl_sched_next",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.destroy()

        self.lbl_freq_display.configure(font=("Consolas", 12, "bold"), fg=UITheme.TEXT_PRIMARY)
        self.lbl_radio_details.configure(font=("Consolas", 9), fg=UITheme.TEXT_MUTED)

        self.dashboard25 = tk.Frame(parent, bg=UITheme.BG_ROOT, padx=6, pady=2)
        self.dashboard25.pack(fill="x", padx=0, pady=0)

        # COLONNE 1 : TÉLÉMÉTRIE RF & TRAITEMENT (Compacte)
        self.metrics25 = tk.Frame(
            self.dashboard25,
            bg=UITheme.BG_PANEL,
            highlightbackground=UITheme.BORDER,
            highlightthickness=1,
            padx=8,
            pady=4,
        )
        tk.Label(
            self.metrics25,
            text="TÉLÉMÉTRIE RF & TRAITEMENT",
            fg=UITheme.TEXT_MUTED,
            bg=UITheme.BG_PANEL,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 2))
        self.bargraph_canvas = tk.Canvas(
            self.metrics25, width=265, height=68, bg=UITheme.BG_ROOT, highlightthickness=0
        )
        self.bargraph_canvas.pack(fill="both", expand=True)

        # COLONNE 2 (INTERCALÉE AU CENTRE) : INFOS RÉCEPTEUR HF + HORAIRES UTC + BOUTONS D'ACTION
        self.center_hub25 = tk.Frame(
            self.dashboard25,
            bg=UITheme.BG_PANEL,
            highlightbackground=UITheme.BORDER,
            highlightthickness=1,
            padx=8,
            pady=4,
        )
        self.lbl_hw_state25 = tk.Label(
            self.center_hub25,
            text="",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=2,
            anchor="w",
            justify="left",
            highlightbackground=UITheme.BORDER,
            highlightthickness=1,
        )
        self.lbl_hw_state25.pack(fill="x", pady=(0, 2))

        sched_row = tk.Frame(self.center_hub25, bg=UITheme.BG_PANEL)
        sched_row.pack(fill="x", pady=(0, 3))
        sched_row.columnconfigure(0, weight=1)
        sched_row.columnconfigure(1, weight=1)

        self.lbl_sched_current = tk.Label(
            sched_row,
            text="Créneau théorique : chargement...",
            bg=UITheme.BG_PANEL,
            fg=UITheme.TEXT_MUTED,
            font=("Segoe UI", 8),
            anchor="w",
            justify="left",
        )
        self.lbl_sched_current.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.lbl_sched_next = tk.Label(
            sched_row,
            text="Prochaine émission : chargement...",
            bg=UITheme.BG_PANEL,
            fg=UITheme.TEXT_PRIMARY,
            font=("Segoe UI", 8, "bold"),
            anchor="e",
            justify="right",
        )
        self.lbl_sched_next.grid(row=0, column=1, sticky="ew")

        self.controls_slot25 = tk.Frame(self.center_hub25, bg=UITheme.BG_PANEL)
        self.controls_slot25.pack(fill="x", pady=(1, 0))

        # COLONNE 3 (À DROITE) : SPECTRE BF TEMPS RÉEL (Longueur réduite et équilibrée)
        self.spectrum25 = tk.Frame(
            self.dashboard25,
            bg=UITheme.BG_PANEL,
            highlightbackground=UITheme.BORDER,
            highlightthickness=1,
            padx=8,
            pady=4,
        )
        self.lbl_spectrum_header = tk.Label(
            self.spectrum25,
            text="SPECTRE BF (1500 Noir · 1900 · 2300 Blanc)",
            fg=UITheme.TEXT_MUTED,
            bg=UITheme.BG_PANEL,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_spectrum_header.pack(fill="x", pady=(0, 2))
        self.top_signal_canvas = tk.Canvas(
            self.spectrum25, width=340, height=68, bg=UITheme.BG_ROOT, highlightthickness=0
        )
        self.top_signal_canvas.pack(fill="both", expand=True)

        self.center_hub25.bind("<Configure>", lambda e: self._wrap_schedule25(e.width))
        self.dashboard25.bind("<Configure>", self._layout_dashboard25)
        self.dashboard_mode25 = None
        self._layout_dashboard25()
        self._register_tip25(self.bargraph_canvas, "snr")
        self._register_tip25(self.metrics25, "rf")
        self._register_tip25(self.lbl_hw_state25, "demarrage")
        self.bargraph_canvas.bind("<Motion>", self._bar_help25, add="+")
        self._register_tip25(self.top_signal_canvas, "spectre")
        self._register_tip25(self.lbl_spectrum_header, "spectre")
        self._register_tip25(self.lbl_sched_current, "programmes")
        self._register_tip25(self.lbl_sched_next, "programmes")

    def _build_permanent_top_bar_base(self, parent):
        self.qsy_policy = tk.StringVar(value="Confirmation")
        self.prevent_sleep = tk.BooleanVar(value=True)
        menu = tk.Menu(self.root)
        tools = tk.Menu(menu, tearoff=False)
        for label, command in [
            ("Radio", lambda: self._show_settings("RADIO")),
            ("Image", lambda: self._show_settings("IMAGE")),
            ("Bulletin / observations", lambda: self._show_settings("METEO")),
            ("Plan de réception (bulletins, veille)", lambda: self._show_settings("PLAN")),
            ("Diagnostics", self._show_diagnostics),
            ("Météo & bulletin (réceptions, analyse, rédaction)", self._open_bulletin_desk),
            ("Calcul du vent géostrophique", self._weather_dialog),
            ("Journal CSV", self._open_csv),
            ("Dossier archives", self._open_archive),
            ("Aide", self._general_help),
        ]:
            tools.add_command(label=label, command=command)
        if not getattr(sys, "frozen", False):
            tools.add_command(label="Compiler .exe", command=self._compile_exe)
        menu.add_cascade(label="Outils", menu=tools)
        policy = tk.Menu(menu, tearoff=False)
        for val in ("Jamais", "Confirmation", "Automatique"):
            policy.add_radiobutton(label="Rescan : " + val, variable=self.qsy_policy, value=val)
        policy.add_checkbutton(label="Empêcher la veille", variable=self.prevent_sleep)
        menu.add_cascade(label="Automatisation", menu=policy)
        self.root.configure(menu=menu)
        band = tk.Frame(parent, bg="#101c30", padx=8, pady=3)
        band.pack(fill="x")
        band.columnconfigure(1, weight=1)
        tk.Button(
            band, text="Démarrer en auto", command=self._one_click, bg="#047857", fg="white", padx=8
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.lbl_freq_display = tk.Label(
            band, text="Station WEFAX", font=("Segoe UI", 13, "bold"), bg="#101c30", fg="#55cfea", anchor="w"
        )
        self.lbl_freq_display.grid(row=0, column=1, sticky="ew")
        self.lbl_radio_details = tk.Label(
            band, text="", bg="#101c30", fg="#b3c4d8", anchor="w", justify="left"
        )
        self.lbl_radio_details.grid(row=0, column=2, sticky="e", padx=(10, 10))
        tk.Button(band, text="Réglages", command=self._show_settings).grid(row=0, column=3, padx=3)
        # 2.10.0 — le bouton porte aussi l'aperçu du secteur à 3-6 h (niveau et indice de fiabilité)
        self.btn_meteo_desk = tk.Button(
            band, text="Météo & bulletin", command=self._open_bulletin_desk, justify="center"
        )
        self.btn_meteo_desk.grid(row=0, column=4, padx=3)
        # 2.11.0 — accès direct à la liste des stations : choix manuel si le scan automatique se trompe
        self.btn_stations = tk.Button(band, text="Stations", command=self._open_scan_results)
        self.btn_stations.grid(row=0, column=5, padx=3)
        self._btn_stations_bg = self.btn_stations.cget("bg")
        # 2.12.0 — bouton « Rendre la main à l'automatique » : visible/actif dès que le contrôle n'est
        # plus automatique (mode MANUEL, pause manuelle, etc.). Un clic restaure le mode HYBRIDE.
        self.btn_auto_restore = tk.Button(
            band,
            text="⟳ Auto",
            command=self._give_back_to_auto,
            relief="raised",
        )
        self.btn_auto_restore.grid(row=0, column=6, padx=3)
        self.btn_auto_restore.grid_remove()  # caché par défaut ; affiché par _update_auto_btn()

        box = tk.Frame(self.diagnostics_window, bg="#0b1424", padx=8, pady=8)
        box.pack(fill="both", expand=True)
        badges = tk.Frame(box, bg="#0b1424")
        badges.pack(fill="x")
        for name in ("lbl_cat_badge", "lbl_daynight_badge", "lbl_busy_badge"):
            label = tk.Label(badges, text="En attente", bg="#334155", fg="white")
            label.pack(side="left", padx=4)
            setattr(self, name, label)
        self.lbl_sched_current = tk.Label(
            box, text="Programme indicatif", wraplength=650, anchor="w", justify="left"
        )
        self.lbl_sched_current.pack(fill="x")
        self.lbl_sched_next = tk.Label(box, text="", wraplength=650, anchor="w", justify="left")
        self.lbl_sched_next.pack(fill="x")
        self.bargraph_canvas = tk.Canvas(box, height=60, bg="#020617", highlightthickness=0)
        self.bargraph_canvas.pack(fill="x")
        self.lbl_spectrum_header = tk.Label(box, text="Spectre audio", anchor="w")
        self.lbl_spectrum_header.pack(fill="x")
        self.top_signal_canvas = tk.Canvas(box, height=110, bg="#020617", highlightthickness=0)
        self.top_signal_canvas.pack(fill="both", expand=True)

    # Zone carte : construction 2.4 puis déplacement des commandes dans la colonne centrale 2.5
    def _build_right_map_area(self, parent):
        self._build_right_map_area_base(parent)
        # 1. Déplacement des boutons Cartes / Réception / Traitée / Décodée / Comparer / Décodage / Ajuster
        # directement dans la colonne centrale intercalée entre Télémétrie et Spectre !
        old_toolbar = getattr(self, "map_toolbar_frame", None)
        if old_toolbar is not None and hasattr(self, "controls_slot25"):
            old_toolbar.pack_forget()
            for child in list(old_toolbar.winfo_children()):
                child.destroy()
            old_toolbar.destroy()

            bar = self.controls_slot25
            choices = tk.Menubutton(bar, text="Cartes ▾", relief="flat")
            choices.pack(side="left", padx=(0, 3))
            cm = tk.Menu(
                choices,
                tearoff=False,
                bg=UITheme.BG_PANEL,
                fg=UITheme.TEXT_PRIMARY,
                activebackground=UITheme.ACCENT,
                activeforeground="#ffffff",
            )
            for label, command in [
                ("Dernière carte", self._show_completed),
                ("Réception directe", self._show_live),
                ("Historique", self._history),
                ("Ouvrir", self._load_wefax_file),
                ("Exporter PNG", self._save_stamped_wefax),
                ("Corriger marge / slant", self._geometry_dialog),
                ("Carte Web (Internet)", self._download_web_weather_chart),
            ]:
                cm.add_command(label=label, command=command)
            choices.configure(menu=cm)

            rx = tk.Menubutton(bar, text="Réception ▾", relief="flat")
            rx.pack(side="left", padx=3)
            rm = tk.Menu(
                rx,
                tearoff=False,
                bg=UITheme.BG_PANEL,
                fg=UITheme.TEXT_PRIMARY,
                activebackground=UITheme.ACCENT,
                activeforeground="#ffffff",
            )
            rm.add_command(label="Reprendre en milieu de carte", command=self._resume_midchart)
            rm.add_command(label="Estimer marge / slant", command=self._run_auto_margin_and_slant)
            rm.add_command(label="Scanner les 7 fréquences", command=self._trigger_carrier_scan)
            rm.add_command(
                label="Résultats du dernier scan / choisir la fréquence…", command=self._open_scan_results
            )
            rx.configure(menu=rm)

            self.grp_display_mode = SegmentedRadioGroup(
                bar,
                options=[("PROCESSED", "Traitée", ""), ("RAW", "Décodée", ""), ("SPLIT", "Comparer", "")],
                command=self._on_display_mode_changed,
                default_value=self.display_mode,
            )
            self.grp_display_mode.pack(side="left", padx=4)

            self.btn_top_rx = SwitchCheckButton(
                bar, text="Décodage", command=self._toggle_rx_decoding, initial=self.rx_decoding_active
            )
            self.btn_top_rx.pack(side="left", padx=4)

            tk.Button(bar, text="Ajuster 100%", command=self._reset_zoom_pan).pack(side="right", padx=(4, 0))

        # 2. Suppression de la barre de compteur séparée : les labels seront logés directement
        # dans l'en-tête du bandeau de réception (gain de 28 px supplémentaires)
        if hasattr(self, "lbl_archive_state") and hasattr(self, "lbl_rx_line_counter"):
            info_bar = self.lbl_rx_line_counter.master
            self.lbl_archive_state.pack_forget()
            info_bar.pack_forget()

    def _build_right_map_area_base(self, parent):
        self.map_toolbar_frame = row = tk.Frame(parent, bg="#172338", padx=6, pady=3)
        row.pack(fill="x")
        choices = tk.Menubutton(row, text="Cartes ▾", relief="raised")
        choices.pack(side="left", padx=3)
        cm = tk.Menu(choices, tearoff=False)
        for label, command in [
            ("Dernière carte", self._show_completed),
            ("Réception directe", self._show_live),
            ("Historique", self._history),
            ("Ouvrir", self._load_wefax_file),
            ("Exporter PNG", self._save_stamped_wefax),
            ("Corriger marge / slant", self._geometry_dialog),
            ("Carte Web (Internet)", self._download_web_weather_chart),
        ]:
            cm.add_command(label=label, command=command)
        choices.configure(menu=cm)
        rx = tk.Menubutton(row, text="Réception ▾", relief="raised")
        rx.pack(side="left", padx=3)
        rm = tk.Menu(rx, tearoff=False)
        rm.add_command(label="Reprendre en milieu de carte", command=self._resume_midchart)
        rm.add_command(label="Estimer marge / slant", command=self._run_auto_margin_and_slant)
        rx.configure(menu=rm)
        self.grp_display_mode = SegmentedRadioGroup(
            row,
            options=[("PROCESSED", "Traitée", ""), ("RAW", "Décodée", ""), ("SPLIT", "Comparer", "")],
            command=self._on_display_mode_changed,
            default_value="PROCESSED",
        )
        self.grp_display_mode.pack(side="left", padx=3)
        self.btn_top_rx = SwitchCheckButton(
            row, text="Décodage", command=self._toggle_rx_decoding, initial=True
        )
        self.btn_top_rx.pack(side="left", padx=3)
        tk.Button(row, text="Ajuster", command=self._reset_zoom_pan).pack(side="right")
        self.lbl_archive_state = tk.Label(
            parent, text="", anchor="w", bg="#0b1424", fg="#91cbb3", justify="left"
        )
        self.lbl_archive_state.pack(fill="x")
        state = tk.Frame(parent, bg="#0b1424")
        state.pack(fill="x")
        self.lbl_rx_line_counter = tk.Label(state, text="En attente", bg="#0b1424", fg="#34d399", anchor="w")
        self.lbl_rx_line_counter.pack(fill="x")
        for code, title in WEFAX_STAGES:
            self.stage_badge_widgets[code] = tk.Label(state, text=title)
        self.canvas = tk.Canvas(parent, bg="#050811", highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        binds = {
            "<Configure>": lambda e: self._refresh_canvas(),
            "<Motion>": self._on_canvas_motion,
            "<ButtonPress-1>": self._on_left_down,
            "<ButtonRelease-1>": self._on_left_up,
            "<ButtonPress-3>": self._on_right_down,
            "<ButtonRelease-3>": self._on_right_up,
            "<Double-Button-1>": self._on_double_click_zoom,
            "<ButtonPress-2>": self._on_middle_down,
            "<B2-Motion>": self._on_middle_drag,
            "<ButtonRelease-2>": self._on_middle_up,
            "<MouseWheel>": self._on_mouse_wheel,
        }
        for event, callback in binds.items():
            self.canvas.bind(event, callback)
        self.canvas.bind("<Button-4>", lambda e: self._zoom_at_point(e.x, e.y, 1.18))
        self.canvas.bind("<Button-5>", lambda e: self._zoom_at_point(e.x, e.y, 1 / 1.18))
        parent.bind("<Configure>", self._wrap_main_labels, add="+")
        self._responsive_toolbar(row)

    def _responsive_toolbar(self, frame):
        widgets = list(frame.winfo_children())
        previous = [None]

        def layout(event=None):
            width = max(200, frame.winfo_width() - 8)
            desired = tuple(max(36, w.winfo_reqwidth()) + 6 for w in widgets)
            signature = (width, desired)
            if signature == previous[0]:
                return
            previous[0] = signature
            for widget in widgets:
                widget.pack_forget()
                widget.grid_forget()
            row = column = used = 0
            for widget, required in zip(widgets, desired):
                if used and used + required > width:
                    row += 1
                    column = used = 0
                widget.grid(row=row, column=column, padx=2, pady=1, sticky="w")
                used += required
                column += 1

        frame.bind("<Configure>", layout, add="+")
        frame.after_idle(layout)

    def _wrap_main_labels(self, event):
        if event.widget is not self.root:
            return
        width = max(250, event.width - 25)
        self.lbl_archive_state.configure(wraplength=width)
        self.lbl_rx_line_counter.configure(wraplength=width)

    def _layout_dashboard25(self, event=None):
        width = max(400, self.dashboard25.winfo_width())
        mode = "three_cols" if width >= 980 else "stacked"
        if mode == getattr(self, "dashboard_mode25", None):
            return
        self.dashboard_mode25 = mode
        self.metrics25.grid_forget()
        self.center_hub25.grid_forget()
        self.spectrum25.grid_forget()
        if mode == "three_cols":
            self.dashboard25.columnconfigure(0, weight=0)
            self.dashboard25.columnconfigure(1, weight=5)
            self.dashboard25.columnconfigure(2, weight=4)
            self.metrics25.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
            self.center_hub25.grid(row=0, column=1, sticky="nsew", padx=(0, 5))
            self.spectrum25.grid(row=0, column=2, sticky="nsew")
        else:
            self.dashboard25.columnconfigure(0, weight=1)
            self.dashboard25.columnconfigure(1, weight=1)
            self.dashboard25.columnconfigure(2, weight=0)
            self.metrics25.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=(0, 3))
            self.spectrum25.grid(row=0, column=1, sticky="nsew", pady=(0, 3))
            self.center_hub25.grid(row=1, column=0, columnspan=2, sticky="nsew")

    def _layout_station_status_complete(self):
        from tkinter import font as tkfont

        win = self.settings_window
        win.resizable(True, True)
        old = self.tree_freqs
        saved = [(iid, old.item(iid)) for iid in old.get_children()]
        selected = old.selection()
        old.master.pack_forget()
        panel = tk.LabelFrame(
            win, text="Stations et resultat du scan", bg=UITheme.BG_PANEL, fg=UITheme.TEXT_PRIMARY
        )
        first = next(
            (w for w in win.winfo_children() if w is not panel and w.winfo_manager() == "pack"), None
        )
        options = dict(side="bottom", fill="x", padx=4, pady=4)
        if first is not None:
            options["before"] = first
        panel.pack(**options)
        # 2.8 : le tableau unifié (onglet « Plan de réception » et fenêtre « Résultats du dernier scan »)
        # remplace ce tableau WEFAX seul, masqué pour laisser la place aux réglages (le widget reste actif).
        self.root.after(50, panel.pack_forget)
        body = tk.Frame(panel)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        columns = ("id", "station", "freq", "dial", "period", "snr")
        display = ("id", "station", "freq", "dial", "period", "snr")
        tree = ttk.Treeview(
            body,
            columns=columns,
            displaycolumns=display,
            show="headings",
            height=7,
            style="StationsFit.Treeview",
        )
        titles = {
            "id": "Indic.",
            "station": "Station",
            "freq": "RF kHz",
            "dial": "USB kHz",
            "period": "Periode",
            "snr": "WEFAX / proxy",
        }
        for col in columns:
            tree.heading(col, text=titles[col])
            tree.column(col, minwidth=0, stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        ys = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        ys.grid(row=0, column=1, sticky="ns")
        xs = ttk.Scrollbar(body, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        for iid, item in saved:
            tree.insert("", "end", iid=iid, values=item["values"], tags=item["tags"])
        if selected:
            tree.selection_set(selected)
        self.tree_freqs = tree
        old.destroy()
        detail = tk.Label(
            panel,
            text="Survolez une station pour lire ses valeurs completes",
            anchor="w",
            justify="left",
            bg=UITheme.BG_PANEL,
            fg=UITheme.TEXT_PRIMARY,
        )
        detail.pack(fill="x", padx=3, pady=3)
        style = ttk.Style(tree)
        cell_font = tkfont.Font(root=tree, family="Consolas", size=9)
        head_font = tkfont.Font(root=tree, family="Segoe UI", size=8)
        style.configure("StationsFit.Treeview", font=cell_font, rowheight=22)
        style.configure("StationsFit.Treeview.Heading", font=head_font)
        cache = [None]
        # 2.10.0 — mesure avec des polices à part : reconfigurer la police des cellules (9, 8, 7 pt) à
        # chaque essai relançait la mise en page de TOUTE la liste, chaque seconde (≈ 0,2 s par appel,
        # 70 % du temps d'interface mesuré pendant une réception simulée). Rien n'est recalculé si ni la
        # largeur ni le contenu n'ont changé.
        measure_fonts = {size: tkfont.Font(root=tree, family="Consolas", size=size) for size in (9, 8, 7)}
        content_cache = [None]

        def fit(event=None):
            if not tree.winfo_exists():
                return
            available = max(1, tree.winfo_width() - 4)
            rows = tuple(tuple(tree.item(iid, "values")) for iid in tree.get_children())
            if content_cache[0] == (available, rows):
                return
            content_cache[0] = (available, rows)
            values = [dict(zip(columns, r)) for r in rows]
            required = None
            chosen = 9
            for size in (9, 8, 7):
                mf = measure_fonts[size]
                required = {
                    col: max(
                        [head_font.measure(titles[col])] + [mf.measure(str(row.get(col, ""))) for row in values]
                    )
                    + 14
                    for col in columns
                }
                chosen = size
                if sum(required.values()) <= available:
                    break
            if int(cell_font.cget("size")) != chosen:
                cell_font.configure(size=chosen)
            signature = (available, tuple(required.values()))
            if cache[0] == signature:
                return
            cache[0] = signature
            if sum(required.values()) <= available:
                xs.grid_remove()
                spare = available - sum(required.values())
                required["station"] += spare // 2
                required["snr"] += spare - spare // 2
                tree.xview_moveto(0)
            else:
                xs.grid(row=1, column=0, sticky="ew")
            for col, w in required.items():
                tree.column(col, width=w, minwidth=0, stretch=False)
            detail.configure(wraplength=max(180, available - 12))

        def show(row):
            if not row:
                return
            data = dict(zip(columns, tree.item(row, "values")))
            detail.configure(
                text=f"{data.get('id','')} — {data.get('station','')} | RF {data.get('freq','')} kHz | USB {data.get('dial','')} kHz | {data.get('period','')} | WEFAX : {data.get('snr','')}"
            )

        tree.bind("<Configure>", fit, add="+")
        tree.bind("<Motion>", lambda e: show(tree.identify_row(e.y)), add="+")
        tree.bind("<<TreeviewSelect>>", self._on_station_row_clicked)
        tree.bind("<<TreeviewSelect>>", lambda e: show(next(iter(tree.selection()), "")), add="+")

        def refresh():
            if not tree.winfo_exists():
                return
            fit()
            row = next(iter(tree.selection()), "")
            if row:
                show(row)
            tree.after(1000, refresh)

        tree.after_idle(refresh)
        group = self.grp_if_filter
        for idx in (1, 2, 3):
            if idx in group.buttons:
                button, _ = group.buttons[idx]
                group.buttons[idx] = (button, f"FIL{idx} (memoire poste)")
        group.set_value(group.current_value, trigger_callback=False)
        self.log_event(
            "BUILD UI_STATIONS_FIT_3 : colonnes mesurees selon police/contenu et largeur reelle ; CAT inchangee"
        )

    def _dashboard_tick25(self):
        if self.closing:
            return
        self._update_programme()
        self._draw_three_quality_bargraphs()
        self.root.after(5000, self._dashboard_tick25)

    def _update_startup_readiness_banner25(self):
        if not hasattr(self, "lbl_hw_state25"):
            return
        cat_ok = bool(self.radio.port_open and self.radio.handshake_ok)
        aud_ok = bool(self.audio_live_connected)

        if cat_ok and aud_ok:
            msg = (
                f"● Poste HF opérationnel — {self.radio.cat_label} · "
                f"{self.radio.actual_mode_str} / {self.radio.actual_filter_str} / AGC {self.radio.actual_agc_str} · "
                f"Audio USB ({self.audio_fs} Hz)"
            )
            self.lbl_hw_state25.configure(
                text=msg, bg="#0f291e", fg=UITheme.OK_FG, highlightbackground=UITheme.OK_BG
            )
        elif cat_ok and not aud_ok:
            msg = "▲ CAT connecté mais Audio USB inactif — Choisir le codec IC-705 dans Réglages"
            self.lbl_hw_state25.configure(
                text=msg, bg="#2e1f0f", fg=UITheme.WARN_FG, highlightbackground=UITheme.WARN_BG
            )
        elif aud_ok and not cat_ok:
            msg = "▲ Audio USB actif mais CAT inactif — Cliquez sur « Démarrer en auto »"
            self.lbl_hw_state25.configure(
                text=msg, bg="#2e1f0f", fg=UITheme.WARN_FG, highlightbackground=UITheme.WARN_BG
            )
        else:
            msg = "○ En attente de connexion matérielle (CAT + Audio USB) — Cliquez sur « Démarrer en auto »"
            self.lbl_hw_state25.configure(
                text=msg, bg=UITheme.BG_SURFACE, fg=UITheme.TEXT_MUTED, highlightbackground=UITheme.BORDER
            )

    # ---------------------------------------------------- fenêtres annexes
    def _fit_window(self, window, width, height):
        sw = window.winfo_screenwidth()
        sh = window.winfo_screenheight()
        window.geometry(f"{max(400,min(width,sw-50))}x{max(300,min(height,sh-100))}")

    def _show_settings(self, tab="RADIO"):
        self._select_navigation_tab(tab)
        self._fit_window(self.settings_window, 860, 720)
        self.settings_window.deiconify()
        self.settings_window.lift()
        self._style_widget_tree25(self.settings_window)
        self._select_navigation_tab(tab)
        self._install_help(self.settings_window)

    def _show_diagnostics(self):
        self._fit_window(self.diagnostics_window, 760, 500)
        self.diagnostics_window.deiconify()
        self.diagnostics_window.lift()
        self._style_widget_tree25(self.diagnostics_window)
