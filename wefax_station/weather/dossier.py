"""Dossier météo : tous les bulletins texte utiles des dernières heures, et non le dernier message reçu.

2.8.6 — le 17/11 à 07:05, le rapport a été rédigé à partir du dernier texte reçu (« SMEN43 … NIL », une
synop vide) : il concluait « aucune prévision à moins de 500 km » alors que la prévision Méditerranée de
04:14 annonçait force 7-8, rafales 10 et 5 m de mer en mer Ligure. Le rapport s'appuie maintenant sur ce
dossier :

* chaque bulletin archivé (bulletins_radio/*_original.txt) des dernières 30 h est relu ;
* les messages sans prévision exploitable sont écartés (synops AAXX/BBXX, « NIL », avis à la navigation,
  séquences de service) ;
* pour chaque point ou zone, la prévision la plus récente fait foi ;
* les points reçus mais illisibles sont signalés, avec la source qui les contenait.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wefax_station.weather.rtty_parse import parse_point_forecasts
from wefax_station.weather.rtty_repair import repair_bulletin

_HDR_STATION = re.compile(r"Station\s*:\s*(\S+)\s*\(([\d.]+)\s*kHz\)")
_HDR_START = re.compile(r"Début UTC\s*:\s*(\S+)")
_HDR_PRODUCT = re.compile(r"Produit\s*:\s*(.+?)\s*\|")
_WMO = re.compile(r"\b([A-Z]{4})(\d{2})\s+([A-Z]{4})\s+(\d{6})\b")

# en-têtes OMM sans prévision lisible par l'application : observations (S…), avis à la navigation (WWXX
# « NAUTISCHE WARNNACHRICHTEN » contient aussi un avis de vent, il est donc gardé), etc.
_SKIP_TT = ("SI", "SM", "SN", "SA", "US", "UK")


def classify(body):
    """'prevision', 'avis', ou None (sans intérêt pour la synthèse) + raison."""
    up = (body or "").upper()
    core = re.sub(r"\b(ZCZC\s*\d*|NNNN)\b", " ", up)
    core = _WMO.sub(" ", core)
    if re.search(r"\b(AAXX|BBXX)\b", up):
        if re.search(r"\b(AAXX|BBXX)\b\s*(\d{4}[0-9/]\s*)?NIL\b", up) and not re.search(r"=\s*\S", up):
            return None, "observations vides (NIL)"
        return "observations", "observations (SYNOP / SHIP)"
    if re.fullmatch(r"[\s=]*NIL[\s=]*", core) or len(re.sub(r"\W", "", core)) < 20:
        return None, "message vide (NIL)"
    if "CURRENT MARINE WEATHER REPORTS" in up or ("PHONE:" in up and "INTERNET:" in up):
        return None, "informations de service"
    m = _WMO.search(up)
    if m and m.group(1)[:2] in _SKIP_TT:
        return None, f"observations ({m.group(1)})"
    if re.search(r"\(\s*\d{1,2}\.\d\s*[NS]\s+\d{1,3}\.\d\s*[EW]\s*\)", up) and re.search(r"\d{2}Z:", up):
        return "prevision", "prévision par points"
    if any(k in up for k in ("GALE", "STORM", "STURM", "WARNING", "FORECAST", "WIND", "BEAUFORT", "BFT")):
        return "avis", "avis / prévision par zones"
    return None, "sans prévision météo"


def _read_archive(path):
    try:
        txt = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    head, _, body = txt.partition("=" * 78)
    st = _HDR_STATION.search(head)
    start = _HDR_START.search(head)
    prod = _HDR_PRODUCT.search(head)
    try:
        t = datetime.fromisoformat(start.group(1)) if start else None
    except ValueError:
        t = None
    if t is None:
        t = datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc)
    return {
        "path": Path(path),
        "station": st.group(1) if st else "?",
        "freq": float(st.group(2)) if st else 0.0,
        "time": t,
        "product": prod.group(1) if prod else "",
        "body": body.strip(),
    }


def collect(day_dirs, now=None, hours=30, live_text=None, live_source=None):
    """Dossier des bulletins utiles. day_dirs = dossiers « receptions/AAAA-MM-JJ » à parcourir."""
    now = now or datetime.now(timezone.utc)
    docs = []
    for d in day_dirs:
        from wefax_station.storage.layout import bulletin_text_dirs

        for f in sorted(x for bd in bulletin_text_dirs(d) for x in bd.glob("*_original.txt")):
            doc = _read_archive(f)
            if doc and doc["time"] >= now - timedelta(hours=hours):
                docs.append(doc)
    if live_text and live_text.strip():
        docs.append(
            {
                "path": None,
                "station": (live_source or {}).get("id", "?"),
                "freq": (live_source or {}).get("freq", 0.0),
                "time": now,
                "product": "réception en cours",
                "body": live_text,
                "live": True,
            }
        )
    return assemble(docs, now)


def assemble(docs, now=None):
    """Dossier à partir d'une liste de documents {station, freq, time, product, body}."""
    now = now or datetime.now(timezone.utc)
    docs = sorted(docs, key=lambda x: x["time"])
    used, skipped = [], []
    observations = []
    points, areas_text = {}, []
    unreadable = {}
    for doc in docs:
        kind, why = classify(doc["body"])
        if kind is None:
            skipped.append((doc, why))
            continue
        if kind == "observations":
            from wefax_station.weather.synop import parse_observations

            obs = parse_observations(doc["body"], doc["time"])
            for o in obs:
                o["source"] = doc
            observations += obs
            doc["kind"] = kind
            doc["obs_count"] = len(obs)
            continue
        repaired, rep = repair_bulletin(doc["body"])
        doc["kind"], doc["repair"] = kind, rep
        doc["wmo"] = (lambda m: f"{m.group(1)}{m.group(2)} {m.group(3)} {m.group(4)}" if m else "")(
            _WMO.search(doc["body"].upper())
        )
        used.append(doc)
        for p in parse_point_forecasts(repaired, repaired=True):
            p["source"] = doc
            points[p["point"]] = p  # le plus récent remplace l'ancien
            unreadable.pop(p["point"], None)
        for name, v in rep.get("points", {}).items():
            if v["ok"] == 0 and name not in points:
                unreadable[name] = doc
        if kind == "avis":
            areas_text.append(doc["body"])
    return {
        "points": list(points.values()),
        "areas_text": "\n".join(areas_text),
        "used": used,
        "skipped": skipped,
        "unreadable": unreadable,
        "observations": observations,
        "obs_docs": [d for d in docs if d.get("kind") == "observations"],
        "now": now,
    }


