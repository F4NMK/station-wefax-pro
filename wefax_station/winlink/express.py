"""Lecture (seule) de l'installation Winlink Express et VARA HF de l'opérateur.

2.8.7 — l'application aide à exploiter Winlink sans le remplacer :
* diagnostic de VARA HF pour l'IC-705 (carte son, commande d'émission) ;
* choix des passerelles HF à l'heure voulue, d'après les fichiers que Winlink Express tient à jour
  (« RMS Channels.dat » et « Path Quality.csv », calculés depuis le locator de l'opérateur) ;
* les fichiers de Winlink et de VARA ne sont jamais modifiés par ce module.
"""

import configparser
import csv
import math
import re
from pathlib import Path

DEFAULT_RMS_DIRS = (Path(r"C:\RMS Express"), Path(r"C:\Program Files (x86)\RMS Express"))
DEFAULT_VARA_DIRS = (Path(r"C:\VARA"), Path(r"C:\Program Files\VARA"), Path(r"C:\Program Files (x86)\VARA"))

# Codes de mode des listes de canaux Winlink (« RMS Channels.dat »)
MODES = {
    0: "Packet 1200",
    1: "Packet 2400",
    2: "Packet 4800",
    3: "Packet 9600",
    11: "Pactor 1",
    12: "Pactor 1-2",
    13: "Pactor 1-3",
    14: "Pactor 2",
    15: "Pactor 2-3",
    16: "Pactor 3",
    17: "Pactor 1-4",
    18: "Pactor 2-4",
    19: "Winmor",
    30: "Robust Packet",
    40: "ARDOP 200",
    41: "ARDOP 500",
    42: "ARDOP 1000",
    43: "ARDOP 2000",
    50: "VARA HF",
    53: "VARA HF 500",
    54: "VARA HF 2750",
}
VARA_HF_MODES = (50, 53, 54)
ARDOP_MODES = (40, 41, 42, 43)


def _read_ini(path):
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read_string(Path(path).read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, configparser.Error):
        return None
    return cp


def locate(rms_dir=None, vara_dir=None):
    """Dossiers trouvés et identité Winlink (indicatif, locator) ; valeurs None si absent."""
    rms = Path(rms_dir) if rms_dir else next((d for d in DEFAULT_RMS_DIRS if (d / "RMS Express.exe").exists()), None)
    vara = Path(vara_dir) if vara_dir else next((d for d in DEFAULT_VARA_DIRS if (d / "VARA.exe").exists()), None)
    info = {"rms_dir": rms, "vara_dir": vara, "callsign": None, "grid": None, "mode": None}
    if rms is not None:
        ini = _read_ini(rms / "RMS Express.ini")
        if ini is not None:
            call = ini.get("Properties", "Callsign", fallback="") or ini.get("Properties", "Call signs", fallback="")
            call = call.split(",")[0].strip().upper() or None
            info["callsign"] = call
            if call and ini.has_section(call):
                info["grid"] = ini.get(call, "Grid Square", fallback="").strip().upper() or None
                info["mode"] = ini.get(call, "Mode", fallback="").strip() or None
    return info


def user_dir(info):
    if info.get("rms_dir") and info.get("callsign"):
        d = Path(info["rms_dir"]) / info["callsign"]
        return d if d.is_dir() else None
    return None


