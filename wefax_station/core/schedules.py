"""Programmes de diffusion UTC (cartes WEFAX, bulletins texte) et calculs d'échéance."""

import re
from datetime import datetime, timezone

BROADCAST_SCHEDULES_UTC = {
    # 2.9.0 — programme DWD Hamburg/Pinneberg (DDH3 3855, DDK3 7880, DDK6 13882,5 kHz), repris du
    # « Worldwide Marine Radiofacsimile Broadcast Schedules » de la NOAA (information datée du 24/07/2024,
    # d'après le plan DWD 10/2020). L'ancienne table (jusqu'en 2.8.9) ne correspondait pas aux émissions :
    # le 18/11, la « FSXX48 de 18:30 » était en fait la prévision 48 h de 18:47, et la carte « vue vers
    # 19:00 » la prévision 84 h. Pas d'émission de 22:12 à 04:30. Vacations phonie (5905 / 6180 kHz) de
    # 05:55, 11:55, 15:55 et 19:55 (40 min) : pas de carte pendant ce temps. À confirmer par la carte
    # « programme d'émission » que le DWD diffuse lui-même à 14:25 et 14:45 UTC.
    # Codes : ASXX = analyse de surface (isobares, situation présente) ; FSXXnn = prévision de pression de
    # surface à nn h ; FUXX = altitude ; WWXX = vagues ; ICE, SST, TROP, PROG = autres produits.
    "DWD": [
        (4, 30, "ASXX", "Analyse de surface Atlantique Nord / Europe"),
        (5, 12, "FSXX36", "Prévision pression de surface H+36"),
        (5, 25, "ASXX", "Analyse pression de surface, déplacement des systèmes, temps significatif, glaces"),
        (6, 38, "TROP", "Tempêtes tropicales Atlantique Nord (en saison)"),
        (6, 51, "FUXX500", "Prévisions H+12/H+24 500 hPa et pression de surface"),
        (7, 4, "FUXX850", "Prévisions H+12/H+24 température 850 hPa (et humidité 700 hPa selon la NOAA)"),
        (7, 17, "FSXX36", "Prévision pression de surface H+36 (rediffusion de 05:12)"),
        (7, 30, "FSXX48", "Prévision pression de surface H+48"),
        (7, 43, "FSXX60", "Prévision pression de surface H+60"),
        (8, 4, "FSXX84", "Prévision pression de surface H+84"),
        (8, 17, "FSXX108", "Prévision pression de surface H+108"),
        (8, 30, "WWXX24", "Vagues (mer du vent + houle) et vent 10 m H+24"),
        (8, 42, "WWXX48", "Vagues et vent 10 m H+48"),
        (8, 54, "WWXX72", "Vagues et vent 10 m H+72"),
        (9, 6, "WWXX96", "Vagues et vent 10 m H+96"),
        (9, 30, "FUXX500", "Prévisions H+36/H+48 500 hPa et pression de surface"),
        (9, 45, "SST", "Température de surface de la mer du Nord"),
        (10, 7, "ICE", "Glaces Baltique occidentale (selon la situation)"),
        (10, 29, "WWXX48", "Prévision des vagues H+48 Atlantique Nord"),
        (10, 50, "ASXX", "Analyse de surface Atlantique Nord / Europe"),
        (11, 11, "FUXX850", "Prévisions H+36/H+48 850 hPa, humidité 700 hPa"),
        (11, 23, "FUXX500", "Prévisions H+60/H+72 500 hPa et pression de surface"),
        (11, 35, "FUXX850", "Prévisions H+60/H+72 850 hPa, humidité 700 hPa"),
        (12, 36, "ASXX", "Analyse de surface (rediffusion de 10:50)"),
        (12, 56, "FSXX36", "Prévision pression de surface H+36 (rediffusion de 05:12)"),
        (13, 8, "FSXX48", "Prévision pression de surface H+48 (rediffusion de 07:30)"),
        (13, 20, "FSXX60", "Prévision pression de surface H+60 (rediffusion de 07:43)"),
        (13, 32, "FSXX84", "Prévision pression de surface H+84 (rediffusion de 08:04)"),
        (13, 44, "FSXX108", "Prévision pression de surface H+108 (rediffusion de 08:17)"),
        (13, 56, "ASXX", "Analyse de surface (rediffusion de 10:50)"),
        (14, 25, "PROG", "Programme d'émission, partie 1"),
        (14, 45, "PROG", "Programme d'émission, partie 2"),
        (15, 8, "ICE", "Glaces Atlantique Nord-Ouest (service canadien / patrouille des glaces)"),
        (15, 20, "ICE", "Glaces Baltique (ou zone particulière)"),
        (15, 40, "ICE", "Glaces mer Arctique européenne (ou zone particulière)"),
        (16, 36, "ASXX", "Analyse de surface Atlantique Nord / Europe"),
        (18, 0, "ASXX", "Analyse pression de surface, déplacement des systèmes, temps significatif, glaces"),
        (18, 21, "TROP", "Tempêtes tropicales Atlantique Nord (en saison)"),
        (18, 34, "FSXX36", "Prévision pression de surface H+36"),
        (18, 47, "FSXX48", "Prévision pression de surface H+48"),
        (19, 0, "FSXX84", "Prévision pression de surface H+84"),
        (19, 13, "WWXX24", "Vagues et vent 10 m H+24"),
        (19, 26, "WWXX48", "Vagues et vent 10 m H+48"),
        (19, 39, "WWXX72", "Vagues et vent 10 m H+72"),
        (21, 0, "ICE", "Glaces Atlantique Nord-Ouest"),
        (21, 15, "ICE", "Glaces Baltique (ou zone particulière)"),
        (21, 36, "WWXX48", "Prévision des vagues H+48 Atlantique Nord"),
        (22, 0, "ASXX", "Analyse de surface Atlantique Nord / Europe"),
    ],
    # 2.9.4 — programme Northwood (GYA : 2618,5 kHz de 22:00 à 05:00, 4610 kHz 24 h/24, 8040 kHz 24 h/24,
    # 11086,5 kHz de 06:00 à 20:00) relu dans le document NOAA réel téléchargé par la station le 19/11/2026
    # (« JOMOC HF-Fax Schedule », information du 05/01/2022) : tableau en deux colonnes, produit puis heure ;
    # 102 cartes, créneaux vides du document non listés. Chaque produit porte son heure de référence. Une
    # analyse de même heure de référence que la précédente est marquée « rediffusion » : elle ne coupe qu'un
    # bulletin déjà reçu ; la première analyse 00Z, 06Z, 12Z ou 18Z est prioritaire.
    "GYA": [
        (0, 0, "ASUK", "Northwood — Analyse de surface (18Z) — rediffusion"),
        (0, 12, "FSUK24", "Northwood — Prévision de surface H+24 (18Z)"),
        (0, 24, "PRUK12", "Northwood — Précipitations et visibilité réduite H+12 (18Z)"),
        (0, 36, "PRUK24", "Northwood — Précipitations et visibilité réduite H+24 (18Z)"),
        (0, 48, "ASUK", "Northwood — Analyse de surface (18Z) — rediffusion"),
        (1, 0, "FSUK24", "Northwood — Prévision de surface H+24 (18Z)"),
        (1, 12, "WWUK48", "Northwood — Mer du vent et houle H+48 (18Z)"),
        (1, 24, "WWUK72", "Northwood — Mer du vent et houle H+72 (18Z)"),
        (1, 36, "FRONTS", "Northwood — Fronts océaniques"),
        (1, 48, "WWUK24", "Northwood — Mer du vent et houle H+24 (18Z)"),
        (2, 0, "ASUK", "Northwood — Analyse de surface (18Z) — rediffusion"),
        (2, 12, "SST", "Northwood — Température de surface de la mer (00Z)"),
        (2, 24, "FSUK24", "Northwood — Prévision de surface H+24 (18Z)"),
        (2, 36, "ASUK", "Northwood — Analyse de surface (00Z)"),
        (3, 0, "ASUK", "Northwood — Analyse de surface (00Z) — rediffusion"),
        (3, 24, "WIND24", "Northwood — Vents de surface H+24 (18Z)"),
        (3, 36, "ANPS24", "Northwood — Prévision « ANPS » H+24 (intitulé NOAA) (00Z)"),
        (3, 48, "ANPS72", "Northwood — Prévision « ANPS » H+72 (intitulé NOAA) (00Z)"),
        (4, 0, "ASUK", "Northwood — Analyse de surface (00Z) — rediffusion"),
        (4, 24, "WIND24", "Northwood — Vents de surface H+24 (18Z)"),
        (4, 36, "FSUK24", "Northwood — Prévision de surface H+24 (00Z)"),
        (4, 48, "WIND48", "Northwood — Vents de surface H+48 (18Z)"),
        (5, 0, "ASUK", "Northwood — Analyse de surface (00Z) — rediffusion"),
        (5, 12, "FSUK24", "Northwood — Prévision de surface H+24 (00Z)"),
        (5, 24, "FSUK48", "Northwood — Prévision de surface H+48 (00Z)"),
        (5, 48, "GALE", "Northwood — Avis de coup de vent (carte) (06Z)"),
        (6, 12, "ASUK", "Northwood — Analyse de surface (00Z) — rediffusion"),
        (6, 24, "FSUK24", "Northwood — Prévision de surface H+24 (00Z)"),
        (6, 36, "ASUK", "Northwood — Analyse de surface (00Z) — rediffusion"),
        (6, 48, "FSUK24", "Northwood — Prévision de surface H+24 (00Z)"),
        (7, 0, "ASUK", "Northwood — Analyse de surface (00Z) — rediffusion"),
        (7, 12, "FSUK24", "Northwood — Prévision de surface H+24 (00Z)"),
        (7, 24, "FSUK48", "Northwood — Prévision de surface H+48 (00Z)"),
        (7, 36, "FSUK72", "Northwood — Prévision de surface H+72 (00Z)"),
        (7, 48, "FSUK96", "Northwood — Prévision de surface H+96 (00Z)"),
        (8, 0, "FSUK120", "Northwood — Prévision de surface H+120 (00Z)"),
        (8, 12, "FSUK48", "Northwood — Prévision de surface H+48 (00Z)"),
        (8, 24, "PRUK12", "Northwood — Précipitations et visibilité réduite H+12 (00Z)"),
        (8, 36, "PRUK24", "Northwood — Précipitations et visibilité réduite H+24 (00Z)"),
        (8, 48, "FSUK24", "Northwood — Prévision de surface H+24 (00Z)"),
        (9, 0, "ASUK", "Northwood — Analyse de surface (06Z)"),
        (9, 24, "ANPS24", "Northwood — Prévision « ANPS » H+24 (intitulé NOAA) (00Z)"),
        (9, 36, "ANPS120", "Northwood — Prévision « ANPS » H+120 (intitulé NOAA) (00Z)"),
        (10, 0, "ASUK", "Northwood — Analyse de surface (06Z) — rediffusion"),
        (10, 12, "FSUK24", "Northwood — Prévision de surface H+24 (06Z)"),
        (10, 36, "ANPS24", "Northwood — Prévision « ANPS » H+24 (intitulé NOAA) (00Z)"),
        (11, 0, "ASUK", "Northwood — Analyse de surface (06Z) — rediffusion"),
        (11, 12, "FSUK24", "Northwood — Prévision de surface H+24 (06Z)"),
        (11, 24, "WWUK24", "Northwood — Mer du vent et houle H+24 (06Z)"),
        (11, 36, "FSUK24", "Northwood — Prévision de surface H+24 (06Z)"),
        (11, 48, "WWUK24", "Northwood — Mer du vent et houle H+24 (06Z)"),
        (12, 0, "ASUK", "Northwood — Analyse de surface (06Z) — rediffusion"),
        (12, 12, "FSUK24", "Northwood — Prévision de surface H+24 (06Z)"),
        (12, 24, "PRUK12", "Northwood — Précipitations et visibilité réduite H+12 (06Z)"),
        (12, 36, "PRUK24", "Northwood — Précipitations et visibilité réduite H+24 (06Z)"),
        (12, 48, "ASUK", "Northwood — Analyse de surface (06Z) — rediffusion"),
        (13, 0, "FSUK24", "Northwood — Prévision de surface H+24 (06Z)"),
        (13, 12, "WIND24", "Northwood — Vents de surface H+24 (06Z)"),
        (13, 24, "GALE", "Northwood — Avis de coup de vent (carte) (06Z)"),
        (13, 36, "FRONTS", "Northwood — Fronts océaniques"),
        (13, 48, "WWUK24", "Northwood — Mer du vent et houle H+24 (06Z)"),
        (14, 0, "SST", "Northwood — Température de surface de la mer (00Z)"),
        (14, 12, "ASUK", "Northwood — Analyse de surface (06Z) — rediffusion"),
        (14, 24, "FSUK24", "Northwood — Prévision de surface H+24 (06Z)"),
        (14, 36, "ASUK", "Northwood — Analyse de surface (12Z)"),
        (15, 0, "ASUK", "Northwood — Analyse de surface (12Z) — rediffusion"),
        (15, 12, "ANPS24", "Northwood — Prévision « ANPS » H+24 (intitulé NOAA) (00Z)"),
        (15, 24, "ANPS120", "Northwood — Prévision « ANPS » H+120 (intitulé NOAA) (00Z)"),
        (15, 36, "WWUK48", "Northwood — Mer du vent et houle H+48 (06Z)"),
        (16, 0, "ASUK", "Northwood — Analyse de surface (12Z) — rediffusion"),
        (16, 24, "WIND24", "Northwood — Vents de surface H+24 (06Z)"),
        (16, 36, "FSUK24", "Northwood — Prévision de surface H+24 (12Z)"),
        (16, 48, "WIND48", "Northwood — Vents de surface H+48 (06Z)"),
        (17, 0, "ASUK", "Northwood — Analyse de surface (12Z) — rediffusion"),
        (17, 12, "FSUK24", "Northwood — Prévision de surface H+24 (12Z)"),
        (17, 24, "FSUK48", "Northwood — Prévision de surface H+48 (12Z)"),
        (17, 48, "WWUK72", "Northwood — Mer du vent et houle H+72 (06Z)"),
        (18, 0, "ASUK", "Northwood — Analyse de surface (12Z) — rediffusion"),
        (18, 12, "FSUK24", "Northwood — Prévision de surface H+24 (12Z)"),
        (18, 24, "ASUK", "Northwood — Analyse de surface (12Z) — rediffusion"),
        (18, 36, "FSUK24", "Northwood — Prévision de surface H+24 (12Z)"),
        (18, 48, "ASUK", "Northwood — Analyse de surface (12Z) — rediffusion"),
        (19, 0, "FSUK24", "Northwood — Prévision de surface H+24 (12Z)"),
        (19, 24, "FSUK48", "Northwood — Prévision de surface H+48 (12Z)"),
        (19, 36, "FSUK72", "Northwood — Prévision de surface H+72 (12Z)"),
        (19, 48, "FSUK96", "Northwood — Prévision de surface H+96 (12Z)"),
        (20, 12, "FSUK120", "Northwood — Prévision de surface H+120 (12Z)"),
        (20, 24, "FSUK48", "Northwood — Prévision de surface H+48 (12Z)"),
        (20, 36, "PRUK12", "Northwood — Précipitations et visibilité réduite H+12 (12Z)"),
        (20, 48, "FSUK24", "Northwood — Prévision de surface H+24 (12Z)"),
        (21, 0, "ASUK", "Northwood — Analyse de surface (18Z)"),
        (21, 12, "PRUK24", "Northwood — Précipitations et visibilité réduite H+24 (12Z)"),
        (21, 24, "ANPS24", "Northwood — Prévision « ANPS » H+24 (intitulé NOAA) (00Z)"),
        (21, 36, "ANPS120", "Northwood — Prévision « ANPS » H+120 (intitulé NOAA) (00Z)"),
        (22, 0, "ASUK", "Northwood — Analyse de surface (18Z) — rediffusion"),
        (22, 12, "FSUK24", "Northwood — Prévision de surface H+24 (18Z)"),
        (22, 36, "ANPS24", "Northwood — Prévision « ANPS » H+24 (intitulé NOAA) (00Z)"),
        (23, 0, "ASUK", "Northwood — Analyse de surface (18Z) — rediffusion"),
        (23, 12, "FSUK24", "Northwood — Prévision de surface H+24 (18Z)"),
        (23, 24, "WWUK24", "Northwood — Mer du vent et houle H+24 (18Z)"),
        (23, 36, "FSUK24", "Northwood — Prévision de surface H+24 (18Z)"),
        (23, 48, "WWUK24", "Northwood — Mer du vent et houle H+24 (18Z)"),
    ],
    # 2.8.7 — créneau d'Athènes ; l'ordre exact des cartes n'est pas publié ici, le START de chaque carte
    # déclenche la réception.
    "ATH": [
        (8, 45, "ATH", "Athènes — cartes Méditerranée (créneau 08:45-10:45 UTC)"),
    ],
}

