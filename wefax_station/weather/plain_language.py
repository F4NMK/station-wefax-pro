"""Lecture en clair des bulletins météo marine pour un opérateur non spécialiste ou un destinataire.

Le texte reçu (prévisions ponctuelles du DWD, bulletins par zones en anglais/allemand, NAVTEX) est
transformé en réponses simples :
* EST-CE QUE ÇA ME CONCERNE ? — chaque point / zone est situé (mer, distance à la position de
  l'opérateur) ; ce qui est loin est résumé en une ligne ;
* EST-CE DANGEREUX ? — un niveau d'attention (VERT / JAUNE / ORANGE / ROUGE) déduit de la force du
  vent (Beaufort) et de la hauteur de mer, avec des mots courants et des km/h ;
* QUAND ? — jours et heures en heure de Paris ;
* QUE FAIRE ? — une conduite à tenir générale, sans se substituer aux vigilances officielles.

Rien n'est inventé : une ligne illisible est signalée comme telle, jamais complétée.
"""

import math
import re
from datetime import datetime, timedelta, timezone

# ------------------------------------------------------------------------- échelles
BEAUFORT = [
    # force, nom, km/h min-max, effet en mer
    (0, "calme", 0, 1, "mer d'huile"),
    (1, "très légère brise", 1, 5, "rides"),
    (2, "légère brise", 6, 11, "vaguelettes"),
    (3, "petite brise", 12, 19, "quelques moutons"),
    (4, "jolie brise", 20, 28, "moutons nombreux"),
    (5, "bonne brise", 29, 38, "vagues modérées, embruns"),
    (6, "vent frais", 39, 49, "lames, crêtes d'écume blanche"),
    (7, "grand frais", 50, 61, "lames déferlantes, écume en traînées"),
    (8, "coup de vent", 62, 74, "lames hautes, tourbillons d'écume"),
    (9, "fort coup de vent", 75, 88, "lames très hautes, visibilité réduite"),
    (10, "tempête", 89, 102, "mer blanche"),
    (11, "violente tempête", 103, 117, "lames exceptionnelles"),
    (12, "ouragan", 118, 999, "mer entièrement blanche"),
]


def beaufort_words(f_min, f_max=None):
    f_max = f_min if f_max is None else f_max
    lo, hi = BEAUFORT[max(0, min(12, f_min))], BEAUFORT[max(0, min(12, f_max))]
    name = lo[1] if f_min == f_max else f"{lo[1]} à {hi[1]}"
    return f"{name} ({lo[2]}-{hi[3]} km/h, force {f_min}{'' if f_min == f_max else '-' + str(f_max)})"


def sea_words(h):
    """Hauteur significative (m) -> état de la mer (échelle Douglas)."""
    for limit, word in (
        (0.05, "calme"),
        (0.1, "ridée"),
        (0.5, "belle"),
        (1.25, "peu agitée"),
        (2.5, "agitée"),
        (4, "forte"),
        (6, "très forte"),
        (9, "grosse"),
        (14, "très grosse"),
    ):
        if h <= limit:
            return word
    return "énorme"


# 2.8.5 — Repère de niveau. Les pastilles de couleur (émojis) s'affichaient sous Windows comme des ronds
# gris de tailles différentes, impossibles à interpréter. Jauge à quatre cases : PLUS IL Y A DE CASES
# PLEINES, PLUS LE RISQUE EST ÉLEVÉ, avec le niveau en chiffres ; l'interface la colore en plus.
LEVELS = {
    "VERT": (
        "■□□□ 1/4",
        "Pas de danger particulier",
        "Conditions maniables pour la navigation et les activités en mer.",
    ),
    "JAUNE": (
        "■■□□ 2/4",
        "Prudence",
        "Vent ou mer gênants pour les petites embarcations (kayak, annexe, petit voilier) : "
        "se renseigner avant de sortir, rester près des abris.",
    ),
    "ORANGE": (
        "■■■□ 3/4",
        "Danger pour les petites unités",
        "Grand frais ou mer forte : sorties déconseillées aux petites unités, vérifier les amarrages, "
        "consulter les avis officiels.",
    ),
    "ROUGE": (
        "■■■■ 4/4",
        "Danger important",
        "Coup de vent ou tempête : rester au port ou à terre, sécuriser bateaux et "
        "matériel, suivre les consignes des autorités (CROSS, préfecture maritime).",
    ),
}
_ORDER = ["VERT", "JAUNE", "ORANGE", "ROUGE"]


def level_of(bft_max, sea_m=0.0, gust_max=None):
    """Niveau d'attention. Les rafales comptent pour une force de moins (rafales 9 = vent établi 8)."""
    if gust_max:
        bft_max = max(bft_max, gust_max - 1)
    if bft_max >= 8 or sea_m > 4:
        return "ROUGE"
    if bft_max >= 7 or sea_m > 2.5:
        return "ORANGE"
    if bft_max >= 5 or sea_m > 1.25:
        return "JAUNE"
    return "VERT"


