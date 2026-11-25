"""Mise en page adaptative : l'interface reste complète et lisible de 1024×600 à 4K.

Principes :
* la carte WEFAX est prioritaire : tout ce qui n'est pas elle se compacte avant elle ;
* aucune commande n'est jamais masquée par manque de place : la barre de commandes passe sur
  plusieurs lignes (disposition « en flux ») au lieu de couper les boutons de droite ;
* trois paliers de largeur pour le tableau de bord (3 colonnes / 2 + 1 / empilé) et un palier de
  hauteur qui compacte le bandeau des étapes (titres seuls) sur les petits écrans ;
* F9 replie / déplie le tableau de bord (carte en plein écran dans la fenêtre), F11 bascule en plein écran ;
* l'image est recalculée à chaque redimensionnement du canevas (sans clignotement : 120 ms de délai).
"""

import tkinter as tk

from wefax_station.ui.vfo_display import VfoDisplay

WIDE_DASHBOARD_MIN = 1180  # 3 colonnes au-delà
COMPACT_HEIGHT_MAX = 820  # en dessous : bandeau des étapes sur une ligne
TINY_HEIGHT_MAX = 660  # en dessous : tableau de bord replié automatiquement au démarrage


class ResponsiveLayoutMixin:
    def _init_responsive_layout(self):
        self.root.minsize(960, 560)
        self._dash_collapsed = False
        self._layout_state = {}
        # barre de commandes en flux (plus aucun bouton coupé à droite)
        slot = getattr(self, "controls_slot25", None)
        if slot is not None:
            self._make_flow(slot)
        # tableau de bord : colonnes latérales à largeur minimale garantie
        if hasattr(self, "dashboard25"):
            self.dashboard25.unbind("<Configure>")
            self.dashboard25.bind("<Configure>", lambda e: self._schedule_relayout(), add="+")
        # bandeau radio : retour à la ligne au lieu d'être coupé
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        # canevas : rendu recalculé à chaque redimensionnement
        self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")
        self.root.bind("<F9>", lambda e: self._toggle_dashboard())
        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self._exit_fullscreen(), add="+")
        self._add_layout_menu()
        # afficheur façon façade de poste (remplace la ligne « station · fréquence » et le bandeau orange)
        try:
            band = self.lbl_freq_display.master
            self.vfo = VfoDisplay(band, height=64)
            self.lbl_freq_display.grid_remove()
            self.lbl_radio_details.grid_remove()
            # 2.11.2 — retirer les boutons legacy de la barre de base qui débordaient sous le VFO
            # sur les petits écrans : « Réglages » (col 3), « Météo & bulletin » (col 4),
            # « Stations » (col 5). Ces commandes sont désormais toutes accessibles via la barre
            # de menus et la barre de commandes du cockpit ; les conserver dans band crée un
            # doublon visible et, quand btn_stations passe en orange après un choix de station,
            # un bouton coloré inattendu s'affiche sous le tableau de bord.
            for attr in ("btn_meteo_desk", "btn_stations"):
                btn = getattr(self, attr, None)
                if btn is not None:
                    try:
                        btn.grid_remove()
                    except tk.TclError:
                        pass
            # « Réglages » n'a pas d'attribut propre : on le cherche dans la grille de band
            for child in band.grid_slaves():
                try:
                    if str(child.cget("text")) == "Réglages":
                        child.grid_remove()
                        break
                except tk.TclError:
                    pass
            # 2.11.2 — rebrancher _on_manual_hold_changed sur le bouton « Fréquences » du cockpit
            # (btn_stations a été caché via grid_remove ; il faut que l'indicateur orange reste visible)
            cockpit_btn = getattr(self, "_btn_stations_cockpit", None)
            if cockpit_btn is not None:
                self.btn_stations = cockpit_btn
                self._btn_stations_bg = "#334155"  # couleur de base du bouton cockpit (fond sombre)
            self.vfo.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(4, 8), pady=2)
            band.columnconfigure(1, weight=1)
            band.columnconfigure(2, weight=0)
            self.root.after(300, self._update_vfo)
        except (tk.TclError, AttributeError):
            self.vfo = None
        # bouton toujours visible pour replier / déplier le tableau de bord
        try:
            band = self.lbl_freq_display.master
            self.btn_dash_toggle = tk.Button(
                band, text="▴ Tableau de bord", command=self._toggle_dashboard, font=("Segoe UI", 9), padx=6
            )
            self.btn_dash_toggle.grid(row=0, column=5, padx=3)
            self._register_tip25(
                self.btn_dash_toggle,
                "interface",
                "Replie le tableau de bord pour agrandir la carte (F9). F11 : plein écran.",
            )
        except Exception:
            pass
        # la barre d'état est réservée en bas AVANT la carte : elle ne peut plus être écrasée
        try:
            status = self.lbl_status.master
            status.pack_forget()
            status.pack(side="bottom", fill="x", before=self.canvas)
        except (tk.TclError, AttributeError):
            pass
        self.root.after(200, self._relayout)
        if self.root.winfo_screenheight() <= TINY_HEIGHT_MAX:
            self.root.after(400, lambda: self._toggle_dashboard(force=True))

    # ------------------------------------------------------------- afficheur du poste
    def _update_vfo(self):
        vfo = getattr(self, "vfo", None)
        if vfo is None:
            return
        r = self.radio
        arb = getattr(self, "hybrid_arbiter", None)
        service, detail = "WEFAX", "120 lpm · IOC 576"
        if arb is not None and arb.active_pipeline == "RTTY":
            st = arb.active_rtty_station
            if "NAVTEX" in st.get("protocol", ""):
                service, detail = "NAVTEX", "SITOR-B 100 Bd · 170 Hz"
            else:
                service, detail = "RTTY", f"{st['baud']:.0f} Bd · shift {st['shift_hz']:.0f} Hz"
        if arb is not None and arb.veille_active:
            detail += " · veille de propagation"
        quality = ""
        try:
            from wefax_station.weather.reliability import WeatherReliabilityEstimator

            if service == "WEFAX":
                rel = WeatherReliabilityEstimator.compute_wefax_reliability(self)
            else:
                rel = WeatherReliabilityEstimator.compute_rtty_reliability(
                    self.rtty_decoder, arb.rtty_raw_buffer
                )
            quality = f"Fiabilité {rel['score_pct']} % [{rel['grade']}]"
        except Exception:
            pass
        connected = bool(r.port_open and r.handshake_ok)
        vfo.update_state(
            freq_khz=float(r.actual_freq_khz),
            dial_khz=float(r.actual_dial_khz),
            station=str(r.active_station_id),
            name=str(r.active_station_name),
            mode=str(r.actual_mode_str),
            filter=str(r.actual_filter_str),
            agc=str(r.actual_agc_str),
            preamp=int(r.actual_preamp or 0),
            att=bool(r.actual_att),
            s_raw=(r.s_meter_raw if (connected and r.s_meter_valid) else None),
            s_label=str(r.s_meter_label),
            service=service,
            service_detail=detail,
            quality=quality,
            cat=connected,
        )

    # ------------------------------------------------------------- flux
    def _make_flow(self, frame):
        widgets = [w for w in frame.pack_slaves()] + [w for w in frame.grid_slaves()[::-1]]
        seen, ordered = set(), []
        for w in widgets:
            if str(w) not in seen:
                seen.add(str(w))
                ordered.append(w)
        for w in ordered:
            w.pack_forget()
        frame._flow_widgets = ordered
        frame._flow_sig = None

        def layout(event=None):
            width = max(120, frame.winfo_width())
            req = tuple((w.winfo_reqwidth(), w.winfo_reqheight()) for w in ordered)
            sig = (width, req)
            if sig == frame._flow_sig:
                return
            frame._flow_sig = sig
            # placement libre ligne par ligne (pas de colonnes partagées : chaque bouton garde sa largeur)
            x = y = row_h = 0
            for w, (rw, rh) in zip(ordered, req):
                if x and x + rw > width:
                    x = 0
                    y += row_h + 3
                    row_h = 0
                w.place(x=x, y=y)
                x += rw + 4
                row_h = max(row_h, rh)
            total = y + row_h + 2
            if int(frame.cget("height") or 0) != total:
                frame.configure(height=total)

        frame.pack_propagate(False)
        frame.grid_propagate(False)
        frame.bind("<Configure>", layout, add="+")
        frame.after_idle(layout)

    # ------------------------------------------------------- disposition
    def _on_root_configure(self, event):
        if event.widget is self.root:
            self._schedule_relayout()

    def _schedule_relayout(self):
        if getattr(self, "_relayout_job", None):
            try:
                self.root.after_cancel(self._relayout_job)
            except tk.TclError:
                pass
        self._relayout_job = self.root.after(60, self._relayout)

    def _relayout(self):
        self._relayout_job = None
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
        except tk.TclError:
            return
        if w < 50:
            return
        self._layout_dashboard_columns(w)
        self._layout_steps(h, w)

    def _layout_dashboard_columns(self, width):
        if not hasattr(self, "dashboard25") or self._dash_collapsed:
            return
        mode = "wide" if width >= WIDE_DASHBOARD_MIN else "stacked"
        if self._layout_state.get("dash") == mode:
            return
        self._layout_state["dash"] = mode
        d = self.dashboard25
        for wdg in (self.metrics25, self.center_hub25, self.spectrum25):
            wdg.grid_forget()
        for c in range(3):
            d.columnconfigure(c, weight=0, minsize=0)
        if mode == "wide":
            d.columnconfigure(0, weight=0, minsize=250)
            d.columnconfigure(1, weight=1)
            d.columnconfigure(2, weight=0, minsize=320)
            self.metrics25.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
            self.center_hub25.grid(row=0, column=1, sticky="nsew", padx=(0, 5))
            self.spectrum25.grid(row=0, column=2, sticky="nsew")
        else:
            d.columnconfigure(0, weight=1, uniform="dash")
            d.columnconfigure(1, weight=1, uniform="dash")
            self.metrics25.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=(0, 3))
            self.spectrum25.grid(row=0, column=1, sticky="nsew", pady=(0, 3))
            self.center_hub25.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.dashboard_mode25 = "three_cols" if mode == "wide" else "stacked"

    def _layout_steps(self, height, width):
        banner = getattr(self, "rx_step_banner", None)
        if banner is None or not getattr(banner, "cells", None):
            return
        compact = height < COMPACT_HEIGHT_MAX or width < 1100
        if self._layout_state.get("steps") == compact:
            return
        self._layout_state["steps"] = compact
        for cell, lbl_t, lbl_d in banner.cells.values():
            if compact:
                lbl_d.pack_forget()
                lbl_t.configure(font=("Segoe UI", 8, "bold"))
            elif not lbl_d.winfo_manager():
                lbl_d.pack(fill="x")
            # le détail reste lisible en infobulle quand il est masqué
            cell._detail_label = lbl_d
        if compact and not getattr(banner, "_tips_installed", False):
            banner._tips_installed = True
            for cell, lbl_t, lbl_d in banner.cells.values():
                lbl_t.bind("<Enter>", lambda e, d=lbl_d, t=lbl_t: self._step_tip(t, d), add="+")

    def _step_tip(self, lbl_t, lbl_d):
        try:
            self.lbl_status.configure(text=f"{lbl_t.cget('text')} — {lbl_d.cget('text')}")
        except tk.TclError:
            pass

    # ------------------------------------------------------------- carte
    def _on_canvas_configure(self, event):
        sig = (event.width, event.height)
        if sig == getattr(self, "_canvas_sig", None):
            return
        self._canvas_sig = sig
        if getattr(self, "_canvas_job", None):
            try:
                self.root.after_cancel(self._canvas_job)
            except tk.TclError:
                pass
        self._canvas_job = self.root.after(120, self._refresh_canvas)

    # ------------------------------------------------- repli / plein écran
    def _toggle_dashboard(self, force=None):
        collapse = (not self._dash_collapsed) if force is None else bool(force)
        if collapse == self._dash_collapsed:
            return
        self._dash_collapsed = collapse
        banner = getattr(getattr(self, "rx_step_banner", None), "frame", None)
        if collapse:
            self.dashboard25.pack_forget()
            self.log_event("Tableau de bord replié (F9 pour le réafficher) : carte agrandie.")
        else:
            self.dashboard25.pack(
                fill="x", padx=0, pady=0, before=banner if banner is not None else self.canvas
            )
            self._layout_state.pop("dash", None)
            self._schedule_relayout()
        if hasattr(self, "_layout_menu_var"):
            self._layout_menu_var.set(collapse)
        if hasattr(self, "btn_dash_toggle"):
            self.btn_dash_toggle.configure(text="▾ Tableau de bord" if collapse else "▴ Tableau de bord")
        self.root.after(150, self._refresh_canvas)

    def _toggle_fullscreen(self):
        try:
            state = bool(self.root.attributes("-fullscreen"))
            self.root.attributes("-fullscreen", not state)
        except tk.TclError:
            pass

    def _exit_fullscreen(self):
        try:
            if self.root.attributes("-fullscreen"):
                self.root.attributes("-fullscreen", False)
        except tk.TclError:
            pass

    def _add_layout_menu(self):
        try:
            menubar = self.root.nametowidget(self.root.cget("menu"))
        except (tk.TclError, KeyError):
            return
        self._layout_menu_var = tk.BooleanVar(master=self.root, value=False)
        menu = tk.Menu(menubar, tearoff=False)
        menu.add_checkbutton(
            label="Replier le tableau de bord (carte agrandie)    F9",
            variable=self._layout_menu_var,
            command=lambda: self._toggle_dashboard(force=self._layout_menu_var.get()),
        )
        menu.add_command(label="Plein écran    F11", command=self._toggle_fullscreen)
        menu.add_command(label="Ajuster la carte à la fenêtre", command=self._reset_zoom_pan)
        menubar.add_cascade(label="Affichage", menu=menu)
