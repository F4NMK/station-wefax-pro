"""Fenêtre principale : composition des domaines fonctionnels et séquence d'initialisation.

L'ordre des phases d'initialisation reproduit exactement l'ordre d'exécution de l'ancienne
cascade de constructeurs (V2.0 → 2.1 → 2.3 → 2.4 → 2.5 → bandeau → socle portable/RTTY).
"""

from wefax_station.core.schedules import SCHEDULE_REV
import os
from wefax_station.storage import portable as portable_storage
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
import numpy as np
import cv2
from wefax_station.app.archives import ArchivesMixin
from wefax_station.app.georef_tool import GeorefToolMixin
from wefax_station.app.bulletin_desk import BulletinDeskMixin
from wefax_station.app.canvas_view import CanvasViewMixin
from wefax_station.app.help_system import HelpMixin
from wefax_station.app.image_tools import ImageToolsMixin
from wefax_station.app.layout import LayoutMixin
from wefax_station.app.lifecycle import LifecycleMixin
from wefax_station.app.menus import MenusMixin
from wefax_station.app.teleprinter_panel import TeleprinterPanelMixin
from wefax_station.app.winlink_desk import WinlinkDeskMixin
from wefax_station.app.spectral_watch import SpectralWatchMixin
from wefax_station.app.operator_profile import OperatorProfileMixin
from wefax_station.app.recording import RecordingMixin
from wefax_station.app.responsive import ResponsiveLayoutMixin
from wefax_station.app.radio_link import RadioLinkMixin
from wefax_station.app.reception import ReceptionMixin
from wefax_station.app.reception_plan import ReceptionPlanMixin
from wefax_station.app.scanner import ScannerMixin
from wefax_station.app.settings_tabs import SettingsTabsMixin
from wefax_station.app.styling import StylingMixin
from wefax_station.app.telemetry import TelemetryMixin
from wefax_station.app.weather_desk import WeatherDeskMixin
from wefax_station.core.schedules import BROADCAST_SCHEDULES_UTC
from wefax_station.core.stations import WEFAX_STATIONS
from wefax_station.dsp.engine import WefaxSignalAndImageEngine
from wefax_station.hybrid.arbiter import HybridModeArbiter
from wefax_station.hybrid.planner import ScheduleSyncAndPlanner
from wefax_station.hybrid.window import BulletinsAndHybridWindow
from wefax_station.radio.controller import UnifiedRadioController
from wefax_station.rtty.decoder import RTTYITA2Decoder
from wefax_station.rtty.translator import OfflineWeatherTranslator
from wefax_station.storage.atomic import atomic_json
from wefax_station.storage.portable import PortableWorkspaceManager
from wefax_station.ui.reception_banner import ReceptionStepBanner
from wefax_station.ui.theme import UITheme
from wefax_station.validation import check_validated
from wefax_station.version import SOFTWARE_BRAND, SOFTWARE_TITLE, SOFTWARE_VERSION
from wefax_station.weather.synoptic import SynopticWeatherAnalysisEngine