def worst_level(levels):
    return max(levels, key=_ORDER.index) if levels else "VERT"


# ------------------------------------------------------------------------- géographie
SEA_BOXES = [  # lat min, lat max, lon min, lon max, nom (du plus précis au plus large)
    (42.0, 43.6, 3.0, 5.5, "golfe du Lion"),
    (42.5, 43.9, 5.5, 7.6, "large de la Provence et de la Côte d'Azur"),
    (43.0, 44.6, 7.6, 10.0, "mer Ligure"),
    (41.3, 43.1, 8.0, 10.0, "large de la Corse"),
    (38.8, 41.3, 7.5, 10.0, "large de la Sardaigne"),
    (38.0, 41.0, 0.5, 5.0, "Baléares"),
    (35.0, 37.5, -5.6, -1.0, "mer d'Alboran"),
    (38.0, 42.0, 10.0, 15.5, "mer Tyrrhénienne"),
    (40.0, 45.9, 12.0, 19.8, "mer Adriatique"),
    (35.0, 40.0, 15.5, 22.0, "mer Ionienne"),
    (35.0, 41.0, 22.0, 28.0, "mer Égée"),
    (30.0, 37.5, 28.0, 37.0, "Méditerranée orientale (sud de la Turquie, Chypre, Levant)"),
    (30.0, 38.0, 10.0, 15.5, "Méditerranée centrale (Tunisie, Malte, Libye)"),
    (43.3, 48.0, -6.0, -1.0, "golfe de Gascogne"),
    (48.5, 51.2, -6.0, 2.0, "Manche"),
    (51.0, 61.0, -4.0, 9.5, "mer du Nord"),
    (53.5, 66.0, 9.5, 30.0, "mer Baltique"),
    (35.0, 44.0, -20.0, -6.0, "Atlantique au large de la péninsule Ibérique"),
    (40.5, 47.5, 27.0, 42.0, "mer Noire"),
]
AREA_POINTS = {  # zones nommées dans les bulletins anglais / allemands / NAVTEX -> (lat, lon, nom FR)
    "LION": (42.8, 4.3, "golfe du Lion"),
    "PROVENCE": (43.0, 6.5, "large de la Provence"),
    "LIGURIAN": (43.8, 8.8, "mer Ligure"),
    "LIGURE": (43.8, 8.8, "mer Ligure"),
    "GENOA": (43.9, 9.0, "golfe de Gênes"),
    "CORSE": (42.2, 9.2, "Corse"),
    "CORSICA": (42.2, 9.2, "Corse"),
    "KORSIKA": (42.2, 9.2, "Corse"),
    "SARDINIA": (40.0, 8.8, "Sardaigne"),
    "SARDINIEN": (40.0, 8.8, "Sardaigne"),
    "BALEARES": (39.5, 3.0, "Baléares"),
    "BALEARIC": (39.5, 3.0, "Baléares"),
    "BALEAREN": (39.5, 3.0, "Baléares"),
    "MENORCA": (40.0, 4.5, "Minorque"),
    "ALBORAN": (36.0, -3.0, "mer d'Alboran"),
    "TYRRHENIAN": (40.0, 12.0, "mer Tyrrhénienne"),
    "ADRIATIC": (43.0, 15.0, "mer Adriatique"),
    "IONIAN": (37.5, 18.5, "mer Ionienne"),
    "AEGEAN": (38.0, 25.0, "mer Égée"),
    "CRETE": (35.0, 25.0, "Crète"),
    "BISCAY": (45.5, -4.0, "golfe de Gascogne"),
    "FINISTERRE": (43.5, -10.0, "Finisterre"),
    # 2.8.6 — noms espagnols / italiens des bulletins NAVTEX Cabo la Nao (X) et La Maddalena (R)
    "LEON": (42.8, 4.3, "golfe du Lion"),
    "PROVENZA": (43.0, 6.5, "large de la Provence"),
    "LIGURIA": (43.8, 8.8, "mer Ligure"),
    "CORCEGA": (42.2, 9.2, "Corse"),
    "CERDENA": (40.0, 8.8, "Sardaigne"),
    "CABRERA": (39.0, 2.9, "Baléares (Cabrera)"),
    "PALOS": (37.5, -0.5, "cap de Palos"),
    "ARGELIA": (37.5, 3.0, "large de l'Algérie"),
    "ANNABA": (37.5, 7.8, "large d'Annaba"),
    "ELBA": (42.8, 10.3, "île d'Elbe"),
    "ELBE": (42.8, 10.3, "île d'Elbe"),
    "MADDALENA": (41.3, 9.4, "bouches de Bonifacio"),
}

LOCAL_KM = 150  # « votre côte » ; au-delà et jusqu'au rayon choisi : « votre bassin »
# position par défaut : Le Cannet (Alpes-Maritimes)
DEFAULT_QTH = (43.58, 7.02)