TEXT_BULLETIN_SCHEDULES_UTC = [
    # 2.8.6 — créneaux météo NAVTEX réels (Méditerranée occidentale) ; les anciens « H+50 / H+40 toutes
    # les 4 h » ne correspondaient à aucune émission météo.
    (6, 50, 10, "NAVTEX_INT", "NAVTEX R 0650", "NAVTEX La Maddalena (R, 518 kHz) — météo Ligure / Tyrrhénienne"),
    (7, 0, 10, "NAVTEX_FR", "NAVTEX S 0700", "NAVTEX La Garde (S, 490 kHz) — bulletin météo en français"),
    (7, 50, 10, "NAVTEX_INT", "NAVTEX X 0750", "NAVTEX Cabo la Nao (X, 518 kHz) — Lion, Provence, Ligure, Corse"),
    (9, 20, 10, "NAVTEX_FR", "NAVTEX I 0920", "NAVTEX La Maddalena (I, 490 kHz) — bulletin météo en italien"),
    (11, 40, 10, "NAVTEX_INT", "NAVTEX W 1140", "NAVTEX La Garde (W, 518 kHz) — prévisions météo"),
    (18, 50, 10, "NAVTEX_INT", "NAVTEX R 1850", "NAVTEX La Maddalena (R, 518 kHz) — météo Ligure / Tyrrhénienne"),
    (19, 0, 10, "NAVTEX_FR", "NAVTEX S 1900", "NAVTEX La Garde (S, 490 kHz) — bulletin météo en français"),
    (19, 50, 10, "NAVTEX_INT", "NAVTEX X 1950", "NAVTEX Cabo la Nao (X, 518 kHz) — Lion, Provence, Ligure, Corse"),
    (21, 20, 10, "NAVTEX_FR", "NAVTEX I 2120", "NAVTEX La Maddalena (I, 490 kHz) — bulletin météo en italien"),
    (23, 40, 10, "NAVTEX_INT", "NAVTEX W 2340", "NAVTEX La Garde (W, 518 kHz) — prévisions météo"),
    (
        0,
        35,
        18,
        "DWD_RTTY",
        "WQXX/FQXX 00Z",
        "DWD RTTY — Avis de Coup de Vent & Prévisions Mer du Nord / Atlantique",
    ),
    (2, 15, 18, "DWD_RTTY", "FQMM 02Z", "DWD RTTY — Prévision Maritime Méditerranée Occidentale & Orientale"),
    (3, 15, 18, "DWD_RTTY", "WQXX 03Z", "DWD RTTY — Avis de Tempête & Situation Synoptique Europe"),
    (
        6,
        25,
        18,
        "DWD_RTTY",
        "FQXX 06Z",
        "DWD RTTY — Grand Bulletin Maritime Atlantique / Baltique / Mer du Nord",
    ),
    (
        7,
        0,
        18,
        "DWD_RTTY",
        "FQMM 07Z",
        "DWD RTTY — Bulletin Météo Méditerranée (Golfe du Lion, Gênes, Corse)",
    ),
    (8, 35, 18, "DWD_RTTY", "SYNOP 08Z", "DWD RTTY — Observations Côtières & Bouées Europe"),
    (11, 15, 18, "DWD_RTTY", "WQXX 11Z", "DWD RTTY — Avis de Coup de Vent & Frontologie Europe (12Z)"),
    (12, 5, 18, "DWD_RTTY", "FQXX 12Z", "DWD RTTY — Prévision Maritime Europe & Atlantique NE (12Z)"),
    (13, 0, 18, "DWD_RTTY", "FQMM 13Z", "DWD RTTY — Prévision Maritime Méditerranée (Lion, Gênes, Baléares)"),
    (14, 15, 18, "DWD_RTTY", "ICE/BALT 14Z", "DWD RTTY — Bulletin Glaces & Sécurité Navigation"),
    (15, 0, 18, "DWD_RTTY", "WQXX 15Z", "DWD RTTY — Avis de Tempête & Tendance Barométrique"),
    (16, 55, 18, "DWD_RTTY", "FQMM 17Z", "DWD RTTY — Bulletin du Soir Méditerranée Occidentale & Corse"),
    (17, 20, 18, "DWD_RTTY", "FQXX 17Z", "DWD RTTY — Prévisions Côtières & Hauturières Europe"),
    (19, 40, 18, "DWD_RTTY", "WQXX 19Z", "DWD RTTY — Avis de Coup de Vent Nocturne & Situation 18Z"),
    (21, 20, 18, "DWD_RTTY", "FQXX 21Z", "DWD RTTY — Synthèse Synoptique Nocturne Atlantique & Europe"),
    (23, 10, 18, "DWD_RTTY", "FQMM 23Z", "DWD RTTY — Bulletin de Nuit Méditerranée & Atlantique"),
]

