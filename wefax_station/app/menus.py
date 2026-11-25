"""Barre de menus unique, organisée par tâche (2.8.5).

Avant : six menus (Outils, Automatisation, Aide, Bulletins, Enregistrements, Affichage) plus deux listes
déroulantes dans la barre de commandes (« Cartes ▾ », « Réception ▾ »), construits par cinq modules
différents, avec les mêmes commandes à plusieurs endroits (scan des fréquences à trois endroits, plan de
réception à deux, aide à deux, rapport à trois).

Maintenant : cinq menus, chaque commande à UN seul endroit.

2.8.8 — règle appliquée partout : le menu ouvre les fenêtres et porte les commandes générales ; une
fenêtre ne garde que les actions de SA tâche. Ainsi « Winlink » ouvre directement l'assistant (ses trois
étapes y sont), le scan RTTY est dans le téléscripteur, le vent géostrophique dans « Météo & bulletin ».

    Réception   ce que fait le poste : démarrer, scanner, choisir la fréquence, mode, enregistrement audio
    Cartes      les images : afficher, ouvrir, exporter, corriger, agrandir
    Bulletins   les textes : téléscripteur, météo & bulletin, rapport, vent
    Réglages    ce qui se règle une fois : radio, image, opérateur, plan de réception, automatismes, dossiers
    Aide

Cette barre est construite en dernier, une fois tous les modules initialisés, et remplace l'ancienne.
Le profil « Membre ADRASEC » (Réglages › Opérateur) adapte les libellés et les documents produits.
"""

import sys
import tkinter as tk

from wefax_station.ui.theme import UITheme