def distance_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, h)))


def sea_name(lat, lon):
    for la0, la1, lo0, lo1, name in SEA_BOXES:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name
    return "Atlantique Nord" if lon < -5 else "zone maritime"


# ------------------------------------------------------------------------- heure de Paris
def _last_sunday(year, month):
    d = (
        datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
        if month < 12
        else datetime(year, 12, 31, tzinfo=timezone.utc)
    )
    return d - timedelta(days=(d.weekday() + 1) % 7)


def to_paris(dt_utc):
    """UTC -> heure de Paris (règle européenne : été du dernier dimanche de mars au dernier d'octobre)."""
    y = dt_utc.year
    start = _last_sunday(y, 3).replace(hour=1)
    end = _last_sunday(y, 10).replace(hour=1)
    off = 2 if start <= dt_utc < end else 1
    return dt_utc + timedelta(hours=off)


JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def when_fr(dt_utc):
    loc = to_paris(dt_utc)
    h = loc.hour
    moment = "la nuit" if h < 6 else ("le matin" if h < 12 else ("l'après-midi" if h < 18 else "le soir"))
    return f"{JOURS[loc.weekday()]} {loc.day} {moment} ({loc:%Hh} heure de Paris)"


def step_datetime(day_of_month, hour, now=None):
    """Retrouve la date UTC d'une échéance donnée par son seul jour du mois (« MO 16. 00Z »)."""
    now = now or datetime.now(timezone.utc)
    for months_back in (0, -1, 1):
        y, m = now.year, now.month + months_back
        if m == 0:
            y, m = y - 1, 12
        if m == 13:
            y, m = y + 1, 1
        try:
            dt = datetime(y, m, day_of_month, hour, tzinfo=timezone.utc)
        except ValueError:
            continue
        if abs((dt - now).total_seconds()) < 12 * 86400:
            return dt
    return None


# ------------------------------------------------------------------------- bulletins par zones (texte)
_DIR_WORDS = {
    "NORTHWEST": "nord-ouest",
    "NORTHEAST": "nord-est",
    "SOUTHWEST": "sud-ouest",
    "SOUTHEAST": "sud-est",
    "NORTH": "nord",
    "SOUTH": "sud",
    "EAST": "est",
    "WEST": "ouest",
    "VARIABLE": "variable",
    "NORDWEST": "nord-ouest",
    "NORDOST": "nord-est",
    "SUEDWEST": "sud-ouest",
    "SUEDOST": "sud-est",
    "NORD": "nord",
    "SUED": "sud",
    "OST": "est",
    "WEST ": "ouest",
    "UMLAUFEND": "variable",
    "NW": "nord-ouest",
    "NE": "nord-est",
    "SW": "sud-ouest",
    "SE": "sud-est",
    "N": "nord",
    "S": "sud",
    "E": "est",
    "W": "ouest",
}
_SEA_WORDS = {
    "SLIGHT": 0.8,
    "MODERATE": 1.8,
    "ROUGH": 3.0,
    "VERY ROUGH": 5.0,
    "HIGH": 7.0,
    "SMOOTH": 0.3,
    "CALM": 0.1,
}
_FORCE = re.compile(
    r"\b(NORTHWEST|NORTHEAST|SOUTHWEST|SOUTHEAST|NORTH|SOUTH|EAST|WEST|VARIABLE|NORDWEST|NORDOST|SUEDWEST|"
    r"SUEDOST|NORD|SUED|OST|UMLAUFEND|NW|NE|SW|SE|N|S|E|W)\s+(\d{1,2})(?:\s*(?:TO|BIS|-|OR)\s*(\d{1,2}))?"
)


def parse_area_forecasts(text):
    """Bulletins par zones (« LION: NORTHWEST 6 TO 7, OCCASIONALLY 8. ROUGH. ») : zones connues seulement."""
    out = []
    up = (text or "").upper().replace("\r", "\n")
    # 2.8.5 — les tableaux de prévisions ponctuelles (« GOLFE-LION (42.5N 4.5E) … TU 17. 12Z: SW 6 … »)
    # étaient relus ici comme un bulletin par zones : chaque point proche apparaissait deux fois, la
    # seconde avec une plage de vent fausse (« force 2-7 »). Ces lignes sont retirées avant l'analyse.
    up = "\n".join(
        ln
        for ln in up.split("\n")
        if not re.match(r"^\s*[A-Z]{2,3}\s+\d{1,2}\.\s+\d{2}Z:", ln)
        and not re.search(r"\(\s*\d{1,2}\.\d\s*[NS]\s+\d{1,3}\.\d\s*[EW]\s*\)", ln)
    )
    names = sorted(AREA_POINTS, key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(names) + r")\b")
    hits = list(pattern.finditer(up))
    for i, m in enumerate(hits):
        seg = up[m.end() : hits[i + 1].start() if i + 1 < len(hits) else min(len(up), m.end() + 300)]
        seg = seg[:300]
        forces = [(d, int(a), int(b) if b else int(a)) for d, a, b in _FORCE.findall(seg)]
        forces = [f for f in forces if 0 <= f[1] <= 12 and 0 <= f[2] <= 12]
        if not forces:
            continue
        sea = max((v for k, v in _SEA_WORDS.items() if k in seg), default=None)
        lat, lon, fr = AREA_POINTS[m.group(1)]
        bft_max = max(f[2] for f in forces)
        bft_min = min(f[1] for f in forces)
        out.append(
            {
                "point": fr,
                "lat": lat,
                "lon": lon,
                "bft_min": bft_min,
                "bft_max": bft_max,
                "dir": _DIR_WORDS.get(forces[0][0], forces[0][0].lower()),
                "sea_m": sea,
                "gale": any(k in seg for k in ("GALE", "STORM", "STURM", "WARNING")),
            }
        )
    return out


