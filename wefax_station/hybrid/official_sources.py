"""2.9.2 — Mise à jour des programmes par les sources officielles, sans jamais bloquer la station.

Principe (demande F4NMK du 19/11/2026) :
* les programmes intégrés au logiciel restent la base : la station reçoit cartes et bulletins en totale
  autonomie, sans Internet (blackout, plan ORSEC) ;
* quand Internet est joignable, les documents officiels sont téléchargés EN ENTIER, dans un fil séparé,
  avec un délai et une taille plafonnés, puis conservés dans configuration/sources (date, SHA-256, taille) ;
* le texte du PDF est extrait, les heures de chaque station sont relevées et comparées au programme
  utilisé ; la date « INFORMATION DATED » de chaque section est relevée ;
* rien n'est modifié automatiquement : l'opérateur accepte ou refuse les différences. Un programme accepté
  est conservé dans configuration/programmes_acceptes.json et reste utilisé hors ligne.

Le registre des sources est un fichier JSON modifiable (configuration/sources_officielles.json) : une adresse
qui change peut être corrigée sans nouvelle version du logiciel.
"""

import hashlib
import json
import re
import time
import zlib
from datetime import datetime, timezone

from wefax_station.core.schedules import BROADCAST_SCHEDULES_UTC, SCHEDULE_REV, set_accepted_overrides

# ----------------------------------------------------------------------------- registre par défaut
# Seules des adresses d'organismes officiels sont listées. « families » : programmes WEFAX que le document
# décrit. Le document NOAA est la compilation mondiale (information DWD du 24/07/2024, Northwood du
# 05/01/2022 dans l'édition du 07/03/2025) ; le document DWD est le plan publié par le DWD lui-même.
DEFAULT_SOURCES = [
    {
        "id": "DWD_FAX",
        "label": "DWD — programme radiofac-similé (plan 10/2020)",
        # 2.9.4 — sans « ?__blob=publicationFile », dwd.de renvoie une page HTML (constaté le 19/11/2026) ;
        # adresse donnée par le document NOAA lui-même
        "url": "https://www.dwd.de/EN/specialusers/shipping/broadcast_en/broadcast_fax_102020.pdf?__blob=publicationFile&v=1",
        "families": ["DWD"],
    },
    {
        "id": "NOAA_RFAX",
        "label": "NOAA — Worldwide Marine Radiofacsimile Broadcast Schedules",
        "url": "https://www.weather.gov/media/marine/rfax.pdf",
        "families": ["DWD", "GYA"],
    },
]

# 2.9.4 — adresses périmées enregistrées par une version précédente dans sources_officielles.json
URL_FIXES = {
    "https://www.dwd.de/EN/specialusers/shipping/broadcast_en/broadcast_fax_102020.pdf":
    "https://www.dwd.de/EN/specialusers/shipping/broadcast_en/broadcast_fax_102020.pdf?__blob=publicationFile&v=1",
}

# Repères de section dans les documents (texte extrait, majuscules).
SECTION_START = {
    "DWD": ("HAMBURG/PINNEBERG", "HAMBURG / PINNEBERG", "PINNEBERG"),
    "GYA": ("NORTHWOOD, UNITED KINGDOM", "NORTHWOOD"),
}
SECTION_END = ("NORTHWOOD, UNITED KINGDOM", "HAMBURG/PINNEBERG", "ATHENS", "APPENDIX A", "MURMANSK")
SECTION_MAX_CHARS = 30000

# Dates « INFORMATION DATED » des sections sur lesquelles reposent les programmes intégrés.
KNOWN_INFO_DATES = {"DWD": "24 July 2024", "GYA": "Jan 05, 2022"}

USER_AGENT = "StationWEFAXPro (programmes de diffusion maritime; usage radioamateur ADRASEC)"
CONNECT_TIMEOUT_S = 10
TOTAL_DEADLINE_S = 90
MAX_BYTES = 12 * 1024 * 1024


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


