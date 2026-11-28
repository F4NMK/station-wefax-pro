"""Situation actuelle et prévision à courte échéance (3 à 6 h) sur le secteur de l'opérateur (2.10.0).

Le logiciel reçoit des bulletins de prévision (RTTY DWD, NAVTEX), des observations codées (SYNOP, SHIP,
bouées), parfois un GRIB par Winlink, et l'opérateur peut noter sa propre observation (pression, tendance,
vent, mer). Ce module les croise pour répondre à deux questions :

1. Que se passe-t-il maintenant dans le secteur ?
2. Que peut-on attendre dans 3 à 6 h, et avec quelle confiance ?

Règles de méthode :

* les FAITS (ce qui a été reçu ou observé, avec son heure et sa source) et les ESTIMATIONS (ce que l'on
  en déduit) restent séparés ;
* une prévision officielle reçue prime toujours ; le GRIB est un modèle brut (GFS), l'observation dit ce
  qui se passe, la tendance barométrique renseigne sur l'évolution ;
* l'indice de fiabilité mesure ce que l'on sait (fraîcheur, nombre de sources indépendantes, accord entre
  elles, lisibilité de la réception, distance du point de prévision) — pas la météo elle-même ;
* rien n'est inventé : sans donnée, la section le dit.

Tendance barométrique sur 3 h (termes des bulletins marins britanniques, repris par la plupart des
services) : stationnaire < 0,1 hPa ; lente 0,1 à 1,5 ; (sans adverbe) 1,6 à 3,5 ; rapide 3,6 à 6,0 ;
très rapide > 6,0. Une baisse rapide annonce en général un renforcement du vent dans les heures qui
suivent ; une hausse rapide après une dépression, du vent fort et des grains sur l'arrière.
"""

from datetime import datetime, timedelta, timezone

from wefax_station.weather.plain_language import distance_km, level_of, sea_name, step_datetime, worst_level

LOCAL_KM = 150
OBS_FRESH_H = 3.0
OBS_MAX_H = 6.0
WINDOW_H = (3.0, 6.0)

# ---------------------------------------------------------------------------------------- tendance
TENDENCY_CLASSES = (  # (seuil haut |hPa/3 h|, mot)
    (0.1, "stationnaire"),
    (1.5, "lente"),
    (3.5, ""),
    (6.0, "rapide"),
    (99.0, "très rapide"),
)

# valeurs du formulaire « Observations locales » (Réglages › Opérateur), anciennes valeurs comprises
OPERATOR_TENDENCY = {
    "stationnaire (< 0,1 hpa)": 0.0,
    "hausse lente (0,1 à 1,5 hpa)": 0.8,
    "hausse (1,6 à 3,5 hpa)": 2.5,
    "hausse rapide (3,6 à 6 hpa)": 4.5,
    "hausse très rapide (> 6 hpa)": 7.0,
    "baisse lente (0,1 à 1,5 hpa)": -0.8,
    "baisse (1,6 à 3,5 hpa)": -2.5,
    "baisse rapide (3,6 à 6 hpa)": -4.5,
    "baisse très rapide (> 6 hpa)": -7.0,
    # jusqu'à 2.9.8
    "stable": 0.0,
    "hausse": 1.6,
    "baisse modérée": -1.6,
    "chute rapide": -4.5,
}
OPERATOR_TENDENCY_VALUES = [
    "Non renseigné",
    "Stationnaire (< 0,1 hPa)",
    "Hausse lente (0,1 à 1,5 hPa)",
    "Hausse (1,6 à 3,5 hPa)",
    "Hausse rapide (3,6 à 6 hPa)",
    "Hausse très rapide (> 6 hPa)",
    "Baisse lente (0,1 à 1,5 hPa)",
    "Baisse (1,6 à 3,5 hPa)",
    "Baisse rapide (3,6 à 6 hPa)",
    "Baisse très rapide (> 6 hPa)",
]
OPERATOR_WIND_DIR_VALUES = [
    "Non renseigné",
    "Calme",
    "Nord",
    "Nord-Est",
    "Est",
    "Sud-Est",
    "Sud",
    "Sud-Ouest",
    "Ouest",
    "Nord-Ouest",
    "Variable",
]
OPERATOR_BFT_VALUES = ["Non renseigné"] + [f"Force {i}" for i in range(0, 13)]
OPERATOR_SEA_VALUES = [  # échelle Douglas (mer du vent)
    "Non renseigné",
    "Calme (0 m)",
    "Ridée (0 à 0,1 m)",
    "Belle (0,1 à 0,5 m)",
    "Peu agitée (0,5 à 1,25 m)",
    "Agitée (1,25 à 2,5 m)",
    "Forte (2,5 à 4 m)",
    "Très forte (4 à 6 m)",
    "Grosse (6 à 9 m)",
    "Très grosse (9 à 14 m)",
]
_SEA_MID_M = {0: 0.0, 1: 0.05, 2: 0.3, 3: 0.9, 4: 1.9, 5: 3.2, 6: 5.0, 7: 7.5, 8: 11.0}