# ------------------------------------------------------------------------- synthèse
def interpret(points=None, areas=None, qth=DEFAULT_QTH, radius_km=500, now=None):
    """Synthèse en clair. points = parse_point_forecasts(), areas = parse_area_forecasts()."""
    now = now or datetime.now(timezone.utc)
    near, far = [], []
    for p in points or []:
        d = distance_km(qth, (p["lat"], p["lon"]))
        steps = []
        for s in p["steps"]:
            dt = step_datetime(s["date"], s["hour"], now)
            if dt is not None and dt >= now - timedelta(hours=6):
                steps.append((dt, s))
        if not steps:
            continue
        worst = max(steps, key=lambda x: (max(x[1]["bft_max"], (x[1].get("gust_max") or 0) - 1), x[1]["sea_m"]))
        lvl = worst_level([level_of(s["bft_max"], s["sea_m"], s.get("gust_max")) for _, s in steps])
        item = {
            "name": p["point"],
            "where": sea_name(p["lat"], p["lon"]),
            "dist": d,
            "level": lvl,
            "steps": steps,
            "worst": worst,
            "water": p.get("water_c"),
        }
        (near if d <= radius_km else far).append(item)
    for a in areas or []:
        d = distance_km(qth, (a["lat"], a["lon"]))
        lvl = level_of(a["bft_max"], a["sea_m"] or 0.0)
        if a.get("gale"):
            lvl = worst_level([lvl, "ORANGE"])
        item = {"name": a["point"], "where": a["point"], "dist": d, "level": lvl, "area": a}
        (near if d <= radius_km else far).append(item)
    near, far = _merge_duplicates(near), _merge_duplicates(far)
    near.sort(key=lambda x: x["dist"])
    return {"near": near, "far": far, "level": worst_level([x["level"] for x in near]), "radius": radius_km}


def _merge_duplicates(items):
    """2.11.0 — un même lieu publié sous deux noms par deux bulletins (« GOLFE DU LION » du bulletin
    Méditerranée et « GOLFE-LION » du bulletin à 5 jours ; « W OF CORSE/SARD. » et « CORS/SARD.-W ») était
    listé deux fois. Points distants de moins de 25 km et situés dans la même mer = un seul lieu ; pour
    une même échéance, la prévision la plus sévère est gardée (prudence)."""
    out = []
    for it in items:
        twin = None
        if "steps" in it:
            for o in out:
                if "steps" in o and o["where"] == it["where"] and abs(o["dist"] - it["dist"]) < 25:
                    twin = o
                    break
        if twin is None:
            out.append(it)
            continue
        by_dt = {dt: s for dt, s in twin["steps"]}
        sev = lambda s: (level_of(s["bft_max"], s["sea_m"], s.get("gust_max")), s["bft_max"], s.get("gust_max") or 0)
        for dt, s in it["steps"]:
            if dt not in by_dt or _ORDER.index(sev(s)[0]) > _ORDER.index(sev(by_dt[dt])[0]) or (
                sev(s)[0] == sev(by_dt[dt])[0] and sev(s)[1:] > sev(by_dt[dt])[1:]
            ):
                by_dt[dt] = s
        twin["steps"] = sorted(by_dt.items(), key=lambda x: x[0])
        twin["aliases"] = twin.get("aliases", []) + [it["name"]]
        twin["level"] = worst_level([twin["level"], it["level"]])
        twin["worst"] = max(
            twin["steps"], key=lambda x: (max(x[1]["bft_max"], (x[1].get("gust_max") or 0) - 1), x[1]["sea_m"])
        )
        if twin.get("water") is None:
            twin["water"] = it.get("water")
    return out


_ABBR = {
    "N": "nord",
    "NE": "nord-est",
    "E": "est",
    "SE": "sud-est",
    "S": "sud",
    "SO": "sud-ouest",
    "O": "ouest",
    "NO": "nord-ouest",
    "variable": "variable",
    "calme": "calme",
}