# ----------------------------------------------------------------------------- registre et fichiers
def sources_dir(root_dir):
    return root_dir / "configuration" / "sources"


def registry_path(root_dir):
    return root_dir / "configuration" / "sources_officielles.json"


def state_path(root_dir):
    return sources_dir(root_dir) / "etat_sources.json"


def accepted_path(root_dir):
    return root_dir / "configuration" / "programmes_acceptes.json"


def _read_json(path, default):
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path, data):
    try:
        from wefax_station.storage.atomic import atomic_json

        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, data)
        return True
    except Exception:
        return False


def load_registry(root_dir):
    """Sources : fichier opérateur s'il est valide, sinon registre par défaut (le fichier est créé)."""
    path = registry_path(root_dir)
    data = _read_json(path, None)
    out = []
    if isinstance(data, dict) and isinstance(data.get("sources"), list):
        for s in data["sources"]:
            if isinstance(s, dict) and str(s.get("url", "")).startswith("https://") and s.get("id"):
                out.append(
                    {
                        "id": str(s["id"]),
                        "label": str(s.get("label") or s["id"]),
                        "url": URL_FIXES.get(str(s["url"]), str(s["url"])),
                        "families": [str(f) for f in (s.get("families") or []) if str(f) in SECTION_START],
                        "enabled": bool(s.get("enabled", True)),
                    }
                )
    fixed = isinstance(data, dict) and any(
        str(s.get("url")) in URL_FIXES for s in (data.get("sources") or []) if isinstance(s, dict)
    )
    if not out or fixed:
        out = out or [dict(s, enabled=True) for s in DEFAULT_SOURCES]
        _write_json(
            path,
            {
                "commentaire": "Sources officielles des programmes WEFAX. Adresses modifiables (https uniquement). "
                "families : DWD et/ou GYA. enabled : false pour ne plus télécharger une source.",
                "sources": out,
            },
        )
    return out


def load_accepted(root_dir):
    data = _read_json(accepted_path(root_dir), {})
    return data if isinstance(data, dict) else {}


def apply_accepted(root_dir):
    """Programmes acceptés par l'opérateur, valables pour la révision intégrée actuelle."""
    acc = load_accepted(root_dir)
    valid = {}
    for fam, rec in acc.items():
        if isinstance(rec, dict) and rec.get("base_rev") == SCHEDULE_REV and isinstance(rec.get("slots"), list):
            try:
                slots = [tuple(x) for x in rec["slots"] if len(x) == 4 and 0 <= int(x[0]) <= 23 and 0 <= int(x[1]) <= 59]
            except Exception:
                continue
            if len(slots) >= 4:
                valid[fam] = slots
    set_accepted_overrides(valid)
    return valid


# ----------------------------------------------------------------------------- téléchargement
def download(url, deadline_s=TOTAL_DEADLINE_S, max_bytes=MAX_BYTES, opener=None):
    """Téléchargement complet (bornes : délai de connexion, délai total, taille). Lève une exception en cas
    d'échec. N'est appelé que depuis un fil séparé : l'interface et la réception ne sont jamais bloquées."""
    import ssl
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*;q=0.5"})
    t0 = time.monotonic()
    if opener is None:
        ctx = ssl.create_default_context()

        def opener(r, timeout):
            return urllib.request.urlopen(r, timeout=timeout, context=ctx)

    chunks, total = [], 0
    with opener(req, CONNECT_TIMEOUT_S) as resp:
        while True:
            if time.monotonic() - t0 > deadline_s:
                raise TimeoutError("délai total dépassé")
            block = resp.read(65536)
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                raise ValueError("document trop volumineux")
            chunks.append(block)
    data = b"".join(chunks)
    if not data:
        raise ValueError("document vide")
    return data