def tendency_words(dp):
    """« baisse rapide (−4,2 hPa en 3 h) » ; dp en hPa sur 3 h."""
    if dp is None:
        return ""
    a = abs(dp)
    word = next(w for lim, w in TENDENCY_CLASSES if a <= lim)
    if word == "stationnaire":
        return f"pression stationnaire ({dp:+.1f} hPa en 3 h)".replace(".", ",")
    sense = "hausse" if dp > 0 else "baisse"
    return f"{sense}{(' ' + word) if word else ''} ({dp:+.1f} hPa en 3 h)".replace(".", ",")


def tendency_outlook(dp):
    """Ce qu'une tendance annonce en général pour les heures suivantes (règle empirique, pas une prévision)."""
    if dp is None:
        return None
    if dp <= -6.0:
        return "chute très rapide : risque de coup de vent ou de tempête dans les prochaines heures"
    if dp <= -3.6:
        return "baisse rapide : renforcement du vent probable dans les 3 à 6 h, dégradation"
    if dp <= -1.6:
        return "baisse nette : dégradation possible, vent en hausse"
    if dp >= 6.0:
        return "hausse très rapide : vent fort et grains possibles sur l'arrière de la perturbation"
    if dp >= 3.6:
        return "hausse rapide : vent fort possible un temps, puis amélioration"
    if dp >= 1.6:
        return "hausse nette : amélioration probable"
    return "pression peu changeante : pas d'évolution marquée attendue"


