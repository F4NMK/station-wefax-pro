"""Lecture structurée des bulletins RTTY du DWD : prévisions ponctuelles (vent, mer) par point de mer.

Format (programme allemand, prévisions Méditerranée / Atlantique) :
    TAURUS-W (35.7N  30.0E) WT: 22 C
    SO 15. 12Z: W        3        0.5 M        //
    MO 16. 06Z: W-NW   3-4         1  M  SH    //
c.-à-d. jour (abrégé allemand) + date, heure UTC, direction du vent, force Beaufort (ou plage),
hauteur de mer en mètres, phénomène éventuel (SH = averses, TS = orages, FG = brouillard…).
Les versions anglaises utilisent les mêmes champs avec les jours en anglais.

Le résultat est un tableau par point et un résumé en français : vent dominant, force maximale et son
échéance, mer maximale. Les erreurs de réception (« & », « * ») sont tolérées : la ligne est ignorée si
un champ indispensable est illisible, jamais devinée.
"""

import re

DAYS = {
    "MO": "lun.",
    "DI": "mar.",
    "MI": "mer.",
    "DO": "jeu.",
    "FR": "ven.",
    "SA": "sam.",
    "SO": "dim.",
    # 2.8.5 — abréviations ANGLAISES à deux lettres du programme 1 du DWD (MO TU WE TH FR SA SU). Seules
    # MO, FR et SA coïncident avec l'allemand : les lignes TU, WE, TH et SU étaient ignorées, donc les
    # échéances du mardi au jeudi disparaissaient de la lecture en clair (bulletin DDK9 du 16/11).
    "TU": "mar.",
    "WE": "mer.",
    "TH": "jeu.",
    "SU": "dim.",
    "MON": "lun.",
    "TUE": "mar.",
    "WED": "mer.",
    "THU": "jeu.",
    "FRI": "ven.",
    "SAT": "sam.",
    "SUN": "dim.",
}
DIRS_FR = {
    "N": "N",
    "NE": "NE",
    "E": "E",
    "SE": "SE",
    "S": "S",
    "SW": "SO",
    "W": "O",
    "NW": "NO",
    "O": "E",
    "NO": "NE",
    "SO": "SO",
    "VAR": "variable",
    "V": "variable",
    "C": "calme",
}
WX = {
    "SH": "averses",
    "TS": "orages",
    "FG": "brouillard",
    "RA": "pluie",
    "DZ": "bruine",
    "SN": "neige",
    "BR": "brume",
    "HZ": "brume sèche",
    "GU": "rafales",
    "SQ": "grains",
}

_POINT = re.compile(
    r"^\s*([A-Z0-9][A-Z0-9 .\-/]{2,30}?)\s*\((\d{1,2}\.\d)\s*([NS])\s+(\d{1,3}\.\d)\s*([EW])\)\s*(?:(?:WT|SST):\s*(\d{1,2})\s*C)?"
)
_LINE = re.compile(
    # jour date heure : direction  force  [rafales]  mer M  [phénomène] //
    # 2.8.5 — colonne RAFALES (« W 7  9-10  3.5 M ») : absente du motif, toute ligne comportant des rafales
    # était rejetée, c'est-à-dire précisément les échéances dangereuses.
    r"^\s*([A-Z]{2,3})\s+(\d{1,2})\.\s+(\d{2})Z:\s*([A-Z]{1,3}(?:-[A-Z]{1,3})?)\s+(\d{1,2}(?:-\d{1,2})?)\s+"
    r"(?:(\d{1,2}(?:-\d{1,2})?)\s+)?(\d{1,2}(?:\.\d)?)\s*M\b\s*([A-Z ]*?)\s*(?://|$)"
)


def _dir_fr(d):
    return "-".join(DIRS_FR.get(p, p) for p in d.split("-"))