# ---------------------------------------------------------------- diagnostic VARA HF / IC-705
def diagnose(info, cat_port=None):
    """Liste de (niveau, constat, conseil) ; niveau = OK / ATTENTION / BLOQUANT."""
    out = []
    if info.get("rms_dir") is None:
        out.append(("BLOQUANT", "Winlink Express introuvable.", "Indiquer son dossier dans l'onglet État."))
    else:
        out.append(("OK", f"Winlink Express trouvé ({info['rms_dir']}), indicatif {info.get('callsign') or '?'}.", ""))
        if not info.get("grid"):
            out.append(
                (
                    "ATTENTION",
                    "Locator non renseigné dans Winlink Express.",
                    "Settings › Winlink Express Setup › Grid Square : sans lui, pas de prévision de liaison.",
                )
            )
    vdir = info.get("vara_dir")
    if vdir is None:
        out.append(("BLOQUANT", "VARA HF introuvable.", "Installer VARA HF (rosmodem.wordpress.com)."))
        return out
    ini = _read_ini(Path(vdir) / "VARA.ini")
    if ini is None:
        out.append(("ATTENTION", "VARA.ini illisible.", "Lancer VARA HF une fois puis fermer."))
        return out
    sin = ini.get("Soundcard", "Input Device Name", fallback="").strip()
    sout = ini.get("Soundcard", "Output Device Name", fallback="").strip()
    if not sin or not sout:
        out.append(
            (
                "BLOQUANT",
                "VARA HF n'a pas de carte son choisie (entrée ou sortie vide) : il ne peut ni écouter ni émettre.",
                "Dans VARA HF : Settings › Soundcard. Entrée « Microphone (USB Audio CODEC) », sortie "
                "« Haut-parleurs (USB Audio CODEC) » — ce sont l'entrée et la sortie USB de l'IC-705.",
            )
        )
    elif "USB" not in (sin + sout).upper() and "CODEC" not in (sin + sout).upper():
        out.append(
            (
                "ATTENTION",
                f"Carte son de VARA : « {sin} » / « {sout} » — ce n'est pas l'audio USB de l'IC-705.",
                "Choisir « USB Audio CODEC » en entrée et en sortie.",
            )
        )
    else:
        out.append(("OK", f"Carte son de VARA : {sin} / {sout}.", ""))
    via = ini.get("PTT", "Via", fallback="").strip()
    cport = ini.get("PTT", "CATPort", fallback="").strip()
    baud = ini.get("PTT", "Baud", fallback="").strip()
    icom = ini.get("PTT", "Icom Address", fallback="").strip()
    if cat_port and cport and cport.upper() != str(cat_port).upper():
        out.append(
            (
                "ATTENTION",
                f"Commande d'émission de VARA sur {cport} à {baud} bauds, alors que l'IC-705 est relié sur {cat_port}.",
                f"Dans VARA HF : Settings › PTT. Choisir CAT, Icom, port {cat_port}, adresse A4, même vitesse "
                "que dans Station WEFAX. Ou plus simple : PTT « VOX » avec le réglage USB SEND de l'IC-705.",
            )
        )
    elif via and not icom and "ICOM" not in ini.get("PTT", "Rig", fallback="").upper():
        out.append(
            (
                "ATTENTION",
                "Adresse CI-V de l'IC-705 non renseignée dans VARA.",
                "Settings › PTT : adresse Icom A4.",
            )
        )
    else:
        out.append(("OK", f"Commande d'émission de VARA : port {cport or '?'} ({baud or '?'} bauds).", ""))
    lic = any(ini.get("Setup", f"Callsign Licence {k}", fallback="").strip() for k in range(4))
    out.append(
        (
            "OK" if lic else "INFO",
            "VARA HF enregistré." if lic else "VARA HF en version gratuite : débit réduit, suffisant pour la météo (quelques ko).",
            "" if lic else "Préférer les passerelles qui proposent « VARA HF » standard ; « VARA HF 2750 » peut exiger la version enregistrée.",
        )
    )
    log = Path(vdir) / "VARAHF.log"
    try:
        if "missing in action" in log.read_text(encoding="utf-8", errors="replace")[-4000:]:
            out.append(
                (
                    "ATTENTION",
                    "Le journal de VARA signale une carte son absente au démarrage.",
                    "Brancher l'IC-705 (USB) AVANT de lancer VARA, puis vérifier Settings › Soundcard.",
                )
            )
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- passerelles
def _dist(a, b):
    r = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _bearing(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def grid_to_latlon(grid):
    g = grid.strip().upper()
    if len(g) < 4:
        return None
    lon = (ord(g[0]) - 65) * 20 - 180 + int(g[2]) * 2
    lat = (ord(g[1]) - 65) * 10 - 90 + int(g[3])
    if len(g) >= 6:
        lon += (ord(g[4]) - 65) * 5 / 60 + 2.5 / 60
        lat += (ord(g[5]) - 65) * 2.5 / 60 + 1.25 / 60
    else:
        lon += 1
        lat += 0.5
    return lat, lon


def _hours_ok(spec, hour):
    for part in str(spec).split(","):
        m = re.fullmatch(r"\s*(\d{1,2})-(\d{1,2})\s*", part)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a <= hour <= b or (a > b and (hour >= a or hour <= b)):
            return True
    return False


def load_channels(udir):
    """Canaux HF publics : {(indicatif, fréquence centrale Hz): {...}}."""
    chans = {}
    try:
        txt = (Path(udir) / "Data" / "RMS Channels.dat").read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return chans
    for line in txt.splitlines():
        f = line.strip().split("|")
        if len(f) < 6 or not f[2].isdigit():
            continue
        try:
            mode = int(f[3])
        except ValueError:
            continue
        key = (f[0], int(f[2]))
        c = chans.setdefault(key, {"call": f[0], "grid": f[1], "center_hz": int(f[2]), "modes": set(), "hours": f[4]})
        c["modes"].add(mode)
    return chans


def load_path_quality(udir):
    """{(indicatif, fréquence kHz arrondie): [indice 0-100 par heure UTC]} ; 101 = trop proche pour être calculé."""
    pq = {}
    try:
        with open(Path(udir) / "Data" / "Path Quality.csv", encoding="utf-8-sig", errors="replace") as fh:
            rd = csv.reader(fh)
            next(rd, None)
            for row in rd:
                row = [c.strip() for c in row]
                if len(row) < 29:
                    continue
                # la fréquence contient un séparateur de milliers (« 7,065 ») qui ajoute une colonne
                extra = len(row) - 29
                freq = float("".join(row[2 : 3 + extra]).replace(",", "").replace(" ", ""))
                hrs = row[5 + extra : 29 + extra]
                vals = []
                for h in hrs:
                    try:
                        vals.append(int(h.split("/")[0]))
                    except (ValueError, IndexError):
                        vals.append(0)
                pq[(row[0], int(freq))] = vals
    except OSError:
        pass
    return pq




def rank_gateways(udir, my_grid, hour_utc, modes=VARA_HF_MODES, max_km=2500, min_km=60, n=5, prefer_free=False):
    """Passerelles conseillées à cette heure : meilleure prévision de liaison d'abord."""
    me = grid_to_latlon(my_grid or "")
    if me is None:
        return []
    chans = load_channels(udir)
    pq = load_path_quality(udir)
    rows = []
    for (call, hz), c in chans.items():
        m = sorted(c["modes"] & set(modes))
        if not m or not _hours_ok(c["hours"], hour_utc):
            continue
        pos = grid_to_latlon(c["grid"])
        if pos is None:
            continue
        d = _dist(me, pos)
        if d < min_km or d > max_km:
            continue
        q = pq.get((call, hz // 1000)) or pq.get((call, round(hz / 1000)))
        score = q[hour_utc] if q else None
        if score is not None and score > 100:
            score = None
        rows.append(
            {
                "call": call,
                "grid": c["grid"],
                "center_khz": hz / 1000,
                "dial_khz": hz / 1000 - 1.5,
                "modes": [MODES.get(k, str(k)) for k in m],
                "free_ok": 50 in m or 53 in m,
                "dist_km": d,
                "bearing": _bearing(me, pos),
                "score": score,
                "hours": c["hours"],
            }
        )
    if prefer_free:  # VARA non enregistré : passerelles « VARA HF » standard d'abord
        rows.sort(key=lambda r: (not r["free_ok"], -(r["score"] or 0), r["dist_km"]))
    else:
        rows.sort(key=lambda r: (-(r["score"] or 0), not r["free_ok"], r["dist_km"]))
    # une seule ligne par passerelle (sa meilleure fréquence)
    seen, best = set(), []
    for r in rows:
        if r["call"] in seen:
            continue
        seen.add(r["call"])
        best.append(r)
        if len(best) >= n:
            break
    return best


def band_name(khz):
    for lo, hi, nm in ((1800, 2000, "160 m"), (3500, 3800, "80 m"), (5300, 5410, "60 m"), (7000, 7200, "40 m"),
                       (10100, 10150, "30 m"), (14000, 14350, "20 m"), (18068, 18168, "17 m"), (21000, 21450, "15 m"),
                       (24890, 24990, "12 m"), (28000, 29700, "10 m")):
        if lo <= khz <= hi:
            return nm
    return ""
