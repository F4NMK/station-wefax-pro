"""Observations codées OMM reçues en RTTY : SYNOP (stations terrestres, AAXX), SHIP et bouées (BBXX).

2.8.7 — la DWD diffuse entre ses prévisions des relevés d'observations ; ils étaient écartés faute de
décodeur. Ils donnent ce qui se passe réellement (vent, mer, pression et sa tendance, temps présent)
et complètent les prévisions du rapport.

Formats FM 12 SYNOP et FM 13 SHIP (Manuel des codes OMM n° 306). Seuls les groupes utiles à un bulletin
marin sont décodés ; un groupe illisible (« ///// » ou caractère parasite) est ignoré, jamais deviné.
Les SHIP et bouées portent leur position dans le message. Les stations terrestres sont repérées par
leur indicatif OMM dans une petite table (côte méditerranéenne) ; une station inconnue est listée sans
distance.
"""

import re
from datetime import datetime, timedelta, timezone

from wefax_station.weather.plain_language import distance_km

_BFT_KN = (1, 4, 7, 11, 17, 22, 28, 34, 41, 48, 56, 64)  # limites hautes (nœuds) des forces 0 à 11


def bft_from_kn(kn):
    for f, lim in enumerate(_BFT_KN):
        if kn < lim:
            return f
    return 12

# Stations terrestres (indicatif OMM -> nom, lat, lon). Positions arrondies au centième de degré.
LAND_STATIONS = {
    "07690": ("Nice", 43.65, 7.20),
    "07650": ("Marseille-Marignane", 43.44, 5.22),
    "07661": ("Cap Cépet (Toulon)", 43.08, 5.94),
    "07643": ("Montpellier", 43.58, 3.96),
    "07747": ("Perpignan", 42.74, 2.87),
    "07790": ("Bastia", 42.55, 9.48),
    "07761": ("Ajaccio", 41.92, 8.79),
    "16120": ("Gênes", 44.41, 8.85),
    "16560": ("Cagliari", 39.25, 9.06),
    "08181": ("Barcelone", 41.29, 2.07),
}

BUOY_NAMES = {
    "61001": "bouée Côte d'Azur",
    "61002": "bouée Golfe du Lion",
}

_GROUP = re.compile(r"^[0-9/]{5}$")

DIR16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]


def _num(s):
    return None if "/" in s else int(s)


def visibility_km(vv):
    if vv is None:
        return None
    if vv <= 50:
        return vv / 10
    if 56 <= vv <= 80:
        return float(vv - 50)
    if 81 <= vv <= 88:
        return 30.0 + (vv - 80) * 5
    if vv == 89:
        return 70.0
    return {90: 0.03, 91: 0.05, 92: 0.2, 93: 0.5, 94: 1, 95: 2, 96: 4, 97: 10, 98: 20, 99: 50}.get(vv)


def weather_text(ww):
    if ww is None or ww < 4:
        return ""
    table = [
        (4, 5, "fumée ou brume sèche"),
        (10, 10, "brume"),
        (11, 12, "brouillard en bancs"),
        (13, 13, "éclairs au loin"),
        (17, 17, "orage sans précipitation"),
        (18, 18, "grains"),
        (19, 19, "trombe"),
        (20, 29, "précipitations dans l'heure passée"),
        (30, 39, "tempête de poussière ou de neige"),
        (40, 49, "brouillard"),
        (50, 59, "bruine"),
        (60, 65, "pluie"),
        (66, 67, "pluie verglaçante"),
        (68, 69, "pluie et neige"),
        (70, 79, "neige"),
        (80, 82, "averses de pluie"),
        (83, 90, "averses (neige, grésil ou grêle)"),
        (91, 94, "orage récent, précipitations"),
        (95, 99, "orage"),
    ]
    for lo, hi, txt in table:
        if lo <= ww <= hi:
            return txt + (" fortes" if ww in (65, 75, 82, 97, 99) else "")
    return ""


