"""Demandes de fichiers GRIB à Saildocs, et récupération des réponses arrivées dans Winlink Express.

2.8.7 — Saildocs envoie par messagerie des prévisions de modèle numérique (GFS, vagues) au format GRIB,
sur simple demande à query@saildocs.com. Par Winlink, cela fonctionne sans Internet sur place.
L'application prépare le texte de la demande ; l'opérateur l'envoie avec Winlink Express ; la réponse
reçue est lue directement dans le dossier des messages de Winlink (lecture seule) et le GRIB est copié
dans le dossier de l'application.
"""

import email
import email.policy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SAILDOCS_ADDRESS = "query@saildocs.com"


def build_request(qth, half_lat=2.5, half_lon=4.0, step_deg=0.5, hours=72, every_h=6, waves=True, model="gfs"):
    """Texte de la demande (une ligne « send ») et estimation de la taille de la réponse en ko."""
    lat0, lat1 = qth[0] - half_lat, qth[0] + half_lat
    lon0, lon1 = qth[1] - half_lon, qth[1] + half_lon

    def la(v):
        return f"{abs(round(v))}{'N' if v >= 0 else 'S'}"

    def lo(v):
        return f"{abs(round(v))}{'E' if v >= 0 else 'W'}"

    params = ["WIND", "PRMSL"] + (["WAVES"] if waves else [])
    line = (
        f"send {model}:{la(lat0)},{la(lat1)},{lo(lon0)},{lo(lon1)}|{step_deg:g},{step_deg:g}|"
        f"0,{every_h}..{hours}|{','.join(params)}"
    )
    npts = (int(2 * half_lat / step_deg) + 1) * (int(2 * half_lon / step_deg) + 1)
    nsteps = hours // every_h + 1
    nfields = 3 + (1 if waves else 0)  # U, V, pression, vagues
    size_kb = (npts * nfields * nsteps * 12 / 8 + nfields * nsteps * 90) / 1024
    return line, size_kb


def transfer_minutes(size_kb, bytes_per_min=1500):
    """Durée indicative de la réception (VARA HF gratuit, bonnes conditions : de l'ordre de 1 à 3 ko/min)."""
    return max(1.0, size_kb * 1024 / bytes_per_min)


def _processed_db(app_dir):
    p = Path(app_dir) / "deja_lus.json"
    try:
        return p, json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return p, {}


def collect_gribs(winlink_user_dir, app_grib_dir, only_new=True):
    """Copie les GRIB des messages Winlink reçus (de Saildocs ou en pièce jointe .grb) ; renvoie la liste
    [{path, received, sender, subject, message_id}]. Les messages ne sont jamais modifiés."""
    app_grib_dir = Path(app_grib_dir)
    app_grib_dir.mkdir(parents=True, exist_ok=True)
    db_path, db = _processed_db(app_grib_dir)
    found = []
    msg_dir = Path(winlink_user_dir) / "Messages"
    if not msg_dir.is_dir():
        return found
    for f in sorted(msg_dir.glob("*.mime"), key=lambda x: x.stat().st_mtime):
        if only_new and f.name in db:
            continue
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        if b"GRIB" not in raw and b".grb" not in raw.lower() and b"saildocs" not in raw.lower():
            db[f.name] = "sans GRIB"
            continue
        try:
            msg = email.message_from_bytes(raw, policy=email.policy.default)
        except Exception:
            continue
        sender = str(msg.get("From", ""))
        subject = str(msg.get("Subject", ""))
        try:
            received = email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
        except (TypeError, ValueError):
            received = None
        if received is None:
            received = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        n = 0
        for part in msg.walk():
            fn = part.get_filename() or ""
            if part.is_multipart():
                continue
            payload = part.get_payload(decode=True) or b""
            if not (fn.lower().endswith((".grb", ".grb2", ".grib", ".bz2")) or payload[:4] == b"GRIB"):
                continue
            if fn.lower().endswith(".bz2"):
                import bz2

                try:
                    payload = bz2.decompress(payload)
                    fn = fn[:-4]
                except OSError:
                    continue
            h = hashlib.sha1(payload).hexdigest()[:10]
            dest = app_grib_dir / f"{received:%Y%m%d_%H%M}Z_{Path(fn or 'saildocs.grb').stem}_{h}.grb"
            if not dest.exists():
                dest.write_bytes(payload)
            found.append(
                {"path": dest, "received": received, "sender": sender, "subject": subject, "message_id": f.stem}
            )
            n += 1
        db[f.name] = f"{n} GRIB" if n else "sans GRIB"
    try:
        db_path.write_text(json.dumps(db, indent=1), encoding="utf-8")
    except OSError:
        pass
    return found


def latest_grib(app_grib_dir):
    files = sorted(Path(app_grib_dir).glob("*.grb"), key=lambda p: p.name)
    return files[-1] if files else None