WEFAX_STAGES = [
    ("PORTEUSE", "1. PORTEUSE"),
    ("PHASE", "2. PHASE"),
    ("TEST_BLANC", "3. TEST BLANC"),
    ("TEST_NOIR", "4. TEST NOIR"),
    ("SYNCHRO", "5. SYNCHRO"),
    ("START", "6. START (300Hz)"),
    ("STOP", "7. STOP (450Hz)"),
    ("FIN", "8. FIN & SAVE"),
]




def schedule_pair(slots, now):
    if not slots:
        return None, None
    events = sorted((int(h) * 60 + int(m), str(code), str(desc)) for h, m, code, desc in slots)
    minute = now.hour * 60 + now.minute
    current = next((e for e in reversed(events) if e[0] <= minute), events[-1])
    following = next((e for e in events if e[0] > minute), events[0])
    return current, following


def next_schedule25(slots, now):
    if not slots:
        return None
    if any(not (0 <= int(h) <= 23 and 0 <= int(m) <= 59) for h, m, _, _ in slots):
        raise ValueError("Horaire UTC invalide")
    events = sorted((int(h) * 60 + int(m), str(code), str(desc)) for h, m, code, desc in slots)
    if any(not 0 <= minute < 1440 for minute, _, _ in events):
        raise ValueError("Horaire UTC invalide")
    seconds = now.hour * 3600 + now.minute * 60 + now.second
    event = next((e for e in events if e[0] * 60 > seconds), events[0])
    delay = (event[0] * 60 - seconds) % 86400
    return event, delay