class MenusMixin:
    # ------------------------------------------------------------------ profil ADRASEC
    def is_adrasec(self) -> bool:
        var = getattr(self, "adrasec_var", None)
        try:
            return bool(var.get()) if var is not None else False
        except tk.TclError:
            return False

    def report_label(self) -> str:
        """Nom du rapport en un clic selon le profil de l'opérateur."""
        return "Rapport ADRASEC" if self.is_adrasec() else "Rapport météo"

    def _apply_adrasec_mode(self):
        """Met à jour tout ce qui dépend du profil (libellés de boutons et de menus)."""
        label = "📋 " + self.report_label()
        for btn in list(getattr(self, "_report_buttons", [])):
            try:
                if btn.winfo_exists():
                    btn.configure(text=label)
            except tk.TclError:
                pass
        menu, index = getattr(self, "_report_menu_entry", (None, None))
        if menu is not None:
            try:
                menu.entryconfigure(index, label=self.report_label() + " (1 clic)")
            except tk.TclError:
                pass

    def register_report_button(self, button):
        if not hasattr(self, "_report_buttons"):
            self._report_buttons = []
        self._report_buttons.append(button)
        try:
            button.configure(text="📋 " + self.report_label())
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ netteté des cartes
    def _apply_sharpness(self, save=True):
        from wefax_station.dsp.wefax_demod import WefaxStreamDemodulator

        var = getattr(self, "sharpness_var", None)
        mode = str(var.get()).upper() if var is not None else "AUTO"
        if mode not in ("AUTO", "DETAIL", "ROBUSTE"):
            mode = "AUTO"
        if WefaxStreamDemodulator.SHARPNESS != mode:
            WefaxStreamDemodulator.SHARPNESS = mode
            self.log_event(f"Netteté des cartes : {mode} (prise en compte dès la ligne suivante)")
        if save and hasattr(self, "_save_preferences"):
            self._save_preferences()

    # ------------------------------------------------------------------ barre de menus
    def _menu(self, parent):
        return tk.Menu(
            parent,
            tearoff=False,
            bg=UITheme.BG_PANEL,
            fg=UITheme.TEXT_PRIMARY,
            activebackground=UITheme.ACCENT,
            activeforeground="#ffffff",
        )

    def _rebuild_menubar(self):
        bar = tk.Menu(self.root, tearoff=False)
        arb = getattr(self, "hybrid_arbiter", None)
        planner = getattr(self, "schedule_planner", None)
        bulletins = getattr(self, "bulletins_ui", None)

        # ---- Réception
        m = self._menu(bar)
        m.add_command(label="Démarrer en auto (connexion et meilleure fréquence)", command=self._one_click)
        m.add_command(label="Reprendre en milieu de carte", command=self._resume_midchart)
        m.add_separator()
        m.add_command(label="Chercher la meilleure fréquence des cartes (scan WEFAX)", command=self._trigger_carrier_scan)
        m.add_command(label="Résultats du dernier scan / choisir la fréquence…", command=self._open_scan_results)
        if arb is not None:
            m.add_separator()
            if not hasattr(self, "_mode_var"):
                self._mode_var = tk.StringVar(master=self.root, value=arb.requested_mode)
            mode = self._menu(m)
            for value, label in (
                ("HYBRIDE", "Cartes + bulletins planifiés (recommandé)"),
                ("WEFAX", "Cartes WEFAX seulement"),
                ("BULLETINS", "Bulletins RTTY / NAVTEX seulement"),
                ("MANUEL", "Manuel (aucune bascule automatique)"),
            ):
                mode.add_radiobutton(
                    label=label,
                    variable=self._mode_var,
                    value=value,
                    command=lambda v=value: arb.set_requested_mode(v, True),
                )
            m.add_cascade(label="Mode de réception", menu=mode)
        if hasattr(self, "auto_record_var"):
            rec = self._menu(m)
            rec.add_command(label="Démarrer / arrêter l'enregistrement", command=self._toggle_recording)
            rec.add_checkbutton(
                label="Enregistrer automatiquement chaque carte (START → fin)", variable=self.auto_record_var
            )
            rec.add_separator()
            rec.add_command(label="Rejouer un enregistrement WAV dans le décodeur…", command=self._replay_wav_dialog)
            rec.add_command(label="Arrêter la relecture", command=lambda: self._stop_replay("Arrêt opérateur"))
            rec.add_separator()
            rec.add_command(label="Ouvrir le dossier des enregistrements", command=self._open_recordings_dir)
            m.add_cascade(label="Enregistrement audio", menu=rec)
        bar.add_cascade(label="Réception", menu=m)

        # ---- Cartes
        m = self._menu(bar)
        m.add_command(label="Réception directe", command=self._show_live)
        m.add_command(label="Dernière carte reçue", command=self._show_completed)
        m.add_command(label="Historique…", command=self._history)
        m.add_separator()
        m.add_command(label="Ouvrir une image…", command=self._load_wefax_file)
        m.add_command(label="Exporter en PNG…", command=self._save_stamped_wefax)
        m.add_command(label="Télécharger la carte Web (Internet)", command=self._download_web_weather_chart)
        m.add_separator()
        m.add_command(label="Recaler automatiquement (marge et inclinaison)", command=self._run_auto_margin_and_slant)
        m.add_command(label="Corriger à la main (marge, inclinaison, rotation)…", command=self._geometry_dialog)
        m.add_separator()
        m.add_command(label="Ajuster la carte à la fenêtre", command=self._reset_zoom_pan)
        if not hasattr(self, "_layout_menu_var"):
            self._layout_menu_var = tk.BooleanVar(master=self.root, value=False)
        m.add_checkbutton(
            label="Replier le tableau de bord (carte agrandie)    F9",
            variable=self._layout_menu_var,
            command=lambda: self._toggle_dashboard(force=self._layout_menu_var.get()),
        )
        m.add_command(label="Plein écran    F11", command=self._toggle_fullscreen)
        bar.add_cascade(label="Cartes", menu=m)

        # ---- Bulletins
        m = self._menu(bar)
        if bulletins is not None:
            m.add_command(label="Téléscripteur RTTY / NAVTEX (direct et bulletins reçus)", command=bulletins.show)
        m.add_command(label="Météo & bulletin (réceptions, analyse, rédaction)", command=self._open_bulletin_desk)
        if bulletins is not None:
            m.add_command(
                label=self.report_label() + " (1 clic)", command=bulletins._generate_orsec_bulletin_dialog
            )
            self._report_menu_entry = (m, m.index("end"))
        if planner is not None:
            m.add_separator()
            m.add_command(
                label="Programmes : sources officielles (télécharger et comparer)…",
                command=lambda: planner.open_sources_window(refresh=True),
            )
        bar.add_cascade(label="Bulletins", menu=m)

        # ---- Winlink : une seule entrée, l'assistant fait le reste (2.8.8)
        if hasattr(self, "_open_winlink_desk"):
            bar.add_command(label="Winlink", command=self._open_winlink_desk)

        # ---- Réglages
        m = self._menu(bar)
        m.add_command(label="Radio…", command=lambda: self._show_settings("RADIO"))
        m.add_command(label="Image…", command=lambda: self._show_settings("IMAGE"))
        m.add_command(label="Opérateur & observations…", command=lambda: self._show_settings("METEO"))
        m.add_command(label="Plan de réception (bulletins à recevoir, veille)…", command=lambda: self._show_settings("PLAN"))
        m.add_separator()
        rescan = self._menu(m)
        for val in ("Jamais", "Confirmation", "Automatique"):
            rescan.add_radiobutton(label=val, variable=self.qsy_policy, value=val)
        m.add_cascade(label="Nouveau scan quand le signal se perd", menu=rescan)
        m.add_checkbutton(label="Empêcher la mise en veille de l'ordinateur", variable=self.prevent_sleep)
        if planner is not None:
            if not hasattr(self, "_net_var"):
                self._net_var = tk.BooleanVar(master=self.root, value=True)
            m.add_checkbutton(
                label="Autoriser l'accès Internet (horaires, cartes Web)",
                variable=self._net_var,
                command=lambda: (
                    planner.set_manual_network_cutoff(not self._net_var.get()),
                    self._sync_ui_from_hardware(),
                ),
            )
        m.add_separator()
        m.add_command(label="Diagnostics", command=self._show_diagnostics)
        m.add_command(label="Ouvrir le journal (CSV)", command=self._open_csv)
        m.add_command(label="Ouvrir le dossier des archives", command=self._open_archive)
        if not getattr(sys, "frozen", False):
            m.add_command(label="Compiler en .exe", command=self._compile_exe)
        bar.add_cascade(label="Réglages", menu=m)

        # ---- Aide
        m = self._menu(bar)
        m.add_command(label="Sommaire et recherche    F1", command=self._general_help)
        m.add_command(label="Guide illustré (français / English)", command=self._open_illustrated_guide)
        m.add_command(label="Lire les indicateurs", command=lambda: self._show_help25("spectre"))
        m.add_command(label="Prochaine carte / programme UTC", command=lambda: self._show_help25("programmes"))
        if bulletins is not None:
            m.add_command(
                label="Indices de qualité et choix de fréquence", command=bulletins.show_reliability_help_dialog
            )
        if hasattr(self, "_show_about"):
            m.add_separator()
            m.add_command(label="À propos de Station WEFAX PRO…", command=self._show_about)
        bar.add_cascade(label="Aide", menu=m)

        self.root.configure(menu=bar)
        self._remove_toolbar_dropdowns()

    def _open_illustrated_guide(self):
        """2.10.0 — guide illustré autonome (docs/Guide_Station_WEFAX_PRO.html), lisible sans Internet."""
        import webbrowser
        from pathlib import Path

        from wefax_station.version import PROJECT_ROOT

        guide = Path(PROJECT_ROOT) / "docs" / "Guide_Station_WEFAX_PRO.html"
        if not guide.is_file():
            from tkinter import messagebox

            messagebox.showwarning("Guide illustré", f"Guide introuvable :\n{guide}")
            return False
        try:
            if sys.platform == "win32":
                import os

                os.startfile(str(guide))
            else:
                webbrowser.open(guide.as_uri())
            self.log_event(f"📘 Guide illustré ouvert : {guide.name}")
            return True
        except Exception as exc:
            self.log_event(f"Guide illustré non ouvert : {exc!r}")
            return False

    def _remove_toolbar_dropdowns(self):
        """Supprime les anciens Menubutton « Cartes ▾ » / « Réception ▾ » de la barre LEGACY uniquement.

        2.11.2 — ces widgets existent à deux endroits :
          * map_toolbar_frame (barre legacy construite par _build_right_map_area_base) → à supprimer ;
          * controls_slot25 (barre de commandes du nouveau cockpit, en flux) → à CONSERVER.
        La version précédente parcourait toute la hiérarchie et détruisait aussi les boutons du cockpit,
        ce qui rendait les menus déroulants inaccessibles depuis la barre de commandes.
        """
        legacy = getattr(self, "map_toolbar_frame", None)
        if legacy is None:
            return
        try:
            for child in list(legacy.winfo_children()):
                if child.winfo_class() == "Menubutton" and str(child.cget("text")).rstrip(" ▾") in (
                    "Cartes",
                    "Réception",
                ):
                    child.place_forget()
                    child.destroy()
        except tk.TclError:
            pass
