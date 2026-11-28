"""Repérage de la carte et zone d'analyse.

La zone d'analyse de l'opérateur est la CASE placée sur la carte (outil « Zone manuelle »). Pour que
les bulletins texte (latitudes / longitudes) soient lus pour cette même zone, la carte est repérée une
fois par type de carte : 3 clics sur des croisements méridien / parallèle dont on saisit les
coordonnées. Ensuite le centre et le rayon de la case sont calculés automatiquement.

Sans repérage pour la famille de l'émetteur, l'analyse retombe sur la position déclarée dans
Réglages › Plan de réception (et le dit).
"""

from tkinter import messagebox, simpledialog

from wefax_station.weather.georef import Georef, GeorefStore, km_label, parse_latlon


class GeorefToolMixin:
    def _georef_store(self):
        st = getattr(self, "_georef_store_obj", None)
        if st is None:
            ws = getattr(self, "portable_ws", None)
            base = (
                ws.root_dir / "configuration"
                if ws is not None
                else __import__("pathlib").Path(self.archive_dir)
            )
            st = GeorefStore(base / "reperage_cartes.json")
            self._georef_store_obj = st
        return st

    def _chart_family(self):
        return str(getattr(self.radio, "active_station_family", "DWD") or "DWD")

    # ------------------------------------------------------------------ zone d'analyse
    def analysis_zone(self):
        """Zone utilisée par toutes les analyses : dict(lat, lon, radius, label, source)."""
        geo = self._georef_store().active(self._chart_family())
        if getattr(self, "weather_roi_box", None) is None:
            try:
                self._recompute_roi_from_qth()
            except Exception:
                pass
        box = getattr(self, "weather_roi_box", None)
        if geo is not None and box is not None:
            lat, lon, r = geo.zone_from_box(box)
            r = max(30.0, r)
            return {
                "lat": lat,
                "lon": lon,
                "radius": r,
                "label": f"zone de votre case ({km_label(lat, lon, r)})",
                "source": f"case repérée sur « {geo.name} »",
            }
        arb = getattr(self, "hybrid_arbiter", None)
        plan = arb.plan if arb is not None else {}
        lat, lon = plan.get("qth", (43.58, 7.02))
        r = float(plan.get("radius_km", 500))
        zone = self.zone_var.get() if hasattr(self, "zone_var") else "votre position"
        return {
            "lat": float(lat),
            "lon": float(lon),
            "radius": r,
            "label": f"{zone} ({km_label(float(lat), float(lon), r)})",
            "source": "position déclarée (carte non repérée : Réception › Repérer la carte)",
        }

    def _zone_box_caption(self):
        z = self.analysis_zone()
        return (
            ("ZONE " + km_label(z["lat"], z["lon"], z["radius"]))
            if "case" in z["source"]
            else "ZONE (carte non repérée)"
        )

    # ------------------------------------------------------------------ outil de repérage
    def _start_georef(self):
        if getattr(self, "rotation_quarters", 0):
            messagebox.showwarning("Repérer la carte", "Remettez d'abord la carte à l'endroit (rotation).")
            return
        self.canvas_tool_mode = "GEOREF"
        self._georef_pts = []
        self.canvas.config(cursor="crosshair")
        self.lbl_status.configure(
            text="📐 REPÉRAGE : cliquez un croisement méridien / parallèle dont vous lisez les coordonnées sur la "
            "carte, puis saisissez-les. 3 points au moins, bien écartés (Échap pour annuler).",
            fg="#38bdf8",
        )
        self.root.bind("<Escape>", lambda e: self._cancel_georef(), add="+")
        self._refresh_canvas()

    def _cancel_georef(self):
        if getattr(self, "canvas_tool_mode", "") == "GEOREF":
            self.canvas_tool_mode = "NONE"
            self._georef_pts = []
            self.canvas.config(cursor="fleur")
            self.lbl_status.configure(text="Repérage annulé.")
            self._refresh_canvas()

    def _georef_click(self, event):
        ix, iy = self._canvas_to_image_coords(event.x, event.y)
        n = len(self._georef_pts) + 1
        while True:
            txt = simpledialog.askstring(
                f"Point {n}",
                f"Coordonnées du croisement cliqué (X={ix}, Y={iy})\nexemples : 40N 10E · 45 N 5 O · 50, -20",
                parent=self.root,
            )
            if txt is None:
                return
            try:
                lat, lon = parse_latlon(txt)
                break
            except ValueError as exc:
                messagebox.showwarning("Coordonnées", str(exc), parent=self.root)
        self._georef_pts.append((ix, iy, lat, lon))
        self._refresh_canvas()
        if len(self._georef_pts) >= 3:
            more = messagebox.askyesno(
                "Repérage",
                f"{len(self._georef_pts)} points saisis.\nAjouter un point de contrôle (conseillé) ?\n"
                "Non = terminer et enregistrer.",
                parent=self.root,
            )
            if not more:
                self._finish_georef()
        else:
            self.lbl_status.configure(text=f"📐 Point {n} enregistré ({lat:.1f}, {lon:.1f}). Point suivant…")

    def _finish_georef(self):
        try:
            fam = self._chart_family()
            default = f"{fam} — {self.radio.active_station_id} — {self.raw_wefax_img.shape[0]} lignes"
            name = simpledialog.askstring(
                "Type de carte",
                "Nom de ce type de carte (réutilisé pour les cartes de même mise en page) :",
                initialvalue=default,
                parent=self.root,
            )
            if not name:
                return
            geo = Georef(self._georef_pts, name=name, family=fam)
            res = geo.residual_km()
            self._georef_store().add(geo)
            z = self.analysis_zone()
            msg = (
                f"Carte repérée ({len(self._georef_pts)} points, écart maximal {res:.0f} km).\n"
                f"Votre case couvre : {km_label(z['lat'], z['lon'], z['radius'])}.\n"
                "Les bulletins texte sont maintenant analysés pour cette zone."
            )
            if res > 150:
                msg += "\n\nÉcart élevé : refaire le repérage avec des points plus proches de votre case."
            messagebox.showinfo("Repérage enregistré", msg, parent=self.root)
            self.log_event(
                f"📐 Carte repérée « {name} » (écart {res:.0f} km) : zone {km_label(z['lat'], z['lon'], z['radius'])}"
            )
        except ValueError as exc:
            messagebox.showwarning("Repérage", str(exc), parent=self.root)
        finally:
            self.canvas_tool_mode = "NONE"
            self._georef_pts = []
            self.canvas.config(cursor="fleur")
            self._refresh_canvas()