def _de(words):
    return ("d'" if words[:1] in "aeiouéèê" else "de ") + words


def dir_words(d):
    """« O-NO » -> « ouest à nord-ouest »."""
    return " à ".join(_ABBR.get(p, p) for p in str(d).split("-"))


def _point_sentences(item):
    lines = []
    if "area" in item:
        a = item["area"]
        sea = f", mer {sea_words(a['sea_m'])}" if a.get("sea_m") else ""
        lines.append(f"Vent {_de(a['dir'])}, {beaufort_words(a['bft_min'], a['bft_max'])}{sea}.")
        if a.get("gale"):
            lines.append("Le bulletin contient un AVIS (coup de vent ou tempête) pour cette zone.")
        return lines
    steps = item["steps"]
    # regroupe les échéances consécutives de même niveau
    groups = []
    for dt, s in steps:
        lvl = level_of(s["bft_max"], s["sea_m"], s.get("gust_max"))
        if groups and groups[-1]["lvl"] == lvl:
            groups[-1]["end"] = dt
            groups[-1]["s"].append(s)
        else:
            groups.append({"lvl": lvl, "start": dt, "end": dt, "s": [s]})
    for g in groups:
        f_lo = min(s["bft_min"] for s in g["s"])
        f_hi = max(s["bft_max"] for s in g["s"])
        sea = max(s["sea_m"] for s in g["s"])
        dirs = []
        for s in g["s"]:
            d = dir_words(s["dir"])
            if d not in dirs:
                dirs.append(d)
        period = (
            when_fr(g["start"])
            if g["start"] == g["end"]
            else f"de {when_fr(g['start'])} à {when_fr(g['end'])}"
        )
        wx = sorted({w for s in g["s"] for w in s["wx"]})
        gusts = [s["gust_max"] for s in g["s"] if s.get("gust_max")]
        gust_txt = ""
        if gusts:
            gm = max(gusts)
            gust_txt = f", RAFALES jusqu'à force {gm} ({BEAUFORT[min(12, gm)][1]}, {BEAUFORT[min(12, gm)][2]}-{BEAUFORT[min(12, gm)][3]} km/h)"
        lines.append(
            f"{LEVELS[g['lvl']][0]} {period[0].upper() + period[1:]} : vent {_de(', puis '.join(dirs))}, "
            f"{beaufort_words(f_lo, f_hi)}{gust_txt} ; mer {sea_words(sea)} ({str(sea).rstrip('0').rstrip('.').replace('.', ',')} m)"
            + (f" ; {', '.join(wx)}" if wx else "")
            + "."
        )
    return lines


def reception_in_progress(text):
    """Vrai si le dernier bulletin du texte est encore en cours de réception (pas de NNNN après le dernier ZCZC)."""
    up = (text or "").upper()
    return up.rfind("ZCZC") > up.rfind("NNNN") or ("ZCZC" not in up and "NNNN" not in up and bool(up.strip()))


def trend_line(interp):
    """Tendance jour par jour (pire niveau des points proches) : « mar. 17 ■■□□ → … »."""
    by_day = {}
    for it in interp.get("near", []):
        for dt, s in it.get("steps", []):
            loc = to_paris(dt)
            key = loc.date()
            lvl = level_of(s["bft_max"], s["sea_m"], s.get("gust_max"))
            by_day[key] = worst_level([by_day.get(key, "VERT"), lvl])
    if len(by_day) < 2:
        return ""
    parts = [f"{JOURS[d.weekday()][:3]}. {d.day} {LEVELS[l][0].split()[0]}" for d, l in sorted(by_day.items())]
    return "TENDANCE (pire niveau du jour, votre secteur) : " + " → ".join(parts)


def unreadable_lines(unreadable, qth, radius_km):
    """Points reçus mais illisibles, du plus proche au plus lointain (les proches d'abord)."""
    from wefax_station.weather.rtty_repair import KNOWN_POINTS

    out = []
    for name, doc in (unreadable or {}).items():
        key = difflib_name(name, KNOWN_POINTS)
        pos = KNOWN_POINTS.get(key) if key else None
        d = distance_km(qth, pos) if pos else None
        when = f"{doc['time']:%d/%m %H:%M} UTC" if doc.get("time") else ""
        out.append((d if d is not None else 1e9, name, when, doc.get("station", "")))
    out.sort()
    lines = []
    for d, name, when, st in out:
        near = d <= radius_km
        where = f"à {d:.0f} km" if d < 1e8 else "position inconnue"
        lines.append(
            f" • {'⚠ ' if near else ''}{name} ({sea_name(*KNOWN_POINTS[difflib_name(name, KNOWN_POINTS)]) if d < 1e8 else '?'}, {where}) — "
            f"reçu {when} sur {st} mais ILLISIBLE"
            + (" : prévision inconnue pour cette zone proche, à reprendre au prochain passage." if near else ".")
        )
    return lines


