"""Rédaction du bulletin documentaire à partir des cartes annotées et confirmées."""

from datetime import datetime, timedelta, timezone
from wefax_station.version import BRAND


def build_bulletin(cards, zone, observations, now=None):
    now = now or datetime.now(timezone.utc)
    lines = [
        BRAND,
        "BULLETIN DOCUMENTAIRE — " + now.strftime("%Y-%m-%d %H:%M UTC"),
        "Secteur opérateur : " + (zone or "non renseigné"),
        "",
        "1. SOURCES ET SITUATION FACTUELLE",
    ]
    verified = []
    for c in cards:
        a = c.get("annotations", {})
        if not a.get("confirmed") or a.get("zone", "").strip().casefold() != zone.strip().casefold():
            continue
        try:
            dt = datetime.fromisoformat(a["valid_utc"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if abs((now - dt).total_seconds()) > 48 * 3600:
            continue
        verified.append((dt, a, c))
    verified.sort(key=lambda item: item[0], reverse=True)
    for dt, a, c in verified[:8]:
        lines.append(
            f"- {a.get('type','Type non confirmé')} | validité {dt.strftime('%Y-%m-%d %H:%M UTC')} | {c.get('file','carte')}"
        )
        if a.get("facts"):
            lines.append("  Lecture confirmée par l'opérateur : " + a["facts"])
    if not verified:
        lines.append(
            "Aucune carte annotée, datée et confirmée pour ce secteur : situation locale non déterminée automatiquement."
        )
    lines += ["", "2. OBSERVATIONS OPÉRATEUR"]
    for name, value in observations.items():
        if value and value != "Non renseigné":
            lines.append(f"- {name} : {value}")
    if not any(value and value != "Non renseigné" for value in observations.values()):
        lines.append("Non renseignées.")
    lines += ["", "3. ÉVOLUTION CONDITIONNELLE"]
    for horizon in (3, 12, 24):
        statements = []
        for dt, a, c in verified:
            if a.get("h" + str(horizon)):
                try:
                    ref = datetime.fromisoformat(a.get("annotated_utc", "").replace("Z", "+00:00"))
                    if ref.tzinfo is None:
                        ref = ref.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if ref <= now and now < ref + timedelta(hours=horizon):
                    statements.append(
                        "Hypothèse opérateur (référence "
                        + ref.strftime("%d/%m %H:%M UTC")
                        + ", échéance "
                        + (ref + timedelta(hours=horizon)).strftime("%d/%m %H:%M UTC")
                        + ") : "
                        + a["h" + str(horizon)]
                    )
                    break
        for dt, a, c in verified:
            age = (now - dt).total_seconds() / 3600
            if not (0 <= age <= 6 and a.get("type") == "Analyse de surface" and a.get("toward_zone")):
                continue
            try:
                distance = float(a.get("distance_km", ""))
                speed = float(a.get("speed_kmh", ""))
            except (TypeError, ValueError):
                continue
            if distance <= 0 or speed <= 0 or speed > 200:
                continue
            eta = distance / speed - age
            if eta <= 0:
                statements.append(
                    "Projection frontale périmée : passage théorique déjà atteint ; actualiser les observations."
                )
            elif eta <= horizon:
                statements.append(
                    f"Si trajectoire et vitesse restent constantes : passage possible du front avant H+{horizon}, dans environ {eta:.1f} h. Intensité des pluies et du vent non déduite."
                )
            else:
                statements.append(
                    f"À déplacement constant, front non attendu avant H+{horizon} (délai théorique {eta:.1f} h). Cela ne garantit pas un temps calme."
                )
            break
        lines.append(
            f"H+{horizon} : "
            + (
                " ".join(statements)
                if statements
                else "Non déterminable avec les données confirmées disponibles."
            )
        )
    lines += [
        "",
        "Confiance : non calibrée. Les projections ne constituent pas une vigilance officielle.",
        "Les heures des cartes sont distinctes des heures de réception. Les annotations et hypothèses doivent être relues.",
        "",
        "4. COMPLÉMENTS ET DÉCISIONS DE L'OPÉRATEUR",
        "",
    ]
    return "\n".join(lines)