class StationWefaxApp(
    LifecycleMixin,
    MenusMixin,
    TeleprinterPanelMixin,
    WinlinkDeskMixin,
    SpectralWatchMixin,
    LayoutMixin,
    SettingsTabsMixin,
    StylingMixin,
    HelpMixin,
    RadioLinkMixin,
    ScannerMixin,
    ReceptionMixin,
    ImageToolsMixin,
    CanvasViewMixin,
    TelemetryMixin,
    ArchivesMixin,
    WeatherDeskMixin,
    OperatorProfileMixin,
    RecordingMixin,
    ResponsiveLayoutMixin,
    ReceptionPlanMixin,
    BulletinDeskMixin,
    GeorefToolMixin,
):
    """Station WEFAX Pro — fenêtre principale."""

    def __init__(self, root):
        # 1. État initial, avant la construction de l'interface
        self._init_state_help_and_workspace()
        self._init_state_geometry()
        self._init_state_reception()
        self._init_state_supervision()
        # 2. Fenêtre principale, moteurs DSP / radio et interface graphique
        self._init_main_window(root)
        # 3. Services complémentaires (ordre historique conservé)
        self._init_journal_and_tables()
        self._init_preferences_and_schedules()
        self._init_geometry_tools()
        self._init_cockpit_and_help()
        self._init_reception_banner()
        self._init_portable_and_bulletins()
        self._init_recording()
        self._init_responsive_layout()
        # 2.8.5 : barre de menus unique, construite une fois tous les modules prêts (voir app/menus.py)
        self._rebuild_menubar()
        self._apply_adrasec_mode()
        # 4. Contrôle d'intégrité des modules validés terrain (voir outils/module_guard.py)
        for problem in check_validated():
            self.log_event("⚠️ VALIDATION : " + problem)

    # ------------------------------------------------------------------ phases
    def _init_state_help_and_workspace(self):
        self.help_tips25 = {}
        self.help_window25 = None
        # 2.8.3 — Application entièrement portable : plus rien n'est lu ni écrit dans %LOCALAPPDATA%.
        # Tant que l'espace portable de l'opérateur n'est pas ouvert, les fichiers de démarrage vont dans
        # <dossier de l'application>/StationWEFAXPro/configuration/demarrage.
        self.base_root_dir = str(portable_storage.default_portable_root())
        os.makedirs(os.path.join(self.base_root_dir, "configuration"), exist_ok=True)
        self.global_state_path = Path(self.base_root_dir) / "configuration" / "last_operator.json"
        self._operator_debounce_id = None

    def _init_state_geometry(self):
        self.last_geometry_test = -1

    def _init_state_reception(self):
        self.connection_busy = False
        self.waiting_after_stop = False
        self.completed_rgb = None
        self.completed_raw = None
        self.pin_completed = False
        self.generation = 0
        self.saved_generation = -1
        self.last_saved_path = None
        self.current_metadata_path = None
        self.last_audio_callback = 0.0
        self.audio_status_count = 0
        self.rotation_quarters = 0
        self.power_held = False
        self.tooltip_widgets = set()
        self.fold_sections = []
        self.weather_initialized = False
        self.annotation_cache = []
        self.bulletin_dirty = False
        self.draft_loading = False

    def _init_state_supervision(self):
        self.main_thread = threading.get_ident()
        self.ui_events = queue.Queue()
        self.demo_enabled = False
        self.audio_drop_count = 0
        self.scan_reference = None
        self.degraded_since = None
        self.last_scan_request = 0.0
        self.last_periodic_scan_ts = time.monotonic()
        self.last_day_night_mode = 6 <= datetime.now(timezone.utc).hour < 18
        self.last_quality_line = -1
        self.last_checkpoint = 0.0
        self.last_good_audio = time.monotonic()
        self.csv_path = None
        self.closing = False

    def _init_main_window(self, root):
        self.root = root
        self.root.title(SOFTWARE_TITLE)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        win_w = max(600, min(1560, int(sw * 0.92)))
        win_h = max(440, min(950, int(sh * 0.85)))
        pos_x = max(0, (sw - win_w) // 2)
        pos_y = max(0, (sh - win_h) // 2 - 15)
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.root.minsize(640, 480)
        self.root.configure(bg="#090d16")
        self.compact_screen = sh < 860

        base_dir = os.path.join(str(portable_storage.default_portable_root()), "configuration")
        self.archive_dir = os.path.join(base_dir, "demarrage")
        try:
            os.makedirs(self.archive_dir, exist_ok=True)
        except Exception:
            self.archive_dir = base_dir

        self.radio = UnifiedRadioController(log_callback=self.log_event)
        self.audio_fs = 44100
        self.dsp = WefaxSignalAndImageEngine(sample_rate=self.audio_fs)
        self.wx_engine = SynopticWeatherAnalysisEngine()

        self.is_busy = False
        self.auto_rf_loop_active = True
        self.auto_day_night_active = True
        self.carrier_scan_active = False
        self.rx_decoding_active = True
        self.snr_squelch_threshold_db = 4.5
        self.apt_auto_start_active = True
        self.upstream_hf_cond_active = True
        self.auto_margin_once_active = True
        self.auto_save_png_active = True

        self.line_phase_offset_px = 0
        self.auto_margin_locked_for_chart = False
        self.phase_locked_from_header = False
        self.last_margin_confidence_pct = 0.0
        self.current_wefax_stage = "PORTEUSE"
        self.stage_badge_widgets = {}

        self.audio_stream = None
        self.audio_live_connected = False
        self.rx_audio_queue = queue.Queue(maxsize=400)
        self.rx_sample_accumulator = np.zeros(0, dtype=np.float32)
        self.rx_fractional_rem = 0.0
        self.rx_current_line = 0
        self.rx_sheet_initialized_for_live = False
        self.apt_start_hits = 0
        self.apt_stop_hits = 0
        self._start_window = []
        self._stop_window = []
        self._low_snr_tail_lines = 0
        self.audio_ring = np.zeros(22050, dtype=np.float32)
        self.last_spectrum_info = {
            "snr_db": 0.0,
            "rms_dbfs": -90.0,
            "locked": False,
            "carrier_2300": True,
            "carrier_1500": False,
            "freqs": None,
            "psd_db": None,
        }

        self.display_mode = "PROCESSED"
        self.split_ratio = 0.50

        self.apply_usb_offset = tk.BooleanVar(value=True)
        self.qrn_blanker_var = tk.BooleanVar(value=True)
        self.fft_notch_var = tk.BooleanVar(value=True)
        self.tensor_var = tk.BooleanVar(value=True)
        self.adapt_bin_var = tk.BooleanVar(value=False)
        self.dept_overlay_var = tk.BooleanVar(value=False)

        self.creator_callsign = "F4NMK"
        self.operator_callsign_var = tk.StringVar(value="")
        self.custom_logo_pil = None
        self.custom_logo_path = ""

        self.canvas_tool_mode = "NONE"
        self.pending_margin_x = None
        self.dragging_target = None
        self.qth_rel_pos = [0.585, 0.725]
        self.roi_rel_radius = 0.065
        self.weather_roi_box = None
        self.roi_drag_start = None

        self.zoom_scale = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.left_btn_down = False
        self.right_btn_down = False
        self.pan_start_mouse = None
        self.pan_start_offset = None

        self.current_snr_db = 0.0
        self.carrier_locked = False
        self.wefax_signal_verdict = "no_signal"
        self.station_snr_map = {
            "DDH3": "+15.4 dB",
            "DDK3": "+16.5 dB",
            "DDK6": "+12.8 dB",
            "GYA1": "+7.2 dB",
            "GYA2": "+9.8 dB",
            "GYA3": "+14.1 dB",
            "GYA4": "+11.0 dB",
        }
        self.last_weather_result = {"reliability_pct": 0, "alert": "NON ÉVALUÉ"}

        self.reference_sim_chart = cv2.resize(
            self._generate_realistic_test_wefax("ANA"), (1809, 1200), interpolation=cv2.INTER_LINEAR
        )
        self.raw_wefax_img = np.full((1200, 1809), 248, np.uint8)
        self._recompute_roi_from_qth()
        self.processed_wefax_img = self.dsp.restore_image_v1_9(
            self.raw_wefax_img, use_fft_notch=True, use_structure_tensor=True, use_adaptive_bin=False
        )
        self.tk_img_ref = None

        self._setup_styles()
        self._build_ui()
        self._set_wefax_protocol_stage("PORTEUSE")
        self._refresh_canvas()
        self._run_expert_weather_analysis()

        self.root.after(180, self._realtime_rx_and_spectrum_loop)
        self.root.after(5000, self._periodic_watchdog_tick)

        self.log_event(
            f"🚀 {SOFTWARE_BRAND} prête — Décodage 120 RPM armé (Squelch SNR >= {self.snr_squelch_threshold_db} dB)."
        )

    def _init_journal_and_tables(self):
        # 2.8.5 — journal des toutes premières secondes (avant l'ouverture de l'espace de l'opérateur) :
        # un seul fichier, réécrit à chaque lancement, au lieu d'un fichier de plus à chaque démarrage.
        self.csv_path = Path(self.archive_dir) / "journal_demarrage.csv"
        try:
            self.csv_path.unlink(missing_ok=True)
            for old in Path(self.archive_dir).glob("journal_2*.csv"):
                old.unlink(missing_ok=True)
        except OSError:
            pass
        self.station_snr_map = {s["id"]: "Non mesure" for s in WEFAX_STATIONS}
        self._populate_freq_table()
        self._reset_blank_rx_sheet()
        self.rx_sheet_initialized_for_live = False
        self.lbl_freq_display.configure(font=("Consolas", 13, "bold"), wraplength=680, justify="left")
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._pump_events)
        self.root.after(2000, self._supervisor)

    def _init_preferences_and_schedules(self):
        self.root.title(SOFTWARE_BRAND)
        self.lbl_freq_display.configure(font=("Segoe UI", 15, "bold"), wraplength=520)
        self.config_path = Path(self.archive_dir) / "preferences.json"
        self.schedule_path = Path(self.archive_dir) / "programmes_wefax.json"
        self.schedule_data = {k: list(v) for k, v in BROADCAST_SCHEDULES_UTC.items()}
        if not self.schedule_path.exists():
            try:
                atomic_json(
                    self.schedule_path,
                    {
                        "status": "Programme indicatif hérité ; vérifier auprès de l'émetteur",
                        "stations": self.schedule_data, "schedule_rev": SCHEDULE_REV,
                    },
                )
            except OSError as exc:
                self.log_event("Programme non sauvegarde : " + repr(exc))
        self._reload_schedules()
        self._load_preferences()
        self.root.after(1000, self._housekeeping)
        self.root.after(20000, self._wl_poll_loop)  # 2.8.7 : GRIB reçus par Winlink
        self.root.after(1200, lambda: self._install_help(self.root))
        self._refresh_logo_preview()
        self.log_event(SOFTWARE_BRAND + " ; archives=" + self.archive_dir)
        self.log_event("Journal CSV=" + str(self.csv_path))

    def _init_geometry_tools(self):
        self.root.title(SOFTWARE_BRAND)
        self.root.minsize(640, 480)
        self.sld_slant.configure(resolution=0.000001)
        self.log_event(f"{SOFTWARE_VERSION} : detection de marge et analyse du vent assistee actives")

    def _init_cockpit_and_help(self):
        self.root.after(2500, self._startup_cat_autostart)
        self.root.after(9000, self._radio_hotplug_watch)  # 2.8.8 : câble USB branché/débranché à chaud
        self._spectral_watch_start()  # 2.8.9 : niveau des autres stations lu sur le spectre du poste
        self.root.title(SOFTWARE_BRAND)
        self.root.configure(bg=UITheme.BG_ROOT)

        self._polish_all_containers25()

        self._init_operator_workspace_on_startup()
        self.operator_callsign_var.trace_add("write", self._on_operator_name_changed25)
        self.root.bind("<F1>", self._focused_help25)
        self._install_help(self.root)
        try:
            menubar = self.root.nametowidget(self.root.cget("menu"))
            menubar.configure(
                bg=UITheme.BG_PANEL,
                fg=UITheme.TEXT_PRIMARY,
                activebackground=UITheme.ACCENT,
                activeforeground="#ffffff",
                bd=0,
            )
            menu = tk.Menu(
                menubar,
                tearoff=False,
                bg=UITheme.BG_PANEL,
                fg=UITheme.TEXT_PRIMARY,
                activebackground=UITheme.ACCENT,
                activeforeground="#ffffff",
            )
            menu.add_command(label="Sommaire et recherche — F1", command=self._general_help)
            menu.add_command(label="Lire les indicateurs", command=lambda: self._show_help25("spectre"))
            menu.add_command(
                label="Prochaine carte / programme UTC", command=lambda: self._show_help25("programmes")
            )
            menubar.add_cascade(label="Aide", menu=menu)
        except tk.TclError:
            pass
        self._update_startup_readiness_banner25()
        self.root.after(1000, self._dashboard_tick25)
        self.log_event(
            f"{SOFTWARE_VERSION} : cockpit 3 colonnes compact ; place maximale pour la carte WEFAX"
        )
        self.root.after_idle(self._layout_station_status_complete)

    def _init_reception_banner(self):
        try:
            self.rx_step_banner = ReceptionStepBanner(self)
        except Exception:
            pass

    def _init_portable_and_bulletins(self):
        try:
            self.lbl_freq_display.grid_configure(row=0, column=1, columnspan=2, sticky="w", padx=(6, 0))
            self.lbl_radio_details.grid_configure(
                row=1, column=0, columnspan=5, sticky="ew", padx=0, pady=(4, 1)
            )

            self.portable_ws = PortableWorkspaceManager(self)
            self.schedule_planner = ScheduleSyncAndPlanner(self, self.portable_ws)
            self.rtty_decoder = RTTYITA2Decoder(sample_rate=self.audio_fs)
            self.offline_translator = OfflineWeatherTranslator(self.portable_ws.root_dir / "ressources")
            self.hybrid_arbiter = HybridModeArbiter(
                self, self.portable_ws, self.rtty_decoder, self.offline_translator, self.schedule_planner
            )
            self.bulletins_ui = BulletinsAndHybridWindow(self, self.hybrid_arbiter)

            self._switch_operator_workspace25(self.operator_callsign_var.get(), load_prefs=True)

            if hasattr(self, "btn_top_rx"):
                self.btn_top_rx.base_text = "Réception WEFAX"
                self.hybrid_arbiter._style_wefax_toggle_button()
                self._register_tip25(
                    self.btn_top_rx,
                    "apt",
                    "BOUTON COMMUTATEUR [ON/OFF] : Arme ([ON] 🟢) ou met en pause ([OFF] ⚪) la réception de cartes météo WEFAX 120 RPM.",
                )

            if hasattr(self, "controls_slot25"):
                sep = tk.Frame(self.controls_slot25, bg="#f59e0b", width=2, height=20)
                sep.pack(side="left", padx=4, pady=2)

                btn_rtty = tk.Button(
                    self.controls_slot25,
                    text="📠 Téléscripteur RTTY",
                    command=self.bulletins_ui.show,
                    bg="#1d4ed8",
                    fg="#ffffff",
                    activebackground="#2563eb",
                    activeforeground="#ffffff",
                    font=("Segoe UI", 8, "bold"),
                    bd=1,
                    relief="raised",
                    padx=7,
                    pady=2,
                    cursor="hand2",
                )
                btn_rtty.pack(side="left", padx=2)
                self._register_tip25(
                    btn_rtty,
                    "interface",
                    "BOUTON D'ACTION : Ouvre la fenêtre du téléscripteur dédié aux bulletins météo écrits (RTTY DWD 50 Bd / NAVTEX 100 Bd) et leur traduction française.",
                )

                # Simplification 2.8 : « Rapport ADRASEC » (menu Bulletins et fenêtre Météo), « Réseau »
                # (menu Automatisation) et « Aide qualité » (menu Aide) quittent la barre de commandes.
                btn_freqs = tk.Button(
                    self.controls_slot25,
                    text="📋 Fréquences",
                    command=self._open_scan_results,
                    bg="#334155",
                    fg="#ffffff",
                    activebackground="#475569",
                    activeforeground="#ffffff",
                    font=("Segoe UI", 8, "bold"),
                    bd=1,
                    relief="raised",
                    padx=7,
                    pady=2,
                    cursor="hand2",
                )
                btn_freqs.pack(side="left", padx=2)
                # 2.11.2 — référence conservée pour _on_manual_hold_changed (couleur orange au choix opérateur)
                self._btn_stations_cockpit = btn_freqs
                self._register_tip25(
                    btn_freqs,
                    "programmes",
                    "Résultats du dernier scan pour toutes les stations (WEFAX, RTTY, NAVTEX) : double-clic pour "
                    "accorder le poste sur une station sans relancer de scan.",
                )

            if hasattr(self, "page_radio"):
                f_port = tk.LabelFrame(
                    self.page_radio,
                    text=" Stockage portable (archives 7 jours) ",
                    bg=UITheme.BG_PANEL,
                    fg="#fef3c7",
                    font=("Segoe UI", 9, "bold"),
                    padx=8,
                    pady=6,
                )
                f_port.pack(fill="x", padx=5, pady=(4, 10))

                lbl_root = tk.Label(
                    f_port,
                    text=f"Dossier portable actif : {self.portable_ws.root_dir}",
                    bg=UITheme.BG_PANEL,
                    fg=UITheme.TEXT_MUTED,
                    font=("Consolas", 8),
                    anchor="w",
                    justify="left",
                )
                lbl_root.pack(fill="x", pady=(0, 4))

                row_p = tk.Frame(f_port, bg=UITheme.BG_PANEL)
                row_p.pack(fill="x")

                b_purge = tk.Button(
                    row_p,
                    text="Purger >7j & Index",
                    command=self.bulletins_ui._run_retention_check,
                    bg=UITheme.BG_SURFACE,
                    fg=UITheme.TEXT_PRIMARY,
                    font=("Segoe UI", 8, "bold"),
                    relief="raised",
                    bd=1,
                    padx=8,
                    pady=3,
                    cursor="hand2",
                )
                b_purge.pack(side="left", padx=(0, 4))

                b_exp = tk.Button(
                    row_p,
                    text="Exporter (>7j)",
                    command=self.bulletins_ui._export_autonomous_bundle,
                    bg=UITheme.BG_SURFACE,
                    fg=UITheme.TEXT_PRIMARY,
                    font=("Segoe UI", 8, "bold"),
                    relief="raised",
                    bd=1,
                    padx=8,
                    pady=3,
                    cursor="hand2",
                )
                b_exp.pack(side="left", padx=4)

                # 2.8.8 : « Horaires Web » (menu Bulletins) et « Scanner RTTY » (téléscripteur) ne sont plus doublés ici

            try:
                menubar = self.root.nametowidget(self.root.cget("menu"))
                hyb_menu = tk.Menu(
                    menubar,
                    tearoff=False,
                    bg=UITheme.BG_PANEL,
                    fg=UITheme.TEXT_PRIMARY,
                    activebackground="#d97706",
                    activeforeground="#ffffff",
                )
                hyb_menu.add_command(
                    label="📠 Ouvrir le Téléscripteur Météo RTTY & Traduction hors-ligne",
                    command=self.bulletins_ui.show,
                )
                hyb_menu.add_command(
                    label="📋 Générer le Rapport Météo ADRASEC (1-Clic)",
                    command=self.bulletins_ui._generate_orsec_bulletin_dialog,
                )
                hyb_menu.add_command(
                    label="❓ Guide des Indices de Qualité & Sélection HF Anti-Bruit",
                    command=self.bulletins_ui.show_reliability_help_dialog,
                )
                hyb_menu.add_separator()
                hyb_menu.add_command(
                    label="🔍 Scanner les fréquences RTTY DWD utiles",
                    command=lambda: self.hybrid_arbiter.trigger_rtty_frequency_scan(family_filter="DWD_RTTY"),
                )
                hyb_menu.add_command(
                    label="🌐 Programmes : sources officielles (télécharger et comparer)…",
                    command=lambda: self.schedule_planner.open_sources_window(refresh=True),
                )
                hyb_menu.add_separator()
                hyb_menu.add_command(
                    label="📋 Résultats du dernier scan / choisir la fréquence…",
                    command=self._open_scan_results,
                )
                hyb_menu.add_command(
                    label="🗓️ Plan de réception (bulletins à recevoir)…",
                    command=lambda: self._show_settings("PLAN"),
                )
                menubar.add_cascade(label="Bulletins", menu=hyb_menu)
                # Automatisation : mode d'exploitation et accès Internet (anciens boutons de la barre)
                auto_menu = self.root.nametowidget(menubar.entrycget("Automatisation", "menu"))
                auto_menu.add_separator()
                self._mode_var = tk.StringVar(master=self.root, value=self.hybrid_arbiter.requested_mode)
                labels = {
                    "HYBRIDE": "Cartes + bulletins planifiés (recommandé)",
                    "WEFAX": "Cartes WEFAX seulement",
                    "BULLETINS": "Bulletins RTTY / NAVTEX seulement",
                    "MANUEL": "Manuel (aucune bascule automatique)",
                }
                for m_name, lab in labels.items():
                    auto_menu.add_radiobutton(
                        label=lab,
                        variable=self._mode_var,
                        value=m_name,
                        command=lambda m=m_name: self.hybrid_arbiter.set_requested_mode(m, True),
                    )
                auto_menu.add_separator()
                self._net_var = tk.BooleanVar(master=self.root, value=True)
                auto_menu.add_checkbutton(
                    label="Autoriser l'accès Internet (horaires, cartes Web)",
                    variable=self._net_var,
                    command=lambda: (
                        self.schedule_planner.set_manual_network_cutoff(not self._net_var.get()),
                        self._sync_ui_from_hardware(),
                    ),
                )
                try:
                    help_menu = self.root.nametowidget(menubar.entrycget("Aide", "menu"))
                    help_menu.add_command(
                        label="Indices de qualité et choix de fréquence",
                        command=self.bulletins_ui.show_reliability_help_dialog,
                    )
                except tk.TclError:
                    pass
            except Exception:
                pass

            self.portable_ws.enforce_retention_and_quota()
            self._hide_main_canvas_roi_overlays()
            self._sync_ui_from_hardware()
            self._update_programme()
            self.root.after(1500, lambda: self.schedule_planner.trigger_web_schedule_sync(manual=False))
            self.log_event(
                f"✅ Protection Anti-Scission WEFAX + Détecteur Porteuse 2300 Hz + Squelch RTTY Strict initialisés : {self.portable_ws.root_dir}"
            )
        except Exception as exc:
            self.log_event("ERREUR initialisation socle portable/RTTY : " + repr(exc))
