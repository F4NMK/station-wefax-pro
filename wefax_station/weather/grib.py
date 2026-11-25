"""Lecture des fichiers GRIB édition 1 (Saildocs, modèle GFS / vagues WW3), sans bibliothèque externe.

2.8.7 — les fichiers reçus par Winlink sont petits (quelques ko) et utilisent toujours la même
forme : grille régulière latitude/longitude, compactage simple. Ce module décode ce cas, et refuse
proprement le reste (GRIB 2, harmoniques sphériques, compactage complexe).

Référence : OMM, Manuel des codes n° 306, FM 92 GRIB édition 1 ; table 2 des paramètres NCEP.
"""

import math
from datetime import datetime, timedelta, timezone

import numpy as np

from wefax_station.weather.units import ms_to_beaufort

PARAMS = {
    2: ("PRMSL", "pression mer", "Pa"),
    7: ("HGT", "géopotentiel", "gpm"),
    11: ("TMP", "température", "K"),
    33: ("UGRD", "vent U", "m/s"),
    34: ("VGRD", "vent V", "m/s"),
    61: ("APCP", "précipitations", "kg/m2"),
    100: ("HTSGW", "hauteur des vagues", "m"),
    101: ("WVDIR", "direction des vagues", "°"),
    103: ("WVPER", "période des vagues", "s"),
}


class GribError(ValueError):
    pass


def _u(b):
    return int.from_bytes(b, "big")


def _s(b):
    """Entier signé GRIB 1 : bit de signe en tête, pas de complément à deux."""
    v = int.from_bytes(b, "big")
    sign = 1 << (8 * len(b) - 1)
    return -(v & (sign - 1)) if v & sign else v


def _ibm(b):
    v = int.from_bytes(b, "big")
    if v == 0:
        return 0.0
    sign = -1.0 if v >> 31 else 1.0
    exp = (v >> 24) & 0x7F
    mant = v & 0xFFFFFF
    return sign * mant / float(1 << 24) * 16.0 ** (exp - 64)


def _unit_hours(code):
    return {0: 1 / 60, 1: 1, 2: 24, 10: 3, 11: 6, 12: 12, 254: 1 / 3600}.get(code, 1)


def read_messages(data):
    """Liste des champs décodés {param, name, unit, level, ref, valid, lats, lons, values}."""
    out = []
    pos = 0
    while True:
        i = data.find(b"GRIB", pos)
        if i < 0:
            break
        if len(data) < i + 8:
            break
        total = _u(data[i + 4 : i + 7])
        ed = data[i + 7]
        if ed != 1:
            raise GribError(f"GRIB édition {ed} non pris en charge (demander le format GRIB 1)")
        msg = data[i : i + total]
        out.append(_decode(msg))
        pos = i + max(total, 8)
    if not out:
        raise GribError("aucun message GRIB dans le fichier")
    return out


def _decode(msg):
    p = 8
    pds_len = _u(msg[p : p + 3])
    pds = msg[p : p + pds_len]
    flags = pds[7]
    param = pds[8]
    level_type, level = pds[9], _u(pds[10:12])
    yy, mm, dd, hh, mi = pds[12], pds[13], pds[14], pds[15], pds[16]
    unit, p1, p2, tri = pds[17], pds[18], pds[19], pds[20]
    century = pds[24] if pds_len > 24 else 21
    dscale = _s(pds[26:28]) if pds_len > 27 else 0
    year = (century - 1) * 100 + yy
    ref = datetime(year, mm, dd, hh, mi, tzinfo=timezone.utc)
    step = (p1 * 256 + p2) if tri == 10 else (p2 if tri in (2, 3, 4) else p1)
    valid = ref + timedelta(hours=step * _unit_hours(unit))
    p += pds_len
    if not flags & 0x80:
        raise GribError("grille non décrite (GDS absente)")
    gds_len = _u(msg[p : p + 3])
    gds = msg[p : p + gds_len]
    if gds[5] != 0:
        raise GribError(f"type de grille {gds[5]} non pris en charge (seule la grille lat/lon l'est)")
    ni, nj = _u(gds[6:8]), _u(gds[8:10])
    la1, lo1 = _s(gds[10:13]) / 1000, _s(gds[13:16]) / 1000
    la2, lo2 = _s(gds[17:20]) / 1000, _s(gds[20:23]) / 1000
    scan = gds[27]
    p += gds_len
    bitmap = None
    if flags & 0x40:
        bms_len = _u(msg[p : p + 3])
        if _u(msg[p + 4 : p + 6]) != 0:
            raise GribError("masque prédéfini non pris en charge")
        bits = np.unpackbits(np.frombuffer(msg[p + 6 : p + bms_len], dtype=np.uint8))
        bitmap = bits[: ni * nj].astype(bool)
        p += bms_len
    bds_len = _u(msg[p : p + 3])
    bds = msg[p : p + bds_len]
    bflag = bds[3]
    if bflag & 0xC0:
        raise GribError("compactage non simple (harmoniques ou complexe) non pris en charge")
    escale = _s(bds[4:6])
    refv = _ibm(bds[6:10])
    nbits = bds[10]
    npts = int(bitmap.sum()) if bitmap is not None else ni * nj
    if nbits == 0:
        packed = np.zeros(npts)
    else:
        raw = np.unpackbits(np.frombuffer(bds[11:], dtype=np.uint8))
        need = npts * nbits
        if len(raw) < need:
            raise GribError("message GRIB tronqué")
        raw = raw[:need].reshape(npts, nbits).astype(np.int64)
        weights = 1 << np.arange(nbits - 1, -1, -1, dtype=np.int64)
        packed = raw @ weights
    vals = (refv + packed * (2.0**escale)) / (10.0**dscale)
    if bitmap is not None:
        full = np.full(ni * nj, np.nan)
        full[bitmap] = vals
        vals = full
    # balayage : bit 0x80 = i vers l'ouest ; 0x40 = j vers le nord ; 0x20 = j consécutif
    if scan & 0x20:
        grid = vals.reshape(ni, nj).T
    else:
        grid = vals.reshape(nj, ni)
    lats = np.linspace(la1, la2, nj)
    if lo2 < lo1 and not scan & 0x80:
        lo2 += 360
    lons = np.linspace(lo1, lo2, ni)
    lons = np.where(lons > 180, lons - 360, lons)
    name = PARAMS.get(param, (f"P{param}", f"paramètre {param}", ""))
    return {
        "param": name[0],
        "name": name[1],
        "unit": name[2],
        "level_type": level_type,
        "level": level,
        "ref": ref,
        "valid": valid,
        "lats": lats,
        "lons": lons,
        "values": grid,
    }