def day_dirs_for(workspace, now=None):
    now = now or datetime.now(timezone.utc)
    out = []
    for back in (1, 0):
        try:
            out.append(Path(workspace.reception_day_dir(now - timedelta(days=back))))
        except Exception:
            pass
    return out


def sources_lines(dossier, now=None):
    now = now or dossier.get("now") or datetime.now(timezone.utc)
    L = []
    for d in reversed(dossier["used"]):
        age_h = (now - d["time"]).total_seconds() / 3600
        rep = d.get("repair") or {}
        lis = f" — {rep['readable_pct']} % lisible" if rep.get("step_lines") else ""
        what = d.get("wmo") or d.get("product") or ""
        L.append(
            f" • {d['time']:%d/%m %H:%M} UTC ({'en cours' if d.get('live') else (f'il y a {age_h:.0f} h' if age_h >= 1 else f'il y a {age_h * 60:.0f} min')}) — "
            f"{d['station']} {d['freq']:.1f} kHz — {what}{lis}"
        )
    obs_docs = dossier.get("obs_docs") or []
    if obs_docs:
        n = sum(d.get("obs_count", 0) for d in obs_docs)
        last = max(obs_docs, key=lambda d: d["time"])
        L.append(
            f" • Observations : {n} relevé(s) dans {len(obs_docs)} message(s), le dernier reçu "
            f"{last['time']:%d/%m %H:%M} UTC sur {last['station']}"
        )
    for title, when, what in dossier.get("extra_sources", []):
        L.append(f" • {title} : {what} ({when})")
    return L