def parse_point_forecasts(text, repaired=False):
    """Points de prévision lus dans le texte. 2.8.6 : le texte passe d'abord par weather/rtty_repair
    (lignes recollées, inversions lettres/chiffres corrigées, en-têtes illisibles neutralisés)."""
    if not repaired:
        from wefax_station.weather.rtty_repair import repair_bulletin

        text, _rep = repair_bulletin(text)
    points, cur = [], None
    for raw in (text or "").replace("\r", "\n").split("\n"):
        line = raw.upper().strip()
        if line.startswith("### POINT ILLISIBLE") or line.startswith(("ZCZC", "NNNN")):
            cur = None  # échéances d'un point inconnu : jamais rattachées au point précédent
            continue
        m = _POINT.match(line)
        if m:
            name, lat, ns, lon, ew, wt = m.groups()
            cur = {
                "point": name.strip(),
                "lat": float(lat) * (1 if ns == "N" else -1),
                "lon": float(lon) * (1 if ew == "E" else -1),
                "water_c": int(wt) if wt else None,
                "steps": [],
            }
            points.append(cur)
            continue
        m = _LINE.match(line)
        if m and cur is not None:
            day, date, hour, d, bft, gust, sea, wx = m.groups()
            if day not in DAYS:
                continue
            if cur["steps"] and (int(date), int(hour)) <= (cur["steps"][-1]["date"], cur["steps"][-1]["hour"]) \
                    and abs(int(date) - cur["steps"][-1]["date"]) < 20:
                cur = None  # la série recommence : en-tête du point suivant perdu
                continue
            lo_hi = [int(v) for v in bft.split("-")]
            gusts = [int(v) for v in gust.split("-")] if gust else []
            if max(lo_hi) > 12 or (gusts and max(gusts) > 12):
                continue  # valeur impossible : erreur de réception, ligne ignorée
            cur["steps"].append(
                {
                    "day": DAYS[day],
                    "date": int(date),
                    "hour": int(hour),
                    "dir": _dir_fr(d),
                    "bft_min": lo_hi[0],
                    "bft_max": lo_hi[-1],
                    "gust_min": gusts[0] if gusts else None,
                    "gust_max": gusts[-1] if gusts else None,
                    "sea_m": float(sea),
                    "wx": [WX[w] for w in wx.split() if w in WX],
                }
            )
    # un même point diffusé deux fois (deux émissions du bulletin) : la dernière reçue fait foi
    latest = {}
    for p in points:
        if p["steps"]:
            latest[p["point"]] = p
    return list(latest.values())




def gale_warnings(text, translate=False):
    """Avis explicites de coup de vent ou de tempête (GALE, STORM, STURM, AVIS DE GRAND FRAIS…).

    2.11.0 — les titres de rubrique (« STRONG WIND, GALE AND STORM WARNINGS FOR SEA AREAS: »), les
    mentions négatives (« NO WARNING », « KEINE WARNUNGEN ») et les avertissements de NAVIGATION
    (NAVTEX : épaves, exercices…) ne sont plus pris pour des avis météo : le bulletin du 20/11 affichait
    « ⚠ NO WARNING. » à côté d'un niveau orange. translate=True rend chaque avis en français."""
    keys = ("GALE", "STORM", "STURM", "WARNING", "WARNUNG", "BEAUFORT 8", "BF 8", "COUP DE VENT", "TEMPETE")
    negative = ("NO WARNING", "NO GALE", "NO STORM", "KEINE", "NOT IN FORCE", "NONE", " NIL")
    navigation = ("NAVIGATIONAL WARNING", "WARNNACHRICHT", "NAVTEX", "NAUTISCHE")
    hits = []
    for line in (text or "").upper().split("\n"):
        u = line.strip()
        if not any(k in u for k in keys):
            continue
        if any(n in u for n in negative) or any(n in u for n in navigation):
            continue
        if u.endswith(":") or re.search(r"WARNINGS? FOR (?:SEA AREAS|GERMAN BIGHT|THE)|WARNUNGEN FUER|^STRONG WIND, GALE AND STORM", u) and not re.search(r"\d", u):
            continue  # titre de rubrique
        if len(u) < 8 or u in hits:
            continue
        hits.append(u)
    if translate:
        from wefax_station.weather.marine_translate import translate_prose

        hits = [translate_prose(h) for h in hits]
    return hits[:12]
