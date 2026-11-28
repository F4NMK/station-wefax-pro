"""Onglets de la fenêtre Réglages : Radio, Image & opérateur, Bulletin météo."""

from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk
from wefax_station.core.web_charts import WEB_WEATHER_CHARTS
from wefax_station.deps import HAS_SERIAL, serial
from wefax_station.radio.controller import UnifiedRadioController
from wefax_station.ui.widgets import SegmentedRadioGroup, SwitchCheckButton
from wefax_station.version import SOFTWARE_BRAND


class SettingsTabsMixin:
    def _build_tab_radio(self, parent):
        f_cat = tk.LabelFrame(
            parent,
            text=" 🔌 Transceiver HF & Entrée Audio USB (IC-705 / Yaesu) ",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=2,
        )
        f_cat.pack(fill="x", padx=4, pady=2)

        r_auto = tk.Frame(f_cat, bg="#0f172a")
        r_auto.pack(fill="x", pady=1)

        btn_autodetect = tk.Button(
            r_auto,
            text="▶ AUTO-CONNEXION IC-705 / YAESU (CAT + USB-D + Audio)",
            command=self._run_auto_detect_cat_and_audio,
            bg="#1d4ed8",
            fg="#ffffff",
            font=("Segoe UI", 8, "bold"),
            pady=2,
            relief="raised",
            bd=2,
            cursor="hand2",
        )
        btn_autodetect.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_cat_conn = SwitchCheckButton(
            r_auto, text="LIAISON CAT", command=self._toggle_manual_cat, initial=False
        )
        self.btn_cat_conn.pack(side="right")

        r_proto = tk.Frame(f_cat, bg="#0f172a")
        r_proto.pack(fill="x", pady=1)
        tk.Label(r_proto, text="Modèle :", bg="#0f172a", fg="#cbd5e1", font=("Segoe UI", 8)).pack(side="left")
        self.cmb_proto = ttk.Combobox(
            r_proto, values=UnifiedRadioController.PROTOCOLS, state="readonly", width=38
        )
        self.cmb_proto.set(UnifiedRadioController.PROTOCOLS[-1])  # AUTO : Icom puis Yaesu
        self.cmb_proto.pack(side="right")

        r_port = tk.Frame(f_cat, bg="#0f172a")
        r_port.pack(fill="x", pady=1)
        tk.Label(r_port, text="Port:", bg="#0f172a", fg="#cbd5e1", font=("Segoe UI", 8)).pack(side="left")
        ports = (
            [p.device for p in serial.tools.list_ports.comports()]
            if HAS_SERIAL
            else ["COM14", "COM5", "COM3"]
        )
        if not ports:
            ports = ["COM14", "COM5", "COM3"]
        self.cmb_port = ttk.Combobox(r_port, values=ports, width=9)
        self.cmb_port.set(ports[0])
        self.cmb_port.pack(side="left", padx=2)

        tk.Button(
            r_port,
            text="🔄",
            command=self._refresh_com_ports_list,
            bg="#1e293b",
            fg="#38bdf8",
            font=("Segoe UI", 8),
            padx=3,
            cursor="hand2",
        ).pack(side="left", padx=1)

        tk.Label(r_port, text="Baud:", bg="#0f172a", fg="#cbd5e1", font=("Segoe UI", 8)).pack(
            side="left", padx=2
        )
        self.cmb_baud = ttk.Combobox(r_port, values=["4800", "9600", "19200", "38400", "115200"], width=7)
        self.cmb_baud.set("19200")
        self.cmb_baud.pack(side="left", padx=2)

        tk.Label(r_port, text="CI-V:", bg="#0f172a", fg="#cbd5e1", font=("Segoe UI", 8)).pack(
            side="left", padx=2
        )
        self.ent_civ = tk.Entry(r_port, width=4, bg="#1e293b", fg="#ffffff", insertbackground="white")
        self.ent_civ.insert(0, "A4")
        self.ent_civ.pack(side="left")

        r_aud = tk.Frame(f_cat, bg="#0f172a")
        r_aud.pack(fill="x", pady=(2, 1))
        tk.Label(r_aud, text="Audio RX :", bg="#0f172a", fg="#38bdf8", font=("Segoe UI", 8, "bold")).pack(
            side="left"
        )
        audio_devs = self._enumerate_audio_input_devices()
        self.cmb_audio = ttk.Combobox(r_aud, values=audio_devs, state="readonly", width=32)
        self.cmb_audio.current(0)
        self.cmb_audio.pack(side="left", fill="x", expand=True, padx=3)
        self.cmb_audio.bind("<<ComboboxSelected>>", self._on_audio_device_selected)

        btn_aud_auto = tk.Button(
            r_aud,
            text="🎙️ Auto IC-705",
            command=self._auto_connect_ic705_audio,
            bg="#0284c7",
            fg="#ffffff",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            cursor="hand2",
        )
        btn_aud_auto.pack(side="right")

        f_rf = tk.LabelFrame(
            parent,
            text=" 🛡️ Étage RF, Filtre FI IC-705 (USB-D / AGC FAST) & Contre-Réaction ",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=2,
        )
        f_rf.pack(fill="x", padx=4, pady=2)

        self.grp_preamp = SegmentedRadioGroup(
            f_rf,
            group_title="PRÉAMPLIFICATEUR HF",
            options=[
                (0, "P.AMP 0 (IPO)", "Préampli coupé"),
                (1, "P.AMP 1 (Optimal)", "Préampli 1 activé par défaut"),
                (2, "P.AMP 2 (Max)", "Préampli 2 grand gain"),
            ],
            command=self._set_rf_preamp,
            default_value=1,
            active_bg="#0284c7",
        )
        self.grp_preamp.pack(fill="x", pady=(1, 2))

        self.grp_if_filter = SegmentedRadioGroup(
            f_rf,
            group_title="FILTRE FI IC-705 EN MODE USB-D (AGC FAST + NB ON + NR OFF)",
            options=[
                (1, "FIL1 (Large 3.0k)", "Filtre large"),
                (2, "FIL2 (Optimal WEFAX 2.4k)", "Optimal pour 1500..2300 Hz à 120 RPM"),
                (3, "FIL3 (Étroit QRM)", "Filtre serré si fort QRM adjacent"),
            ],
            command=self._on_if_filter_changed,
            default_value=2,
            active_bg="#059669",
        )
        self.grp_if_filter.pack(fill="x", pady=(1, 2))

        rf2 = tk.Frame(f_rf, bg="#0f172a")
        rf2.pack(fill="x", pady=1)
        self.btn_att = SwitchCheckButton(
            rf2,
            text="ATTÉNUATEUR (-20dB)",
            command=self._toggle_rf_att,
            initial=False,
            active_color="#b45309",
            active_fg="#ffffff",
        )
        self.btn_att.pack(side="left", expand=True, fill="x", padx=(0, 2))

        self.btn_auto_rf = SwitchCheckButton(
            rf2, text="AUTO RF (P.AMP + ATT)", command=self._toggle_auto_rf_loop, initial=True
        )
        self.btn_auto_rf.pack(side="left", expand=True, fill="x", padx=(2, 0))

        f_scan = tk.LabelFrame(
            parent,
            text=" 🌐 Les 7 Émetteurs WEFAX (Scan Intégral Jour+Nuit) — Cliquez pour QSY ",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=2,
        )
        f_scan.pack(fill="both", expand=True, padx=4, pady=2)

        sc_row = tk.Frame(f_scan, bg="#0f172a")
        sc_row.pack(fill="x", pady=1)
        self.btn_daynight = SwitchCheckButton(
            sc_row, text="VEILLE JOUR/NUIT UTC", command=self._toggle_auto_daynight, initial=True
        )
        self.btn_daynight.pack(side="left", expand=True, fill="x", padx=(0, 2))

        self.btn_scan_carrier = tk.Button(
            sc_row,
            text="▶ SCANNER LES 7 FRÉQUENCES (JOUR+NUIT)",
            command=self._trigger_carrier_scan,
            bg="#1d4ed8",
            fg="#ffffff",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=2,
            relief="raised",
            bd=2,
            cursor="hand2",
        )
        self.btn_scan_carrier.pack(side="left", expand=True, fill="x", padx=(2, 0))
        tk.Button(
            sc_row,
            text="📋 RÉSULTATS",
            command=self._open_scan_results,
            bg="#334155",
            fg="#ffffff",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=2,
            relief="raised",
            bd=2,
            cursor="hand2",
        ).pack(side="left", padx=(2, 0))
        self._add_tip(
            self.btn_scan_carrier,
            "Balaie les 7 fréquences (Jour ET Nuit sans exclusion) et sélectionne celle qui offre\n"
            "réellement le meilleur SNR In-Band à votre QTH à l'instant T.",
        )

        tree_container = tk.Frame(f_scan, bg="#090d16")
        tree_container.pack(fill="both", expand=True, pady=2)

        cols = ("id", "station", "freq", "dial", "period", "snr")
        self.tree_freqs = ttk.Treeview(tree_container, columns=cols, show="headings", height=6)
        for cid, lbl, w, anc in [
            ("id", "Indic.", 48, "center"),
            ("station", "Station Émettrice", 118, "w"),
            ("freq", "Porteuse", 64, "e"),
            ("dial", "Dial USB-D", 66, "e"),
            ("period", "Optimum", 66, "center"),
            ("snr", "SNR Mesuré", 74, "center"),
        ]:
            self.tree_freqs.heading(cid, text=lbl)
            self.tree_freqs.column(cid, width=w, anchor=anc)

        tree_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree_freqs.yview)
        self.tree_freqs.configure(yscrollcommand=tree_scroll.set)
        self.tree_freqs.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        self.tree_freqs.bind("<<TreeviewSelect>>", self._on_station_row_clicked)
        self._populate_freq_table()
        self.tree_freqs.selection_set("DDK3")

        web_row = tk.Frame(f_scan, bg="#0f172a")
        web_row.pack(fill="x", pady=(2, 1))
        self.cmb_web_chart = ttk.Combobox(
            web_row, values=list(WEB_WEATHER_CHARTS.keys()), state="readonly", width=33
        )
        self.cmb_web_chart.current(0)
        self.cmb_web_chart.pack(side="left", fill="x", expand=True, padx=(0, 3))

        btn_dl_web = tk.Button(
            web_row,
            text="🌐 Télécharger Carte Web",
            command=self._download_web_weather_chart,
            bg="#059669",
            fg="#ffffff",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=2,
            relief="raised",
            bd=2,
            cursor="hand2",
        )
        btn_dl_web.pack(side="right")

    def _build_tab_image_and_operator(self, parent):
        self._build_tab_image_and_operator_base(parent)
        for frame in parent.winfo_children():
            if isinstance(frame, tk.LabelFrame) and "Signature" in frame.cget("text"):
                frame.pack_forget()
        geo = tk.LabelFrame(parent, text="Orientation et géométrie", bg="#0f172a", fg="#9dd4e7")
        geo.pack(fill="x")
        row = tk.Frame(geo, bg="#0f172a")
        row.pack(fill="x", pady=4)
        tk.Button(row, text="↶ 90°", command=lambda: self._rotate(-1)).pack(side="left", padx=3)
        tk.Button(row, text="↷ 90°", command=lambda: self._rotate(1)).pack(side="left", padx=3)
        tk.Button(row, text="Corriger la carte affichée…", command=self._geometry_dialog).pack(
            side="left", padx=3
        )
        self.lbl_slant_state = tk.Label(
            geo, text="Slant : 0,000 px/ligne · marge en attente", fg="#cbd5e1", bg="#0f172a", anchor="w"
        )
        self.lbl_slant_state.pack(fill="x", pady=5)

    def _build_tab_image_and_operator_base(self, parent):
        f_qth = tk.LabelFrame(
            parent,
            text=" 📍 Positionnement du Repère 06/83 & Zone d'Analyse Météo ",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=2,
        )
        f_qth.pack(fill="x", padx=4, pady=2)

        r_q1 = tk.Frame(f_qth, bg="#0f172a")
        r_q1.pack(fill="x", pady=1)
        self.btn_overlay_dept = SwitchCheckButton(
            r_q1, text="AFFICHER REPÈRES 06/83", command=self._toggle_dept_overlay, initial=True
        )
        self.btn_overlay_dept.pack(side="left", expand=True, fill="x", padx=(0, 2))

        self.btn_move_qth = SwitchCheckButton(
            r_q1,
            text="PLACER REPÈRE AU CLIC GAUCHE",
            command=self._toggle_move_qth_mode,
            initial=False,
            active_color="#0284c7",
        )
        self.btn_move_qth.pack(side="left", expand=True, fill="x", padx=(2, 0))

        r_nudge = tk.Frame(f_qth, bg="#090d16", bd=1, relief="sunken", padx=4, pady=2)
        r_nudge.pack(fill="x", pady=1)
        tk.Label(
            r_nudge, text="Déplacer Repère & Zone :", bg="#090d16", fg="#cbd5e1", font=("Segoe UI", 8, "bold")
        ).pack(side="left", padx=(2, 6))

        for lbl_b, dx, dy in [
            ("◀ Gauche", -0.02, 0.0),
            ("▲ Haut", 0.0, -0.02),
            ("▼ Bas", 0.0, 0.02),
            ("▶ Droite", 0.02, 0.0),
        ]:
            b = tk.Button(
                r_nudge,
                text=lbl_b,
                command=lambda x=dx, y=dy: self._nudge_qth_position(x, y),
                bg="#1e293b",
                fg="#38bdf8",
                font=("Segoe UI", 8, "bold"),
                padx=5,
                pady=1,
                cursor="hand2",
            )
            b.pack(side="left", padx=2)

        r_sz = tk.Frame(f_qth, bg="#0f172a")
        r_sz.pack(fill="x", pady=1)
        tk.Label(r_sz, text="Taille Zone Cible :", bg="#0f172a", fg="#cbd5e1", font=("Segoe UI", 8)).pack(
            side="left"
        )
        self.sld_roi_size = tk.Scale(
            r_sz,
            from_=3,
            to=18,
            resolution=1,
            orient="horizontal",
            bg="#0f172a",
            fg="#38bdf8",
            highlightthickness=0,
            troughcolor="#1e293b",
            command=self._on_roi_size_slider_changed,
        )
        self.sld_roi_size.set(7)
        self.sld_roi_size.pack(side="left", fill="x", expand=True, padx=4)

        f_geo = tk.LabelFrame(
            parent,
            text=" 📡 Décodage 120 RPM (Armé), Anti-QSB 2D, Auto-Marge & Auto-Save ",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=2,
        )
        f_geo.pack(fill="x", padx=4, pady=2)

        r_rx = tk.Frame(f_geo, bg="#0f172a")
        r_rx.pack(fill="x", pady=1)
        self.btn_rx_start = SwitchCheckButton(
            r_rx, text="DÉCODAGE 120 RPM (ARMÉ)", command=self._toggle_rx_decoding, initial=True
        )
        self.btn_rx_start.pack(side="left", expand=True, fill="x", padx=(0, 2))

        self.btn_apt_auto = SwitchCheckButton(
            r_rx, text="AUTO-START/STOP APT", command=self._toggle_apt_auto, initial=True
        )
        self.btn_apt_auto.pack(side="left", expand=True, fill="x", padx=(2, 0))

        r_live_cond = tk.Frame(f_geo, bg="#0f172a")
        r_live_cond.pack(fill="x", pady=1)
        self.btn_hf_cond = SwitchCheckButton(
            r_live_cond,
            text="CONDITIONNEUR HF & ANTI-QSB 2D",
            command=self._toggle_upstream_hf_cond,
            initial=True,
        )
        self.btn_hf_cond.pack(side="left", expand=True, fill="x", padx=(0, 2))

        self.btn_auto_margin_once = SwitchCheckButton(
            r_live_cond, text="AUTO-MARGE DÉBUT", command=self._toggle_auto_margin_once, initial=True
        )
        self.btn_auto_margin_once.pack(side="left", expand=True, fill="x", padx=(2, 0))

        r_rx2 = tk.Frame(f_geo, bg="#0f172a")
        r_rx2.pack(fill="x", pady=1)
        self.btn_qrn_blanker = SwitchCheckButton(
            r_rx2, text="BLANKER QRN AMONT", command=self._toggle_qrn_blanker, initial=True
        )
        self.btn_qrn_blanker.pack(side="left", expand=True, fill="x", padx=(0, 2))

        self.btn_autosave_png = SwitchCheckButton(
            r_rx2, text="AUTO-SAVE PNG FIN CARTE", command=self._toggle_auto_save_png, initial=True
        )
        self.btn_autosave_png.pack(side="left", expand=True, fill="x", padx=(2, 2))

        tk.Button(
            r_rx2,
            text="🆕 Feuille Vierge",
            command=self._reset_blank_rx_sheet,
            bg="#0284c7",
            fg="#ffffff",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=2,
            cursor="hand2",
        ).pack(side="right")

        r_mrg = tk.Frame(f_geo, bg="#0f172a")
        r_mrg.pack(fill="x", pady=1)
        self.btn_mode_margin = SwitchCheckButton(
            r_mrg, text="PLACER MARGE (Clic-G)", command=self._toggle_margin_tool_mode, initial=False
        )
        self.btn_mode_margin.pack(side="left", expand=True, fill="x", padx=(0, 2))

        tk.Button(
            r_mrg,
            text="⚡ Auto-Marge & Slant Maintenant",
            command=self._run_auto_margin_and_slant,
            bg="#1d4ed8",
            fg="#ffffff",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=2,
            relief="raised",
            bd=2,
            cursor="hand2",
        ).pack(side="left", padx=2)

        r_sl = tk.Frame(f_geo, bg="#0f172a")
        r_sl.pack(fill="x")
        tk.Label(r_sl, text="Slant fin :", bg="#0f172a", fg="#cbd5e1", font=("Segoe UI", 8)).pack(side="left")
        self.sld_slant = tk.Scale(
            r_sl,
            from_=-0.06,
            to=0.06,
            resolution=0.00001,
            digits=7,
            orient="horizontal",
            bg="#0f172a",
            fg="#38bdf8",
            highlightthickness=0,
            troughcolor="#1e293b",
            command=self._on_manual_slant_slider,
        )
        self.sld_slant.set(0.0)
        self.sld_slant.pack(side="left", fill="x", expand=True, padx=4)

        f_rest = tk.LabelFrame(
            parent,
            text=" ✨ Restauration Documentaire & Rehaussement des Isobares ",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=2,
        )
        f_rest.pack(fill="x", padx=4, pady=2)

        # 2.8.5 — netteté des cartes à la réception (largeur des filtres du décodeur)
        if not hasattr(self, "sharpness_var"):
            self.sharpness_var = tk.StringVar(master=self.root, value="AUTO")
        f_sharp = tk.Frame(f_rest, bg="#0f172a")
        f_sharp.pack(fill="x", pady=(1, 4))
        tk.Label(f_sharp, text="Netteté à la réception :", bg="#0f172a", fg="#cbd5e1").pack(side="left", padx=(4, 6))
        for value, label in (("AUTO", "Automatique"), ("DETAIL", "Détail (plus net, plus de grain)"), ("ROBUSTE", "Robuste (signal faible)")):
            tk.Radiobutton(
                f_sharp,
                text=label,
                value=value,
                variable=self.sharpness_var,
                command=self._apply_sharpness,
                bg="#0f172a",
                fg="#e2e8f0",
                selectcolor="#1e293b",
                activebackground="#0f172a",
                activeforeground="#ffffff",
            ).pack(side="left", padx=4)

        self.btn_fft2d = SwitchCheckButton(
            f_rest, text="Lissage conservateur", command=self._toggle_fft_filter, initial=True
        )
        self.btn_fft2d.pack(fill="x", pady=1)

        self.btn_tensor = SwitchCheckButton(
            f_rest, text="Préserver les traits fins", command=self._toggle_tensor_filter, initial=True
        )
        self.btn_tensor.pack(fill="x", pady=1)

        self.btn_bin = SwitchCheckButton(
            f_rest, text="Binarisation forte (option avancée)", command=self._toggle_bin_filter, initial=False
        )
        self.btn_bin.pack(fill="x", pady=1)

        r_opt = tk.Frame(f_rest, bg="#0f172a")
        r_opt.pack(fill="x", pady=2)
        tk.Label(r_opt, text="Rideau Split (%) :", bg="#0f172a", fg="#cbd5e1", font=("Segoe UI", 8)).pack(
            side="left"
        )
        self.sld_split = tk.Scale(
            r_opt,
            from_=10,
            to=90,
            resolution=1,
            orient="horizontal",
            bg="#0f172a",
            fg="#10b981",
            highlightthickness=0,
            troughcolor="#1e293b",
            command=self._on_split_slider_changed,
        )
        self.sld_split.set(50)
        self.sld_split.pack(side="left", fill="x", expand=True, padx=4)

        tk.Button(
            r_opt,
            text="⭐ Rétablir Réglages Optimaux",
            command=self._apply_optimal_defaults_preset,
            bg="#059669",
            fg="#ffffff",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=2,
            relief="raised",
            bd=2,
            cursor="hand2",
        ).pack(side="right")

        f_id = tk.LabelFrame(
            parent,
            text=" 🏷️ Signature Bas de Page : Créateur F4NMK + Opérateur + Logo ",
            bg="#0f172a",
            fg="#38bdf8",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=2,
        )
        f_id.pack(fill="x", padx=4, pady=2)

        r_id1 = tk.Frame(f_id, bg="#0f172a")
        r_id1.pack(fill="x", pady=1)
        tk.Label(
            r_id1,
            text=SOFTWARE_BRAND,
            bg="#1e293b",
            fg="#38bdf8",
            font=("Consolas", 8, "bold"),
            padx=6,
            pady=2,
        ).pack(side="left")
        tk.Label(
            r_id1, text=" | Indicatif Opérateur :", bg="#0f172a", fg="#cbd5e1", font=("Segoe UI", 8)
        ).pack(side="left")
        self.ent_operator = tk.Entry(
            r_id1,
            textvariable=self.operator_callsign_var,
            width=13,
            bg="#1e293b",
            fg="#ffffff",
            insertbackground="white",
            font=("Consolas", 9, "bold"),
        )
        self.ent_operator.pack(side="left", padx=3)
        self.ent_operator.bind("<KeyRelease>", lambda e: self._refresh_canvas())

        tk.Button(
            r_id1,
            text="🖼️ Logo...",
            command=self._choose_custom_logo,
            bg="#1d4ed8",
            fg="#ffffff",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            cursor="hand2",
        ).pack(side="right", padx=2)

    def _build_tab_weather(self, parent):
        identity = tk.LabelFrame(
            parent, text="Opérateur et signature", bg="#0f172a", fg="#a6ddef", padx=8, pady=8
        )
        identity.pack(fill="x", padx=5, pady=(4, 12))
        tk.Label(identity, text="Indicatif opérateur", fg="#cbd5e1", bg="#0f172a").grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.ent_operator = tk.Entry(identity, textvariable=self.operator_callsign_var, width=16)
        self.ent_operator.grid(row=0, column=1, sticky="w", padx=6)
        tk.Label(identity, text="Secteur / commune", fg="#cbd5e1", bg="#0f172a").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.zone_var = tk.StringVar(value="Le Cannet / Alpes-Maritimes")
        tk.Entry(identity, textvariable=self.zone_var, width=30).grid(row=1, column=1, sticky="ew", padx=6)
        # 2.8.5 — l'application n'est pas réservée à l'ADRASEC : ce profil adapte les libellés et les documents
        # (rapport « ADRASEC / cellule ORSEC » ou simple « rapport météo »).
        if not hasattr(self, "adrasec_var"):
            self.adrasec_var = tk.BooleanVar(master=self.root, value=False)
        tk.Checkbutton(
            identity,
            text="Membre ADRASEC (rapports au format cellule ORSEC / ADRASEC)",
            variable=self.adrasec_var,
            command=lambda: (self._apply_adrasec_mode(), self._save_preferences()),
            bg="#0f172a",
            fg="#e2e8f0",
            selectcolor="#1e293b",
            activebackground="#0f172a",
            activeforeground="#ffffff",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        logos = tk.Frame(identity, bg="#0f172a")
        logos.grid(row=3, column=0, columnspan=2, sticky="ew", pady=7)
        self.logo_preview = tk.Label(logos, bg="#0f172a", fg="#cbd5e1")
        self.logo_preview.pack(side="left")
        tk.Button(logos, text="Charger un logo…", command=self._choose_custom_logo).pack(side="left", padx=5)
        tk.Button(logos, text="Logo de l'application", command=self._remove_logo).pack(side="left", padx=5)
        fields = tk.LabelFrame(
            parent, text="Observations locales datées", bg="#0f172a", fg="#a6ddef", padx=8, pady=8
        )
        fields.pack(fill="x", padx=5, pady=(0, 12))
        self.obs_time = tk.StringVar(value=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        tk.Label(fields, text="Observation UTC", bg="#0f172a", fg="#cbd5e1").grid(row=0, column=0, sticky="w")
        tk.Entry(fields, textvariable=self.obs_time, width=23).grid(row=0, column=1, sticky="w", pady=3)
        self.ent_press = tk.Entry(fields, width=10)
        self.ent_temp = tk.Entry(fields, width=10)
        self.ent_rh = tk.Entry(fields, width=10)
        for row, label, widget in (
            (1, "Pression hPa", self.ent_press),
            (2, "Température °C", self.ent_temp),
            (3, "Humidité %", self.ent_rh),
        ):
            tk.Label(fields, text=label, bg="#0f172a", fg="#cbd5e1").grid(
                row=row, column=0, sticky="w", pady=3
            )
            widget.grid(row=row, column=1, sticky="w")
        # 2.10.0 — tendance en classes chiffrées (termes des bulletins marins), force du vent et état de la mer :
        # ils alimentent la « Situation actuelle et prévision 3-6 h » du bulletin et son indice de fiabilité.
        from wefax_station.weather.nowcast import (
            OPERATOR_BFT_VALUES,
            OPERATOR_SEA_VALUES,
            OPERATOR_TENDENCY_VALUES,
            OPERATOR_WIND_DIR_VALUES,
        )

        self.cmb_ptrend = ttk.Combobox(fields, values=OPERATOR_TENDENCY_VALUES, width=27, state="readonly")
        self.cmb_wind = ttk.Combobox(fields, values=OPERATOR_WIND_DIR_VALUES, width=27, state="readonly")
        self.cmb_wind_force = ttk.Combobox(fields, values=OPERATOR_BFT_VALUES, width=27, state="readonly")
        self.cmb_sea = ttk.Combobox(fields, values=OPERATOR_SEA_VALUES, width=27, state="readonly")
        self.cmb_sky = ttk.Combobox(
            fields,
            values=["Non renseigné", "Dégagé", "Nuageux", "Couvert", "Pluie", "Averses", "Orage", "Brouillard"],
            width=27,
            state="readonly",
        )
        for row, label, widget in (
            (4, "Tendance 3 h", self.cmb_ptrend),
            (5, "Vent observé (direction)", self.cmb_wind),
            (6, "Vent observé (force)", self.cmb_wind_force),
            (7, "Mer observée", self.cmb_sea),
            (8, "Ciel observé", self.cmb_sky),
        ):
            tk.Label(fields, text=label, bg="#0f172a", fg="#cbd5e1").grid(
                row=row, column=0, sticky="w", pady=3
            )
            widget.grid(row=row, column=1, sticky="w")
            widget.set("Non renseigné")
        actions = tk.Frame(parent, bg="#0f172a")
        actions.pack(fill="x", padx=5, pady=5)
        # 2.8.3 — Cet onglet ne garde que ce qui se RÈGLE ici (opérateur, observations, compléments).
        # Annoter / Repérer la carte, Copier et Enregistrer le bulletin existaient en double avec la fenêtre
        # « Météo & bulletin » : ils ne sont plus qu'à un seul endroit, accessible par le bouton ci-dessous.
        tk.Button(actions, text="Établir / actualiser le bulletin", command=self._generate_bulletin).pack(
            side="left", padx=2
        )
        self.btn_roi_mode = SwitchCheckButton(
            actions, text="Zone manuelle", command=self._toggle_roi_mode, initial=False
        )
        self.btn_roi_mode.pack(side="left", padx=2)
        tk.Button(
            actions,
            text="Ouvrir Météo & bulletin ▸",
            command=self._open_bulletin_desk,
            bg="#1d4ed8",
            fg="#ffffff",
        ).pack(side="right", padx=2)
        tk.Label(
            parent,
            text="Compléments de l'opérateur — repris dans la partie C du bulletin (fenêtre Météo & bulletin)",
            fg="#cbd5e1",
            bg="#0f172a",
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 0))
        self.lbl_reliability = tk.Label(
            parent, text="Confiance : non calibrée", fg="#e2c275", bg="#0f172a", anchor="w"
        )
        self.lbl_reliability.pack(fill="x", padx=8)
        self.lbl_alert_badge = tk.Label(
            parent, text="Faits / hypothèses séparés", fg="#a5b6ca", bg="#0f172a", anchor="w"
        )
        self.lbl_alert_badge.pack(fill="x", padx=8)
        self.txt_weather_report = tk.Text(
            parent,
            height=14,
            wrap="word",
            undo=True,
            bg="#091322",
            fg="#e2e8f0",
            insertbackground="white",
            padx=9,
            pady=8,
            font=("Segoe UI", 10),
        )
        self.txt_weather_report.pack(fill="both", expand=True, padx=5, pady=8)
        self.txt_weather_report.bind("<<Modified>>", self._bulletin_modified)