def difflib_name(name, table):
    import difflib

    if name in table:
        return name
    m = difflib.get_close_matches(name.replace("?", "-"), list(table), n=1, cutoff=0.75)
    return m[0] if m else None


def _num(v):
    return str(v).rstrip("0").rstrip(".").replace(".", ",") if "." in str(v) else str(v)


def _step_short(s):
    """« ouest 7, rafales 9, mer 5,5 m » (mots courants, sans jargon)."""
    d = dir_words(s["dir"])
    f = f"{s['bft_min']}" if s["bft_min"] == s["bft_max"] else f"{s['bft_min']}-{s['bft_max']}"
    g = f", RAFALES jusqu'à force {s['gust_max']}" if s.get("gust_max") else ""
    return f"{d} force {f}{g}, mer {sea_words(s['sea_m'])} ({_num(s['sea_m'])} m)"


def _days_of(item):
    """Pire niveau par jour (heure de Paris) : [(date, niveau, échéance la plus sévère)]."""
    days = {}
    for dt, s in item.get("steps", []):
        key = to_paris(dt).date()
        lvl = level_of(s["bft_max"], s["sea_m"], s.get("gust_max"))
        cur = days.get(key)
        rank = (_ORDER.index(lvl), max(s["bft_max"], (s.get("gust_max") or 0) - 1), s["sea_m"])
        if cur is None or rank > cur[0]:
            days[key] = (rank, lvl, dt, s)
    return [(k, v[1], v[2], v[3]) for k, v in sorted(days.items())]


def _zone_lines(it):
    """Deux lignes par lieu : le pic, puis la jauge jour par jour."""
    label = it["where"] if it["where"] not in ("zone maritime", "Atlantique Nord") else it["name"]
    names = " / ".join([it["name"]] + it.get("aliases", []))
    head = f" • {label[0].upper() + label[1:]} ({names}, {it['dist']:.0f} km"
    head += f", eau {it['water']} °C)" if it.get("water") is not None else ")"
    if "area" in it:
        return [head + " — " + " ".join(_point_sentences(it))]
    dt, s = it["worst"]
    lines = [f"{head} — pic {when_fr(dt)} : {_step_short(s)}."]
    days = _days_of(it)
    if len(days) > 1:
        lines.append(
            "     " + " · ".join(f"{JOURS[d.weekday()][:3]}. {d.day} {LEVELS[l][0].split()[0]}" for d, l, _dt, _s in days)
        )
    return lines


def _clean_synopsis(paras, max_chars=420):
    """Une situation générale lisible, courte : paragraphes trop abîmés (mots non traduits) écartés."""
    from wefax_station.weather.marine_translate import untranslated_words

    for p in paras or []:
        body = p.split(" — ", 1)[-1]
        if len(body) < 30 or "indisponible" in body.lower() or body.lower().startswith("néant"):
            continue
        bad = untranslated_words(p)
        words = max(1, len(p.split()))
        if len(bad) > 2 or len(bad) / words > 0.06:
            continue
        if len(p) <= max_chars:
            return p
        cut = p[:max_chars]
        end = max(cut.rfind(". "), cut.rfind("; "))
        return (cut[: end + 1] if end > 80 else cut.rstrip() + "…").strip()
    return ""