def looks_html(data: bytes) -> bool:
    head = (data or b"")[:600].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def find_pdf_link(data: bytes, base_url: str):
    """2.9.4 — page HTML reçue à la place du PDF : premier lien vers un .pdf du même site."""
    from urllib.parse import urljoin, urlparse

    try:
        html = data.decode("utf-8", "replace")
    except Exception:
        return None
    host = urlparse(base_url).netloc
    for m in re.finditer(r'href="([^"]+?\.pdf[^"]*)"', html, re.I):
        href = m.group(1).replace("&amp;", "&")
        href = re.sub(r";jsessionid=[^?#]*", "", href)
        url = urljoin(base_url, href)
        if urlparse(url).netloc == host and url.startswith("https://"):
            return url
    return None


# ----------------------------------------------------------------------------- extraction du texte PDF
def extract_pdf_text(data: bytes) -> str:
    """Texte d'un PDF : pypdf s'il est installé, sinon extracteur minimal (flux FlateDecode, opérateurs
    Tj / TJ / ' / "). Suffisant pour relever des heures et des dates ; renvoie '' si rien n'est lisible."""
    if not data:
        return ""
    if not data[:1024].lstrip().startswith(b"%PDF"):
        try:
            return data.decode("utf-8", "replace")
        except Exception:
            return ""
    try:
        import io

        from pypdf import PdfReader  # facultatif

        reader = PdfReader(io.BytesIO(data))
        txt = "\n".join((p.extract_text() or "") for p in reader.pages)
        if txt.strip():
            return txt
    except Exception:
        pass
    return _minimal_pdf_text(data)


_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
_TEXT_OP_RE = re.compile(rb"\((?:\\.|[^\\)])*\)|\[(?:[^\]])*\]\s*TJ|T\*|Td|TD|Tm|ET", re.S)


def _pdf_string(raw: bytes) -> str:
    body = raw[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        c = body[i]
        if c == 0x5C and i + 1 < len(body):  # antislash
            n = body[i + 1]
            esc = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("("): 40, ord(")"): 41, 0x5C: 0x5C}
            if n in esc:
                out.append(esc[n])
                i += 2
                continue
            if 0x30 <= n <= 0x37:
                j = i + 1
                oct_digits = b""
                while j < len(body) and len(oct_digits) < 3 and 0x30 <= body[j] <= 0x37:
                    oct_digits += bytes([body[j]])
                    j += 1
                out.append(int(oct_digits, 8) & 0xFF)
                i = j
                continue
            i += 2
            continue
        out.append(c)
        i += 1
    return out.decode("latin-1", "replace")


def _minimal_pdf_text(data: bytes) -> str:
    lines = []
    for m in _STREAM_RE.finditer(data):
        raw = m.group(1)
        try:
            content = zlib.decompress(raw)
        except Exception:
            content = raw
        if b"Tj" not in content and b"TJ" not in content:
            continue
        cur = []
        for tok in _TEXT_OP_RE.finditer(content):
            t = tok.group(0)
            if t.startswith(b"("):
                cur.append(_pdf_string(t))
            elif t.startswith(b"["):
                parts = re.findall(rb"\((?:\\.|[^\\)])*\)", t)
                cur.append("".join(_pdf_string(p) for p in parts))
            else:
                if cur:
                    lines.append("".join(cur))
                    cur = []
        if cur:
            lines.append("".join(cur))
    return "\n".join(lines)


# ----------------------------------------------------------------------------- analyse
# 2.9.4 — la date peut être coupée en deux lignes (« Jan 05, » puis « 2022) ») dans le texte extrait
_INFO_RE = re.compile(r"INFORMATION\s+DATED\s*\(?\s*([^)]{4,40}?)\s*\)", re.I)
# Heures HHMM, HH.MM ou HH:MM isolées ; on écarte les nombres suivis d'une unité (1000 hPa, 7880 kHz…).
_TIME_RE = re.compile(
    r"(?<![\d.,:/])([01]\d|2[0-3])[.:h]?([0-5]\d)(?![\d]|[.,]\d)(?!\s*(?:hPa|kHz|Hz|kW|mb|km|nm|°|%))",
    re.I,
)


