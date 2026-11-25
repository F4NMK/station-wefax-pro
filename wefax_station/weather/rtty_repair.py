"""Réparation prudente des tableaux de prévisions DWD reçus en RTTY, et mesure honnête de leur lisibilité.

2.8.6 — retour de la nuit du 16 au 17/11 (DDH7, prévision 5 jours Méditerranée) : un tiers des lignes
était illisible, dont tout le golfe du Lion, mais le fichier était noté « 99 % [A] » et le rapport
concluait qu'aucune prévision ne concernait Le Cannet. Ce module :

1. recolle les lignes coupées en deux par un retour chariot parasite ;
2. corrige les erreurs typiques de l'ITA2 : un caractère d'inversion lettres/chiffres perdu transforme
   « WE 18. 00Z » en « 23 18. 00TC ». La correspondance lettres <-> chiffres est celle du clavier
   télétype (Q=1, W=2, E=3, R=4, T=5, Y=6, U=7, I=8, O=9, P=0) ;
3. reconstitue le jour, la date et l'heure d'une échéance d'après la ligne précédente et la suivante
   (les échéances se suivent de 12 h, ou de 6 h dans le programme allemand) ;
4. n'invente jamais une valeur de vent ou de mer : une ligne dont la force ou la mer reste illisible
   est retirée et comptée comme manquante ;
5. remplace un en-tête de point illisible par un repère « POINT ILLISIBLE » (ou par le point connu le plus
   proche du nom reçu) pour que ses échéances ne soient plus attribuées au point précédent ;
6. renvoie la proportion réelle de lignes lisibles et la liste des points incomplets.
"""

import difflib
import re

# ITA2 : même touche, rangée lettres / rangée chiffres (clavier télétype)
_L2F = {"Q": "1", "W": "2", "E": "3", "R": "4", "T": "5", "Y": "6", "U": "7", "I": "8", "O": "9", "P": "0"}
_F2L = {v: k for k, v in _L2F.items()}
_F2L.update({"-": "A", ":": "C", "$": "D", "!": "F", "&": "G", "#": "H", "(": "K", ")": "L", ".": "M",
             ",": "N", "'": "S", "/": "X", "=": "V", "+": "Z", "?": "B"})

DAY_EN = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
DAY_DE = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]

STEP = re.compile(
    r"^\s*([A-Z]{2,3})\s+(\d{1,2})\.\s+(\d{2})Z:\s*([A-Z]{1,3}(?:-[A-Z]{1,3})?|VAR|---)\s+(\d{1,2}(?:-\d{1,2})?)\s+"
    r"(?:(\d{1,2}(?:-\d{1,2})?)\s+)?(\d{1,2}(?:\.\d)?)\s*M\b\s*([A-Z ]*?)\s*(?://|$)"
)
POINT = re.compile(
    r"^\s*[^A-Z0-9]{0,2}([A-Z0-9][A-Z0-9 .\-/?]{2,30}?)\s*\((\d{1,2}\.\d)\s*([NS])\s+(\d{1,3}\.\d)\s*([EW])\)"
)
_NAME_POS = re.compile(r"^\s*(\d{2})N\s+(\d{1,3})([EW])\b")
UNREADABLE = "### POINT ILLISIBLE"

