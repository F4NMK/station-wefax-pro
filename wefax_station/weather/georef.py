"""Repérage géographique d'une carte WEFAX (pixels <-> latitude / longitude).

L'opérateur clique au moins 3 croisements de méridiens et de parallèles et indique leurs coordonnées.
On ajuste une transformation affine par moindres carrés (exacte avec 3 points, contrôlée avec 4 ou
plus). Les cartes DWD / Northwood sont en projection stéréographique ou Mercator : l'affine est une
approximation locale, d'autant meilleure que les points entourent la zone d'intérêt ; l'écart résiduel
est affiché en km pour juger la qualité du repérage.

Un repérage est mémorisé par famille d'émetteur et type de carte (même mise en page d'une émission à
l'autre) dans configuration/reperage_cartes.json.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from wefax_station.weather.plain_language import distance_km


def parse_latlon(text):
    """« 40N 10E », « 40 N 5 O », « 43.5, -7 », « 45°N 0° » -> (lat, lon) ; ValueError sinon.

    Hémisphères : N / S, E / W ou O (ouest).
    """
    t = (text or "").upper().replace("°", " ").replace(",", " ").replace(";", " ")
    t = " ".join(t.split())
    import re

    toks = re.findall(r"(-?\d+(?:\.\d+)?)\s*([NSEWO])?", t)
    if len(toks) != 2:
        raise ValueError("Deux valeurs attendues : latitude puis longitude (ex. 40N 10E ou 40, -5)")
    vals = []
    for num, hemi in toks:
        v = float(num)
        hemi = "W" if hemi == "O" else hemi
        if hemi in ("S", "W"):
            v = -abs(v)
        vals.append((v, hemi or None))
    (a, ha), (b, hb) = vals
    if ha in ("E", "W") or hb in ("N", "S"):
        a, b = b, a
    if not (-90 <= a <= 90 and -180 <= b <= 180):
        raise ValueError("Latitude entre -90 et 90, longitude entre -180 et 180")
    return a, b


class Georef:
    def __init__(self, points, name="", family=""):
        self.points = [tuple(map(float, p)) for p in points]  # (x px, y px, lat, lon)
        self.name = name
        self.family = family
        P = np.array([[x, y, 1.0] for x, y, _, _ in self.points])
        lat = np.array([p[2] for p in self.points])
        lon = np.array([p[3] for p in self.points])
        self.c_lat, *_ = np.linalg.lstsq(P, lat, rcond=None)
        self.c_lon, *_ = np.linalg.lstsq(P, lon, rcond=None)
        A = np.array([[self.c_lat[0], self.c_lat[1]], [self.c_lon[0], self.c_lon[1]]])
        if abs(np.linalg.det(A)) < 1e-12:
            raise ValueError("Points alignés : choisir 3 croisements qui forment un triangle")
        self._inv = np.linalg.inv(A)

    def to_geo(self, x, y):
        return (float(self.c_lat @ [x, y, 1.0]), float(self.c_lon @ [x, y, 1.0]))

    def to_px(self, lat, lon):
        v = self._inv @ np.array([lat - self.c_lat[2], lon - self.c_lon[2]])
        return float(v[0]), float(v[1])

    def residual_km(self):
        errs = [distance_km(self.to_geo(x, y), (la, lo)) for x, y, la, lo in self.points]
        return max(errs) if errs else 0.0

    def zone_from_box(self, box):
        """Case (x0, y0, x1, y1) en pixels -> (lat, lon) du centre et rayon (km) jusqu'au coin le plus loin."""
        x0, y0, x1, y1 = box
        c = self.to_geo((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        r = max(distance_km(c, self.to_geo(x, y)) for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)))
        return c[0], c[1], r

    def to_dict(self):
        return {
            "name": self.name,
            "family": self.family,
            "points": [list(p) for p in self.points],
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }


class GeorefStore:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {"active": {}, "items": []}
        try:
            if self.path.is_file():
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            from wefax_station.storage.atomic import atomic_json

            atomic_json(self.path, self.data)
        except Exception:
            pass

    def add(self, geo):
        self.data["items"] = [
            i for i in self.data["items"] if not (i["name"] == geo.name and i["family"] == geo.family)
        ]
        self.data["items"].append(geo.to_dict())
        self.data["active"][geo.family] = geo.name
        self.save()

    def names(self, family):
        return [i["name"] for i in self.data["items"] if i["family"] == family]

    def set_active(self, family, name):
        self.data["active"][family] = name
        self.save()

    def active(self, family):
        name = self.data.get("active", {}).get(family)
        for i in self.data["items"]:
            if i["family"] == family and i["name"] == name:
                try:
                    return Georef(i["points"], i["name"], i["family"])
                except ValueError:
                    return None
        return None


def km_label(lat, lon, r):
    return (
        f"{abs(lat):.1f}°{'N' if lat >= 0 else 'S'} {abs(lon):.1f}°{'E' if lon >= 0 else 'O'}, "
        f"rayon {r:.0f} km"
    ).replace(".", ",")