def find_section(text: str, family: str, whole_document=False) -> str:
    """Texte de la section d'une station (document NOAA) ou tout le document (document DWD)."""
    if whole_document:
        return text
    up = text.upper()
    start = -1
    for mk in SECTION_START.get(family, ()):
        start = up.find(mk)
        if start >= 0:
            break
    if start < 0:
        return ""
    end = start + SECTION_MAX_CHARS
    own = SECTION_START.get(family, ())
    for mk in SECTION_END:
        if any(mk in o or o in mk for o in own):
            continue
        p = up.find(mk, start + 50)
        if 0 <= p < end:
            end = p
    return text[start:end]


def section_info_date(section: str):
    m = _INFO_RE.search(section or "")
    return re.sub(r"\s+", " ", m.group(1)).strip(" (") if m else None


def extract_times(section: str):
    """Heures (minutes depuis 00:00 UTC) relevées dans une section, sans les lignes de date."""
    # 2.9.4 — plus de suppression des « années » 19xx / 20xx : elle effaçait les heures 19:00 à 20:48
    clean = _INFO_RE.sub(" ", section or "")
    found = set()
    for m in _TIME_RE.finditer(clean):
        found.add(int(m.group(1)) * 60 + int(m.group(2)))
    return sorted(found)


def _tokens(section):
    return [t.strip() for t in (section or "").split("\n") if t.strip()]


def parse_dwd_rows(section):
    """2.9.4 — tableau du DWD (plan 10/2020, repris par la NOAA) : « HH.MM », « 120 », « / », « 576 », IOC,
    heure de référence, intitulé. Les créneaux de phonie (« 05.55 - 06.35 Voice ») et les heures de
    référence (« 00.00 ») ne sont pas des cartes. Renvoie [(minute, intitulé)]."""
    # 2.9.4 — le PDF du DWD lui-même (téléchargé le 19/11) sépare les cellules par « x-none » et écrit
    # « 120 / 576 » d'un seul tenant : on ramène les deux mises en page à la même suite d'éléments
    toks = []
    for t in _tokens(section):
        if t.lower() == "x-none":
            continue
        m = re.fullmatch(r"(\d{2,3})\s*/\s*(\d{3})", t)
        toks.extend([m.group(1), "/", m.group(2)] if m else [t])
    rows = []
    i = 0
    tre = re.compile(r"^([01]\d|2[0-3])\.([0-5]\d)$")
    while i < len(toks):
        m = tre.match(toks[i])
        if m and i + 3 < len(toks) and toks[i + 1] in ("120", "60", "90") and toks[i + 2] == "/":
            minute = int(m.group(1)) * 60 + int(m.group(2))
            j = i + 6  # temps, vitesse, « / », IOC, durée, heure de référence
            words = []
            while j < len(toks) and not (tre.match(toks[j]) and j + 2 < len(toks) and toks[j + 1] in ("120", "60", "90")):
                if tre.match(toks[j]) and j + 1 < len(toks) and toks[j + 1] == "-":
                    break  # créneau de phonie suivant
                words.append(toks[j])
                j += 1
                if len(words) > 40:
                    break
            rows.append((minute, " ".join(words).strip()))
            i = j
            continue
        i += 1
    return rows


def parse_label_time_rows(section):
    """2.9.4 — tableau de Northwood (NOAA) en deux colonnes : intitulé puis heure « HHMM ». Les heures sans
    intitulé (créneaux vides) sont ignorées. Renvoie [(minute, intitulé)]."""
    up = section or ""
    k = up.find("(Z)")
    k2 = up.find("(Z)", k + 3) if k >= 0 else -1
    if k2 < 0:
        return []
    end = len(up)
    for mk in ("All MAPS", "Abbreviations", "INFORMATION DATED"):
        p = up.find(mk, k2)
        if 0 <= p < end:
            end = p
    rows, lab = [], []
    for tok in _tokens(up[k2 + 3:end]):
        if re.fullmatch(r"([01]\d|2[0-3])[0-5]\d", tok):
            if lab:
                rows.append((int(tok[:2]) * 60 + int(tok[2:]), " ".join(lab)))
            lab = []
        else:
            lab.append(tok)
    return sorted(rows)


