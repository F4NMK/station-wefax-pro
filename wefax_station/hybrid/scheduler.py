"""Ordonnancement WEFAX / RTTY / NAVTEX et table de propagation.

Constats terrain (15/11/2026) :
* le DWD émet des cartes WEFAX presque en continu (une carte toutes les 12 min environ, 1 à 2 min de
  pause entre deux cartes) : on ne peut pas « attendre un trou » de 10 min pour faire du RTTY ;
* le RTTY DWD tourne 24 h/24 sur deux programmes (P1 surtout en anglais : DDK2 4583, DDH7 7646,
  DDK9 10100,8 kHz ; P2 surtout en allemand : DDH47 147,3, DDH9 11039, DDH8 14467,3 kHz) ; entre deux
  bulletins, l'émetteur boucle sur « RYRY… CQ CQ CQ DE … FREQUENCIES » ;
* après la fin d'un bulletin (NNNN), l'application restait 8 min sur la boucle de service.

Règles retenues (mode HYBRIDE) :
1. une carte en cours de tracé n'est jamais interrompue ;
2. un bulletin RTTY « d'intérêt » (catégories choisies dans Réglages) est pris à son heure si aucune
   carte n'est en cours, sinon juste après le STOP de la carte ;
3. le bulletin se termine sur NNNN, sur 30 s de boucle de service, sur 60 s sans signal RTTY valide ou
   à la fin de son créneau : il est archivé sans la boucle de service et l'on revient aux cartes ;
4. la table de propagation (qualité mesurée par fréquence, avec son heure) est tenue à jour par les
   scans, par la réception elle-même, et par une VEILLE légère : au plus toutes les 30 min le jour
   (45 min la nuit), uniquement dans le temps mort qui suit un STOP, quelques fréquences périmées
   mesurées 2 s chacune. On sollicite donc peu la radio (≤ 8 changements de fréquence par heure) ;
5. au moment de changer de mode, la meilleure fréquence de la table est utilisée directement si sa
   mesure a moins de 30 min ; sinon on mesure d'abord les fréquences du programme.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ----------------------------------------------------------------------------- programmes RTTY DWD
# Source : plan d'émission RTTY du DWD (programmes 1 et 2, 24 h/24). Horaires UTC de début.
# Catégories : AVIS (avertissements), MED (Méditerranée), ATL (Atlantique / Europe de l'Ouest),
# NORD (mer du Nord, Baltique, côtes allemandes), PREV5 (prévisions 5 jours), OBS (observations),
# SERVICE (informations de service : jamais recherchées).
_P1 = """0000 AVIS Avis de coup de vent / tempête
0005 NORD Bulletin mer du Nord / Baltique
0020 NORD Bulletin côtes allemandes
0030 SERVICE Note d'utilisation des données
0035 OBS Observations SYNOP
0200 OBS Observations de navires
0300 AVIS Avis par zones maritimes
0305 NORD Bulletin mer du Nord / Baltique
0320 NORD Bulletin côtes allemandes
0330 PREV5 Prévision 5 jours Baltique
0355 PREV5 Prévision 5 jours mer du Nord
0415 MED Prévision 5 jours Méditerranée
0440 OBS Observations de navires
0515 AVIS Avis aux navigateurs
0535 NORD Bulletin mer du Nord / Baltique
0550 NORD Bulletin côtes allemandes
0600 AVIS Avis par zones maritimes
0603 SERVICE Note d'utilisation des données
0604 ATL Prévision 5 jours Atlantique Est
0630 OBS Observations SYNOP
0735 OBS Observations de navires
0815 OBS Observations des bouées
0835 NORD Bulletin mer du Nord / Baltique
0850 NORD Bulletin côtes allemandes
0900 AVIS Avis par zones maritimes
0905 NORD Bulletin mer de Norvège / Baltique
0930 ATL Bulletin Atlantique Nord
0955 ATL Bulletin eaux d'Europe de l'Ouest
1015 MED Bulletin Méditerranée occidentale
1035 OBS Observations de navires
1110 SERVICE Informations générales / pannes
1115 MED Bulletin Méditerranée orientale
1135 NORD Bulletin mer du Nord / Baltique
1150 NORD Bulletin côtes allemandes
1200 AVIS Avis par zones maritimes
1205 SERVICE Note d'utilisation des données
1210 OBS Observations SYNOP
1335 OBS Observations de navires
1413 MED Prévision 5 jours Méditerranée
1435 NORD Bulletin mer du Nord / Baltique
1450 NORD Bulletin côtes allemandes
1500 AVIS Avis par zones maritimes
1505 PREV5 Prévision 5 jours Baltique
1530 PREV5 Prévision 5 jours mer du Nord
1550 MED Bulletin Méditerranée (texte)
1557 MED Bulletin Méditerranée orientale
1610 MED Prévision 5 jours Méditerranée
1635 OBS Observations de navires
1715 AVIS Avis aux navigateurs
1735 NORD Bulletin mer du Nord / Baltique
1750 NORD Bulletin côtes allemandes
1800 AVIS Avis par zones maritimes
1803 SERVICE Note d'utilisation des données
1804 ATL Prévision 5 jours Atlantique Est
1830 OBS Observations SYNOP
1935 OBS Observations de navires
2015 OBS Observations des bouées
2035 NORD Bulletin mer du Nord / Baltique
2050 NORD Bulletin côtes allemandes
2100 AVIS Avis par zones maritimes
2105 NORD Bulletin mer de Norvège / Baltique
2130 ATL Bulletin Atlantique Nord
2155 ATL Bulletin eaux d'Europe de l'Ouest
2215 MED Bulletin Méditerranée occidentale
2235 OBS Observations de navires
2315 MED Bulletin Méditerranée orientale"""

_P2 = """0000 AVIS Avis de tempête
0005 NORD Bulletin mer du Nord / Baltique
0020 NORD Bulletin côtes allemandes
0030 PREV5 Prévision 5 jours Baltique
0055 PREV5 Prévision 5 jours mer du Nord
0125 OBS Observations des stations mer du Nord / Baltique
0130 OBS Observations des stations Méditerranée
0135 MED Prévision 5 jours Méditerranée
0200 ATL Prévision 5 jours Atlantique Est
0235 SERVICE Avis de pannes
0300 AVIS Avis par zones maritimes
0305 NORD Bulletin mer du Nord / Baltique
0320 NORD Bulletin côtes allemandes
0325 NORD Prévision 2 jours mer de Norvège / Baltique
0350 ATL Prévision 2 jours Atlantique Nord
0425 OBS Observations des stations mer du Nord / Baltique
0430 OBS Observations des stations Méditerranée
0435 ATL Prévision 2 jours eaux d'Europe de l'Ouest
0500 AVIS Avis par zones maritimes
0505 NORD Bulletin mer du Nord / Baltique
0520 NORD Bulletin côtes allemandes
0530 OBS Observations des stations mer du Nord / Baltique
0535 MED Prévision 5 jours Méditerranée
0600 AVIS Avis par zones maritimes
0605 NORD Bulletin mer du Nord / Baltique
0620 NORD Bulletin côtes allemandes
0630 NORD Prévision 2 jours mer de Norvège / Baltique
0700 ATL Prévision 2 jours Atlantique Nord
0725 OBS Observations des stations mer du Nord / Baltique
0730 OBS Observations des stations Méditerranée
0734 ATL Prévision 5 jours Atlantique Est
0755 OBS Observations de navires Atlantique Nord
0820 ATL Prévision 2 jours eaux d'Europe de l'Ouest
0840 MED Prévision 2 jours Méditerranée occidentale
0900 AVIS Avis par zones maritimes
0905 NORD Bulletin mer du Nord / Baltique
0920 NORD Bulletin côtes allemandes
0930 MED Prévision 2 jours Méditerranée orientale
0950 AVIS Avis aux navigateurs
1010 SERVICE Utilisation des données / pannes
1025 OBS Observations des stations mer du Nord / Baltique
1030 OBS Observations des stations Méditerranée
1035 PREV5 Prévision 5 jours Baltique
1100 PREV5 Prévision 5 jours mer du Nord
1120 MED Prévision 5 jours Méditerranée
1145 SERVICE Programme navires de recherche
1200 AVIS Avis par zones maritimes
1205 NORD Bulletin mer du Nord / Baltique
1220 NORD Bulletin côtes allemandes
1230 NORD Prévision mer de Norvège (rediffusion)
1300 ATL Prévision Atlantique Nord (rediffusion)
1325 OBS Observations des stations mer du Nord / Baltique
1330 OBS Observations des stations Méditerranée
1335 OBS Observations de navires Atlantique Nord
1420 ATL Eaux d'Europe de l'Ouest (rediffusion)
1440 MED Méditerranée occidentale (rediffusion)
1500 AVIS Avis par zones maritimes
1505 NORD Bulletin mer du Nord / Baltique
1520 NORD Bulletin côtes allemandes
1530 MED Méditerranée orientale (rediffusion)
1545 PREV5 Prévision 5 jours Baltique (rediffusion)
1610 MED Bulletin Méditerranée (texte)
1625 OBS Observations des stations mer du Nord / Baltique
1630 OBS Observations des stations Méditerranée
1635 MED Méditerranée (rediffusion / spécial)
1715 AVIS Avis aux navigateurs
1735 MED Prévision 5 jours Méditerranée (rediffusion)
1800 AVIS Avis par zones maritimes
1805 NORD Bulletin mer du Nord / Baltique
1820 NORD Bulletin côtes allemandes
1830 NORD Prévision mer de Norvège / Baltique
1900 ATL Prévision Atlantique Nord
1925 OBS Observations des stations mer du Nord / Baltique
1930 OBS Observations des stations Méditerranée
1934 ATL Prévision 5 jours Atlantique Est
1955 OBS Observations de navires
2020 ATL Prévision eaux d'Europe de l'Ouest
2040 MED Prévision Méditerranée occidentale
2100 AVIS Avis par zones maritimes
2105 NORD Bulletin mer du Nord / Baltique
2120 NORD Bulletin côtes allemandes
2130 MED Prévision Méditerranée orientale
2155 PREV5 Prévision 5 jours Baltique
2225 OBS Observations des stations mer du Nord / Baltique
2230 OBS Observations des stations Méditerranée
2235 PREV5 Prévision 5 jours mer du Nord
2305 MED Prévision 5 jours Méditerranée"""

CATEGORIES = {
    "AVIS": "Avis de coup de vent, tempête, avis aux navigateurs",
    "MED": "Méditerranée",
    "ATL": "Atlantique / Europe de l'Ouest",
    "NORD": "Mer du Nord, Baltique, côtes allemandes",
    "PREV5": "Prévisions à 5 jours (Baltique, mer du Nord)",
    "OBS": "Observations (SYNOP, navires, bouées, stations)",
    "NAVTEX": "NAVTEX Méditerranée ouest (La Maddalena, Cabo la Nao ; La Garde si réactivée) : bulletins météo",
}
DEFAULT_INTEREST = ("AVIS", "MED", "NAVTEX", "ATL")
DEFAULT_PROGRAMS = (1,)  # anglais : la traduction hors ligne est la plus fiable
PROGRAM_STATIONS = {1: ("DDK2", "DDH7", "DDK9"), 2: ("DDH47", "DDH9", "DDH8")}
PROGRAM_LABEL = {
    1: "Programme 1 (anglais)",
    2: "Programme 2 (allemand)",
    "NAVTEX-INT": "NAVTEX 518 kHz",
    "NAVTEX-FR": "NAVTEX 490 kHz",
}
# NAVTEX, Méditerranée occidentale (créneaux météo de 10 min, horaires UTC). Une seule fréquence par
# service : 518 kHz (international, anglais) et 490 kHz (national). 2.8.6 — ajout de La Maddalena (R/I)
# et de Cabo la Nao (X/M), qui couvrent aussi Provence, Ligure, Lion et Corse : un émetteur muet (La Garde
# était annoncé « temporairement suspendu » par l'OHI en 2023-2024) ne laisse plus la station sans NAVTEX.
NAVTEX_WEATHER = [
    (6 * 60 + 50, "NAVTEX-INT", "NAVTEX", "NAVTEX La Maddalena (R) : météo mer Ligure / Tyrrhénienne (EN)"),
    (18 * 60 + 50, "NAVTEX-INT", "NAVTEX", "NAVTEX La Maddalena (R) : météo mer Ligure / Tyrrhénienne (EN)"),
    (7 * 60 + 50, "NAVTEX-INT", "NAVTEX", "NAVTEX Cabo la Nao (X) : météo Lion, Provence, Ligure, Corse (EN)"),
    (19 * 60 + 50, "NAVTEX-INT", "NAVTEX", "NAVTEX Cabo la Nao (X) : météo Lion, Provence, Ligure, Corse (EN)"),
    (11 * 60 + 40, "NAVTEX-INT", "NAVTEX", "NAVTEX La Garde (W) : prévisions météo (EN)"),
    (23 * 60 + 40, "NAVTEX-INT", "NAVTEX", "NAVTEX La Garde (W) : prévisions météo (EN)"),
    (7 * 60, "NAVTEX-FR", "NAVTEX", "NAVTEX La Garde (S) : bulletin météo (FR)"),
    (19 * 60, "NAVTEX-FR", "NAVTEX", "NAVTEX La Garde (S) : bulletin météo (FR)"),
    (9 * 60 + 20, "NAVTEX-FR", "NAVTEX", "NAVTEX La Maddalena (I) : bulletin météo (IT)"),
    (21 * 60 + 20, "NAVTEX-FR", "NAVTEX", "NAVTEX La Maddalena (I) : bulletin météo (IT)"),
]
NAVTEX_SLOT_MIN = 10


def _parse(block, program):
    out = []
    for line in block.strip().splitlines():
        hhmm, cat, label = line[:4], line[5:].split(" ", 1)[0], line[5:].split(" ", 1)[1]
        out.append((int(hhmm[:2]) * 60 + int(hhmm[2:]), program, cat, label))
    return out


DWD_RTTY_PROGRAMME = sorted(_parse(_P1, 1) + _parse(_P2, 2))


@dataclass
class RttyItem:
    start: datetime
    end: datetime
    program: object  # 1 / 2 (programmes RTTY DWD) ou identifiant NAVTEX
    category: str
    label: str

    @property
    def key(self):
        return f"P{self.program}-{self.start:%Y%m%d%H%M}"

    @property
    def is_navtex(self):
        return str(self.program).startswith("NAVTEX")

    def describe(self):
        return f"{self.start:%H:%M} UTC · {self.label} ({PROGRAM_LABEL.get(self.program, self.program)})"


def rtty_items(now, horizon_min=180, programs=(1, 2), categories=DEFAULT_INTEREST, lookback_min=30):
    """Bulletins d'intérêt entre now-lookback et now+horizon, durée = jusqu'au bulletin suivant du programme."""
    now = now.astimezone(timezone.utc)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    items = []
    for d in (-1, 0, 1):
        base = day0 + timedelta(days=d)
        for prog in (1, 2):
            entries = [e for e in DWD_RTTY_PROGRAMME if e[1] == prog]
            for i, (minute, p, cat, label) in enumerate(entries):
                nxt = entries[i + 1][0] if i + 1 < len(entries) else entries[0][0] + 1440
                start = base + timedelta(minutes=minute)
                end = base + timedelta(minutes=min(nxt, minute + 25))
                if p not in programs or cat not in categories:
                    continue
                if end < now - timedelta(minutes=lookback_min) or start > now + timedelta(
                    minutes=horizon_min
                ):
                    continue
                items.append(RttyItem(start, end, p, cat, label))
        if "NAVTEX" in categories:
            for minute, sid, cat, label in NAVTEX_WEATHER:
                start = base + timedelta(minutes=minute)
                end = start + timedelta(minutes=NAVTEX_SLOT_MIN)
                if end < now - timedelta(minutes=lookback_min) or start > now + timedelta(
                    minutes=horizon_min
                ):
                    continue
                items.append(RttyItem(start, end, sid, cat, label))
    items.sort(key=lambda it: (it.start, str(it.program)))
    return items


# ----------------------------------------------------------------------------- table de propagation
@dataclass
class PropEntry:
    station: str
    freq_khz: float
    mode: str  # WEFAX / RTTY / NAVTEX
    quality: int = 0  # 0..100
    active: bool = False  # émission reconnue (structure WEFAX ou FSK valide)
    detail: str = ""
    measured: float = 0.0  # epoch s
    source: str = ""  # scan / veille / réception

    def age_s(self, now=None):
        return (now or time.time()) - self.measured if self.measured else float("inf")


@dataclass
class PropagationTable:
    path: Path = None
    entries: dict = field(default_factory=dict)

    def load(self):
        if self.path and Path(self.path).is_file():
            try:
                data = json.loads(Path(self.path).read_text(encoding="utf-8"))
                for k, v in data.get("entries", {}).items():
                    self.entries[k] = PropEntry(**v)
            except (OSError, ValueError, TypeError):
                self.entries = {}
        return self

    def save(self):
        if not self.path:
            return
        try:
            from wefax_station.storage.atomic import atomic_json

            atomic_json(
                self.path,
                {"schema": "propagation-1", "entries": {k: vars(v) for k, v in self.entries.items()}},
            )
        except Exception:
            pass

    def update(self, station, freq_khz, mode, quality, active, detail="", source="scan", when=None):
        e = PropEntry(
            station,
            float(freq_khz),
            mode,
            int(max(0, min(100, quality))),
            bool(active),
            detail,
            when or time.time(),
            source,
        )
        self.entries[station] = e
        return e

    def get(self, station):
        return self.entries.get(station)

    def stale(self, stations, max_age_s, now=None):
        return [s for s in stations if (self.get(s) is None or self.get(s).age_s(now) > max_age_s)]

    def best(self, stations, max_age_s=1800, now=None):
        """Meilleure station mesurée récemment (émission reconnue d'abord), ou None."""
        cands = [
            self.get(s) for s in stations if self.get(s) is not None and self.get(s).age_s(now) <= max_age_s
        ]
        if not cands:
            return None
        return max(cands, key=lambda e: (e.active, e.quality, -e.age_s(now))).station


# ----------------------------------------------------------------------------- décisions
@dataclass
class ScheduleState:
    now: datetime
    pipeline: str  # WEFAX / RTTY
    chart_drawing: bool
    seconds_since_chart: float  # depuis la dernière ligne de carte tracée (inf si jamais)
    rtty_text_active: bool  # texte météo reçu dans les 30 dernières secondes
    rtty_service_s: float  # durée de la boucle de service en cours (RY / CQ)
    rtty_no_signal_s: float  # durée sans FSK valide
    rtty_end_marker: bool  # NNNN reçu depuis le début du bulletin
    current_item: RttyItem = None  # bulletin en cours de réception
    done_keys: tuple = ()
    is_day: bool = True
    manual_text_s: object = None  # 2.8.6 : secondes depuis un accord MANUEL sur une fréquence texte
    wefax_family: str = ""  # 2.8.7 : famille de la station WEFAX écoutée (DWD / GYA / ATH)
    athens_enabled: bool = False
    rtty_end_age_s: object = None  # 2.8.9 : secondes depuis la fin (NNNN) du bulletin d'intérêt, None sinon
    # 2.9.0 : programme des cartes de la famille WEFAX de retour [(h, m, code, libellé)] et bulletins
    # (libellés) reçus en entier dans les 12 dernières heures
    chart_slots: tuple = ()
    received_recent: tuple = ()
    # 2.9.1 : famille de référence (DWD) et son programme
    preferred_family: str = ""
    pref_slots: tuple = ()
    # 2.9.3 : Athènes non identifiée au dernier contrôle (pas de structure WEFAX) : on ne s'y attarde pas
    athens_unconfirmed: bool = False
    # 2.9.5 : la carte en cours a été prise depuis son START (ou son phasage)
    chart_from_start: bool = True
    # 2.11.0 — part des lignes fiables de la carte en cours (0-100), None si moins de 2 min tracées
    chart_reliable_pct: object = None


@dataclass
class Decision:
    action: str  # STAY / GO_RTTY / GO_WEFAX / VEILLE / WEFAX_RECHECK
    reason: str = ""
    item: RttyItem = None


class ReceptionScheduler:
    # 2.11.0 — RÈGLE DE BASE F4NMK (20/11) : une carte en cours n'est jamais coupée, SAUF si sa fiabilité est
    # faible : moins de LOW_RELIABILITY_PCT % de lignes fiables mesurées sur au moins 2 min de tracé.
    LOW_RELIABILITY_PCT = 40
    VEILLE_DAY_S = 1800
    VEILLE_NIGHT_S = 2700
    WEFAX_SILENCE_RECHECK_S = 480  # 8 min sans carte : on vérifie les autres fréquences WEFAX

    def __init__(self, programs=DEFAULT_PROGRAMS, categories=DEFAULT_INTEREST, rtty_enabled=True):
        self.programs = tuple(programs)
        self.categories = tuple(categories)
        self.rtty_enabled = rtty_enabled
        self.last_veille = 0.0
        self.last_wefax_recheck = 0.0
        self.recheck_streak = 0
        # 2.9.2 — filtre des stations texte (désactivées ou en sommeil) : callable(item) -> bool
        self.station_filter = None

    # 2.11.0 — contrôles espacés quand ils ne trouvent rien : 8 puis 16 min.
    # 2.11.3 — RECHECK_MAX_STEPS réduit de 2 à 1 : avec 2 étapes le backoff atteignait 32 min, bloquant
    # toutes les cartes DWD (08:42, 08:54, 09:00, 09:06) quand le streak montait à 2 après deux scans sans
    # résultat. 16 min max est un compromis raisonnable : on évite les allers-retours incessants tout en
    # gardant une réactivité correcte sur les fréquences DWD.
    RECHECK_MAX_STEPS = 1

    def recheck_interval(self):
        return self.WEFAX_SILENCE_RECHECK_S * (2 ** min(int(getattr(self, "recheck_streak", 0)), self.RECHECK_MAX_STEPS))

    def _allowed(self, it, now=None):
        f = self.station_filter
        if f is None:
            return True
        try:
            return bool(f(it))
        except Exception:
            return True

    def due_item(self, st: ScheduleState, exclude=()):
        if not self.rtty_enabled:
            return None
        due = []
        for it in rtty_items(st.now, horizon_min=2, programs=self.programs, categories=self.categories):
            if it.key in st.done_keys or it.key in exclude:
                continue
            if not self._allowed(it):
                continue
            remaining = (it.end - st.now).total_seconds()
            if it.start - timedelta(seconds=60) <= st.now and remaining >= 120:
                due.append(it)
        if not due:
            return None

        # priorité : ordre des catégories choisi par l'opérateur, puis ordre des programmes
        def rank(it):
            prog = self.programs.index(it.program) if it.program in self.programs else 0
            return (self.categories.index(it.category), prog, it.start)

        return min(due, key=rank)

    def next_items(self, now, n=4):
        if not self.rtty_enabled:
            return []
        return [
            it
            for it in rtty_items(
                now, horizon_min=240, programs=self.programs, categories=self.categories, lookback_min=0
            )
            if it.start >= now and self._allowed(it)
        ][:n]

    def veille_due(self, st: ScheduleState, mono_now=None):
        mono_now = mono_now if mono_now is not None else time.monotonic()
        period = self.VEILLE_DAY_S if st.is_day else self.VEILLE_NIGHT_S
        return (mono_now - self.last_veille) >= period

    END_GRACE_S = 12.0
    OVERRUN_MAX_MIN = 6
    # 2.9.0 — carte prioritaire : on rejoint les cartes 45 s avant l'heure (START 300 Hz puis phasage) ;
    # jusqu'à 60 s après l'heure on peut encore la prendre dès le début du tracé
    PRIORITY_LEAD_S = 45
    PRIORITY_LATE_S = 60
    LATE_BULLETIN_S = 300  # 2.9.7 : bulletin commencé depuis plus de 5 min = bulletin déjà bien entamé
    ANALYSE_GUARD_S = 180  # pas de départ en RTTY dans les 3 min qui précèdent une analyse de surface
    RECHECK_AFTER_START_S = 300  # 2.11.0 : 5 min (le 23/11, contrôle à 16:38:01, 2 min après l'analyse de 16:36 : carte prise sans son haut) ; 2.9.1 : ni contrôle des fréquences dans les 2 min qui suivent l'heure d'une carte
    FAMILY_LEAD_S = 120  # 2.9.1 : retour sur la famille de référence 2 min avant l'heure de sa carte
    FAMILY_LATE_S = 60

    def priority_chart(self, st: ScheduleState, before_s=None, after_s=None):
        """Carte prioritaire commençant dans la fenêtre [now - after_s, now + before_s], ou None.
        Renvoie (datetime, code, libellé, priorité)."""
        from wefax_station.core.schedules import chart_priority, chart_slots_around

        before_s = self.PRIORITY_LEAD_S if before_s is None else before_s
        after_s = self.PRIORITY_LATE_S if after_s is None else after_s
        for t, code, desc in chart_slots_around(st.chart_slots, st.now, before_s=before_s, after_s=after_s):
            pr = chart_priority(code, desc)
            if pr:
                return t, code, desc, pr
        return None

    def chart_interrupt(self, st: ScheduleState):
        """Règle F4NMK (18/11/2026) — une carte prioritaire peut-elle interrompre le bulletin RTTY en cours ?
        * analyse de surface (situation présente, isobares) : oui, y compris un avis ou un créneau NAVTEX
          (décision F4NMK du 19/11/2026 : « carte analyse surface prioritaire ») ;
        * avis (coup de vent, tempête) : par aucune autre carte ;
        * prévision de surface ≤ 48 h, rediffusion d'analyse : seulement si cette prévision RTTY a déjà été
          reçue en entier dans les 12 dernières heures ;
        * autres cartes, NAVTEX, écoute choisie par l'opérateur : jamais.
        Renvoie une Decision, ou None si la règle ne s'applique pas."""
        from wefax_station.core.schedules import PRIORITY_ANALYSE, chart_short_label

        it = st.current_item
        if it is None or it.program == "OPERATEUR":
            return None
        pc = self.priority_chart(st)
        if pc is None:
            return None
        t, code, desc, pr = pc
        what = f"{t:%H:%M} {chart_short_label(code, desc)}"
        if pr == PRIORITY_ANALYSE:
            kind = "NAVTEX" if it.is_navtex else ("avis RTTY" if it.category == "AVIS" else "prévision RTTY")
            return Decision(
                "GO_WEFAX", f"Carte prioritaire {what} (situation présente, isobares) : {kind} interrompu"
            )
        if it.is_navtex:
            return None
        if it.category == "AVIS":
            return Decision("STAY", f"Avis RTTY en cours : jamais interrompu par cette carte ({what})")
        if it.label in st.received_recent:
            return Decision(
                "GO_WEFAX",
                f"Carte prioritaire {what} : « {it.label} » déjà reçue il y a moins de 12 h, bulletin interrompu",
            )
        return None

    def decide(self, st: ScheduleState, mono_now=None) -> Decision:
        if st.pipeline == "WEFAX":
            if st.chart_drawing:
                # 2.9.5 — carte d'une autre famille prise en cours de route (sans START) : elle cède la place à
                # une carte de la famille de référence (hors rediffusion) qui va commencer. Le 19/11 à 12:49,
                # une carte de Northwood prise au milieu a retenu le poste pendant la carte DWD de 12:56.
                low_rel = st.chart_reliable_pct is not None and float(st.chart_reliable_pct) < self.LOW_RELIABILITY_PCT
                if (
                    not st.chart_from_start
                    and low_rel
                    and st.preferred_family
                    and st.wefax_family
                    and st.wefax_family not in (st.preferred_family, "ATH")
                    and st.pref_slots
                ):
                    from wefax_station.core.schedules import chart_short_label, chart_slots_around

                    soon = [
                        x
                        for x in chart_slots_around(
                            st.pref_slots, st.now, before_s=self.FAMILY_LEAD_S, after_s=self.FAMILY_LATE_S
                        )
                        if "rediffusion" not in str(x[2]).lower()
                    ]
                    if soon:
                        t, code, desc = soon[0]
                        return Decision(
                            "GO_FAMILY",
                            f"Carte {st.preferred_family} prévue à {t:%H:%M} ({chart_short_label(code, desc)}) : la carte "
                            f"{st.wefax_family} prise en cours de route, peu fiable ({float(st.chart_reliable_pct):.0f} % de "
                            "lignes fiables), lui cède la place",
                        )
                it = self.due_item(st)
                return Decision(
                    "STAY",
                    "Carte en cours : jamais interrompue"
                    + (f" (bulletin {it.describe()} pris après le STOP)" if it else ""),
                )
            it = self.due_item(st)
            if it is not None:
                # 2.9.0 — analyse de surface imminente : on la prend d'abord (2.9.3 : avant un avis ou un NAVTEX
                # aussi, décision F4NMK du 19/11)
                # 2.9.8 — fenêtre prolongée après l'heure : le 19/11 à 18:00:07, START de l'analyse DWD reçu à
                # 18:00:02 mais aucune ligne encore tracée (START puis phasage), départ vers l'avis de 18:00 et
                # retour 15 s plus tard (deux changements de fréquence, avis coupé)
                pc = self.priority_chart(st, before_s=self.ANALYSE_GUARD_S, after_s=self.PRIORITY_LATE_S)
                if pc is not None and pc[3] == "ANALYSE":
                    from wefax_station.core.schedules import chart_short_label

                    return Decision(
                        "STAY",
                        f"Carte prioritaire {pc[0]:%H:%M} {chart_short_label(pc[1], pc[2])} imminente : "
                        f"bulletin {it.describe()} pris après le STOP",
                    )
                # 2.9.7 — bulletin déjà bien entamé et carte de la station écoutée sur le point de commencer :
                # la carte d'abord, le bulletin ensuite s'il est encore à l'antenne. Le 19/11 à 17:23, départ vers
                # l'avis de 17:15 (DDK9) : 3 min de texte illisible, rien d'archivé, et le début de la carte GYA
                # de 17:24 perdu (reprise en cours de route à 17:26:49).
                late_s = (st.now - it.start).total_seconds()
                if not it.is_navtex and late_s > self.LATE_BULLETIN_S:
                    from wefax_station.core.schedules import chart_short_label, chart_slots_around

                    soon = [
                        x
                        for x in chart_slots_around(
                            st.chart_slots, st.now, before_s=self.ANALYSE_GUARD_S, after_s=self.PRIORITY_LATE_S
                        )
                        if "rediffusion" not in str(x[2]).lower()
                    ]
                    if soon:
                        t, code, desc = soon[0]
                        return Decision(
                            "STAY",
                            f"Bulletin {it.describe()} commencé il y a {late_s / 60:.0f} min et carte "
                            f"{t:%H:%M} {chart_short_label(code, desc)} imminente : la carte d'abord, le bulletin "
                            "après le STOP s'il est encore émis",
                        )
                return Decision("GO_RTTY", f"Bulletin RTTY d'intérêt : {it.describe()}", it)
            # 2.8.7 — créneau quotidien d'Athènes (cartes centrées sur la Méditerranée)
            from wefax_station.core.schedules import ATHENS_WINDOW_MIN

            m = st.now.hour * 60 + st.now.minute
            in_win = ATHENS_WINDOW_MIN[0] <= m < ATHENS_WINDOW_MIN[1]
            pref_soon = ()
            if st.preferred_family and st.pref_slots:
                from wefax_station.core.schedules import chart_slots_around as _around

                pref_soon = _around(st.pref_slots, st.now, before_s=self.FAMILY_LEAD_S + 60, after_s=self.FAMILY_LATE_S)
            if st.athens_enabled and in_win and st.wefax_family != "ATH" and not st.athens_unconfirmed and not pref_soon:
                return Decision("GO_ATHENS", "Créneau d'Athènes (08:45-10:45 UTC) : cartes de la Méditerranée")
            if st.wefax_family == "ATH" and not in_win:
                return Decision("LEAVE_ATHENS", "Fin du créneau d'Athènes : retour aux cartes habituelles")
            # 2.9.3 — le 19/11, Athènes n'a jamais été identifiée (contrôles de 08:51, 09:03, 09:11) mais le poste
            # y est resté tout le créneau : cartes DWD de 08:54, 09:06, 09:30, 09:45… perdues, DDK3 fort
            if st.wefax_family == "ATH" and st.athens_unconfirmed:
                return Decision(
                    "LEAVE_ATHENS",
                    "Athènes non identifiée (aucune structure WEFAX) : retour à la famille de référence, nouvel essai "
                    "dans 30 min",
                )
            # 2.9.1 — carte de la famille de référence (DWD) imminente alors que le poste est sur une autre famille
            # (hors créneau d'Athènes) : retour sur la famille de référence pour prendre la carte dès son START
            if (
                st.preferred_family
                and st.wefax_family
                and st.wefax_family not in (st.preferred_family, "ATH")
                and st.pref_slots
            ):
                from wefax_station.core.schedules import chart_short_label, chart_slots_around

                soon = chart_slots_around(st.pref_slots, st.now, before_s=self.FAMILY_LEAD_S, after_s=self.FAMILY_LATE_S)
                if soon:
                    t, code, desc = soon[0]
                    return Decision(
                        "GO_FAMILY",
                        f"Carte {st.preferred_family} prévue à {t:%H:%M} ({chart_short_label(code, desc)}) : "
                        f"retour de {st.wefax_family} vers {st.preferred_family}",
                    )
            if self.veille_due(st, mono_now):
                return Decision("VEILLE", "Veille de propagation (temps mort entre deux cartes)")
            # 2.11.3 — le streak est remis à 0 dès qu'une carte a été tracée depuis la dernière remontée
            # (seconds_since_chart < WEFAX_SILENCE_RECHECK_S). En 2.11.0, le streak grimpait jusqu'à 2 même
            # quand une carte arrivait entre deux RECHECK, parce que la remise à 0 ne s'appliquait que si
            # la carte était très récente.
            if st.seconds_since_chart < self.WEFAX_SILENCE_RECHECK_S:
                self.recheck_streak = 0
            interval = self.recheck_interval()
            if st.seconds_since_chart >= self.WEFAX_SILENCE_RECHECK_S:
                mono_now = mono_now if mono_now is not None else time.monotonic()
                # 2.9.0 — pas de contrôle des autres fréquences dans les 3 min qui précèdent une carte prévue :
                # le 18/11, ce contrôle a précédé de peu les cartes de 18:47 et 19:39 (START non vus ensuite)
                from wefax_station.core.schedules import chart_slots_around

                # 2.9.1 — fenêtre prolongée après l'heure : le 18/11 à 21:00:00 le contrôle est parti à la seconde
                # même où la carte prévue commençait (garde « avant » seulement)
                soon = chart_slots_around(
                    st.chart_slots, st.now, before_s=self.ANALYSE_GUARD_S, after_s=self.RECHECK_AFTER_START_S
                )
                if soon and mono_now - self.last_wefax_recheck >= interval:
                    return Decision("STAY", f"Carte prévue à {soon[0][0]:%H:%M} : contrôle des fréquences reporté")
                if mono_now - self.last_wefax_recheck >= interval:
                    self.recheck_streak = getattr(self, "recheck_streak", 0) + 1
                    return Decision(
                        "WEFAX_RECHECK",
                        f"Aucune carte depuis {st.seconds_since_chart / 60:.0f} min : contrôle des autres fréquences "
                        f"WEFAX (prochain contrôle dans {self.recheck_interval() / 60:.0f} min si rien ne change)",
                    )
            return Decision("STAY", "Attente de la carte suivante")
        # ----- RTTY
        # 2.8.6 — NAVTEX : l'émission occupe un créneau de 10 min et peut commencer n'importe quand dans le
        # créneau (file d'attente de l'émetteur). Le 16-17/11 l'écoute était abandonnée après 6 s à 1 min.
        if st.current_item is not None and (st.current_item.is_navtex or st.current_item.program == "OPERATEUR"):
            # 2.8.9 — créneaux NAVTEX consécutifs (La Maddalena 18:50, La Garde 19:00) : on enchaîne
            # directement au lieu de repasser par les cartes (le 18/11, 2 min 30 du créneau de 19:00 perdues)
            if st.now >= st.current_item.end and not (
                st.rtty_text_active and st.now < st.current_item.end + timedelta(minutes=1)
            ):
                nxt = self.due_item(st, exclude=(st.current_item.key,))
                if nxt is not None and nxt.start > st.current_item.start:
                    return Decision("NEXT_RTTY", f"Fin du créneau, créneau suivant : {nxt.describe()}", nxt)
            if st.now < st.current_item.end + timedelta(minutes=1):
                if st.rtty_end_marker and not st.rtty_text_active and st.now >= st.current_item.start + timedelta(minutes=3):
                    return Decision("GO_WEFAX", "Message NAVTEX terminé (NNNN) : retour aux cartes")
                return Decision("STAY", "Créneau d'écoute en cours (NAVTEX ou choix opérateur) : écoute jusqu'à la fin")
            return Decision("GO_WEFAX", "Fin du créneau d'écoute : retour aux cartes")
        # délai de grâce : on arrive 60 s avant l'heure, la boucle de service précède le bulletin
        if st.current_item is not None and st.now < st.current_item.start + timedelta(seconds=90):
            if st.rtty_no_signal_s >= 120:
                return Decision(
                    "GO_WEFAX", "Aucun signal RTTY exploitable sur cette fréquence : retour aux cartes"
                )
            ci = self.chart_interrupt(st)
            if ci is not None:
                return ci
            return Decision("STAY", "Attente du début du bulletin")
        # 2.8.9 — le DWD enchaîne souvent un autre bulletin juste après le NNNN, sans boucle RY/CQ : le
        # 18/11, la prévision 5 jours Atlantique s'est terminée à 18:33:33 et l'application est restée sur les
        # SYNOP qui suivaient (attente de 30 s de boucle de service qui n'est jamais venue).
        # Désormais : 12 s après le NNNN du bulletin d'intérêt, bulletin d'intérêt suivant s'il est dû,
        # sinon retour aux cartes.
        if st.rtty_end_marker and st.rtty_end_age_s is not None and st.rtty_end_age_s >= self.END_GRACE_S:
            cur = (st.current_item.key,) if st.current_item is not None else ()
            nxt = self.due_item(st, exclude=cur)
            if nxt is not None and (st.current_item is None or nxt.start > st.current_item.start):
                return Decision("NEXT_RTTY", f"Bulletin terminé (NNNN), bulletin suivant : {nxt.describe()}", nxt)
            return Decision("GO_WEFAX", "Bulletin terminé (NNNN) : retour aux cartes")
        if st.rtty_end_marker and st.rtty_service_s >= 5:
            return Decision("GO_WEFAX", "Bulletin terminé (NNNN) : retour aux cartes")
        # 2.8.9 — garde-fou : jamais plus de 6 min au-delà du créneau prévu, même si du texte arrive encore
        if st.current_item is not None and st.now >= st.current_item.end + timedelta(minutes=self.OVERRUN_MAX_MIN):
            return Decision(
                "GO_WEFAX",
                f"Créneau du bulletin dépassé de {self.OVERRUN_MAX_MIN} min (fin du NNNN non reçue) : retour aux cartes",
            )
        if st.rtty_service_s >= 30:
            return Decision(
                "GO_WEFAX", "Boucle de service RTTY (RY / CQ) : bulletin terminé, retour aux cartes"
            )
        if st.rtty_no_signal_s >= 60:
            return Decision("GO_WEFAX", "Plus de signal RTTY valide depuis 60 s : retour aux cartes")
        if (
            st.current_item is not None
            and st.now >= st.current_item.end + timedelta(minutes=2)
            and not st.rtty_text_active
        ):
            return Decision("GO_WEFAX", "Fin du créneau du bulletin : retour aux cartes")
        if st.current_item is None and not st.rtty_text_active and st.rtty_service_s >= 10:
            return Decision("GO_WEFAX", "RTTY manuel sans bulletin en cours : retour aux cartes")
        ci = self.chart_interrupt(st)
        if ci is not None:
            return ci
        return Decision("STAY", "Bulletin RTTY en cours")


# ----------------------------------------------------------------------------- texte RTTY
_SERVICE_TOKENS = ("RYRY", "YRYR", "CQ CQ", "FREQUENCIES", " DE DDH", " DE DDK")


def service_ratio(text):
    """Part du texte récent qui est de la boucle de service (RY, CQ, liste des fréquences)."""
    t = (text or "").upper()
    if len(t) < 40:
        return 0.0
    hits = 0
    for tok in _SERVICE_TOKENS:
        hits += t.count(tok) * len(tok)
    ry = t.count("RY") * 2
    return min(1.0, max(hits, ry) / len(t))


def strip_service(text):
    """Retire la boucle de service (lignes RY/CQ/FREQUENCIES) d'un texte de bulletin."""
    keep = []
    for line in (text or "").replace("\r", "\n").split("\n"):
        u = line.upper().strip()
        if not u:
            keep.append(line)
            continue
        if service_ratio(u + " " * max(0, 40 - len(u))) > 0.45 or u.startswith("CQ CQ") or "FREQUENCIES" in u:
            continue
        if set(u.replace(" ", "")) <= set("RY"):
            continue
        keep.append(line)
    out = "\n".join(keep)
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out.strip()
