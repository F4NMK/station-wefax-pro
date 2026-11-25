"""Aide intégrée : rubriques, recherche, F1 contextuel, infobulles."""

import re
import tkinter as tk
from tkinter import ttk
from wefax_station.ui.help_content import HELP_TOPICS_25, help_plain25
from wefax_station.ui.help_tip import DetailedHelpTip25
from wefax_station.ui.placement import show_over_root
from wefax_station.ui.theme import UITheme
from wefax_station.version import SOFTWARE_BRAND


class HelpMixin:
    def _install_help(self, parent):
        for widget in parent.winfo_children():
            if isinstance(
                widget, (tk.Button, tk.Menubutton, tk.Scale, tk.Entry, tk.Checkbutton, ttk.Combobox)
            ):
                try:
                    label = str(widget.cget("text"))
                except tk.TclError:
                    label = ""
                if isinstance(widget, tk.Scale):
                    label += " slant" if widget is getattr(self, "sld_slant", None) else " image"
                contextual = ""
                mapping = {
                    "cmb_audio": (
                        "audio",
                        "Choisir l’entrée audio du poste. Le CAT peut fonctionner même si cette entrée est incorrecte.",
                    ),
                    "cmb_proto": (
                        "cat",
                        "Choisir le protocole correspondant au poste. Les commandes ne sont pas interchangeables entre tous les modèles.",
                    ),
                    "cmb_port": (
                        "cat",
                        "Choisir le port série du CAT. Un autre logiciel ne doit pas le monopoliser.",
                    ),
                    "cmb_baud": ("cat", "Débit série : il doit correspondre à la configuration du poste."),
                    "ent_civ": (
                        "cat",
                        "Adresse CI-V en hexadécimal. A4 est la valeur par défaut de l’IC-705, mais le poste peut avoir été reconfiguré.",
                    ),
                    "ent_press": (
                        "meteo",
                        "Pression observée en hPa. Saisir une mesure réelle et dater les observations ; laisser vide si inconnue.",
                    ),
                    "ent_temp": (
                        "meteo",
                        "Température observée en degrés Celsius. Cette saisie ne constitue pas une température prédite par la carte.",
                    ),
                    "ent_rh": (
                        "meteo",
                        "Humidité relative observée en pourcentage. Ne pas renseigner une valeur fictive pour compléter le bulletin.",
                    ),
                    "cmb_ptrend": (
                        "meteo",
                        "Variation de pression des trois dernières heures (classes des bulletins marins : lente 0,1 à 1,5 hPa, 1,6 à 3,5, rapide 3,6 à 6, très rapide au-delà). Une baisse rapide annonce en général un renforcement du vent. Non renseigné sans mesure fiable.",
                    ),
                    "cmb_wind": (
                        "meteo",
                        "Vent réellement observé. Le distinguer du vent géostrophique calculé dans le module météo.",
                    ),
                    "cmb_sky": ("meteo", "État du ciel réellement observé au secteur et à la date indiqués."),
                    "cmb_wind_force": (
                        "meteo",
                        "Force du vent observée sur l'échelle de Beaufort (estimée sur l'eau ou mesurée). Elle sert à vérifier la prévision en vigueur dans la prévision à 3-6 h.",
                    ),
                    "cmb_sea": (
                        "meteo",
                        "État de la mer observé (échelle Douglas, hauteur de la mer du vent). Non renseigné si la mer n'est pas visible.",
                    ),
                    "sld_slant": (
                        "geometrie",
                        "Pente du décalage horizontal selon la hauteur. Préférer la fenêtre de correction qui affiche les unités et permet une copie non destructive.",
                    ),
                    "sld_split": (
                        "affichage",
                        "Position du rideau de comparaison entre image décodée et traitée ; ce réglage ne modifie pas les données.",
                    ),
                }
                topic = self._topic_for25(label)
                for name, (candidate, detail) in mapping.items():
                    if widget is getattr(self, name, None):
                        topic, contextual = candidate, detail
                        break
                if isinstance(widget, tk.Entry) and not contextual:
                    try:
                        variable = str(widget.cget("textvariable"))
                        if variable == str(getattr(self, "operator_callsign_var", "_")):
                            topic = "signature"
                        elif variable in (
                            str(getattr(self, "zone_var", "_")),
                            str(getattr(self, "obs_time", "_")),
                        ):
                            topic = "meteo"
                        grid = widget.grid_info()
                        if grid:
                            for sibling in widget.master.winfo_children():
                                if isinstance(sibling, tk.Label) and sibling.grid_info().get(
                                    "row"
                                ) == grid.get("row"):
                                    label = str(sibling.cget("text"))
                                    topic = self._topic_for25(label)
                                    contextual = (
                                        "Champ : "
                                        + label
                                        + ". Vérifier la valeur et les unités avant validation."
                                    )
                                    break
                    except tk.TclError:
                        pass
                self._register_tip25(widget, topic, contextual)
            self._install_help(widget)

    def _general_help(self):
        self._show_help25("demarrage")

    def _show_help25(self, topic="demarrage"):
        if topic not in HELP_TOPICS_25:
            topic = "demarrage"
        if self.help_window25 is not None and self.help_window25.winfo_exists():
            self.help_search25.set("")
            self._filter_help25()
            self._render_help25(topic)
            self.help_window25.deiconify()
            self.help_window25.lift()
            return
        win = self.help_window25 = tk.Toplevel(self.root)
        win.title(f"Aide — {SOFTWARE_BRAND}")
        win.configure(bg=UITheme.BG_ROOT)
        win.geometry("980x700")
        show_over_root(win, self.root)
        top = tk.Frame(win, bg=UITheme.BG_PANEL, padx=10, pady=8)
        top.pack(fill="x")
        tk.Label(
            top,
            text="Rechercher :",
            bg=UITheme.BG_PANEL,
            fg=UITheme.TEXT_PRIMARY,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        self.help_search25 = tk.StringVar()
        entry = tk.Entry(top, textvariable=self.help_search25)
        entry.pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(top, text="Tout afficher", command=lambda: self.help_search25.set("")).pack(side="right")
        pane = tk.PanedWindow(win, orient="horizontal", sashwidth=4, bg=UITheme.BORDER)
        pane.pack(fill="both", expand=True, padx=8, pady=6)
        left = tk.Frame(pane, bg=UITheme.BG_PANEL)
        pane.add(left, minsize=180, width=250)
        self.help_list25 = tk.Listbox(
            left,
            exportselection=False,
            activestyle="none",
            bg=UITheme.BG_ROOT,
            fg=UITheme.TEXT_PRIMARY,
            selectbackground=UITheme.ACCENT,
            selectforeground="#ffffff",
            font=("Segoe UI", 9),
            bd=0,
            highlightthickness=0,
        )
        sb = ttk.Scrollbar(left, orient="vertical", command=self.help_list25.yview)
        self.help_list25.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.help_list25.pack(fill="both", expand=True)
        right = tk.Frame(pane, bg=UITheme.BG_ROOT)
        pane.add(right, minsize=260, stretch="always")
        self.help_body25 = tk.Text(
            right,
            wrap="word",
            padx=18,
            pady=14,
            font=("Segoe UI", 10),
            bg=UITheme.BG_ROOT,
            fg=UITheme.TEXT_PRIMARY,
            cursor="arrow",
            bd=0,
            highlightthickness=0,
        )
        scroll = ttk.Scrollbar(right, orient="vertical", command=self.help_body25.yview)
        self.help_body25.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.help_body25.pack(fill="both", expand=True)
        bottom = tk.Frame(win, bg=UITheme.BG_PANEL, padx=10, pady=6)
        bottom.pack(fill="x")
        for label, command in [
            ("Réglages", self._show_settings),
            ("Diagnostics", self._show_diagnostics),
            ("Ouvrir le CSV", self._open_csv),
            ("Programme local", lambda: self._open_local(self.schedule_path)),
            ("Recharger les horaires", self._reload_schedules),
        ]:
            tk.Button(bottom, text=label, command=command).pack(side="left", padx=3)
        self._style_widget_tree25(win)
        self._responsive_toolbar(bottom)
        self.help_list25.bind("<<ListboxSelect>>", self._select_help25)
        self.help_search25.trace_add("write", lambda *args: self._filter_help25())
        self._filter_help25()
        self._render_help25(topic)
        win.bind("<Escape>", lambda event: win.withdraw())

    def _render_help25(self, key):
        title, body = HELP_TOPICS_25[key]
        text = self.help_body25
        text.configure(state="normal")
        text.delete("1.0", "end")
        for tag in text.tag_names():
            if tag.startswith("link25_"):
                text.tag_delete(tag)
        text.tag_configure("title25", font=("Segoe UI", 14, "bold"), foreground="#ffffff", spacing3=12)
        text.insert("end", title + "\n\n", "title25")
        position = 0
        for i, match in enumerate(re.finditer(r"\[\[([^|]+)\|([^]]+)\]\]", body)):
            text.insert("end", body[position : match.start()])
            target, label = match.groups()
            tag = "link25_" + str(i)
            text.tag_configure(tag, foreground="#60a5fa", underline=True)
            text.insert("end", label, tag)
            text.tag_bind(tag, "<Button-1>", lambda event, k=target: self._show_help25(k))
            text.tag_bind(tag, "<Enter>", lambda event: text.configure(cursor="hand2"))
            text.tag_bind(tag, "<Leave>", lambda event: text.configure(cursor="arrow"))
            position = match.end()
        text.insert("end", body[position:])
        text.configure(state="disabled")
        text.yview_moveto(0)
        if key in self.help_keys25:
            index = self.help_keys25.index(key)
            self.help_list25.selection_clear(0, "end")
            self.help_list25.selection_set(index)
            self.help_list25.see(index)

    def _select_help25(self, event=None):
        selected = self.help_list25.curselection()
        if selected:
            self._render_help25(self.help_keys25[selected[0]])

    def _filter_help25(self):
        query = help_plain25(self.help_search25.get())
        self.help_keys25 = [
            key for key, (title, body) in HELP_TOPICS_25.items() if query in help_plain25(title + " " + body)
        ]
        self.help_list25.delete(0, "end")
        for key in self.help_keys25:
            self.help_list25.insert("end", HELP_TOPICS_25[key][0])
        if not self.help_keys25:
            self.help_body25.configure(state="normal")
            self.help_body25.delete("1.0", "end")
            self.help_body25.insert("1.0", "Aucune rubrique trouvée. Essayer un autre mot ou Tout afficher.")
            self.help_body25.configure(state="disabled")

    def _topic_for25(self, text):
        label = help_plain25(text)
        rules = [
            ("programmes", ("horaire", "programme", "prochaine", "creneau", "suivante")),
            ("geometrie", ("marge", "slant", "geometr", "orientation", "90°", "90 deg")),
            ("signature", ("logo", "indicatif", "operateur")),
            ("compilation", ("compil", ".exe")),
            ("archives", ("archive", "historique", "export", "derniere carte", "ouvrir")),
            ("journal", ("journal", "csv", "diagnostic", "effacer")),
            ("spectre", ("spectre", "courbe", "afc")),
            ("snr", ("snr", "squelch")),
            ("audio", ("audio", "microphone", "codec")),
            ("cat", ("cat", "ci-v", "port serie", "debit", "protocole")),
            ("rf", ("preamp", "p.amp", "atten", "att ", "rf", "s-metre")),
            ("scan", ("scan", "frequen", "qsy", "rescan", "automatique", "en auto")),
            ("apt", ("apt", "decod", "reprendre", "feuille vierge")),
            (
                "traitement",
                ("lissage", "binar", "blanch", "nettet", "traitement", "traits fins", "qrn", "qsb"),
            ),
            (
                "meteo",
                (
                    "meteo",
                    "bulletin",
                    "pression",
                    "temperature",
                    "humid",
                    "vent",
                    "ciel",
                    "latitude",
                    "isobare",
                    "front",
                    "secteur",
                    "zone",
                ),
            ),
            ("affichage", ("direct", "zoom", "ajuster", "compare", "traitee", "decodee", "image")),
        ]
        for topic, words in rules:
            if any(word in label for word in words):
                return topic
        return "interface"

    def _focused_help25(self, event=None):
        widget = self.root.focus_get()
        while widget is not None:
            tip = self.help_tips25.get(str(widget))
            if tip:
                self._show_help25(tip.topic)
                return "break"
            widget = getattr(widget, "master", None)
        x, y = self.root.winfo_pointerxy()
        widget = self.root.winfo_containing(x, y)
        while widget is not None:
            tip = self.help_tips25.get(str(widget))
            if tip:
                self._show_help25(tip.topic)
                return "break"
            widget = getattr(widget, "master", None)
        self._show_help25("demarrage")
        return "break"

    def _bar_help25(self, event):
        tip = self.help_tips25.get(str(self.bargraph_canvas))
        topic = ("rf", "snr", "traitement")[min(2, max(0, event.y // 21))]
        if tip and tip.topic != topic:
            tip.topic = topic
            tip.enter()

    def _register_tip25(self, widget, topic, extra=""):
        key = str(widget)
        existing = self.help_tips25.get(key)
        if existing:
            if extra:
                existing.extra = extra
            return
        self.help_tips25[key] = DetailedHelpTip25(self, widget, topic, extra)

    def _add_tip(self, widget, text):
        try:
            label = widget.cget("text")
        except (tk.TclError, AttributeError):
            label = ""
        self._register_tip25(widget, self._topic_for25(str(label) + " " + text), text)
