# Rôle des modules

## Principe du découpage

* **Bibliothèques sans interface** (`core/`, `radio/`, `dsp/`, `weather/`, `rtty/`, `storage/`) :
  fonctions et classes indépendantes de la fenêtre. Ce sont les meilleurs candidats à la
  validation terrain, car elles évoluent peu.
* **Composants d'interface** (`ui/`) : thème, widgets, bandeau des étapes, aide.
* **Fenêtre principale** (`app/`) : la classe `StationWefaxApp` est composée de « mixins »,
  un par domaine fonctionnel. Une méthode n'est définie qu'une seule fois.
* **Méthodes en étages** : quand l'ancienne version empilait plusieurs couches sur une même
  fonction (ex. fin de carte : 4 couches), les couches sont devenues des méthodes nommées,
  appelées dans le même ordre, dans le même fichier. Exemple (`app/reception.py`) :

  ```
  _finalize_completed_wefax_chart   préparation dossier portable + indexation du document
   └ _finalize_with_banner          étapes STOP / SAUVEGARDE du bandeau
      └ _finalize_geometry_and_save marge + slant automatiques de fin de carte
         └ _save_completed_chart    restauration, signature, PNG + JSON vérifiés
  ```

## Fenêtre principale (`wefax_station/app/`)

| Fichier | Domaine |
|---|---|
| `main_window.py` | Composition de la classe et séquence d'initialisation (phases nommées, ordre historique conservé) |
| `lifecycle.py` | Journal unique (affichage, CSV, journal tournant), file d'événements inter-threads, tâches périodiques, fermeture, compilation |
| `layout.py` | Structure de la fenêtre : navigation, bandeau supérieur « cockpit 3 colonnes », zone carte, fenêtres Réglages / Diagnostics |
| `settings_tabs.py` | Onglets Radio, Image & opérateur, Bulletin |
| `styling.py` | Styles ttk et thème sombre des fenêtres |
| `help_system.py` | Aide F1, recherche, infobulles |
| `radio_link.py` | Connexion CAT/CI-V, entrée audio USB, réglages RF, boucle RF automatique, synchronisation de l'affichage radio |
| `scanner.py` | Scan des fréquences WEFAX (QSY, préparation RF vérifiée, mesures, sélection) |
| `reception.py` | Boucle temps réel, décodage (cœur 2.0 inchangé), START / PHASE / STOP, feuille de réception, fin de carte |
| `image_tools.py` | Slant, marge, rotation, filtres de restauration, correction non destructive |
| `canvas_view.py` | Rendu de la carte, pied de page, zoom / déplacement, repère QTH, zone d'analyse |
| `telemetry.py` | Spectre BF, bargraphes de qualité, horaires UTC |
| `archives.py` | Signature des cartes, historique, consultation, logo |
| `weather_desk.py` | Analyse assistée, annotations, bulletin, cartes Internet |
| `operator_profile.py` | Indicatif, espace opérateur, préférences |
| `recording.py` | Enregistrement WAV des réceptions, relecture d'un enregistrement dans la chaîne |
| `reception_plan.py` | Fenêtre « Résultats du dernier scan » (accorder sans rescanner, mesurer la sélection) et onglet Réglages « Plan de réception » | nouveau (2.8) |
| `bulletin_desk.py` | Fenêtre « Météo & bulletin » : réceptions 24 h, bulletin compilé (analyse des bulletins texte en français), statistiques | nouveau (2.8) |
| `georef_tool.py` | Zone d'analyse = case de l'opérateur ; outil de repérage de la carte (3 clics + coordonnées) | nouveau (2.8.2) |
| `responsive.py` | Mise en page adaptative : barre en flux, paliers du tableau de bord, F9 / F11, menu Affichage |
| `teleprinter_panel.py` | Téléscripteur intégré à la fenêtre principale ; fenêtre « À propos » (placée sur la fenêtre principale, 2.9.0) | nouveau (2.8.6) |
| `spectral_watch.py` | Veille spectrale : lecture périodique du spectre de l'IC-705, niveau des stations visibles, message d'arrêt | nouveau (2.8.9), corrigé (2.9.0) |
| `winlink_desk.py` | Assistant Winlink en 3 étapes (passerelle, connexion, GRIB) | nouveau (2.8.7) |