# Points de prévision du DWD (relevés dans les bulletins reçus). Sert uniquement quand les coordonnées
# d'un en-tête sont illisibles : le nom reçu est rapproché d'un nom connu (ressemblance ≥ 0,75).
KNOWN_POINTS = {
    "GOLFE-LION": (42.5, 4.5),
    "MALLORCA-SE": (39.2, 3.5),
    "LIGURIAN SEA": (43.5, 8.4),
    "CORS/SARD.-W": (41.3, 7.5),
    "TYRRHENIAN SEA-N": (41.4, 11.2),
    "ADRIA-N": (44.1, 14.0),
    "ADRIA-C": (42.9, 15.4),
    "ADRIA-S": (41.6, 17.7),
    "BOOT-S": (37.7, 17.0),
    "IONIAN SEA-S": (37.0, 19.0),
    "AEGEAN SEA-N": (39.0, 25.0),
    "AEGEAN SEA-S": (36.0, 25.4),
    "RHODES/CYPR": (34.9, 30.6),
    "BLACKSEA-W": (43.3, 30.8),
    "BLACKSEA-E": (43.6, 35.3),
    "BAY OF BISCAY": (46.4, -5.7),
    "BAY OF BISCAY-N": (45.3, -7.9),
    "FINISTERRE": (43.5, -9.8),
    "SOLE": (48.0, -6.1),
    "THAMSE": (52.0, 2.8),
    "ENGL. CHANNEL-E": (50.3, 0.0),
    "ENGL. CHANNEL-W": (49.5, -3.7),
    "DOGGER": (55.2, 1.8),
    "FISHER": (57.0, 6.2),
    "FORTIES": (57.3, 1.2),
    "UTSIRA-SOUTH": (58.3, 5.4),
    "UTSIRA-NORTH": (60.0, 4.5),
    "VIKING": (59.8, 1.9),
    "SKAGERRAK": (58.3, 9.8),
    "WEST.O.IRELAND": (54.0, -13.9),
    "SOUTH.O.IRELAND": (50.9, -7.8),
    "ISLE.O.MAN-S": (53.5, -5.3),
    "WEST.O.GIBR.": (35.0, -10.0),
    "AZOREN-NW": (40.0, -30.0),
    "AZOREN-SE": (37.5, -25.0),
    "CANARIAS-E": (32.0, -12.0),
    "LA PALMA-N": (29.0, -18.0),
    "MADEIRA-N": (34.0, -17.0),
}


def _letters(tok, keep="-"):
    return "".join(c if c in keep else _F2L.get(c, c) for c in tok)


def _figures(tok):
    return "".join(_L2F.get(c, c) for c in tok)


def _looks_like_step(line):
    u = line.upper()
    return bool(
        re.search(r"\d{1,2}\s*\.?\s*(00|06|12|18)\s*[Z:]", u)
        or re.search(r"\bM\s*/[/9.]", u)
        or re.match(r"^\s*(MO|TU|WE|TH|FR|SA|SU|DI|MI|DO|SO)\s+\S+\.", u)
    )


def _looks_like_header(line):
    u = line.upper()
    return bool(
        "SST" in u
        or "WT:" in u
        or re.search(r"\(\s*\d{1,2}[.,:\-=]?\S{0,2}\s*[NSEW]", u)
        or re.search(r"\d\.\d\s*[EW]\)", u)
    ) and not STEP.match(u)


def _valid_step(m):
    if m is None:
        return False
    day, date, hour, d, bft, gust, sea, _wx = m.groups()
    if day not in DAY_EN and day not in DAY_DE:
        return False
    if not (1 <= int(date) <= 31) or hour not in ("00", "06", "12", "18"):
        return False
    b = [int(v) for v in bft.split("-")]
    g = [int(v) for v in gust.split("-")] if gust else []
    if max(b) > 12 or (g and (max(g) > 12 or max(g) < max(b))) or float(sea) > 16:
        return False
    if d != "VAR" and d != "---" and not re.fullmatch(r"[NESW]{1,2}(-[NESW]{1,2})?", d):
        return False
    if "-" in d and d.split("-")[0] == d.split("-")[1]:
        return False
    return True


def _days_for(day):
    return DAY_DE if day in ("DI", "MI", "DO", "SO") else DAY_EN


def _next_slot(prev, delta_h):
    day, date, hour = prev
    days = _days_for(day)
    h = int(hour) + delta_h
    d_idx = days.index(day) if day in days else 0
    while h >= 24:
        h -= 24
        date += 1
        d_idx = (d_idx + 1) % 7
    # fin de mois : la date repart à 1 (assez rare pour qu'une erreur reste visible : ligne non réparée)
    if date > 31:
        date = 1
    return days[d_idx], date, f"{h:02d}"


def _repair_rest(rest):
    """Direction + force + [rafales] + mer, après « HHZ: »."""
    toks = rest.replace("//", " ").replace("/9", " ").split()
    toks = [t for t in toks if t not in ("M", ".", "./")]
    if not toks:
        return None
    d = _letters(toks[0].strip(":"))
    if d.startswith("-"):
        return None  # direction tronquée (« -SW ») : jamais devinée
    nums = []
    for t in toks[1:]:
        t = _figures(t)
        if t.endswith("M") and re.fullmatch(r"\d{1,2}(\.\d)?M", t):
            t = t[:-1]
        if not re.fullmatch(r"\d{1,2}(?:-\d{1,2})?|\d{1,2}\.\d", t):
            return None
        nums.append(t)
    if len(nums) not in (2, 3):
        return None
    return d, nums