# ----------------------------------------------------------------------------- 2.9.0 : révision et priorité
# Révision des programmes intégrés. Un programme enregistré sur disque (configuration, profil opérateur)
# avec une autre révision est REMPLACÉ par le programme intégré pour ces familles : sinon l'ancienne table
# DWD, recopiée dans les fichiers locaux depuis des versions, aurait continué à être utilisée.
SCHEDULE_REV = "2.9.4-DWD-NOAA-20240724-GYA-NOAA-20220105-REF"
# 2.9.2 — Northwood ajouté : l'ancienne table GYA (12 cartes non sourcées) est elle aussi remplacée.
REVISED_FAMILIES = ("DWD", "GYA")

# 2.9.1 — famille WEFAX de référence : la seule dont le programme intégré est vérifié (DWD, d'après la NOAA).
# Le 18/11 au soir, après un scan sans aucune carte en cours (trou du programme DWD 19:51-21:00), le poste
# est parti sur Northwood à cause d'une simple porteuse à 1900 Hz et n'est plus jamais revenu au DWD :
# cartes DWD de 21:00, 21:15 et 21:36 manquées alors que DDK3 était entendu sur le spectre.
PREFERRED_WEFAX_FAMILY = "DWD"

# Priorité des cartes face à un bulletin RTTY en cours (règle validée par F4NMK le 18/11/2026) :
# * ANALYSE : situation présente avec isobares (analyse de surface) → peut interrompre une prévision RTTY ;
# * PRIORITAIRE : prévision de pression de surface à courte échéance (≤ 48 h) et rediffusions d'analyse →
#   n'interrompt qu'une prévision déjà reçue dans les 12 dernières heures ;
# * None : autres cartes (altitude, vagues, glaces…) → n'interrompent jamais un bulletin.
# Un AVIS (coup de vent, tempête) n'est jamais interrompu.
PRIORITY_ANALYSE = "ANALYSE"
PRIORITY_HIGH = "PRIORITAIRE"