def plain_report(
    interp,
    zone_label="votre secteur",
    source="",
    in_progress=False,
    synopsis=None,
    unreadable=None,
    sources=None,
    qth=DEFAULT_QTH,
    next_hint="",
    observations=None,
    extra_sections=None,
    detail=False,
):
    """Texte en clair, du plus important au moins important.

    2.11.0 — synthétique par défaut (detail=False) : deux lignes par lieu proche (pic, puis niveau jour par
    jour), au plus 4 lieux détaillés, les autres en une ligne ; « ailleurs » limité aux niveaux 3 et 4 ;
    sources et mode d'emploi résumés. detail=True rend le texte complet échéance par échéance.

    observations : (lignes, alertes) de weather/synop.report_lines ; extra_sections : liste de
    (titre, lignes) ajoutées avant les sources (prévision numérique GRIB, par exemple)."""
    local_km = min(LOCAL_KM, interp["radius"])
    local = [x for x in interp["near"] if x["dist"] <= local_km]
    region = [x for x in interp["near"] if x["dist"] > local_km]
    L = []
    if interp["near"]:
        ref = local or region
        lvl = worst_level([x["level"] for x in ref])
        icon, title, advice = LEVELS[lvl]
        where = (
            zone_label.upper()
            if local
            else f"UN RAYON DE {interp['radius']} KM AUTOUR DE {zone_label.upper()}"
        )
        L.append(f"{icon} EN BREF — {where} : {title.upper()}")
        L.append(f"   {advice}")
        worst = max(ref, key=lambda x: _ORDER.index(x["level"]))
        if "worst" in worst:
            dt, s = worst["worst"]
            gust = (
                f", rafales jusqu'à force {s['gust_max']} ({BEAUFORT[min(12, s['gust_max'])][1]})"
                if s.get("gust_max")
                else ""
            )
            L.append(
                f"   Moment le plus venté : {when_fr(dt)}, {beaufort_words(s['bft_min'], s['bft_max'])}{gust}, "
                f"mer {sea_words(s['sea_m'])} ({worst['name']}, à {worst['dist']:.0f} km)."
            )
        if local and region:
            rl = worst_level([x["level"] for x in region])
            if _ORDER.index(rl) > _ORDER.index(lvl):
                names = ", ".join(sorted({x["where"] for x in region if x["level"] == rl}))
                L.append(
                    f"   {LEVELS[rl][0]} À SURVEILLER plus au large : {names} — {LEVELS[rl][1].lower()}. "
                    "Pertinent pour une traversée ou si le vent tourne vers votre côte."
                )
        L.append("")
        if not detail:
            L.append(f"CE QUI VOUS CONCERNE (moins de {interp['radius']} km ; jauge = pire niveau du jour)")
            for it in interp["near"][:4]:
                L += _zone_lines(it)
            rest = interp["near"][4:]
            if rest:
                L.append(
                    "   Plus loin dans le rayon : "
                    + " ; ".join(f"{x['where'] if x['where'] != 'zone maritime' else x['name']} {LEVELS[x['level']][0]} ({x['dist']:.0f} km)" for x in rest[:5])
                    + ("…" if len(rest) > 5 else "")
                    + "."
                )
        for it in (interp["near"] if detail else []):
            L.append(
                f" • {it['name']} — {it['where']}, à {it['dist']:.0f} km"
                + (f" ; eau à {it['water']} °C" if it.get("water") is not None else "")
            )
            for s in _point_sentences(it):
                L.append("     " + s)
    elif in_progress:
        # 2.8.5 — bulletin en cours : les zones arrivent l'une après l'autre (les points proches de l'opérateur
        # peuvent être les derniers). Ne rien conclure avant la fin (NNNN).
        L.append(f"… RÉCEPTION EN COURS — rien encore reçu pour {zone_label.upper()}")
        L.append(
            f"   Aucune prévision à moins de {interp['radius']} km POUR L'INSTANT. Le bulletin n'est pas terminé : "
            "attendre la fin (NNNN) avant de conclure."
        )
    else:
        near_lost = [u for u in unreadable_lines(unreadable, qth, interp["radius"]) if "⚠" in u]
        if near_lost:
            L.append(f"PRÉVISION INCOMPLÈTE POUR {zone_label.upper()}")
            L.append(
                f"   Les zones à moins de {interp['radius']} km ont été reçues mais sont ILLISIBLES : "
                "aucune conclusion possible, ne pas en déduire que la mer est calme."
            )
        else:
            L.append(f"AUCUNE PRÉVISION REÇUE POUR {zone_label.upper()}")
            L.append(
                f"   Les bulletins reçus ne contiennent aucune prévision à moins de {interp['radius']} km de votre "
                "position. Cela ne signifie PAS que la mer est calme : consulter le prochain bulletin Méditerranée."
            )
        if next_hint:
            L.append(f"   {next_hint}")
    if in_progress and interp["near"]:
        L.insert(0, "… RÉCEPTION EN COURS — synthèse provisoire, mise à jour à chaque ligne reçue.")
    obs_lines, obs_alerts = observations or ([], [])
    if obs_alerts:
        L.insert(2 if len(L) >= 2 else len(L), "")
        for k, a in enumerate(obs_alerts[:3]):
            L.insert(3 + k if len(L) >= 3 else len(L), a)
    tl = trend_line(interp)
    if not detail:
        return _concise_tail(L, interp, obs_lines, extra_sections, tl, unreadable, qth, synopsis, sources, source)
    if obs_lines:
        L.append("")
        L.append("OBSERVATIONS RÉCENTES (SYNOP, navires, bouées — ce qui a été mesuré)")
        L += obs_lines
    for title, lines in extra_sections or []:
        if lines:
            L.append("")
            L.append(title)
            L += lines
    if tl:
        L.append("")
        L.append(tl)
    ul = unreadable_lines(unreadable, qth, interp["radius"])
    if ul:
        L.append("")
        L.append("ZONES REÇUES MAIS ILLISIBLES (réception brouillée)")
        L += ul
    if synopsis:
        L.append("")
        L.append("SITUATION GÉNÉRALE ANNONCÉE PAR LE BULLETIN (traduction)")
        for para in synopsis:
            L.append("   " + para)
    if interp["far"]:
        L.append("")
        L.append("AILLEURS (pour information, sans incidence sur votre secteur)")
        by_sea = {}
        for it in interp["far"]:
            by_sea.setdefault(it["where"], []).append(it)
        for sea, items in sorted(by_sea.items(), key=lambda kv: min(i["dist"] for i in kv[1])):
            lv = worst_level([i["level"] for i in items])
            names = ", ".join(i["name"] for i in items[:4]) + ("…" if len(items) > 4 else "")
            dist = min(i["dist"] for i in items)
            L.append(f" • {LEVELS[lv][0]} {sea} ({names}) — à {dist:.0f} km : {LEVELS[lv][1].lower()}.")
    L.append("")
    L.append(
        "COMMENT LIRE : la force du vent est en Beaufort (0 = calme, 4 = jolie brise ≈ 25 km/h, "
        "7 = grand frais ≈ 55 km/h, 8 et plus = coup de vent). « Mer belle / peu agitée » = moins d'1 m de "
        "vagues ; « agitée » = 1,25 à 2,5 m ; « forte » = 2,5 à 4 m."
    )
    L.append(
        "NIVEAUX — plus il y a de cases pleines, plus le risque est élevé : ■□□□ 1/4 pas de danger · "
        "■■□□ 2/4 prudence · ■■■□ 3/4 danger pour les petites unités · ■■■■ 4/4 danger important. Les rafales "
        "comptent : des rafales de force 9 sont classées comme un vent établi de force 8. Repère indicatif "
        "calculé par l'application, ce n'est PAS une vigilance officielle (Météo-France, CROSS)."
    )
    if sources:
        L.append("")
        L.append("BULLETINS UTILISÉS (le plus récent fait foi pour chaque zone)")
        L += sources
    elif source:
        L.append(f"Source : {source}")
    return "\n".join(L)


