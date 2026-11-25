"""Poste météo : analyse assistée, annotations de carte, bulletin documentaire, cartes Internet."""

import io
import json
import os
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
from PIL import Image
from wefax_station.core.bulletin_text import build_bulletin
from wefax_station.core.web_charts import WEB_WEATHER_CHARTS
from wefax_station.storage.atomic import atomic_json
from wefax_station.ui.placement import show_over_root
from wefax_station.version import SOFTWARE_TITLE, SOFTWARE_VERSION
from wefax_station.weather.geometry import geostrophic_estimate, local_line_axis


class WeatherDeskMixin:
    def _run_expert_weather_analysis(self):
        if not self.weather_initialized:
            self.weather_initialized = True
            self._set_bulletin(build_bulletin([], self.zone_var.get(), {}))

    def _weather_dialog(self):
        self._weather_window()
        self._polish_new_toplevels25()

    def _weather_window(self):
        win = tk.Toplevel(self.root)
        win.title(f"Analyse physique assistée — {SOFTWARE_TITLE}")
        win.geometry("700x700")
        show_over_root(win, self.root)
        container = tk.Canvas(win, highlightthickness=0)
        scroll = ttk.Scrollbar(win, orient="vertical", command=container.yview)
        container.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        container.pack(fill="both", expand=True)
        frame = tk.Frame(container, padx=12, pady=8)
        item = container.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda e: container.configure(scrollregion=container.bbox("all")))
        container.bind("<Configure>", lambda e: container.itemconfigure(item, width=e.width))
        tk.Label(
            frame,
            text="Calcul automatique après validation des mesures.\nCe module ne reconnaît pas encore les isobares, fronts ou cartouches de façon fiable.",
            wraplength=590,
            justify="left",
            fg="#9a3412",
        ).pack(fill="x", pady=5)
        fields = tk.Frame(frame)
        fields.pack(fill="x")
        values = {}
        specs = [
            ("valid", "Validité UTC de la carte (AAAA-MM-JJ HH:MM)", ""),
            ("type", "Type : analyse ou prévision", "analyse"),
            ("lat", "Latitude du secteur, degrés (+ au nord)", ""),
            ("dp", "Écart entre les deux isobares, hPa", ""),
            ("dist", "Distance perpendiculaire réelle, km", ""),
            ("low", "Azimut vrai VERS les basses pressions (facultatif)", ""),
            ("front", "Front proche confirmé : aucun / froid / chaud / occlus", "non déterminé"),
        ]
        for row, (key, title, default) in enumerate(specs):
            tk.Label(fields, text=title, anchor="w", wraplength=360, justify="left").grid(
                row=row, column=0, sticky="w", pady=5
            )
            var = tk.StringVar(value=default)
            values[key] = var
            tk.Entry(fields, textvariable=var, width=23).grid(row=row, column=1, sticky="ew", padx=5)
        fields.columnconfigure(1, weight=1)
        confirmed = tk.BooleanVar(value=False)
        tk.Checkbutton(
            frame,
            text="Je confirme le secteur, l'échelle, la validité et les isobares mesurées",
            variable=confirmed,
            wraplength=590,
            justify="left",
        ).pack(fill="x", pady=8)
        output = tk.Text(frame, height=17, wrap="word", padx=8, pady=8)
        output.pack(fill="both", expand=True)
        output.insert(
            "1.0",
            "En attente de mesures confirmées.\nL'espacement en pixels seul n'est pas une distance géographique.",
        )

        def calculate():
            try:
                if not confirmed.get():
                    raise ValueError("Confirmer les mesures et le secteur avant le calcul")
                kind = values["type"].get().strip().casefold()
                if kind not in ("analyse", "prévision", "prevision"):
                    raise ValueError("Type attendu : analyse ou prévision")
                valid = datetime.strptime(values["valid"].get().strip(), "%Y-%m-%d %H:%M").replace(
                    tzinfo=timezone.utc
                )
                age = (datetime.now(timezone.utc) - valid).total_seconds() / 3600
                fnum = lambda key: float(values[key].get().replace(",", "."))
                result = geostrophic_estimate(
                    fnum("dp"),
                    fnum("dist"),
                    fnum("lat"),
                    fnum("low") if values["low"].get().strip() else None,
                )
                lines = [
                    "CALCUL PHYSIQUE ASSISTÉ — pas une prévision locale complète",
                    f"Carte : {kind} ; validité {valid:%Y-%m-%d %H:%M UTC}",
                    "Source de position et de mesure : confirmation manuelle opérateur.",
                    f"Gradient : {result['gradient_hpa_100km']:.2f} hPa / 100 km",
                    f"Vent géostrophique théorique : {result['geostrophic_kmh']:.0f} km/h ({result['geostrophic_kt']:.0f} kt).",
                    "Ce n'est ni le vent à 10 m, ni une rafale. Densité de l'air supposée : 1,225 kg/m³.",
                ]
                if result["wind_from_deg"] is None:
                    lines.append("Direction : indéterminée sans sens des basses pressions et nord vrai.")
                else:
                    lines.append(
                        f"Direction géostrophique de provenance : {result['wind_from_deg']:.0f}° vrais."
                    )
                if kind == "analyse" and (age < 0 or age > 6):
                    lines.append(
                        "ATTENTION : cette analyse n'est pas assez récente pour être présentée comme la situation actuelle."
                    )
                if kind != "analyse":
                    lines.append("Cette carte décrit son échéance future, pas la situation actuelle.")
                front = values["front"].get().strip().casefold()
                comments = {
                    "froid": "Front froid confirmé à proximité : risque de bande pluvieuse ou d’averses ; horaire et intensité non déduits.",
                    "chaud": "Front chaud confirmé à proximité : nébulosité étendue et précipitations possibles ; horaire et intensité non déduits.",
                    "occlus": "Front occlus confirmé à proximité : nuages et précipitations possibles ; trajectoire à vérifier.",
                }
                lines.append(
                    comments.get(
                        front, "Pluie / couverture nuageuse : non déterminées par ce calcul de gradient."
                    )
                )
                lines.extend(
                    [
                        "Ensoleillement : non déterminable à partir du seul espacement des isobares.",
                        "Évolution à quelques heures : comparer des cartes datées successives ou leurs prévisions. Aucune échéance n'est inventée.",
                        "Relief, friction, courbure et effets côtiers : non modélisés. Confiance non calibrée.",
                    ]
                )
                text = "\n".join(lines)
                output.delete("1.0", "end")
                output.insert("1.0", text)
                self.last_physical_report = text
                self.log_event(
                    "Calcul gradient/vent effectue sur mesures confirmees ; aucune reconnaissance automatique validee"
                )
            except Exception as exc:
                messagebox.showwarning("Analyse non disponible", str(exc), parent=win)

        actions = tk.Frame(frame)
        actions.pack(fill="x", pady=5)
        tk.Button(actions, text="Calculer", command=calculate).pack(side="left", padx=3)

        def save():
            path = filedialog.asksaveasfilename(
                parent=win, initialdir=self.archive_dir, defaultextension=".txt"
            )
            if path:
                Path(path).write_text(output.get("1.0", "end-1c"), encoding="utf-8")

        tk.Button(actions, text="Enregistrer le rapport", command=save).pack(side="left", padx=3)

        def inspect():
            image = (
                self.completed_raw
                if self.pin_completed and self.completed_raw is not None
                else self.raw_wefax_img[: self.rx_current_line]
            )
            if image is None or image.size == 0:
                return
            h, w = image.shape[:2]
            x = int(w * self.qth_rel_pos[0])
            y = int(h * self.qth_rel_pos[1])
            r = max(40, min(h, w) // 10)
            axis = local_line_axis(image[max(0, y - r) : min(h, y + r), max(0, x - r) : min(w, x + r)])
            msg = (
                "Axe non exploitable"
                if axis is None
                else f"Axe des traits : {axis['axis_image_deg']:.1f}° dans l'image ; cohérence {axis['coherence']:.2f}.\nCe ne sont pas nécessairement des isobares ; aucune direction de vent n'en est déduite."
            )
            messagebox.showinfo("Inspection locale expérimentale", msg, parent=win)

        tk.Button(actions, text="Inspecter les traits (expérimental)", command=inspect).pack(
            side="left", padx=3
        )

    def _annotate_card(self):
        self._annotate_card_window()
        self._polish_new_toplevels25()

    def _annotate_card_window(self):
        p = self.current_metadata_path
        if not p or not Path(p).exists():
            choice = filedialog.askopenfilename(
                initialdir=self.archive_dir,
                title="Choisir les métadonnées d'une carte",
                filetypes=[("Métadonnées JSON", "*.json")],
            )
            if not choice:
                return
            p = Path(choice)
        try:
            meta = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror("Annotations", str(exc))
            return
        if not any(key in meta for key in ("station", "files", "lines")):
            messagebox.showerror("Annotations", "Ce JSON ne décrit pas une carte reçue.")
            return
        a = meta.get("annotations", {})
        win = tk.Toplevel(self.root)
        win.title("Lecture et hypothèses confirmées — " + Path(p).name)
        show_over_root(win, self.root)
        grid = tk.Frame(win, padx=12, pady=10)
        grid.pack(fill="both", expand=True)
        variables = {}
        defs = [
            ("type", "Type de carte", a.get("type", "Analyse de surface")),
            ("valid_utc", "Validité UTC (AAAA-MM-JJ HH:MM)", a.get("valid_utc", "")),
            ("zone", "Secteur concerné", a.get("zone", self.zone_var.get())),
            ("distance_km", "Distance du front au secteur (km, facultatif)", a.get("distance_km", "")),
            ("speed_kmh", "Vitesse vers le secteur (km/h, facultatif)", a.get("speed_kmh", "")),
        ]
        for row, (key, label, value) in enumerate(defs):
            tk.Label(grid, text=label).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=value)
            variables[key] = var
            widget = (
                ttk.Combobox(
                    grid,
                    textvariable=var,
                    values=["Analyse de surface", "Prévision de surface", "Altitude", "État de mer", "Autre"],
                    state="readonly",
                )
                if key == "type"
                else tk.Entry(grid, textvariable=var, width=35)
            )
            widget.grid(row=row, column=1, sticky="ew", padx=6)
        toward = tk.BooleanVar(value=a.get("toward_zone", False))
        tk.Checkbutton(
            grid,
            text="Trajectoire du front VERS le secteur confirmée ; distance et vitesse lues/estimées par l'opérateur",
            variable=toward,
            wraplength=750,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=5)
        texts = {}
        for row, (key, label) in enumerate(
            (
                ("facts", "Faits lus sur la carte (ne pas confondre avec hypothèses)"),
                ("h3", "Hypothèse H+3"),
                ("h12", "Hypothèse H+12"),
                ("h24", "Hypothèse H+24"),
            ),
            start=6,
        ):
            tk.Label(grid, text=label).grid(row=row * 2 - 6, column=0, columnspan=2, sticky="w")
            widget = tk.Text(grid, height=3, wrap="word")
            widget.insert("1.0", a.get(key, ""))
            widget.grid(row=row * 2 - 5, column=0, columnspan=2, sticky="ew", pady=(0, 5))
            texts[key] = widget
        confirmed = tk.BooleanVar(value=a.get("confirmed", False))
        tk.Checkbutton(
            grid,
            text="J'ai vérifié le type, la validité, le secteur et la lecture des éléments saisis",
            variable=confirmed,
        ).grid(row=14, column=0, columnspan=2, sticky="w", pady=5)

        def save():
            try:
                value = variables["valid_utc"].get().strip()
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                notes = {k: v.get().strip() for k, v in variables.items()}
                notes["valid_utc"] = dt.isoformat()
                notes.update({k: v.get("1.0", "end-1c").strip() for k, v in texts.items()})
                notes["confirmed"] = confirmed.get()
                notes["toward_zone"] = toward.get()
                notes["annotated_utc"] = datetime.now(timezone.utc).isoformat()
                if toward.get():
                    if float(notes["distance_km"]) <= 0 or not 0 < float(notes["speed_kmh"]) <= 200:
                        raise ValueError("Distance/vitesse invalides")
                meta["annotations"] = notes
                atomic_json(p, meta)
                self.current_metadata_path = Path(p)
                self.log_event("Annotations confirmees=" + str(confirmed.get()) + " : " + str(p))
                win.destroy()
            except Exception as exc:
                messagebox.showerror("Annotations", str(exc))

        tk.Button(grid, text="Enregistrer les annotations", command=save).grid(
            row=15, column=0, columnspan=2, pady=7
        )
        grid.columnconfigure(1, weight=1)
        self._install_help(win)

    def _generate_bulletin(self):
        if self.bulletin_dirty and not messagebox.askyesno(
            "Bulletin modifié",
            "Remplacer le texte actuel par une nouvelle compilation ? Le brouillon actuel sera conservé dans l'historique texte.",
        ):
            return
        old = self.txt_weather_report.get("1.0", "end-1c")
        if old:
            p = Path(self.archive_dir) / (
                "bulletin_avant_actualisation_"
                + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
                + ".txt"
            )
            p.write_text(old, encoding="utf-8")
        cards = []
        for p in Path(self.archive_dir).glob("*.json"):
            try:
                c = json.loads(p.read_text(encoding="utf-8"))
                if c.get("annotations"):
                    c["file"] = p.name
                    cards.append(c)
            except (OSError, ValueError):
                pass
        observations = {
            "Date UTC": self.obs_time.get(),
            "Pression hPa": self.ent_press.get(),
            "Tendance 3 h": self.cmb_ptrend.get(),
            "Température °C": self.ent_temp.get(),
            "Humidité %": self.ent_rh.get(),
            "Vent": self.cmb_wind.get(),
            "Ciel": self.cmb_sky.get(),
        }
        self._set_bulletin(build_bulletin(cards, self.zone_var.get(), observations))
        self._save_draft()
        self.log_event("Bulletin compile depuis les annotations confirmees")

    def _set_bulletin(self, text):
        self.draft_loading = True
        self.txt_weather_report.delete("1.0", "end")
        self.txt_weather_report.insert("1.0", text)
        self.txt_weather_report.edit_modified(False)
        self.draft_loading = False
        self.bulletin_dirty = False

    def _copy_bulletin(self):
        text = self.txt_weather_report.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()
        self.lbl_status.configure(text="Bulletin copié dans le presse-papiers.")

    def _bulletin_modified(self, event=None):
        if self.txt_weather_report.edit_modified():
            if not self.draft_loading:
                self.bulletin_dirty = True
            self.txt_weather_report.edit_modified(False)

    def _save_draft(self):
        """Brouillon du bulletin, écrit seulement s'il a changé (2.10.0 : avant, toutes les 15 s)."""
        if hasattr(self, "txt_weather_report") and hasattr(self, "archive_dir"):
            from wefax_station.storage.atomic import atomic_text

            p = self._draft_path() if hasattr(self, "_draft_path") else Path(self.archive_dir) / "bulletin_brouillon.txt"
            text = self.txt_weather_report.get("1.0", "end-1c")
            if getattr(self, "_draft_saved", None) == (str(p), text):
                return False
            atomic_text(p, text)
            self._draft_saved = (str(p), text)
            return True

    def _save_weather_bulletin_manual(self):
        op = self.operator_callsign_var.get().strip().upper()
        op_tag = f"_{op}" if op else ""
        default_name = (
            f"BULLETIN_METEO_F4NMK{op_tag}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}Z.txt"
        )
        path = filedialog.asksaveasfilename(
            title="Enregistrer le Bulletin Météo (.txt)",
            initialdir=self.archive_dir,
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[("Fichier Texte", "*.txt"), ("Tous", "*.*")],
        )
        if not path:
            return
        try:
            content = self.txt_weather_report.get("1.0", "end").strip()
            with open(path, "w", encoding="utf-8") as f:
                f.write(content + "\n")
            self.log_event(f"📝 Bulletin météo enregistré sur demande opérateur : {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Erreur sauvegarde bulletin", str(exc))

    def _download_web_weather_chart(self):
        """Carte du site de la DWD, affichée en CONSULTATION (2.10.0).

        Avant : l'image téléchargée remplaçait la feuille de réception radio (raw_wefax_img) et restait à
        l'écran sans bandeau — le 19/11 de 19:23 à 20:40 UTC elle a pu passer pour une réception ; si le
        serveur ne répondait pas, une carte de TEST fabriquée était affichée à la place. Maintenant : bandeau
        « Carte Internet », retour automatique au direct comme pour une archive, jamais de carte fabriquée,
        et rien n'est tenté si l'accès Internet est coupé dans les Réglages.
        """
        chart_title = (
            self.cmb_web_chart.get() if hasattr(self, "cmb_web_chart") else list(WEB_WEATHER_CHARTS.keys())[0]
        )
        cfg = WEB_WEATHER_CHARTS.get(chart_title, list(WEB_WEATHER_CHARTS.values())[0])
        url_list = cfg["urls"]
        planner = getattr(self, "schedule_planner", None)
        if planner is not None and getattr(planner, "network_cut_off_manual", False):
            msg = "Accès Internet coupé (Réglages) : carte Web non téléchargée."
            self.lbl_status.configure(text=msg, fg="#fbbf24")
            self.log_event("🔒 " + msg)
            return

        self.set_busy_state(True, "TÉLÉCHARGEMENT CARTE DWD...")
        self.log_event(f"🌐 Téléchargement Web demandé : {chart_title}...")

        def _worker():
            last_error_str = "Serveur DWD injoignable"
            downloaded_np = None
            for candidate_url in url_list:
                try:
                    req = urllib.request.Request(
                        candidate_url,
                        headers={
                            "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; StationWEFAXPro/{SOFTWARE_VERSION})"
                        },
                    )
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        raw_bytes = resp.read()
                    pil_in = Image.open(io.BytesIO(raw_bytes)).convert("L")
                    downloaded_np = np.array(pil_in, dtype=np.uint8)
                    break
                except Exception as exc:
                    last_error_str = str(exc)

            def _display_loaded_chart(img_arr, source_label):
                self.set_busy_state(False)
                self.show_web_chart(img_arr, source_label)

            def _failed():
                self.set_busy_state(False)
                msg = f"⚠️ Carte Web non téléchargée ({last_error_str}) — aucune carte affichée."
                self.lbl_status.configure(text=msg, fg="#fbbf24")
                self.log_event(msg)

            if downloaded_np is not None:
                self.ui_events.put(lambda arr=downloaded_np: _display_loaded_chart(arr, chart_title))
            else:
                self.ui_events.put(_failed)

        threading.Thread(target=_worker, daemon=True).start()

    def show_web_chart(self, img_arr, source_label):
        """Affiche une carte Internet en consultation, sans toucher à la feuille de réception radio."""
        gray = np.asarray(img_arr, dtype=np.uint8)
        self.completed_raw = gray.copy()
        self.completed_rgb = np.dstack([gray, gray, gray])
        self.pin_completed = True
        self.current_metadata_path = None
        name = f"Carte Internet (pas une réception radio) — {source_label}"
        self.viewing_archived_file = name
        if hasattr(self, "lbl_archive_state"):
            self.lbl_archive_state.configure(text="Consultation : " + name)
        if hasattr(self, "_begin_consultation"):
            self._begin_consultation(name)
            self.viewing_archived_file = name
        self._reset_zoom_pan()
        self._refresh_canvas()
        ih, iw = gray.shape[:2]
        msg = f"✅ Carte Web DWD affichée en consultation ({iw}x{ih} px) : {source_label}"
        self.lbl_status.configure(text=msg, fg="#34d399")
        self.log_event(msg)