def structured_rows(section, family):
    rows = parse_dwd_rows(section) if family == "DWD" else parse_label_time_rows(section)
    return rows if len(rows) >= 20 else []


def analyse_family(text: str, family: str, current_slots, whole_document=False):
    """Compare les heures d'une section aux créneaux utilisés. Résultat sérialisable en JSON."""
    section = find_section(text, family, whole_document=whole_document)
    cur = sorted({int(h) * 60 + int(m) for h, m, _c, _d in current_slots or []})
    res = {
        "family": family,
        "section_found": bool(section),
        "info_date": section_info_date(section) if section else None,
        "found": 0,
        "added": [],
        "removed": [],
        "plausible": False,
        "conforme": False,
    }
    if not section:
        return res
    rows = structured_rows(section, family)
    if rows:
        times = sorted({m for m, _l in rows})
        res["method"] = "tableau"
        res["labels"] = {str(m): lab for m, lab in rows}
    else:
        times = extract_times(section)
        res["method"] = "heures"
    res["found"] = len(times)
    cur_set, doc_set = set(cur), set(times)
    common = cur_set & doc_set
    res["added"] = sorted(doc_set - cur_set)
    res["removed"] = sorted(cur_set - doc_set)
    # Analyse jugée exploitable si la majorité des créneaux connus est retrouvée dans le document : sinon le
    # texte est mal extrait (ou le document a changé de forme) et seule la lecture par l'opérateur vaut.
    res["plausible"] = bool(cur_set) and len(common) >= 0.6 * len(cur_set) and len(doc_set) >= 0.5 * len(cur_set)
    # 2.9.4 — sans lecture du tableau, les heures relevées au fil du texte (heures de référence, phonie,
    # plages horaires) sont trop bruitées pour proposer une modification
    if res["method"] != "tableau":
        res["plausible"] = False
    known = KNOWN_INFO_DATES.get(family)
    same_date = bool(known and res["info_date"] and _norm(known) == _norm(res["info_date"]))
    res["same_info_date"] = same_date
    res["conforme"] = res["plausible"] and not res["added"] and not res["removed"]
    return res


def hm(minute):
    return f"{int(minute) // 60:02d}:{int(minute) % 60:02d}"


def proposed_slots(current_slots, analysis):
    """Programme proposé : créneaux connus conservés (avec leur libellé) sauf ceux absents du document,
    heures nouvelles ajoutées avec un libellé générique (l'intitulé de la carte s'affiche sur la carte)."""
    if not analysis.get("plausible"):
        return [tuple(x) for x in current_slots]  # texte mal lu : on ne propose rien
    removed = set(analysis.get("removed") or [])
    out = [tuple(s) for s in current_slots if int(s[0]) * 60 + int(s[1]) not in removed]
    labels = analysis.get("labels") or {}
    for minute in analysis.get("added") or []:
        doc = str(labels.get(str(minute), "")).strip()
        out.append(
            (minute // 60, minute % 60, "CARTE",
             f"Carte au programme officiel : {doc[:80]}" if doc else "Carte au programme officiel (intitulé lu sur la carte reçue)")
        )
    out.sort(key=lambda s: (int(s[0]), int(s[1])))
    return out


def describe_analysis(a):
    fam = a.get("family")
    if not a.get("section_found"):
        return f"{fam} : section introuvable dans le document (lecture par l'opérateur nécessaire)"
    date = a.get("info_date")
    date = f"information du {date}" if date else "date d'information non relevée"
    if a.get("conforme"):
        return f"{fam} : programme utilisé CONFORME au document ({date}, {a['found']} heures)"
    if not a.get("plausible"):
        return (
            f"{fam} : texte du document peu exploitable ({a['found']} heures relevées, {date}). "
            "Ouvrir le document pour le lire ; le programme utilisé n'est pas modifié."
        )
    parts = []
    if a.get("added"):
        parts.append("heures nouvelles " + ", ".join(hm(x) for x in a["added"][:12]) + ("…" if len(a["added"]) > 12 else ""))
    if a.get("removed"):
        parts.append("heures absentes du document " + ", ".join(hm(x) for x in a["removed"][:12]) + ("…" if len(a["removed"]) > 12 else ""))
    return f"{fam} : différences avec le document ({date}) : " + " ; ".join(parts)