def parse_operator_obs(obs, now=None):
    """Formulaire « Observations locales » -> {time, pressure_hpa, tendency_hpa, dir, bft, sea_m} (valeurs
    connues seulement). Les champs « Non renseigné » ou vides sont ignorés."""
    now = now or datetime.now(timezone.utc)
    if not obs:
        return {}
    out = {}

    def val(*keys):
        for k in keys:
            v = obs.get(k)
            if v is not None and str(v).strip() and not str(v).lower().startswith("non renseign"):
                return str(v).strip()
        return None

    t = val("Date UTC")
    if t:
        for fmt in ("%Y-%m-%d %H:%M UTC", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"):
            try:
                out["time"] = datetime.strptime(t, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
    p = val("Pression hPa")
    if p:
        try:
            pv = float(p.replace(",", "."))
            if 900 <= pv <= 1080:
                out["pressure_hpa"] = pv
        except ValueError:
            pass
    tr = val("Tendance 3 h")
    if tr and tr.lower() in OPERATOR_TENDENCY:
        out["tendency_hpa"] = OPERATOR_TENDENCY[tr.lower()]
    d = val("Vent", "Direction du vent")
    if d:
        out["dir"] = d.lower()
    f = val("Force du vent")
    if f and f.lower().startswith("force"):
        try:
            out["bft"] = int(f.split()[1])
        except (IndexError, ValueError):
            pass
    s = val("Mer")
    if s and s in OPERATOR_SEA_VALUES:
        out["sea_m"] = _SEA_MID_M.get(OPERATOR_SEA_VALUES.index(s) - 1)
    if len(out) <= (1 if "time" in out else 0):
        return {}
    out.setdefault("time", now)
    return out


# ---------------------------------------------------------------------------------------- utilitaires
def _age_h(now, t):
    return (now - t).total_seconds() / 3600.0 if t else None


def _fmt_age(h):
    if h is None:
        return "heure inconnue"
    if h < 1:
        return f"il y a {max(1, round(h * 60))} min"
    return f"il y a {h:.0f} h" if h < 48 else f"il y a {h / 24:.0f} j"


def _bft_of_ms(ms):
    kn = ms * 1.94384
    for f, lim in enumerate((1, 4, 7, 11, 17, 22, 28, 34, 41, 48, 56, 64)):
        if kn < lim:
            return f
    return 12


def _num(x):
    return str(x).replace(".", ",")


_DIR_FR = {
    "N": "nord", "NNE": "nord-nord-est", "NE": "nord-est", "ENE": "est-nord-est", "E": "est",
    "ESE": "est-sud-est", "SE": "sud-est", "SSE": "sud-sud-est", "S": "sud", "SSO": "sud-sud-ouest",
    "SSW": "sud-sud-ouest", "SO": "sud-ouest", "SW": "sud-ouest", "OSO": "ouest-sud-ouest",
    "WSW": "ouest-sud-ouest", "O": "ouest", "W": "ouest", "ONO": "ouest-nord-ouest", "WNW": "ouest-nord-ouest",
    "NO": "nord-ouest", "NW": "nord-ouest", "NNO": "nord-nord-ouest", "NNW": "nord-nord-ouest",
}


def dir_fr(d):
    """« SO » -> « sud-ouest », « W-NW » -> « ouest à nord-ouest » ; mots déjà en clair inchangés."""
    if not d:
        return ""
    return " à ".join(_DIR_FR.get(x.strip().upper(), x.strip()) for x in str(d).split("-"))


# ---------------------------------------------------------------------------------------- analyse
def build_nowcast(
    now=None,
    qth=(43.58, 7.02),
    radius_km=300,
    zone_label="",
    points=(),
    areas=(),
    observations=(),
    grib_rows=None,
    grib_received=None,
    operator=None,
    charts=(),
    text_docs=(),
    gale_texts=(),
):
    """Situation actuelle et prévision 3 à 6 h.

    points       : prévisions ponctuelles (weather.rtty_parse / dossier), avec p["source"]["time"] si connu
    areas        : prévisions par zones (plain_language.parse_area_forecasts)
    observations : SYNOP / SHIP décodés (weather.synop.parse_observations)
    grib_rows    : weather.grib.summarize(...) ; grib_received : heure de réception du GRIB
    operator     : parse_operator_obs(...) ou formulaire brut
    charts       : [{"time", "station", "label", "rel"}] cartes WEFAX reçues
    text_docs    : documents texte utilisés [{"time", "station", "repair": {"readable_pct"}}]
    gale_texts   : avis de coup de vent lus dans les textes (rtty_parse.gale_warnings)
    """
    now = now or datetime.now(timezone.utc)
    w0, w1 = now + timedelta(hours=WINDOW_H[0]), now + timedelta(hours=WINDOW_H[1])
    if operator and "Date UTC" in operator:
        operator = parse_operator_obs(operator, now)
    operator = operator or {}
    facts_now, facts_fc, estimates, sources = [], [], [], []
    reasons = []
    score = 0.0

    # ---- 1. observations reçues (SYNOP / SHIP / bouées), les plus proches et les plus fraîches
    near_obs = []
    for o in observations or ():
        if o.get("lat") is None or o.get("time") is None:
            continue
        d = distance_km(qth, (o["lat"], o["lon"]))
        age = _age_h(now, o["time"])
        if d <= radius_km and age is not None and -1 <= age <= OBS_MAX_H:
            near_obs.append((d, age, o))
    latest = {}
    for d, age, o in sorted(near_obs, key=lambda x: x[1]):
        latest.setdefault(o.get("id"), (d, age, o))
    near_obs = sorted(latest.values(), key=lambda x: (x[0] > LOCAL_KM, x[0]))[:4]
    obs_bft = None
    obs_bft_age = None
    obs_tend = None
    for d, age, o in near_obs:
        parts = []
        if o.get("wind_dir") == "calme":
            parts.append("calme")
        elif o.get("bft") is not None:
            parts.append(f"vent {dir_fr(o.get('wind_dir', ''))} force {o['bft']} ({o.get('wind_kn')} nd)".replace("  ", " "))
        if o.get("wave_m") is not None:
            parts.append(f"mer {_num(o['wave_m'])} m")
        if o.get("pressure_hpa") is not None:
            parts.append(f"pression {_num(o['pressure_hpa'])} hPa")
        if o.get("tendency_hpa") is not None:
            parts.append(tendency_words(o["tendency_hpa"]))
        if not parts:
            continue
        facts_now.append(f"{o.get('name', '?')} ({d:.0f} km), {o['time']:%H} UTC ({_fmt_age(age)}) : " + ", ".join(parts))
        if obs_bft is None and o.get("bft") is not None and age <= OBS_FRESH_H:
            obs_bft, obs_bft_age = o["bft"], age
        if obs_tend is None and o.get("tendency_hpa") is not None and age <= OBS_FRESH_H:
            obs_tend = o["tendency_hpa"]
    if facts_now:
        fresh = any(a <= OBS_FRESH_H for _d, a, _o in near_obs)
        score += 10 if fresh else 5
        reasons.append(("observations reçues dans le secteur", 10 if fresh else 5))
        sources.append("observations SYNOP / SHIP")

    # ---- 2. observation de l'opérateur
    op_tend = None
    if operator:
        age = _age_h(now, operator.get("time"))
        parts = []
        if operator.get("dir") or operator.get("bft") is not None:
            parts.append(
                "vent "
                + (operator.get("dir") or "")
                + (f" force {operator['bft']}" if operator.get("bft") is not None else "")
            )
        if operator.get("sea_m") is not None:
            parts.append(f"mer ≈ {_num(operator['sea_m'])} m")
        if operator.get("pressure_hpa") is not None:
            parts.append(f"pression {_num(operator['pressure_hpa'])} hPa")
        if operator.get("tendency_hpa") is not None:
            parts.append(tendency_words(operator["tendency_hpa"]))
            op_tend = operator["tendency_hpa"]
        if parts and (age is None or age <= OBS_MAX_H):
            facts_now.insert(0, f"Observation de l'opérateur ({_fmt_age(age)}) : " + ", ".join(p.strip() for p in parts))
            score += 6
            reasons.append(("observation locale de l'opérateur", 6))
            sources.append("observation opérateur")
            # l'observation de l'opérateur, sur place, prime sur une observation reçue plus ancienne
            if operator.get("bft") is not None and (obs_bft is None or (age or 0) <= (obs_bft_age or 99)):
                obs_bft, obs_bft_age = operator["bft"], age

    # ---- 3. prévisions texte reçues : échéance en vigueur et échéances de la fenêtre 3-6 h
    fc_now, fc_win = None, None  # (bft_max, gust, sea, dir, point, dist, issued)
    best_issue_age = None
    for p in points or ():
        d = distance_km(qth, (p["lat"], p["lon"]))
        if d > radius_km:
            continue
        issued = (p.get("source") or {}).get("time")
        steps = []
        for s in p.get("steps", ()):
            dt = step_datetime(s["date"], s["hour"], now)
            if dt is not None:
                steps.append((dt, s))
        if not steps:
            continue
        # échéance « en vigueur » : la dernière commencée (moins de 6 h), sinon la plus proche
        started = [x for x in steps if now - timedelta(hours=6) <= x[0] <= now + timedelta(minutes=30)]
        cur = max(started, key=lambda x: x[0]) if started else min(steps, key=lambda x: abs((x[0] - now).total_seconds()))
        win = [x for x in steps if w0 - timedelta(hours=3) <= x[0] <= w1 + timedelta(hours=1)]

        def pack(dt_s, p=p, d=d, issued=issued):
            dt, s = dt_s
            return {
                "bft": s["bft_max"],
                "bft_min": s.get("bft_min", s["bft_max"]),
                "gust": s.get("gust_max"),
                "sea": s.get("sea_m"),
                "dir": s.get("dir", ""),
                "point": p["point"],
                "lat": p["lat"],
                "lon": p["lon"],
                "dist": d,
                "issued": issued,
                "valid": dt,
            }

        if started or abs((cur[0] - now).total_seconds()) <= 4 * 3600:
            c = pack(cur)
            if fc_now is None or (c["dist"], -c["bft"]) < (fc_now["dist"], -fc_now["bft"]):
                fc_now = c
        for x in win:
            c = pack(x)
            if fc_win is None or (c["dist"] <= LOCAL_KM, c["bft"], c["sea"] or 0) > (
                fc_win["dist"] <= LOCAL_KM,
                fc_win["bft"],
                fc_win["sea"] or 0,
            ):
                fc_win = c
        if issued is not None:
            a = _age_h(now, issued)
            best_issue_age = a if best_issue_age is None else min(best_issue_age, a)
    for a in areas or ():
        d = distance_km(qth, (a["lat"], a["lon"]))
        if d > radius_km:
            continue
        c = {
            "bft": a["bft_max"],
            "bft_min": a["bft_min"],
            "gust": None,
            "sea": a.get("sea_m"),
            "dir": a.get("dir", ""),
            "point": a["point"],
            "lat": None,
            "lon": None,
            "dist": d,
            "issued": None,
            "valid": None,
            "gale": a.get("gale"),
        }
        if fc_win is None or (c["bft"], c["sea"] or 0) > (fc_win["bft"], fc_win["sea"] or 0):
            fc_win = c
        if fc_now is None:
            fc_now = c

    def fc_words(c):
        w = f"{dir_fr(c['dir'])} force {c['bft_min']}" + (f" à {c['bft']}" if c["bft"] != c["bft_min"] else "")
        if c.get("gust"):
            w += f", rafales {c['gust']}"
        if c.get("sea") is not None:
            w += f", mer {_num(c['sea'])} m"
        place = sea_name(c["lat"], c["lon"]) if c.get("lat") is not None else ""
        where = f"{place} (point {c['point']}, {c['dist']:.0f} km)" if place and place != c["point"] else f"{c['point']} ({c['dist']:.0f} km)"
        when = f", échéance {c['valid']:%d/%m %H} UTC" if c.get("valid") else ""
        return f"{where}{when} : {w.strip()}"

    if fc_now is not None:
        facts_now.append("Prévision en vigueur — " + fc_words(fc_now))
    if fc_win is not None:
        facts_fc.append("Prévision reçue pour la période — " + fc_words(fc_win))
        sources.append("prévision texte reçue")
        if best_issue_age is None:
            pts = 12
        else:
            pts = 22 if best_issue_age <= 12 else 14 if best_issue_age <= 24 else 6
        score += pts
        reasons.append(
            (
                "prévision officielle reçue"
                + (f" ({_fmt_age(best_issue_age)})" if best_issue_age is not None else "")
                + " couvrant la période",
                pts,
            )
        )
        dist_pts = 10 if fc_win["dist"] <= 50 else 6 if fc_win["dist"] <= LOCAL_KM else 2
        score += dist_pts
        reasons.append((f"point de prévision à {fc_win['dist']:.0f} km du secteur", dist_pts))

    # ---- 4. modèle numérique (GRIB)
    g_now, g_win, g_dp = None, None, None
    rows = [r for r in (grib_rows or ()) if r.get("valid") is not None]
    if rows:
        rows.sort(key=lambda r: r["valid"])
        near_now = min(rows, key=lambda r: abs((r["valid"] - now).total_seconds()))
        if abs((near_now["valid"] - now).total_seconds()) <= 3 * 3600:
            g_now = near_now
        win = [r for r in rows if w0 - timedelta(hours=1.5) <= r["valid"] <= w1 + timedelta(hours=1.5)]
        if win:
            g_win = max(win, key=lambda r: r.get("max_ms", r.get("wind_ms", 0)) or 0)
            if g_now and g_now.get("pressure_hpa") is not None and win[-1].get("pressure_hpa") is not None:
                hours = max(1.0, (win[-1]["valid"] - g_now["valid"]).total_seconds() / 3600)
                g_dp = (win[-1]["pressure_hpa"] - g_now["pressure_hpa"]) * 3.0 / hours
    grib_age = _age_h(now, grib_received)
    if g_win is not None:
        b = _bft_of_ms(g_win.get("wind_ms", 0) or 0)
        bm = _bft_of_ms(g_win.get("max_ms", g_win.get("wind_ms", 0)) or 0)
        line = (
            f"Modèle GFS (GRIB reçu {_fmt_age(grib_age)}), échéance {g_win['valid']:%d/%m %H} UTC : "
            f"vent {dir_fr(g_win.get('wind_dir', ''))} force {b} au point de grille le plus proche"
            + (f", jusqu'à force {bm} dans un rayon de 150 km" if bm > b else "")
            + (f", mer max {_num(round(g_win['wave_max_m'], 1))} m" if g_win.get("wave_max_m") is not None else "")
        )
        facts_fc.append(line)
        sources.append("modèle GRIB")
        pts = 12 if (grib_age is not None and grib_age <= 24) else 6
        score += pts
        reasons.append((f"modèle numérique GRIB ({_fmt_age(grib_age)})", pts))
    elif rows:
        reasons.append(("GRIB reçu mais ne couvre pas la période", 0))

    # ---- 5. tendance barométrique : opérateur, sinon observation proche, sinon modèle
    tend, tend_src = None, ""
    for v, src in ((op_tend, "observée par l'opérateur"), (obs_tend, "observation reçue"), (g_dp, "calculée sur le GRIB")):
        if v is not None:
            tend, tend_src = v, src
            break
    if tend is not None:
        estimates.append(f"Tendance barométrique ({tend_src}) : {tendency_words(tend)} — {tendency_outlook(tend)}.")

    # ---- 6. accord entre sources
    if fc_win is not None and g_win is not None:
        diff = abs(fc_win["bft"] - _bft_of_ms(g_win.get("max_ms", g_win.get("wind_ms", 0)) or 0))
        pts = 15 if diff <= 1 else 5 if diff == 2 else -10
        score += pts
        reasons.append((f"prévision texte et modèle {'concordants' if diff <= 1 else 'proches' if diff == 2 else 'en désaccord'} (écart {diff} force{'s' if diff > 1 else ''})", pts))
    if fc_now is not None and obs_bft is not None:
        diff = abs(fc_now["bft"] - obs_bft)
        pts = 6 if diff <= 1 else 0 if diff == 2 else -10
        score += pts
        reasons.append((f"vent observé {'conforme à' if diff <= 1 else 'proche de' if diff == 2 else 'différent de'} la prévision en vigueur (écart {diff})", pts))

    # ---- 7. lisibilité des textes reçus
    rd = [((d.get("repair") or {}).get("readable_pct")) for d in text_docs or () if (d.get("repair") or {}).get("readable_pct") is not None]
    if rd:
        r = sum(rd) / len(rd)
        pts = 12 if r >= 90 else 8 if r >= 70 else 4 if r >= 50 else -5
        score += pts
        reasons.append((f"textes reçus lisibles à {r:.0f} %", pts))

    # ---- 8. situation évolutive : l'incertitude augmente
    if tend is not None and abs(tend) >= 3.6:
        pen = -15 if abs(tend) >= 6 else -8
        score += pen
        reasons.append(("situation évolutive (pression qui varie vite)", pen))

    # ---- 9. cartes
    analysis = [c for c in charts or () if "analys" in str(c.get("label", "")).lower()]
    if analysis:
        last = max(analysis, key=lambda c: c["time"])
        a = _age_h(now, last["time"])
        facts_now.append(f"Dernière carte d'analyse reçue : {last['time']:%d/%m %H:%M} UTC ({last.get('station', '?')}, {_fmt_age(a)})")
        if a is not None and a <= 9:
            score += 5
            reasons.append(("carte d'analyse récente", 5))

    # ---- 10. avis de coup de vent
    gales = list(dict.fromkeys(gale_texts or ()))
    if fc_win is not None and fc_win.get("gale"):
        gales.append(f"avis de coup de vent ou de tempête pour {fc_win['point']}")

    # ---- synthèse : niveau, évolution, estimation chiffrée
    level = None
    if fc_win is not None or g_win is not None:
        b = fc_win["bft"] if fc_win else _bft_of_ms(g_win.get("max_ms", g_win.get("wind_ms", 0)) or 0)
        sea = (fc_win or {}).get("sea") or (g_win or {}).get("wave_max_m") or 0.0
        gust = (fc_win or {}).get("gust")
        level = level_of(b, sea, gust)
        if gales:
            level = worst_level([level, "ORANGE"])
        ref_now = obs_bft if obs_bft is not None else (fc_now or {}).get("bft")
        if ref_now is not None:
            if b >= ref_now + 2:
                evo = f"renforcement du vent (force {ref_now} maintenant, jusqu'à {b} dans 3 à 6 h)"
            elif b <= ref_now - 2:
                evo = f"vent en baisse (force {ref_now} maintenant, {b} dans 3 à 6 h)"
            elif b == ref_now:
                evo = f"vent stable, force {b}"
            else:
                evo = f"peu d'évolution du vent (force {min(ref_now, b)} à {max(ref_now, b)})"
            estimates.insert(0, "Évolution attendue : " + evo + ".")
        if tend is not None and tend <= -3.6 and b < 7:
            estimates.append(
                "La baisse rapide de pression n'apparaît pas dans la prévision reçue : surveiller le prochain "
                "bulletin, le vent pourrait dépasser la prévision."
            )
    elif tend is not None:
        estimates.insert(0, "Aucune prévision reçue pour la période : seule la tendance barométrique renseigne sur l'évolution.")

    n_src = len(set(sources))
    if n_src == 0:
        score, reasons = 0.0, [("aucune donnée reçue ni observée pour le secteur", 0)]
    elif n_src == 1:
        score = min(score, 58.0)
        reasons.append(("une seule source : fiabilité plafonnée", 0))
    score = int(max(0, min(100, round(score))))
    grade = "A" if score >= 80 else "B" if score >= 62 else "C" if score >= 42 else "D"
    return {
        "now": now,
        "window": (w0, w1),
        "zone": zone_label,
        "facts_now": facts_now,
        "facts_forecast": facts_fc,
        "estimates": estimates,
        "gales": gales,
        "level": level,
        "reliability": {"score": score, "grade": grade, "reasons": reasons, "sources": sorted(set(sources))},
    }


GRADE_WORDS = {
    "A": "élevée : plusieurs sources récentes et concordantes",
    "B": "bonne : sources récentes, quelques incertitudes",
    "C": "moyenne : peu de sources ou données anciennes, à confirmer",
    "D": "faible : données insuffisantes, ne pas s'y fier seul",
}
LEVEL_WORDS = {
    "VERT": "🟢 VERT — pas de vent fort attendu",
    "JAUNE": "🟡 JAUNE — vent ou mer sensibles pour les petites unités",
    "ORANGE": "🟠 ORANGE — vent fort, coup de vent possible",
    "ROUGE": "🔴 ROUGE — coup de vent ou tempête",
}


def nowcast_lines(nc, width=78):
    """Texte du bloc « Situation actuelle et prévision 3 à 6 h » pour les bulletins."""
    rel = nc["reliability"]
    w0, w1 = nc["window"]
    L = [
        f"SITUATION ACTUELLE ET PRÉVISION À 3-6 H — {nc['zone']}".rstrip(" —"),
        "-" * width,
        f"Situation à {nc['now']:%d/%m %H:%M} UTC (faits reçus ou observés)",
    ]
    L += [f"  • {x}" for x in nc["facts_now"]]
    if not nc["facts_now"]:
        L.append("  • aucune observation ni prévision en vigueur reçue pour le secteur")
    L += ["", f"Prévision de {w0:%H:%M} à {w1:%H:%M} UTC"]
    if nc["level"]:
        L.append(f"  Niveau d'attention : {LEVEL_WORDS.get(nc['level'], nc['level'])}")
    for g in nc["gales"]:
        L.append(f"  ⚠ {g}")
    L += [f"  • {x}" for x in nc["facts_forecast"]]
    if not nc["facts_forecast"]:
        L.append("  • aucune prévision reçue (texte ou GRIB) ne couvre cette période")
    if nc["estimates"]:
        L.append("  Estimation (déduite des données ci-dessus, pas une prévision officielle) :")
        L += [f"    – {x}" for x in nc["estimates"]]
    L += [
        "",
        f"Indice de fiabilité : {rel['score']} % [{rel['grade']}] — {GRADE_WORDS[rel['grade']]}",
    ]
    # 2.11.0 — justification sur une ligne (elle en prenait sept)
    why = " ; ".join(f"{('+' + str(p)) if p > 0 else str(p)} {w}" if p else w for w, p in rel["reasons"])
    if why:
        L.append(f"  ({why})")
    return L