DIR16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]




def _dist_grid_km(qth, lats, lons):
    """Distances (km) du QTH à chaque point de grille (lats × lons), calcul vectorisé (2.10.0 : avant,
    np.vectorize appelait une fonction Python par point de grille)."""
    la = np.radians(np.asarray(lats, dtype=float))[:, None]
    lo = np.radians(np.asarray(lons, dtype=float))[None, :]
    la0, lo0 = math.radians(qth[0]), math.radians(qth[1])
    h = np.sin((la - la0) / 2) ** 2 + math.cos(la0) * np.cos(la) * np.sin((lo - lo0) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def summarize(fields, qth, radius_km=150):
    """Par échéance : vent au point de grille le plus proche du QTH et vent maxi dans le rayon."""
    by_time = {}
    for f in fields:
        by_time.setdefault(f["valid"], {})[f["param"]] = f
    rows = []
    for t in sorted(by_time):
        d = by_time[t]
        row = {"valid": t, "ref": next(iter(d.values()))["ref"]}
        if "UGRD" in d and "VGRD" in d:
            u, v = d["UGRD"]["values"], d["VGRD"]["values"]
            lats, lons = d["UGRD"]["lats"], d["UGRD"]["lons"]
            sp = np.hypot(u, v)
            dist = _dist_grid_km(qth, lats, lons)
            j0, i0 = np.unravel_index(np.nanargmin(dist), dist.shape)
            row["wind_ms"] = float(sp[j0, i0])
            ang = (math.degrees(math.atan2(-u[j0, i0], -v[j0, i0])) + 360) % 360  # direction d'où vient le vent
            row["wind_dir"] = DIR16[int(ang / 22.5 + 0.5) % 16]
            mask = dist <= radius_km
            if mask.any():
                k = np.nanargmax(np.where(mask, sp, -1))
                jm, im = np.unravel_index(k, sp.shape)
                row["max_ms"] = float(sp[jm, im])
                row["max_at"] = (float(lats[jm]), float(lons[im]))
        if "PRMSL" in d:
            pr = d["PRMSL"]
            lats, lons = pr["lats"], pr["lons"]
            j = int(np.argmin(abs(lats - qth[0])))
            i = int(np.argmin(abs(lons - qth[1])))
            row["pressure_hpa"] = float(pr["values"][j, i]) / 100.0
        if "HTSGW" in d:
            w = d["HTSGW"]
            lats, lons = w["lats"], w["lons"]
            dist = _dist_grid_km(qth, lats, lons)
            vals = np.where(dist <= radius_km, w["values"], np.nan)
            if np.isfinite(vals).any():
                row["wave_max_m"] = float(np.nanmax(vals))
        rows.append(row)
    return rows


def report_lines(rows, label="GFS", received=None, now=None):
    """Rubrique du rapport : une ligne par échéance (heure de Paris)."""
    from wefax_station.weather.plain_language import JOURS, to_paris

    now = now or datetime.now(timezone.utc)
    L = []
    for r in rows:
        if r["valid"] < now - timedelta(hours=3):
            continue
        loc = to_paris(r["valid"])
        parts = []
        if "wind_ms" in r:
            kn = r["wind_ms"] * 1.94384
            parts.append(f"{r['wind_dir']} {kn:.0f} nds (force {ms_to_beaufort(r['wind_ms'])})")
        if "max_ms" in r:
            parts.append(f"maxi secteur {r['max_ms'] * 1.94384:.0f} nds (force {ms_to_beaufort(r['max_ms'])})")
        if "wave_max_m" in r:
            parts.append(f"vagues jusqu'à {r['wave_max_m']:.1f} m".replace(".", ","))
        if "pressure_hpa" in r:
            parts.append(f"{r['pressure_hpa']:.0f} hPa")
        if parts:
            L.append(f" • {JOURS[loc.weekday()][:3]}. {loc.day:02d} {loc.hour:02d} h : " + ", ".join(parts))
    if L and rows:
        head = f"   Modèle {label}, calcul du {rows[0]['ref']:%d/%m %H} UTC" + (
            f", reçu par Winlink le {received:%d/%m à %H:%M} UTC" if received else ""
        )
        L.insert(0, head + ". Prévision brute de modèle, non expertisée : à comparer aux bulletins.")
    return L