def repair_line(line, expected=None):
    """Ligne d'échéance réparée (format DWD) ou None. `expected` = (jour, date, heure) attendu."""
    s = re.sub(r"\s+", " ", line.upper().strip())
    m = STEP.match(s)
    if _valid_step(m):
        return s
    # « JJ DD. HHZ: reste » avec des champs abîmés
    mm = re.match(r"^(\S{0,3})\s*(\S{1,3}?)\s*[.,]?\s+(\S{2,3}?)[ZTC):]*:?\s+(.*)$", s)
    if not mm:
        mm = re.match(r"^(\S{1,3})\s+(\S{1,3})\.\s*(\S{2})\S*\s+(.*)$", s)
    if not mm:
        return None
    day, date, hour, rest = mm.groups()
    day, date, hour = _letters(day)[:2], _figures(date).strip("."), _figures(hour)[:2]
    if expected is not None:
        e_day, e_date, e_hour = expected
        # un champ lisible qui contredit la séquence attendue : on ne force pas
        if date.isdigit() and int(date) != e_date and day in (DAY_EN + DAY_DE) and day != e_day:
            return None
        day, date, hour = e_day, str(e_date), e_hour
    if not (date.isdigit() and hour.isdigit() and day in (DAY_EN + DAY_DE)):
        return None
    r = _repair_rest(rest)
    if r is None:
        return None
    d, nums = r
    sea = nums[-1]
    bft = nums[0]
    gust = nums[1] if len(nums) == 3 else ""
    cand = f"{day} {int(date):02d}. {hour}Z: {d} {bft} " + (f"{gust} " if gust else "") + f"{sea} M //"
    m = STEP.match(cand)
    return cand if _valid_step(m) else None


def _header_fix(line):
    """En-tête de point abîmé : point connu le plus ressemblant, sinon repère « illisible »."""
    up = line.upper()
    name = re.split(r"\(|SST|WT:", up)[0].strip(" .:")
    name = name.replace("?", "-").lstrip(")(#&,.' ")
    pos = _NAME_POS.match(name)
    if pos:  # point nommé par sa position (« 38N 16W ») : les coordonnées sont dans le nom
        lat, lon = float(pos.group(1)), float(pos.group(2)) * (1 if pos.group(3) == "E" else -1)
        nm = f"{pos.group(1)}N {pos.group(2)}{pos.group(3)}"
        return f"{nm} ({lat:.1f}N {abs(lon):.1f}{pos.group(3)})", nm
    best = difflib.get_close_matches(name, list(KNOWN_POINTS), n=1, cutoff=0.75)
    if best:
        lat, lon = KNOWN_POINTS[best[0]]
        sst = re.search(r"(?:SST|WT):\s*(\d{1,2})\s*C", up)
        return (
            f"{best[0]} ({abs(lat):.1f}{'N' if lat >= 0 else 'S'} {abs(lon):.1f}{'E' if lon >= 0 else 'W'})"
            + (f" SST: {sst.group(1)} C" if sst else ""),
            best[0],
        )
    return UNREADABLE, None