def chart_priority(code: str, label: str = ""):
    code = str(code or "").upper()
    rep = "rediffusion" in str(label or "").lower()
    if code.startswith("AS"):
        # 2.9.2 / 2.9.4 — Northwood diffuse une analyse presque toutes les heures : seule la première analyse
        # d'une heure de référence est prioritaire ; les suivantes sont marquées « rediffusion ». Sans heure de
        # référence (table d'un programme accepté), prudence : traitée comme une rediffusion.
        if code.startswith("ASUK") and not re.search(r"\(\d\dZ\)", str(label or "")):
            return PRIORITY_HIGH
        return PRIORITY_HIGH if rep else PRIORITY_ANALYSE
    if code.startswith("FS"):
        digits = "".join(ch for ch in code if ch.isdigit())
        if digits and int(digits) <= 48:
            return PRIORITY_HIGH
    if code == "GALE":  # 2.9.2 — carte d'avis de coup de vent (Northwood) : même rang qu'une prévision courte
        return PRIORITY_HIGH
    return None


def chart_short_label(code: str, desc: str = "") -> str:
    """Libellé court d'une carte pour la ligne « Ensuite : » du bandeau."""
    code = str(code or "").upper()
    digits = "".join(ch for ch in code if ch.isdigit())
    rep = " (rediff.)" if "rediffusion" in str(desc).lower() else ""
    if code.startswith("AS"):
        return "carte analyse de surface" + rep
    if code.startswith("FS") and digits:
        return f"carte prévision surface H+{digits}" + rep
    if code.startswith("WW") and digits:
        return f"carte vagues H+{digits}"
    if code.startswith("FU"):
        return "carte altitude" + (f" {digits} hPa" if digits else "")
    if code.startswith("PR") and digits:
        return f"carte précipitations H+{digits}"
    if code.startswith("WIND") and digits:
        return f"carte vents H+{digits}"
    short = {"ICE": "carte des glaces", "SST": "carte température de la mer", "TROP": "carte tempêtes tropicales",
             "PROG": "programme d'émission (carte)", "GALE": "carte avis de coup de vent",
             "FRONTS": "carte fronts océaniques", "CARTE": "carte (programme officiel)"}
    if code in short:
        return short[code]
    d = str(desc or code).split(" — ")[-1].split(" (")[0]
    return "carte " + d[:40]