def _decode_body(groups, wind_unit_kn):
    """Section 1 (+ 222 pour la mer). groups commence à iRiXhVV."""
    out = {}
    if not groups:
        return out
    g = groups[0]
    if _GROUP.match(g):
        out["vis_km"] = visibility_km(_num(g[3:5]))
    i = 1
    if i < len(groups) and _GROUP.match(groups[i]):
        g = groups[i]
        n, dd, ff = _num(g[0]), _num(g[1:3]), _num(g[3:5])
        out["cloud_oktas"] = n if n is not None and n <= 8 else None
        if ff is not None:
            if ff == 99 and i + 1 < len(groups) and groups[i + 1].startswith("00"):
                ff = _num(groups[i + 1][2:5])
                i += 1
            kn = ff if wind_unit_kn else (ff * 1.94384 if ff is not None else None)
            out["wind_kn"] = round(kn) if kn is not None else None
        if dd is not None:
            out["wind_dir"] = "variable" if dd == 99 else ("calme" if dd == 0 else DIR16[int(((dd * 10) % 360) / 22.5 + 0.5) % 16])
        i += 1
    section = 1
    expect = 1
    while i < len(groups):
        g = groups[i]
        i += 1
        if g in ("222", "333", "444", "555") or re.fullmatch(r"222\d\d|222//", g):
            section = int(g[0])
            expect = 0
            continue
        if not _GROUP.match(g):
            continue
        k = g[0]
        if section == 1:
            if not k.isdigit() or int(k) < expect:
                continue
            expect = int(k) + 1
            if k == "1" and "/" not in g[1:]:
                t = int(g[2:5]) / 10
                out["temp_c"] = -t if g[1] == "1" else t
            elif k == "4" and "/" not in g[1:] and g[1] in "09":
                p = int(g[1:5]) / 10
                out["pressure_hpa"] = p + (1000 if g[1] == "0" else 0)
            elif k == "5" and "/" not in g[1:]:
                a, ppp = int(g[1]), int(g[2:5]) / 10
                out["tendency_hpa"] = -ppp if a >= 5 else (0.0 if a == 4 else ppp)
            elif k == "7" and "/" not in g[1:3]:
                out["ww"] = int(g[1:3])
        elif section == 2:
            if k == "0" and "/" not in g[2:]:
                t = int(g[2:5]) / 10
                out["sea_temp_c"] = -t if g[1] in "1357" else t
            elif k in "12" and "/" not in g[3:5]:
                h = int(g[3:5]) * 0.5
                if k == "1" or "wave_m" not in out:
                    out["wave_m"] = h
                if g[1:3].isdigit():
                    out["wave_period_s"] = int(g[1:3])
            elif k == "4" and "/" not in g[3:5]:
                out["swell_m"] = int(g[3:5]) * 0.5
            elif k == "7" and g[1] == "0" and "/" not in g[2:]:
                out["wave_m"] = int(g[2:5]) / 10
    return out


def _obs_time(issued, day, hour):
    """Date complète d'une observation « JJHH » : le jour le plus récent qui ne soit pas dans le futur."""
    for back in range(0, 40):
        d = (issued - timedelta(days=back)).replace(hour=hour, minute=0, second=0, microsecond=0)
        if d.day == day and d <= issued + timedelta(hours=2):
            return d
    return issued.replace(minute=0, second=0, microsecond=0)


def parse_observations(text, issued=None):
    """Liste d'observations décodées d'un message reçu (AAXX ou BBXX)."""
    issued = issued or datetime.now(timezone.utc)
    up = (text or "").upper().replace("\r", "\n")
    obs = []
    for m in re.finditer(r"\b(AAXX|BBXX)\b(.*?)(?=\b(?:AAXX|BBXX|NNNN|ZCZC)\b|$)", up, re.S):
        kind, body = m.group(1), m.group(2)
        land_head = None
        if kind == "AAXX":
            hm = re.match(r"\s*([0-9/]{5})", body)
            if not hm:
                continue
            land_head = hm.group(1)
            body = body[hm.end():]
        for rep in body.split("="):
            toks = rep.split()
            if not toks or toks == ["NIL"]:
                continue
            try:
                if kind == "AAXX":
                    sid, yyggi, rest = toks[0], land_head, toks[1:]
                    if not re.fullmatch(r"\d{5}", sid):
                        continue
                    name, lat, lon = LAND_STATIONS.get(sid, (f"station {sid}", None, None))
                else:
                    sid, yyggi = toks[0], toks[1]
                    if not toks[2].startswith("99") or not re.fullmatch(r"[1357]\d{4}", toks[3]):
                        continue
                    lat = int(toks[2][2:5]) / 10
                    q = toks[3][0]
                    lon = int(toks[3][1:5]) / 10
                    lat = -lat if q in "35" else lat
                    lon = -lon if q in "57" else lon
                    rest = toks[4:]
                    name = BUOY_NAMES.get(sid) or (f"bouée {sid}" if re.fullmatch(r"\d{5}", sid) else f"navire {sid}")
                if not re.fullmatch(r"\d{4}[0-9/]", yyggi):
                    continue
                day, hour, iw = int(yyggi[:2]), int(yyggi[2:4]), yyggi[4]
                if not (1 <= day <= 31 and hour <= 23):
                    continue
                t = _obs_time(issued, day, hour)
                o = _decode_body(rest, wind_unit_kn=iw in "34")
                o.update({"id": sid, "name": name, "lat": lat, "lon": lon, "time": t, "kind": kind})
                if "wind_kn" in o and o["wind_kn"] is not None:
                    o["bft"] = bft_from_kn(o["wind_kn"])
                obs.append(o)
            except (ValueError, IndexError):
                continue
    return obs