_HEAD = re.compile(r"^\s*([A-Z][A-Z0-9 .\-/]{2,30}?)\s*\(\d{1,2}\.\d\s*[NS]|^\s*(ZCZC|NNNN)")


def clean_raw(text):
    """Texte brut lisible : retours chariot RTTY doublés supprimés, une ligne vide avant chaque point."""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for ln in t.split("\n"):
        ln = ln.rstrip()
        if not ln.strip():
            continue
        if _HEAD.match(ln.upper()) and out:
            out.append("")
        out.append(ln)
    return "\n".join(out).strip()


def _concise_tail(L, interp, obs_lines, extra_sections, tl, unreadable, qth, synopsis, sources, source):
    """Fin du texte synthétique (2.11.0)."""
    if tl:
        L.append(tl.replace("TENDANCE (pire niveau du jour, votre secteur)", "TENDANCE DU SECTEUR"))
    syn = _clean_synopsis(synopsis)
    if syn:
        L += ["", "SITUATION GÉNÉRALE (traduite) : " + syn]
    if obs_lines:
        L += ["", "OBSERVATIONS RÉCENTES (mesures)"] + obs_lines[:4]
    for title, lines in extra_sections or []:
        if lines:
            L += ["", title] + lines[:4]
    ul = unreadable_lines(unreadable, qth, interp["radius"])
    near_ul = [u for u in ul if "⚠" in u]
    if near_ul:
        L += ["", "ZONES PROCHES REÇUES MAIS ILLISIBLES"] + near_ul
    elif ul:
        L += ["", f"Zones lointaines illisibles : {len(ul)} (sans incidence sur votre secteur)."]
    far = [x for x in interp["far"] if x["level"] in ("ORANGE", "ROUGE") and x["dist"] <= 1500]
    if far:
        by_sea = {}
        for it in far:
            by_sea.setdefault(it["where"], []).append(it)
        parts = []
        for sea, items in sorted(by_sea.items(), key=lambda kv: min(i["dist"] for i in kv[1]))[:4]:
            lv = worst_level([i["level"] for i in items])
            parts.append(f"{sea} {LEVELS[lv][0]} ({min(i['dist'] for i in items):.0f} km)")
        L += ["", "AILLEURS (sans incidence directe) : " + " ; ".join(parts) + "."]
    L += [
        "",
        "LECTURE : vent en Beaufort (4 ≈ 25 km/h, 7 ≈ 55 km/h, 8 et plus = coup de vent) ; jauge ■□□□ 1/4 à "
        "■■■■ 4/4, plus il y a de cases pleines plus le risque est élevé. Repère calculé, PAS une vigilance "
        "officielle (Météo-France, CROSS).",
    ]
    if sources:
        L += ["", f"BULLETINS UTILISÉS ({len(sources)}, le plus récent fait foi)"]
        sources = sorted(sources, key=lambda x: ("en cours" in x, "lisible" not in x))
        L += sources[:4]
        if len(sources) > 4:
            L.append(f" • … et {len(sources) - 4} plus ancien(s).")
    elif source:
        L.append(f"Source : {source}")
    return "\n".join(L)