# 2.9.2 — programmes acceptés par l'opérateur après comparaison avec un document officiel
# (hybrid/official_sources) : ils priment sur les copies locales et restent utilisés hors ligne.
_ACCEPTED_OVERRIDES = {}


def set_accepted_overrides(overrides: dict):
    _ACCEPTED_OVERRIDES.clear()
    for fam, slots in (overrides or {}).items():
        _ACCEPTED_OVERRIDES[str(fam)] = [tuple(x) for x in slots]


def accepted_overrides() -> dict:
    return {k: list(v) for k, v in _ACCEPTED_OVERRIDES.items()}


def merge_saved_schedules(saved: dict, saved_rev=None) -> dict:
    """Programmes enregistrés + intégrés : familles révisées remplacées si la révision diffère ;
    un programme accepté par l'opérateur (source officielle) l'emporte pour sa famille."""
    out = {k: list(v) for k, v in BROADCAST_SCHEDULES_UTC.items()}
    for fam, slots in (saved or {}).items():
        if fam in REVISED_FAMILIES and saved_rev != SCHEDULE_REV:
            continue
        if isinstance(slots, list) and slots:
            out[fam] = [tuple(x) for x in slots]
    for fam, slots in _ACCEPTED_OVERRIDES.items():
        out[fam] = list(slots)
    return out