def describe(o, qth=None):
    parts = []
    if o.get("wind_dir") == "calme":
        parts.append("calme")
    elif o.get("wind_kn") is not None:
        parts.append(f"vent {o.get('wind_dir', '?')} {o['wind_kn']} nds (force {o.get('bft', '?')})")
    if o.get("wave_m") is not None:
        parts.append(f"mer {o['wave_m']:.1f} m".replace(".", ","))
    if o.get("swell_m") is not None:
        parts.append(f"houle {o['swell_m']:.1f} m".replace(".", ","))
    if o.get("pressure_hpa") is not None:
        p = f"{o['pressure_hpa']:.1f} hPa".replace(".", ",")
        tnd = o.get("tendency_hpa")
        if tnd is not None and abs(tnd) >= 0.5:
            p += f" ({'+' if tnd > 0 else '−'}{abs(tnd):.1f} en 3 h{', en baisse rapide' if tnd <= -3 else ''})".replace(".", ",")
        parts.append(p)
    w = weather_text(o.get("ww"))
    if w:
        parts.append(w)
    if o.get("vis_km") is not None and o["vis_km"] < 5:
        parts.append(f"visibilité {o['vis_km']:g} km".replace(".", ","))
    if o.get("temp_c") is not None:
        parts.append(f"air {o['temp_c']:.0f} °C")
    if o.get("sea_temp_c") is not None:
        parts.append(f"eau {o['sea_temp_c']:.0f} °C")
    return ", ".join(parts) or "relevé sans donnée utile"


def report_lines(observations, qth, radius_km, now=None, max_age_h=12):
    """Rubrique « observations récentes » du rapport (les plus proches d'abord)."""
    now = now or datetime.now(timezone.utc)
    latest = {}
    for o in observations:
        if now - o["time"] > timedelta(hours=max_age_h):
            continue
        if o["id"] not in latest or o["time"] > latest[o["id"]]["time"]:
            latest[o["id"]] = o
    rows = []
    for o in latest.values():
        d = distance_km(qth, (o["lat"], o["lon"])) if o.get("lat") is not None else None
        rows.append((d if d is not None else 1e9, o))
    rows.sort(key=lambda r: r[0])
    near = [r for r in rows if r[0] <= max(radius_km, 300)]
    lines, alerts = [], []
    for d, o in near[:8]:
        where = f"à {d:.0f} km" if d < 1e8 else "position inconnue"
        lines.append(f" • {o['time']:%d/%m %H} UTC — {o['name']} ({where}) : {describe(o)}")
        if (o.get("bft") or 0) >= 7 or (o.get("wave_m") or 0) >= 4 or (o.get("tendency_hpa") or 0) <= -3:
            alerts.append(f"⚠ OBSERVÉ {o['time']:%H} UTC — {o['name']} ({where}) : {describe(o)}")
    far = len(rows) - len(near)
    if not lines and rows:
        lines.append(
            f" • {len(rows)} observation(s) reçue(s), toutes à plus de {max(radius_km, 300)} km "
            f"(la plus proche : {rows[0][1]['name']}, à {rows[0][0]:.0f} km)." if rows[0][0] < 1e8 else
            f" • {len(rows)} observation(s) reçue(s), aucune dans votre secteur."
        )
    elif far > 0:
        lines.append(f"   (+ {far} observation(s) plus lointaine(s) non détaillée(s))")
    return lines, alerts