def repair_bulletin(text):
    """(texte réparé, rapport). Le texte réparé ne contient que des lignes vérifiées."""
    raw = [ln.rstrip() for ln in (text or "").replace("\r", "\n").split("\n")]
    # 1. recollage : « TH 19. 12Z: SW-W 4-5 » + « 1.5 M // »
    lines = []
    for ln in raw:
        if not ln.strip():
            continue
        if (
            lines
            and re.fullmatch(r"\s*[#&,]?\s*\d{1,2}(\.\d)?\s*M\s*//\s*", ln)
            and not lines[-1].rstrip().endswith("//")
        ):
            lines[-1] = lines[-1].rstrip() + " " + ln.strip()
            continue
        lines.append(ln)

    out, report = [], {"step_lines": 0, "ok": 0, "fixed": 0, "dropped": 0, "headers_fixed": [],
                       "headers_lost": 0, "points": {}}
    cur = None
    in_table = False
    prev = None  # (jour, date, heure)
    delta = 12
    pending = []  # lignes illisibles en attente (la ligne suivante peut fixer la séquence)

    def flush_pending():
        report["dropped"] += len(pending)
        if cur is not None:
            report["points"][cur]["missing"] += len(pending)
        pending.clear()

    for ln in lines:
        up = ln.upper().strip()
        pm = POINT.match(up)
        if pm:
            flush_pending()
            cur = pm.group(1).strip().replace("?", "-")
            report["points"].setdefault(cur, {"ok": 0, "missing": 0})
            prev = None
            in_table = True
            sst = re.search(r"(?:SS[TO0]|WT|ST):\s*(\d{1,2})\s*C", up)
            out.append(
                f"{cur} ({pm.group(2)}{pm.group(3)} {pm.group(4)}{pm.group(5)})"
                + (f" SST: {sst.group(1)} C" if sst else "")
            )
            continue
        if _looks_like_header(up) and not _looks_like_step(up):
            flush_pending()
            in_table = True
            fixed, name = _header_fix(up)
            out.append(fixed)
            if name:
                report["headers_fixed"].append(name)
                cur = name
                report["points"].setdefault(cur, {"ok": 0, "missing": 0, "approx_position": True})
            else:
                report["headers_lost"] += 1
                cur = None
            prev = None
            continue
        if not _looks_like_step(up):
            if not re.search(r"[A-Z]{3,}", up) or re.match(r"^[\W\d]+$", up):
                continue  # bruit pur
            if re.match(r"^\s*(ZCZC|NNNN|[A-Z]{4}\d{2}\s+[A-Z]{4}\s+\d{6})", up):
                flush_pending()
                cur, prev, in_table = None, None, False
                out.append(up)
                continue
            if in_table:
                report["noise_lines"] = report.get("noise_lines", 0) + 1
                continue  # ligne abîmée au milieu d'un tableau : ni échéance, ni en-tête
            flush_pending()
            out.append(up)
            continue
        report["step_lines"] += 1
        expected = _next_slot(prev, delta) if prev else None
        s = repair_line(up, expected)
        if s is None and expected is None:
            pending.append(up)
            continue
        if s is None:
            pending.append(up)
            prev = expected  # la séquence continue malgré la ligne perdue
            continue
        m = STEP.match(s)
        slot = (m.group(1), int(m.group(2)), m.group(3))
        if prev is not None and (slot[1], slot[2]) != (expected[1], expected[2]):
            # nouvelle série sans en-tête lisible : on ne l'attribue pas au point précédent
            if (slot[1], int(slot[2])) < (prev[1], int(prev[2])) and abs(slot[1] - prev[1]) < 20:
                flush_pending()
                out.append(UNREADABLE)
                report["headers_lost"] += 1
                cur = None
            else:
                gap = (slot[1] - prev[1]) * 24 + int(slot[2]) - int(prev[2])
                if gap in (6, 12, 24):
                    delta = gap
        if pending:
            flush_pending()
        out.append(s + " //" if not s.endswith("//") else s)
        if s == re.sub(r"\s+", " ", up):
            report["ok"] += 1
        else:
            report["fixed"] += 1
        if cur is not None:
            report["points"][cur]["ok"] += 1
        prev = slot
    flush_pending()
    # point reçu sans aucune échéance lisible : ses échéances (autant que les autres points) sont manquantes
    oks = sorted(v["ok"] for v in report["points"].values() if v["ok"])
    typical = oks[len(oks) // 2] if oks else 0
    for v in report["points"].values():
        if v["ok"] == 0 and v["missing"] < typical:
            extra = typical - v["missing"]
            v["missing"] += extra
            report["step_lines"] += extra
            report["dropped"] += extra
    total = max(1, report["step_lines"])
    report["readable_pct"] = int(round(100 * (report["ok"] + report["fixed"]) / total))
    report["incomplete"] = sorted(
        n for n, v in report["points"].items() if v["missing"] and v["missing"] >= 0.3 * (v["ok"] + v["missing"])
    )
    return "\n".join(out), report


def readability_summary(report):
    """Phrase courte pour les rapports."""
    if not report or not report.get("step_lines"):
        return ""
    txt = f"{report['readable_pct']} % des lignes de prévision lisibles"
    if report["fixed"]:
        txt += f" (dont {report['fixed']} réparées)"
    if report["headers_lost"]:
        txt += f" ; {report['headers_lost']} point(s) au nom illisible"
    if report["incomplete"]:
        txt += " ; incomplets : " + ", ".join(report["incomplete"][:8])
    return txt + "."