def upcoming_charts(slots, now, horizon_min=240, n=3):
    """Prochaines cartes (début ≥ maintenant) : [(datetime, code, libellé)]."""
    from datetime import timedelta

    now = now.astimezone(timezone.utc)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for d in (0, 1):
        for h, m, code, desc in slots or []:
            t = day0 + timedelta(days=d, hours=int(h), minutes=int(m))
            if now <= t <= now + timedelta(minutes=horizon_min):
                out.append((t, str(code), str(desc)))
    out.sort()
    return out[:n]


def chart_slots_around(slots, now, before_s=60, after_s=90):
    """Cartes dont le début est dans [now - after_s, now + before_s] : [(datetime, code, libellé)]."""
    from datetime import timedelta

    now = now.astimezone(timezone.utc)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for d in (-1, 0, 1):
        for h, m, code, desc in slots or []:
            t = day0 + timedelta(days=d, hours=int(h), minutes=int(m))
            if now - timedelta(seconds=after_s) <= t <= now + timedelta(seconds=before_s):
                out.append((t, str(code), str(desc)))
    out.sort()
    return out


# 2.8.7 — fenêtre d'écoute d'Athènes (minutes UTC)
ATHENS_WINDOW_MIN = (8 * 60 + 43, 10 * 60 + 45)


def programme_of_chart(family, start_utc, tol_s=240):
    """2.10.0 — (code, libellé) de la carte du programme qui commence à start_utc (± 4 min), ou None.

    Sert à nommer une carte archivée (« analyse de surface », « vagues H+24 »…) dans ses métadonnées :
    le bulletin et la prévision à 3-6 h savent ainsi quelle carte d'analyse est la plus récente."""
    if not family or start_utc is None:
        return None
    slots = BROADCAST_SCHEDULES_UTC.get(family) or ()
    near = chart_slots_around(slots, start_utc, before_s=tol_s, after_s=tol_s)
    if not near:
        return None
    t, code, desc = min(near, key=lambda x: abs((x[0] - start_utc).total_seconds()))
    return code, desc