# ----------------------------------------------------------------------------- traitement complet
def process_source(root_dir, source, data: bytes, current_schedules, now=None):
    """Conserve le document, extrait le texte, analyse les familles. Renvoie un enregistrement d'état."""
    now = now or datetime.now(timezone.utc)
    sha = hashlib.sha256(data).hexdigest()
    d = sources_dir(root_dir)
    d.mkdir(parents=True, exist_ok=True)
    ext = ".pdf" if data[:5] == b"%PDF-" else ".txt"
    fname = f"{source['id']}{ext}"
    try:
        (d / fname).write_bytes(data)
    except Exception:
        pass
    text = extract_pdf_text(data)
    try:
        (d / f"{source['id']}_texte.txt").write_text(text, encoding="utf-8")
    except Exception:
        pass
    whole = source["id"].startswith("DWD") and len(source.get("families") or []) == 1
    if looks_html(data):
        # page HTML au lieu du document : on ne compare rien (le fil de téléchargement suit déjà le lien PDF)
        return {
            "id": source["id"], "label": source.get("label"), "url": source["url"], "file": fname,
            "sha256": sha, "size_bytes": len(data), "download_utc": now.isoformat(), "text_chars": 0,
            "analyses": [{"family": f, "section_found": False, "info_date": None, "found": 0, "added": [],
                          "removed": [], "plausible": False, "conforme": False, "method": "html"}
                         for f in source.get("families") or []],
        }
    analyses = [
        analyse_family(text, fam, current_schedules.get(fam, BROADCAST_SCHEDULES_UTC.get(fam, [])), whole_document=whole)
        for fam in source.get("families") or []
    ]
    return {
        "id": source["id"],
        "label": source.get("label"),
        "url": source["url"],
        "file": fname,
        "sha256": sha,
        "size_bytes": len(data),
        "download_utc": now.isoformat(),
        "text_chars": len(text),
        "analyses": analyses,
    }


def record_decision(root_dir, source_id, sha, decision, family=None):
    st = _read_json(state_path(root_dir), {})
    dec = st.setdefault("decisions", {})
    dec[f"{source_id}:{family or '*'}:{sha}"] = {"decision": decision, "utc": datetime.now(timezone.utc).isoformat()}
    _write_json(state_path(root_dir), st)


def decision_for(root_dir, source_id, sha, family=None):
    st = _read_json(state_path(root_dir), {})
    rec = (st.get("decisions") or {}).get(f"{source_id}:{family or '*'}:{sha}")
    return (rec or {}).get("decision")


def accept_family(root_dir, family, slots, source_id, sha):
    acc = load_accepted(root_dir)
    acc[family] = {
        "base_rev": SCHEDULE_REV,
        "source": source_id,
        "sha256": sha,
        "accepted_utc": datetime.now(timezone.utc).isoformat(),
        "slots": [list(s) for s in slots],
    }
    ok = _write_json(accepted_path(root_dir), acc)
    record_decision(root_dir, source_id, sha, "accepte", family)
    apply_accepted(root_dir)
    return ok


def save_state(root_dir, records, online: bool, errors):
    st = _read_json(state_path(root_dir), {})
    st["last_attempt_utc"] = datetime.now(timezone.utc).isoformat()
    st["online"] = bool(online)
    st["errors"] = list(errors)
    srcs = st.setdefault("sources", {})
    for r in records:
        srcs[r["id"]] = r
    _write_json(state_path(root_dir), st)
    return st


def load_state(root_dir):
    st = _read_json(state_path(root_dir), {})
    return st if isinstance(st, dict) else {}