## Bibliothèques

| Fichier | Contenu | Ancien emplacement |
|---|---|---|
| `version.py` | `SOFTWARE_VERSION`, titres, chemins du projet | part01 |
| `deps.py` | pyserial / sounddevice optionnels | part01 |
| `core/stations.py` | `WEFAX_STATIONS`, `RTTY_WEATHER_STATIONS`, identification de fréquence | part01, hf_bulletins |
| `core/schedules.py` | Programmes UTC WEFAX (DWD d'après la NOAA, 2.9.0) et bulletins texte, révision des programmes enregistrés, priorité des cartes, prochaines diffusions | part01, part06, part08, hf_bulletins |
| `core/web_charts.py` | Sources Internet des cartes | part01 |
| `core/bulletin_text.py` | Rédaction du bulletin documentaire | part06 |
| `radio/controller.py` | `UnifiedRadioController` (+ fréquences RTTY, polling CI-V limité à 2 s) | part02 + patch hf_bulletins |
| `radio/yaesu.py` | Commandes CAT Yaesu réception seule : ASCII (FT-991A, FT-891, FT-710, FTDX10/101…) et 5 octets (FT-817/818/857/897), identification du modèle | nouveau (2.8) |
| `radio/rf_verify.py` | `RFVerified705` : écriture + relecture CI-V, liste blanche RX ; P.AMP de référence imposé pendant les scans (2.9.0) | part10 |
| `radio/auto_preamp.py` | P.AMP automatique : essai du cran supérieur, mesure du gain de SNR, retour au réglage de base | nouveau (2.8.8) |
| `radio/scope.py` | Spectre CI-V 27 00 : trames recollées d'une lecture à l'autre (`FrameStream`, 2.9.0), assemblage du balayage, analyse des stations | nouveau (2.8.9) |
| `radio/profiles.py` | Profil de réception unique et justifié (USB-D, 3 kHz, AGC FAST, NR/notch OFF, NB conservé) ; bandes audio utiles par mode | nouveau (2.7) |
| `dsp/engine.py` | `WefaxSignalAndImageEngine` (interface de démodulation, analyse spectrale, restauration) | part03 |
| `dsp/wefax_demod.py` | Démodulateur WEFAX continu : anti-QRN, bande de base, confiance, START/STOP/phasage, AFC, horloge | nouveau (2.7) |
| `dsp/chart_restore.py` | Restauration guidée par la confiance (lignes abîmées réparées verticalement, stries, fond papier, netteté horizontale), recadrage sans repli (`find_wrap_cut`), retrait des lignes vides | nouveau (2.8) |
| `dsp/chart_end.py` | Fin de carte par perte de structure (STOP manqué), ligne de coupe | nouveau (2.11) |
| `dsp/wefax_signature.py` | Reconnaissance d'une carte WEFAX par sa structure (scan) | nouveau (2.7) |
| `dsp/passband.py` | Mesure de la bande passante audio réelle du récepteur | nouveau (2.7) |
| `dsp/scan_diagnostics.py` | `assess_scan_audio` (heuristiques de scan) | part10 |
| `weather/synoptic.py` | `SynopticWeatherAnalysisEngine` | part04 |
| `weather/geometry.py` | `estimate_geometry`, `geostrophic_estimate`, `local_line_axis` | part07 |
| `weather/georef.py` | Transformation pixels <-> lat/lon (affine par moindres carrés), saisie des coordonnées, mémorisation par type de carte | nouveau (2.8.2) |
| `weather/plain_language.py` | Lecture en clair : situation géographique et distance, niveau d'attention, heure de Paris, Beaufort en mots et km/h, état de la mer, conduite à tenir ; bulletins par zones | nouveau (2.8.1) |
| `weather/rtty_parse.py` | Lecture des prévisions ponctuelles DWD (vent, Beaufort, mer, phénomènes) et résumé en français, repérage des avertissements | nouveau (2.8) |
| `weather/reliability.py` | `WeatherReliabilityEstimator` | hf_bulletins |
| `weather/synop.py` | Décodeur SYNOP / navires / bouées (AAXX, BBXX) | nouveau (2.8.7) |
| `weather/grib.py` | Décodeur GRIB 1 sans bibliothèque externe | nouveau (2.8.7) |
| `weather/nowcast.py` | Situation actuelle et prévision 3-6 h du secteur, indice de fiabilité (faits / prévisions reçues / estimation séparés) | nouveau (2.10.0) |
| `winlink/express.py`, `winlink/saildocs.py` | Lecture de l'installation Winlink Express / VARA (sans modification), demandes et réponses Saildocs | nouveau (2.8.7) |
| `rtty/decoder.py` | Façade de réception texte (squelch par validité de trame, AFC, métriques) | hf_bulletins, réécrit (2.7) |
| `rtty/fsk.py` | Démodulateur FSK : filtres adaptés, ATC, contraste des tonalités | nouveau (2.7) |
| `rtty/ita2_async.py` | Décodeur RTTY ITA2 asynchrone | nouveau (2.7) |
| `rtty/sitorb.py` | Décodeur NAVTEX SITOR-B (horloge, 4B/3Y, DX/RX, ZCZC…NNNN, doublons) | nouveau (2.7) |
| `rtty/codes.py` | Tables ITA2 et CCIR 476 (source unique) | nouveau (2.7) |
| `rtty/segmenter.py`, `translator.py` | Découpage des bulletins, traduction hors ligne | hf_bulletins |
| `hybrid/scheduler.py` | Ordonnancement WEFAX / RTTY / NAVTEX : programmes RTTY réels du DWD, créneaux NAVTEX, décisions (dont carte prioritaire contre bulletin, 2.9.0), table de propagation, nettoyage de la boucle de service | nouveau (2.8) |
| `hybrid/planner.py`, `arbiter.py`, `window.py` | Planification, arbitre WEFAX/RTTY, fenêtre téléscripteur | hf_bulletins |
| `hybrid/official_sources.py` | 2.9.2 — sources officielles : téléchargement borné, PDF, comparaison, programmes acceptés | — |
| `hybrid/observed_programme.py` | 2.9.3 — programme observé : START reçus / créneaux muets, créneaux à vérifier | — |
| `hybrid/text_station_health.py` | 2.9.2 — stations NAVTEX / RTTY optionnelles, mise en sommeil automatique | — |
| `storage/atomic.py` | `atomic_png`, `atomic_json` | part06 |
| `storage/layout.py` | Arborescence d'un jour de réception (noms des dossiers, anciens noms lus) | nouveau (2.11) |
| `storage/portable.py` | `PortableWorkspaceManager` | hf_bulletins |
| `storage/recorder.py` | Enregistreur WAV (thread dédié) et lecture WAV | nouveau (2.7) |
| `sim/fake_rigs.py` | Postes Yaesu simulés au niveau du port série (tests sans matériel) | nouveau (2.8) |
| `sim/` | Signaux conformes (WEFAX OMM, ITA2, SITOR-B), canal HF (bruit, Watterson, QRN, accord, ppm), métriques | nouveau (2.7), essais uniquement |
| `ui/theme.py`, `widgets.py` | Thème, infobulles, interrupteurs | part01 |
| `ui/vfo_display.py` | Afficheur façon façade de poste (fréquence 7 segments, indicatif, puces de réglage, S-mètre) | nouveau (2.8) |
| `ui/reception_banner.py` | Bandeau des 7 étapes | reception_banner |
| `ui/help_content.py`, `help_tip.py` | Rubriques d'aide | part08, part09 |
| `ui/placement.py` | Placement des fenêtres annexes et bulles d'aide par rapport à la fenêtre principale (multi-écran, coordonnées négatives) | nouveau (2.9.0) |
| `ui/text_fit.py` | Textes ajustés à une largeur sans couper un élément (ligne « Ensuite », nom de station) | nouveau (2.9.0) |
| `ui/logo.py` | Logo par défaut | part06 |
| `validation.py` | Contrôle des modules validés | nouveau |

## Index des méthodes de la fenêtre principale

| Méthode | Fichier |
|---|---|
| `_accept_auto_slant` | `app/image_tools.py` |
| `_add_layout_menu` | `app/responsive.py` |
| `_add_tip` | `app/help_system.py` |
| `analysis_zone` | `app/georef_tool.py` |
| `_annotate_card` | `app/weather_desk.py` |
| `_annotate_card_window` | `app/weather_desk.py` |
| `_append_log_csv` | `app/lifecycle.py` |
| `_append_log_widget` | `app/lifecycle.py` |
| `_apply_full_restoration` | `app/image_tools.py` |
| `_apply_operator_change25` | `app/operator_profile.py` |
| `_apply_optimal_defaults_preset` | `app/radio_link.py` |
| `_apply_slant_and_filters` | `app/image_tools.py` |
| `_apply_slant_and_filters_base` | `app/image_tools.py` |
| `_audio_device_key` | `app/reception.py` |
| `_auto_connect_ic705_audio` | `app/radio_link.py` |
| `_auto_record_chart_end` | `app/recording.py` |
| `_auto_record_chart_start` | `app/recording.py` |
| `_bar_help25` | `app/help_system.py` |
| `_build_folder_navigation_bar` | `app/layout.py` |
| `_build_permanent_log_dock` | `app/lifecycle.py` |
| `_build_permanent_top_bar` | `app/layout.py` |
| `_build_permanent_top_bar_base` | `app/layout.py` |
| `_build_right_map_area` | `app/layout.py` |
| `_build_right_map_area_base` | `app/layout.py` |
| `_build_tab_image_and_operator` | `app/settings_tabs.py` |
| `_build_tab_image_and_operator_base` | `app/settings_tabs.py` |
| `_build_tab_plan` | `app/reception_plan.py` |
| `_build_tab_radio` | `app/settings_tabs.py` |
| `_build_tab_weather` | `app/settings_tabs.py` |
| `_build_ui` | `app/layout.py` |
| `_bulletin_modified` | `app/weather_desk.py` |
| `_cancel_georef` | `app/georef_tool.py` |
| `_canvas_to_image_coords` | `app/canvas_view.py` |
| `_chart_family` | `app/georef_tool.py` |
| `_check_audio_passband` | `app/radio_link.py` |
| `_check_day_night_schedule` | `app/scanner.py` |
| `_checkpoint_path` | `app/lifecycle.py` |
| `_choose_custom_logo` | `app/archives.py` |
| `_clean_ui_label25` | `app/styling.py` |
| `_clear_safety_checkpoint` | `app/lifecycle.py` |
| `_clock_store_path` | `app/reception.py` |
| `_close` | `app/lifecycle.py` |
| `_compact_groups` | `app/layout.py` |
| `_compile_exe` | `app/lifecycle.py` |
| `_compose_display_image_base` | `app/canvas_view.py` |
| `_compose_display_image_with_footer` | `app/canvas_view.py` |
| `_connect_serialized` | `app/radio_link.py` |
| `_connection_done` | `app/radio_link.py` |
| `_copy_bulletin` | `app/weather_desk.py` |
| `_crop_sheet_rows` | `app/reception.py` |
| `_current_mode_label` | `app/recording.py` |
| `_dashboard_tick25` | `app/layout.py` |
| `_desk_compile` | `app/bulletin_desk.py` |
| `_desk_copy` | `app/bulletin_desk.py` |
| `_desk_documents` | `app/bulletin_desk.py` |
| `_desk_fill_stats` | `app/bulletin_desk.py` |
| `_desk_open` | `app/bulletin_desk.py` |
| `_desk_refresh` | `app/bulletin_desk.py` |
| `_desk_save` | `app/bulletin_desk.py` |
| `_desk_toggle` | `app/bulletin_desk.py` |
| `_diag_export_log` | `app/lifecycle.py` |
| `_doc_text` | `app/bulletin_desk.py` |
| `_download_web_weather_chart` | `app/weather_desk.py` |
| `_draw_permanent_top_signal_curve` | `app/telemetry.py` |
| `_draw_three_quality_bargraphs` | `app/telemetry.py` |
| `_draw_wefax_spectrum` | `app/telemetry.py` |
| `_enumerate_audio_input_devices` | `app/radio_link.py` |
| `_execute_closed_loop_rf_control` | `app/radio_link.py` |
| `_exit_fullscreen` | `app/responsive.py` |
| `_fill_station_tree` | `app/reception_plan.py` |
| `_filter_help25` | `app/help_system.py` |
| `_finalize_completed_wefax_chart` | `app/reception.py` |
| `_finalize_geometry_and_save` | `app/reception.py` |
| `_finalize_with_banner` | `app/reception.py` |
| `_finish_georef` | `app/georef_tool.py` |
| `_finish_scan` | `app/scanner.py` |
| `_fit_window` | `app/layout.py` |
| `_focused_help25` | `app/help_system.py` |
| `_general_help` | `app/help_system.py` |
| `_generate_bulletin` | `app/weather_desk.py` |
| `_generate_realistic_test_wefax` | `app/reception.py` |
| `_geometry_dialog` | `app/image_tools.py` |
| `_geometry_window` | `app/image_tools.py` |
| `_georef_click` | `app/georef_tool.py` |
| `_georef_store` | `app/georef_tool.py` |
| `_get_effective_scale_and_origin` | `app/canvas_view.py` |
| `_hide_main_canvas_roi_overlays` | `app/canvas_view.py` |
| `_highlight_station` | `app/scanner.py` |
| `_history` | `app/archives.py` |
| `_history_window` | `app/archives.py` |
| `_housekeeping` | `app/lifecycle.py` |
| `_housekeeping_base` | `app/lifecycle.py` |
| `_image_to_canvas_coords` | `app/canvas_view.py` |
| `__init__` | `app/main_window.py` |
| `_init_cockpit_and_help` | `app/main_window.py` |
| `_init_geometry_tools` | `app/main_window.py` |
| `_init_journal_and_tables` | `app/main_window.py` |
| `_init_main_window` | `app/main_window.py` |
| `_init_operator_workspace_on_startup` | `app/operator_profile.py` |
| `_init_portable_and_bulletins` | `app/main_window.py` |
| `_init_preferences_and_schedules` | `app/main_window.py` |
| `_init_reception_banner` | `app/main_window.py` |
| `_init_recording` | `app/recording.py` |
| `_init_responsive_layout` | `app/responsive.py` |
| `_init_state_geometry` | `app/main_window.py` |
| `_init_state_help_and_workspace` | `app/main_window.py` |
| `_init_state_reception` | `app/main_window.py` |
| `_init_state_supervision` | `app/main_window.py` |
| `_install_help` | `app/help_system.py` |
| `_is_weather_or_settings_dialog_open` | `app/canvas_view.py` |
| `_layout_dashboard25` | `app/layout.py` |
| `_layout_dashboard_columns` | `app/responsive.py` |
| `_layout_station_status_complete` | `app/layout.py` |
| `_layout_steps` | `app/responsive.py` |
| `_live_recenter_chart` | `app/reception.py` |
| `_load_clock_calibration` | `app/reception.py` |
| `_load_preferences` | `app/operator_profile.py` |
| `_load_wefax_file` | `app/archives.py` |
| `log_event` | `app/lifecycle.py` |
| `_log_new_navtex_messages` | `app/reception.py` |
| `_make_flow` | `app/responsive.py` |
| `_make_station_tree` | `app/reception_plan.py` |
| `_measure_from_tree` | `app/reception_plan.py` |
| `_move_qth_and_roi_to` | `app/canvas_view.py` |
| `_nudge_qth_position` | `app/canvas_view.py` |
| `_on_audio_device_selected` | `app/radio_link.py` |
| `_on_canvas_configure` | `app/responsive.py` |
| `_on_canvas_motion` | `app/canvas_view.py` |
| `_on_display_mode_changed` | `app/canvas_view.py` |
| `_on_double_click_zoom` | `app/canvas_view.py` |
| `_on_if_filter_changed` | `app/radio_link.py` |
| `_on_left_down` | `app/canvas_view.py` |
| `_on_left_down_base` | `app/canvas_view.py` |
| `_on_left_up` | `app/canvas_view.py` |
| `_on_manual_slant_slider` | `app/image_tools.py` |
| `_on_middle_down` | `app/canvas_view.py` |
| `_on_middle_drag` | `app/canvas_view.py` |
| `_on_middle_up` | `app/canvas_view.py` |
| `_on_mouse_wheel` | `app/canvas_view.py` |
| `_on_operator_name_changed25` | `app/operator_profile.py` |
| `_on_right_down` | `app/canvas_view.py` |
| `_on_right_up` | `app/canvas_view.py` |
| `_on_roi_size_slider_changed` | `app/canvas_view.py` |
| `_on_root_configure` | `app/responsive.py` |
| `_on_split_slider_changed` | `app/canvas_view.py` |
| `_on_station_row_clicked` | `app/scanner.py` |
| `_one_click` | `app/radio_link.py` |
| `_open_archive` | `app/archives.py` |
| `_open_bulletin_desk` | `app/bulletin_desk.py` |
| `_open_csv` | `app/archives.py` |
| `_open_local` | `app/archives.py` |
| `_open_recordings_dir` | `app/recording.py` |
| `_open_scan_results` | `app/reception_plan.py` |
| `_periodic_watchdog_tick` | `app/lifecycle.py` |
| `_polish_all_containers25` | `app/styling.py` |
| `_polish_new_toplevels25` | `app/styling.py` |
| `_populate_freq_table` | `app/scanner.py` |
| `_prepare_rf` | `app/scanner.py` |
| `_pump_events` | `app/lifecycle.py` |
| `_realtime_rx_and_spectrum_loop` | `app/reception.py` |
| `_recompute_roi_from_qth` | `app/canvas_view.py` |
| `_recordings_dir` | `app/recording.py` |
| `_refresh_canvas` | `app/canvas_view.py` |
| `_refresh_com_ports_list` | `app/radio_link.py` |
| `_refresh_logo_preview` | `app/archives.py` |
| `_refresh_plan_next` | `app/reception_plan.py` |
| `_refresh_propagation_views` | `app/reception_plan.py` |
| `_register_tip25` | `app/help_system.py` |
| `_relayout` | `app/responsive.py` |
| `_reload_schedules` | `app/telemetry.py` |
| `_remove_logo` | `app/archives.py` |
| `_render_help25` | `app/help_system.py` |
| `_render_signed_chart` | `app/archives.py` |
| `_replay_tick` | `app/recording.py` |
| `_replay_wav_dialog` | `app/recording.py` |
| `_reset_blank_rx_sheet` | `app/reception.py` |
| `_reset_sheet_blank_image` | `app/reception.py` |
| `_reset_sheet_counters` | `app/reception.py` |
| `_reset_sheet_keep_pending_audio` | `app/reception.py` |
| `_reset_sheet_with_banner` | `app/reception.py` |
| `_reset_zoom_pan` | `app/canvas_view.py` |
| `_responsive_toolbar` | `app/layout.py` |
| `_resume_midchart` | `app/reception.py` |
| `_rf_begin_measure` | `app/scanner.py` |
| `_rf_final_complete` | `app/scanner.py` |
| `_rf_final_resume` | `app/scanner.py` |
| `_rf_prepared` | `app/scanner.py` |
| `_roll_confidence` | `app/reception.py` |
| `_rotate` | `app/image_tools.py` |
| `_run_auto_detect_cat_and_audio` | `app/radio_link.py` |
| `_run_auto_margin_and_slant` | `app/image_tools.py` |
| `_run_expert_weather_analysis` | `app/weather_desk.py` |
| `_rx_decode_step` | `app/reception.py` |
| `_rx_loop_with_banner` | `app/reception.py` |
| `_safety_checkpoint` | `app/lifecycle.py` |
| `_sanitize_operator_folder25` | `app/operator_profile.py` |
| `_save_completed_chart` | `app/reception.py` |
| `_save_draft` | `app/weather_desk.py` |
| `_save_plan_from_ui` | `app/reception_plan.py` |
| `_save_preferences` | `app/operator_profile.py` |
| `_save_stamped_wefax` | `app/archives.py` |
| `_save_weather_bulletin_manual` | `app/weather_desk.py` |
| `_scan_measure` | `app/scanner.py` |
| `_scan_measure_window` | `app/scanner.py` |
| `_scan_next` | `app/scanner.py` |
| `_scan_next_station` | `app/scanner.py` |
| `_scan_wefax_signature` | `app/scanner.py` |
| `_schedule_relayout` | `app/responsive.py` |
| `_scroll_left` | `app/layout.py` |
| `_select_help25` | `app/help_system.py` |
| `_select_navigation_tab` | `app/layout.py` |
| `_set_bulletin` | `app/weather_desk.py` |
| `set_busy_state` | `app/lifecycle.py` |
| `_set_power` | `app/radio_link.py` |
| `_set_rf_preamp` | `app/radio_link.py` |
| `_set_wefax_protocol_stage` | `app/reception.py` |
| `_setup_styles` | `app/styling.py` |
| `_sheet_has_wefax_content` | `app/reception.py` |
| `_show_completed` | `app/canvas_view.py` |
| `_show_diagnostics` | `app/layout.py` |
| `_show_help25` | `app/help_system.py` |
| `_show_live` | `app/canvas_view.py` |
| `_show_settings` | `app/layout.py` |
| `_signed` | `app/archives.py` |
| `_slant_label` | `app/image_tools.py` |
| `_start_georef` | `app/georef_tool.py` |
| `_start_recording` | `app/recording.py` |
| `_start_replay` | `app/recording.py` |
| `_start_scan` | `app/scanner.py` |
| `_startup_cat_autostart` | `app/radio_link.py` |
| `_startup_retry_later` | `app/radio_link.py` |
| `_station_buttons` | `app/reception_plan.py` |
| `_station_rows` | `app/reception_plan.py` |
| `_step_tip` | `app/responsive.py` |
| `_stop_recording` | `app/recording.py` |
| `_stop_replay` | `app/recording.py` |
| `_style_rec_button` | `app/recording.py` |
| `_style_widget_tree25` | `app/styling.py` |
| `_supervisor` | `app/lifecycle.py` |
| `_switch_operator_workspace25` | `app/operator_profile.py` |
| `_switch_operator_workspace_legacy` | `app/operator_profile.py` |
| `_sync_ui_cockpit` | `app/radio_link.py` |
| `_sync_ui_from_hardware` | `app/radio_link.py` |
| `_sync_ui_hardware_widgets` | `app/radio_link.py` |
| `_toggle_apt_auto` | `app/reception.py` |
| `_toggle_auto_daynight` | `app/scanner.py` |
| `_toggle_auto_margin_once` | `app/reception.py` |
| `_toggle_auto_rf_loop` | `app/radio_link.py` |
| `_toggle_auto_save_png` | `app/reception.py` |
| `_toggle_bin_filter` | `app/image_tools.py` |
| `_toggle_dashboard` | `app/responsive.py` |
| `_toggle_dept_overlay` | `app/canvas_view.py` |
| `_toggle_fft_filter` | `app/image_tools.py` |
| `_toggle_fullscreen` | `app/responsive.py` |
| `_toggle_manual_cat` | `app/radio_link.py` |
| `_toggle_manual_cat_base` | `app/radio_link.py` |
| `_toggle_margin_tool_mode` | `app/image_tools.py` |
| `_toggle_move_qth_mode` | `app/canvas_view.py` |
| `_toggle_qrn_blanker` | `app/reception.py` |
| `_toggle_recording` | `app/recording.py` |
| `_toggle_rf_att` | `app/radio_link.py` |
| `_toggle_roi_mode` | `app/canvas_view.py` |
| `_toggle_rx_decoding` | `app/reception.py` |
| `_toggle_rx_decoding_base` | `app/reception.py` |
| `_toggle_tensor_filter` | `app/image_tools.py` |
| `_toggle_upstream_hf_cond` | `app/reception.py` |
| `_topic_for25` | `app/help_system.py` |
| `_track_clock_calibration` | `app/reception.py` |
| `_trigger_carrier_scan` | `app/scanner.py` |
| `_tune_from_tree` | `app/reception_plan.py` |
| `_update_image_evidence` | `app/reception.py` |
| `_update_programme` | `app/telemetry.py` |
| `_update_programme_local` | `app/telemetry.py` |
| `_update_programme_slots` | `app/telemetry.py` |
| `_update_startup_readiness_banner25` | `app/layout.py` |
| `_update_vfo` | `app/responsive.py` |
| `_validate_margin_shift` | `app/reception.py` |
| `_view_archive` | `app/archives.py` |
| `_wait_cat` | `app/radio_link.py` |
| `_warn_suboptimal_user_action` | `app/lifecycle.py` |
| `_weather_dialog` | `app/weather_desk.py` |
| `_weather_window` | `app/weather_desk.py` |
| `_wefax_closed_loop_rf_control` | `app/radio_link.py` |
| `_wrap_main_labels` | `app/layout.py` |
| `_wrap_schedule25` | `app/styling.py` |
| `_zone_box_caption` | `app/georef_tool.py` |
| `_zoom_at_point` | `app/canvas_view.py` |
