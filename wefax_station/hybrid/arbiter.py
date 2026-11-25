"""Arbitre de mode WEFAX / RTTY (bascules planifiées, protection anti-scission)."""

import re
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import messagebox
import numpy as np
from wefax_station.core.stations import (
    RTTY_WEATHER_STATIONS,
    WEFAX_STATIONS,
    get_wefax_station_by_freq,
    is_rtty_frequency,
    is_wefax_frequency,
)
from wefax_station.dsp.scan_diagnostics import assess_scan_audio
from wefax_station.weather.plain_language import (
    DEFAULT_QTH,
    LEVELS,
    clean_raw,
    interpret,
    parse_area_forecasts,
    plain_report,
    reception_in_progress,
)
from wefax_station.weather.marine_translate import synopsis_paragraphs
from wefax_station.weather.rtty_parse import parse_point_forecasts
from wefax_station.weather import dossier as weather_dossier
from wefax_station.weather.rtty_repair import readability_summary
from wefax_station.hybrid.planner import ScheduleSyncAndPlanner
from wefax_station.hybrid.scheduler import (
    CATEGORIES,
    DEFAULT_INTEREST,
    DEFAULT_PROGRAMS,
    PROGRAM_STATIONS,
    PropagationTable,
    Decision,
    ReceptionScheduler,
    ScheduleState,
    service_ratio,
    strip_service,
)
from wefax_station.rtty.decoder import RTTYITA2Decoder
from wefax_station.rtty.segmenter import BulletinSegmenter, find_marker, marker_received
from wefax_station.rtty.translator import OfflineWeatherTranslator
from wefax_station.storage.portable import PortableWorkspaceManager
from wefax_station.version import SOFTWARE_BRAND, SOFTWARE_VERSION
from wefax_station.weather.reliability import WeatherReliabilityEstimator


def rtty_items_for_hint(scheduler):
    from wefax_station.hybrid.scheduler import ReceptionScheduler

    probe = ReceptionScheduler(programs=(1, 2), categories=("MED", "AVIS", "NAVTEX"))
    return probe.next_items(datetime.now(timezone.utc), n=6)


class HybridModeArbiter:
    MODES = ("HYBRIDE", "WEFAX", "BULLETINS", "MANUEL", "RELECTURE")
    ACTIVITIES = (
        "ATTENTE",
        "SURVEILLANCE",
        "ACQUISITION",
        "RECEPTION_WEFAX",
        "RECEPTION_RTTY",
        "SCAN",
        "TRANSITION",
        "DEGRADE",
        "ERREUR",
    )

    def __init__(
        self,
        app,
        workspace: PortableWorkspaceManager,
        rtty_decoder: RTTYITA2Decoder,
        translator: OfflineWeatherTranslator,
        planner: ScheduleSyncAndPlanner,
    ):
        self.app = app
        self.workspace = workspace
        self.rtty = rtty_decoder
        self.translator = translator
        self.planner = planner

        self.requested_mode = "HYBRIDE"
        self.current_activity = "SURVEILLANCE"
        self.manual_hold = False
        self.operator_choice = None  # 2.11.1 — choix opérateur (bouton « Stations »), distinct de manual_hold
        self.active_pipeline = "WEFAX"
        self.return_margin_sec = 120
        self.rtty_prescan_sec = 90
        is_day = 7 <= datetime.now(timezone.utc).hour <= 17
        self.wefax_return_freq_khz = 13882.5 if is_day else 7880.0
        self.wefax_return_station = "DDK6" if is_day else "DDK3"
        self.active_rtty_station = RTTY_WEATHER_STATIONS[2]
        self.rtty_scan_active = False
        self.deliberate_wefax_scan_authorized = False
        self.rtty_snr_map = {s["id"]: "Non mesuré" for s in RTTY_WEATHER_STATIONS}
        self.wefax_quality_map = {}
        self.last_transition_mono = time.monotonic()
        self.last_wefax_prescan_slot = None
        self.last_rtty_prescan_slot = None
        self.wefax_guard_until_mono = 0.0
        self.scan_started_mono = 0.0
        self.rtty_raw_buffer = ""
        # 2.8.5 — bulletin EN COURS (depuis le dernier NNNN). rtty_raw_buffer reste le texte complet de la
        # session, affiché et analysé ; les fichiers, eux, sont découpés bulletin par bulletin.
        self.rtty_segment = ""
        self.last_archived_rtty_summary = "Aucun bulletin RTTY complet reçu dans cette session."
        self.rtty_last_logged_len = 0
        self.rtty_session_start_utc = None
        # ----- ordonnancement 2.8 (voir hybrid/scheduler.py)
        cfg = self.workspace.root_dir / "configuration"
        self.prop = PropagationTable(path=cfg / "propagation.json").load()
        self.plan_path = cfg / "plan_reception.json"
        self.plan = self._load_plan()
        self.scheduler = ReceptionScheduler(
            programs=self.plan["programs"],
            categories=self.plan["categories"],
            rtty_enabled=self.plan["rtty_enabled"],
        )
        self.current_item = None
        self.done_items = set()
        # 2.9.0 — bulletins reçus en entier (libellé → heure), pour la règle « carte prioritaire »
        self.received_path = cfg / "bulletins_recus.json"
        self.received_bulletins = self._load_received()
        # 2.9.2 — stations NAVTEX / RTTY optionnelles, mises en sommeil après plusieurs créneaux muets
        from wefax_station.hybrid.text_station_health import TextStationHealth

        self.text_health = TextStationHealth(cfg / "stations_texte.json")
        self.scheduler.station_filter = self.text_health.allows
        # 2.9.3 — programme observé (créneaux reçus / muets), sans réseau
        from wefax_station.hybrid.observed_programme import ObservedProgramme

        self.observed = ObservedProgramme(cfg / "programme_observe.json")
        self.veille_active = False
        self.startup_survey_pending = True
        self.last_chart_mono = time.monotonic()
        self._reset_rtty_tracking()
        self.last_decision = "Démarrage"

    RECEIVED_KEEP_S = 12 * 3600

    def _load_received(self):
        try:
            data = json.loads(Path(self.received_path).read_text(encoding="utf-8"))
            return {str(k): float(v) for k, v in data.get("bulletins", {}).items()}
        except Exception:
            return {}

    def mark_bulletin_received(self, label, when=None):
        when = time.time() if when is None else when
        self.received_bulletins[str(label)] = when
        cutoff = when - 2 * self.RECEIVED_KEEP_S
        self.received_bulletins = {k: v for k, v in self.received_bulletins.items() if v >= cutoff}
        try:
            from wefax_station.storage.atomic import atomic_json

            atomic_json(self.received_path, {"schema": "bulletins-recus-1", "bulletins": self.received_bulletins})
        except Exception:
            pass

    def received_recent_labels(self, now=None):
        now = time.time() if now is None else now
        return tuple(k for k, v in self.received_bulletins.items() if now - v <= self.RECEIVED_KEEP_S)

    def disarm_base_periodic_scan_timers(self):
        """
        Empêche les timers internes du socle (`part08/part09`) de lancer un
        « Debut scan integral ; reception image suspendue » au milieu d'une carte WEFAX !
        """
        now_m = time.monotonic()
        now_t = time.time()
        for attr_m in (
            "last_periodic_scan_ts",
            "last_scan_request",
            "last_sync_ts",
            "last_wefax_activity_ts",
            "last_valid_signal_ts",
            "scan_cooldown_until",
        ):
            if hasattr(self.app, attr_m):
                val = getattr(self.app, attr_m)
                if isinstance(val, (int, float)):
                    setattr(self.app, attr_m, now_t if val > 1e8 else now_m)

    # ------------------------------------------------------------------ lecture en clair
    def zone_label(self):
        z = getattr(self.app, "zone_var", None)
        return (z.get() if z is not None else "") or "votre secteur"

    def _qth_zone(self):
        zone = self.app.analysis_zone() if hasattr(self.app, "analysis_zone") else None
        if zone is not None:
            return (zone["lat"], zone["lon"]), int(zone["radius"]), zone["label"], zone
        try:
            qth = tuple(float(v) for v in self.plan.get("qth", DEFAULT_QTH))
        except (TypeError, ValueError):
            qth = DEFAULT_QTH
        return qth, int(self.plan.get("radius_km", 500)), self.zone_label(), None

    def _next_hint(self):
        useful = [x for x in rtty_items_for_hint(self.scheduler) if x.category in ("MED", "AVIS", "NAVTEX")][:3]
        return ("Prochains bulletins utiles : " + " · ".join(x.describe() for x in useful)) if useful else ""

    def interpret_text(self, text, source="", live=False, dossier=None):
        """(texte en clair, synthèse) pour un bulletin RTTY / NAVTEX reçu, ou pour un dossier de bulletins."""
        qth, radius, label, zone = self._qth_zone()
        if dossier is not None:
            points = dossier["points"]
            areas = parse_area_forecasts(dossier["areas_text"])
            # 2.11.0 — plusieurs candidats, du plus récent au plus ancien : le rapport garde le premier
            # paragraphe lisible (le plus récent était souvent un flux brouillé à 47 %)
            syn = []
            for d in reversed(dossier["used"]):
                syn += synopsis_paragraphs(d["body"])
                if len(syn) >= 4:
                    break
            unreadable = dossier["unreadable"]
            sources = weather_dossier.sources_lines(dossier)
            in_prog = False
            from wefax_station.weather.synop import report_lines as _obs_lines

            observations = _obs_lines(dossier.get("observations", []), qth, radius)
            extra = list(dossier.get("extra_sections", []))
        else:
            from wefax_station.weather.rtty_repair import repair_bulletin

            repaired, rep = repair_bulletin(text)
            points = parse_point_forecasts(repaired, repaired=True)
            areas = parse_area_forecasts(text)
            syn = synopsis_paragraphs(text)
            unreadable = {
                n: {"time": None, "station": source.split()[0] if source else ""}
                for n, v in rep.get("points", {}).items()
                if v["ok"] == 0
            }
            sources = None
            in_prog = live and reception_in_progress(text)
            from wefax_station.weather.synop import parse_observations, report_lines as _obs_lines

            observations = _obs_lines(parse_observations(text), qth, radius, max_age_h=24)
            extra = []
        it = interpret(points, areas, qth=qth, radius_km=radius)
        if isinstance(syn, list) and len(syn) > 1:
            # 2.11.0 — la situation générale qui parle du secteur de l'opérateur d'abord
            keys = {x["where"].lower() for x in it["near"]} | {"méditerranée"}
            syn = sorted(syn, key=lambda p: -sum(k.split(" (")[0] in p.lower() for k in keys))
        hint = "" if it["near"] else self._next_hint()
        report = plain_report(
            it,
            label,
            source,
            in_progress=in_prog,
            synopsis=syn,
            unreadable=unreadable,
            sources=sources,
            qth=qth,
            next_hint=hint,
            observations=observations,
            extra_sections=extra,
        )
        if zone is not None:
            report += f"\nZone d'analyse : {zone['source']}."
        return report, it

    def build_dossier(self, include_live=True):
        live = None
        if include_live and self.active_pipeline == "RTTY" and len(self.rtty_segment.strip()) >= 45:
            live = self.rtty_segment
        dos = weather_dossier.collect(
            weather_dossier.day_dirs_for(self.workspace),
            live_text=live,
            live_source=self.active_rtty_station,
        )
        # 2.8.7 — prévision numérique GRIB reçue par Winlink (moins de 36 h)
        if hasattr(self.app, "winlink_grib_section"):
            try:
                qth, radius, _label, _zone = self._qth_zone()
                sec = self.app.winlink_grib_section(qth, radius)
            except Exception:
                sec = None
            if sec and sec[1]:
                dos["extra_sections"] = [(sec[0], sec[1])]
                if sec[2]:
                    dos["extra_sources"] = [sec[2]]
        return dos

    # ------------------------------------------------------------------ 2.10.0 : situation et 3-6 h
    def operator_observation(self):
        """Formulaire « Observations locales » (Réglages › Opérateur), tel que saisi."""
        app = self.app
        if not hasattr(app, "ent_press"):
            return {}
        get = lambda name: (getattr(app, name).get() if hasattr(app, name) else "")
        return {
            "Date UTC": get("obs_time"),
            "Pression hPa": get("ent_press"),
            "Tendance 3 h": get("cmb_ptrend"),
            "Vent": get("cmb_wind"),
            "Force du vent": get("cmb_wind_force"),
            "Mer": get("cmb_sea"),
        }

    def recent_charts(self, hours=12, now=None):
        import json as _json

        now = now or datetime.now(timezone.utc)
        out = []
        for d in weather_dossier.day_dirs_for(self.workspace, now):
            for f in sorted((Path(d) / "cartes").glob("2*_*.json")):
                try:
                    j = _json.loads(f.read_text(encoding="utf-8"))
                    t = datetime.fromisoformat(j.get("utc_reception_fin"))
                except Exception:
                    continue
                if (now - t).total_seconds() <= hours * 3600:
                    out.append(
                        {
                            "time": t,
                            "station": j.get("station", "?"),
                            "label": j.get("programme") or j.get("programme_code") or "",
                            "rel": j.get("pixels_fiables_pct"),
                            "file": f.name,
                        }
                    )
        return out

    def nowcast_inputs(self):
        """Ce qui doit être lu dans le fil de l'interface (variables Tk) : zone, observation, dossier."""
        return {"zone": self._qth_zone(), "operator": self.operator_observation(), "dossier": self.build_dossier()}

    def compute_nowcast(self, dossier=None, now=None, operator=None, zone=None):
        """Situation actuelle et prévision 3 à 6 h sur le secteur de l'opérateur (weather/nowcast.py).

        Appelée sans argument depuis l'interface ; depuis un fil de travail, lui passer nowcast_inputs()."""
        from wefax_station.weather import nowcast as _nc
        from wefax_station.weather.rtty_parse import gale_warnings as _gales

        now = now or datetime.now(timezone.utc)
        dossier = dossier if dossier is not None else self.build_dossier()
        qth, radius, label, _zone = zone if zone is not None else self._qth_zone()
        operator = operator if operator is not None else self.operator_observation()
        rows, received = (None, None)
        if hasattr(self.app, "winlink_grib_rows"):
            try:
                rows, received = self.app.winlink_grib_rows(qth, radius, now=now)
            except Exception:
                rows, received = None, None
        gales = []
        for d in dossier.get("used", []):
            if (now - d["time"]).total_seconds() <= 12 * 3600:
                gales += _gales(d["body"], translate=True)
        return _nc.build_nowcast(
            now=now,
            qth=qth,
            radius_km=radius,
            zone_label=label,
            points=dossier.get("points", []),
            areas=parse_area_forecasts(dossier.get("areas_text", "")),
            observations=dossier.get("observations", []),
            grib_rows=rows,
            grib_received=received,
            operator=operator,
            charts=self.recent_charts(now=now),
            text_docs=dossier.get("used", []),
            gale_texts=gales[:4],
        )

    def generate_adrasec_orsec_report_1click(self) -> Path:
        """Rapport ADRASEC lisible par tous : d'abord ce qu'il faut retenir, la technique à la fin."""
        now_utc = datetime.now(timezone.utc)
        adrasec = bool(self.app.is_adrasec()) if hasattr(self.app, "is_adrasec") else True
        rel_wf = WeatherReliabilityEstimator.compute_wefax_reliability(self.app)
        rel_rt = WeatherReliabilityEstimator.compute_rtty_reliability(self.rtty, self.rtty_raw_buffer)
        op_call = self.workspace.operator_tag()
        # 2.8.6 — synthèse sur le DOSSIER des bulletins des dernières 30 h (plus seulement le dernier message
        # reçu, qui était une synop vide le 17/11 à 07:05) ; source = station réellement reçue.
        dossier = self.build_dossier()
        if dossier["used"]:
            plain, it = self.interpret_text("", dossier=dossier)
            last_fc = dossier["used"][-1]
            rep = last_fc.get("repair") or {}
            text_quality = readability_summary(rep) or "bulletin sans tableau de prévision"
        else:
            plain, it = ("Aucun bulletin de prévision reçu depuis 30 h (seulement des messages sans prévision).", None)
            text_quality = "aucun bulletin exploitable"
        last_chart = getattr(self.app, "last_saved_path", None)

        def grade_words(rel):
            return {
                "A": "excellente : le texte reçu est fiable",
                "B": "bonne : quelques caractères peuvent manquer",
                "C": "moyenne : vérifier les chiffres importants",
            }.get(rel["grade"], "faible : informations à confirmer par une autre source")

        bar = "=" * 78
        L = [
            bar,
            (
                f"BULLETIN MÉTÉO MARINE — CELLULE ORSEC / ADRASEC — {self.zone_label()}"
                if adrasec
                else f"BULLETIN MÉTÉO MARINE — {self.zone_label()}"
            ),
            f"Établi le {now_utc:%d/%m/%Y à %H:%M} UTC par {op_call}",
            bar,
            "",
            plain,
            "",
            *self._nowcast_block(dossier),
            "-" * 78,
            "CARTES MÉTÉO REÇUES (fac-similé radio)",
            (
                f"Dernière carte : {Path(last_chart).name} (à consulter : situation générale, dépressions, fronts)."
                if last_chart
                else f"Pas de carte archivée dans cette session (écoute sur {self.wefax_return_station})."
            ),
            "",
            "QUALITÉ DE LA RÉCEPTION",
            f"Bulletin texte le plus récent : {text_quality}",
            f"Cartes : {self._charts_quality_line()}",
            (
                f"Messages écartés (sans prévision) : {len(dossier['skipped'])} "
                f"({', '.join(sorted({w for _d, w in dossier['skipped']}))})."
                if dossier["skipped"]
                else ""
            ),
            "",
            "-" * 78,
            # 2.11.0 — plus d'annexe de 3 000 caractères (souvent un avis NAVTEX brouillé sans rapport) :
            # les textes originaux et leur traduction restent dans le dossier du jour.
            "Textes originaux et traductions : dossier « bulletins » du jour (Archives).",
            "",
            f"Détail technique : WEFAX [{rel_wf['detail']}] | RTTY [{rel_rt['detail']}] | "
            f"{SOFTWARE_BRAND} v{SOFTWARE_VERSION}",
            bar,
        ]
        report_text = "\n".join(L)
        day_dir = self.workspace.reception_day_dir(now_utc)
        from wefax_station.storage import layout as _layout

        out_dir = _layout.my_bulletins_dir(day_dir)  # 2.11.0 — « mes_bulletins »
        out_dir.mkdir(parents=True, exist_ok=True)
        kind = "ADRASEC" if adrasec else "METEO"
        out_path = out_dir / f"BULLETIN_{kind}_{op_call}_{now_utc.strftime('%Y%m%d_%H%M%SZ')}.txt"
        out_path.write_text(report_text, encoding="utf-8")
        if hasattr(self.app, "txt_weather_report"):
            try:
                self.app.txt_weather_report.delete("1.0", "end")
                self.app.txt_weather_report.insert("1.0", report_text)
            except Exception:
                pass
        lvl = it["level"] if it and it["near"] else None
        self.app.log_event(
            f"📋 [{'RAPPORT ADRASEC' if adrasec else 'RAPPORT MÉTÉO'}] {out_path.name} — "
            + (f"{LEVELS[lvl][0]} {LEVELS[lvl][1]}" if lvl else "bulletin hors secteur")
        )
        return out_path

    def _nowcast_block(self, dossier=None):
        from wefax_station.weather.nowcast import nowcast_lines

        try:
            nc = self.compute_nowcast(dossier)
            self.last_nowcast = nc
            return ["=" * 78, *nowcast_lines(nc), ""]
        except Exception as exc:  # le rapport doit sortir même si ce bloc échoue
            return ["(Situation et prévision 3-6 h indisponibles : " + repr(exc) + ")", ""]

    def _charts_quality_line(self):
        """Cartes archivées des 12 dernières heures, qualité = pixels fiables (indicateur unique)."""
        import json as _json
        from datetime import timedelta as _td

        now = datetime.now(timezone.utc)
        rows = []
        for d in weather_dossier.day_dirs_for(self.workspace, now):
            for f in sorted((Path(d) / "cartes").glob("2*_*.json")):
                try:
                    j = _json.loads(f.read_text(encoding="utf-8"))
                    t = datetime.fromisoformat(j.get("utc_reception_fin"))
                except Exception:
                    continue
                if t >= now - _td(hours=12):
                    rows.append((t, j.get("station", "?"), j.get("lines", 0), j.get("pixels_fiables_pct")))
        if not rows:
            return f"aucune carte archivée depuis 12 h (écoute sur {self.wefax_return_station})."
        good = [r for r in rows if (r[3] or 0) >= 50 and r[2] >= 900]
        last = rows[-1]
        return (
            f"{len(rows)} carte(s) en 12 h, {len(good)} complète(s) et lisible(s) ; dernière à "
            f"{last[0]:%H:%M} UTC ({last[1]}, {last[2]} lignes"
            + (f", {last[3]:.0f} % de pixels fiables" if last[3] is not None else "")
            + ")."
        )

    def remember_wefax_station_if_valid(self):
        cur_f = float(getattr(self.app.radio, "actual_freq_khz", 7880.0))
        st_wf = get_wefax_station_by_freq(cur_f)
        if st_wf is not None:
            self.wefax_return_freq_khz = float(st_wf["freq"])
            self.wefax_return_station = str(st_wf["id"])

    def is_wefax_signal_actively_present(self) -> bool:
        if self.active_pipeline != "WEFAX":
            return False
        cur_f = float(getattr(self.app.radio, "actual_freq_khz", 0.0))
        if not is_wefax_frequency(cur_f):
            return False
        if getattr(self.app, "waiting_after_stop", False):
            return False
        lines = int(getattr(self.app, "rx_current_line", 0))
        if lines >= 3:
            self.wefax_guard_until_mono = max(self.wefax_guard_until_mono, time.monotonic() + 300.0)
            self.disarm_base_periodic_scan_timers()
            return True
        snr = float(getattr(self.app, "current_snr_db", 0.0))
        if snr >= 8.5:
            self.wefax_guard_until_mono = max(self.wefax_guard_until_mono, time.monotonic() + 180.0)
            self.disarm_base_periodic_scan_timers()
            return True
        return False

    def flush_audio_backlogs(self):
        try:
            while not self.app.rx_audio_queue.empty():
                self.app.rx_audio_queue.get_nowait()
        except Exception:
            pass
        self.app.rx_sample_accumulator = np.zeros(0, dtype=np.float32)

    def set_requested_mode(self, mode: str, user_initiated: bool = True):
        if mode not in self.MODES:
            return
        prev = self.requested_mode
        self.requested_mode = mode
        if user_initiated:
            self.manual_hold = mode == "MANUEL"
        self.app.log_event(f"🎛️ Mode d'exploitation : {prev} -> {mode}")

        if mode == "BULLETINS":
            self.switch_to_rtty_pipeline(reason="Mode BULLETINS RTTY sélectionné")
        elif mode == "WEFAX":
            self.switch_to_wefax_pipeline(reason="Mode CARTES WEFAX sélectionné")
        elif mode == "RELECTURE":
            self.active_pipeline = "NONE"
            self.current_activity = "ATTENTE"
        elif mode == "HYBRIDE":
            self.evaluate_hybrid_schedule(initial_launch=True)

    def notify_manual_stop(self):
        self.manual_hold = True
        self.current_activity = "ATTENTE"
        self.app.log_event("⏸️ Pause manuelle du décodage WEFAX.")

    def resume_automation(self):
        self.manual_hold = False
        self.app.log_event("▶️ Reprise de l'automatisme WEFAX / RTTY.")
        self.evaluate_hybrid_schedule(initial_launch=True)

    def get_next_wefax_countdown(self) -> tuple:
        up = self.planner.get_upcoming_wefax_across_all_families()
        return (
            up["delay_sec"],
            up["code"],
            up["description"],
            up["when_str"],
            up["family"],
            up.get("elapsed_since_last_start_sec", 3600),
        )

    def _listening_name(self, st):
        it = self.current_item
        if it is not None and getattr(it, "is_navtex", False):
            import re as _re

            m = _re.match(r"NAVTEX\s+(.+?\(\w\))", str(it.label))
            if m:
                return "NAVTEX " + m.group(1)
        return str(st.get("id", "?"))

    FAMILY_ARRIVAL_LEAD_S = 90  # 2.9.5 — contrôle (≈ 20 s) et calage terminés avant l'heure de la carte

    def _next_family_slot(self, fam, now):
        from wefax_station.core.schedules import upcoming_charts

        slots = (getattr(self.app, "schedule_data", None) or {}).get(fam, ())
        try:
            nxt = upcoming_charts(slots, now, horizon_min=60, n=1)
        except Exception:
            return None
        return nxt[0][0] if nxt else None

    OBSERVED_FAMILIES = ("DWD", "GYA")

    def _family_signal_ok(self, fam):
        """Signal correct sur la famille écoutée : indicateur spectral ≥ 10 dB ou station vue nette/forte."""
        if float(getattr(self.app, "current_snr_db", 0.0) or 0.0) >= 10.0:
            return True
        seen = getattr(self.app, "spectral_seen", None) or {}
        now_ts = time.time()
        for s in WEFAX_STATIONS:
            r = seen.get(s["id"]) if s.get("family") == fam else None
            if r and now_ts - float(r.get("ts", 0)) <= 300 and float(r.get("contrast", 0)) >= 10:
                return True
        return False

    def _observe_programme(self, now, chart_drawing):
        obs = getattr(self, "observed", None)
        if obs is None:
            return
        cur = get_wefax_station_by_freq(float(getattr(self.app.radio, "actual_freq_khz", 0.0)))
        cur_fam = cur["family"] if (cur and self.active_pipeline == "WEFAX") else None
        data = getattr(self.app, "schedule_data", None) or {}
        for fam in self.OBSERVED_FAMILIES:
            on_air = cur_fam == fam
            muted = obs.tick(now, fam, data.get(fam, ()), on_air, chart_drawing, on_air and self._family_signal_ok(fam))
            for hm, code, desc in muted:
                from wefax_station.core.schedules import chart_short_label

                rec = obs.data.get(fam, {}).get(hm, {})
                self.app.log_event(
                    f"🗓️ [PROGRAMME OBSERVÉ] {fam} {hm} ({chart_short_label(code, desc)}) : aucun START alors que le "
                    f"poste écoutait {cur['id'] if cur else fam} avec un bon signal — carte non émise ou START manqué "
                    f"(muet {rec.get('muet', 1)} fois, reçu {rec.get('recu', 0)} fois)."
                )

    def note_chart_start(self, when=None):
        """2.9.3 — START reçu : relevé dans le programme observé."""
        obs = getattr(self, "observed", None)
        cur = get_wefax_station_by_freq(float(getattr(self.app.radio, "actual_freq_khz", 0.0)))
        if obs is None or cur is None or cur.get("family") not in self.OBSERVED_FAMILIES:
            return None
        when = when or datetime.now(timezone.utc)
        data = getattr(self.app, "schedule_data", None) or {}
        return obs.note_start(cur["family"], when, data.get(cur["family"], ()))

    def note_family_scan(self, family, tier):
        """2.9.3 — résultat d'un contrôle limité à une famille. Athènes sans structure WEFAX (rang < 2) : on la
        laisse 30 min, puis nouvel essai si le créneau dure encore."""
        if family != "ATH":
            return
        self._ath_check_pending = False
        if tier >= 2:
            if getattr(self, "ath_unconfirmed_until_mono", 0.0):
                self.app.log_event("🏛️ Athènes identifiée (modulation WEFAX) : créneau de la Méditerranée conservé.")
            self.ath_unconfirmed_until_mono = 0.0
            return
        self.ath_unconfirmed_until_mono = time.monotonic() + 1800.0
        retry = datetime.now(timezone.utc) + timedelta(minutes=30)
        self.app.log_event(
            f"🏛️ Athènes non identifiée (rang {tier} : aucune modulation WEFAX) : retour aux cartes "
            f"{self.preferred_family()}, nouvel essai vers {retry:%H:%M} UTC si le créneau dure encore."
        )

    def trigger_targeted_wefax_prescan(self, target_family: str, code: str, when_str: str, force: bool = False):
        if getattr(self.app, "carrier_scan_active", False) or getattr(self.app, "connection_busy", False):
            return
        if not self.app.radio.handshake_ok or not self.app.audio_live_connected:
            return

        cur_f = float(getattr(self.app.radio, "actual_freq_khz", 0.0))
        cur_wf_st = get_wefax_station_by_freq(cur_f)
        same_family_wefax = bool(cur_wf_st is not None and cur_wf_st.get("family") == target_family)
        rel_now = WeatherReliabilityEstimator.compute_wefax_reliability(self.app)

        if (
            not force
            and same_family_wefax
            and rel_now["score_pct"] >= 75
            and float(getattr(self.app, "current_snr_db", 0.0)) >= 12.0
        ):
            self.wefax_guard_until_mono = time.monotonic() + 900.0
            self.disarm_base_periodic_scan_timers()
            self.app.log_event(
                f"🛡️ [Pré-Carte {target_family}] Qualité déjà optimale sur {cur_wf_st['id']} "
                f"({cur_wf_st['freq']:.1f} kHz | Qualité={rel_now['score_pct']}%) — Scan évité."
            )
            return

        self.wefax_guard_until_mono = time.monotonic() + 900.0
        self.scan_started_mono = time.monotonic()
        self.deliberate_wefax_scan_authorized = True

        family_stations = [s for s in WEFAX_STATIONS if s.get("family") == target_family]
        if not family_stations:
            family_stations = list(WEFAX_STATIONS)

        is_day = 7 <= datetime.now(timezone.utc).hour <= 17
        if target_family == "DWD":
            default_freq = 13882.5 if is_day else 7880.0
        elif target_family == "ATH":
            default_freq = 8105.0 if is_day else 4481.0
        else:
            default_freq = 8040.0 if is_day else 4610.0
        self.app.scan_origin = default_freq
        self.app.scan_offset = bool(self.app.apply_usb_offset.get())
        self.app.scan_candidates = list(family_stations)
        self.app.scan_results = []
        self.wefax_quality_map.clear()
        self.app.rx_current_line = 0
        self.app.rx_sheet_initialized_for_live = False
        self.app.carrier_scan_active = True
        self.disarm_base_periodic_scan_timers()
        self.flush_audio_backlogs()
        self.app.set_busy_state(
            True, f"SCAN QUALITÉ {target_family} ({len(family_stations)} fréquences) avant [{code}]..."
        )
        self.app.log_event(
            f"🔍 [Scan WEFAX Qualité {target_family}] Recherche de la porteuse blanche 2300 Hz parmi "
            f"{[s['id'] for s in family_stations]} avant [{code}] ({when_str})..."
        )
        self.app._scan_next()

    def trigger_rtty_frequency_scan(self, family_filter: str = None, on_complete_cb=None, station_ids=None):
        if (
            self.rtty_scan_active
            or getattr(self.app, "carrier_scan_active", False)
            or getattr(self.app, "connection_busy", False)
        ):
            return
        if not self.app.radio.handshake_ok or not self.app.audio_live_connected:
            if not family_filter:
                messagebox.showwarning(
                    "Scan RTTY",
                    "Une liaison CAT vérifiée et un flux audio USB actif sont requis pour scanner les fréquences RTTY.",
                )
            return

        self.remember_wefax_station_if_valid()

        if family_filter in ("NAVTEX_FR", "NAVTEX_INT"):
            target_st = next(
                (s for s in RTTY_WEATHER_STATIONS if s["family"] == family_filter), RTTY_WEATHER_STATIONS[-2]
            )
            self.switch_to_rtty_pipeline(
                target_st,
                reason=f"Accès direct sans scan au créneau {target_st['id']} ({target_st['freq']} kHz)",
            )
            if on_complete_cb:
                on_complete_cb(target_st)
            return

        utc_h = datetime.now(timezone.utc).hour
        is_day_utc = 6 <= utc_h < 18

        if station_ids:
            candidates = [s for s in RTTY_WEATHER_STATIONS if s["id"] in station_ids]
        elif family_filter == "DWD_RTTY":
            target_periods = ("JOUR/NUIT", "JOUR") if is_day_utc else ("JOUR/NUIT", "NUIT")
            candidates = [
                s
                for s in RTTY_WEATHER_STATIONS
                if s["family"] == "DWD_RTTY" and s.get("period") in target_periods
            ]
        else:
            candidates = list(RTTY_WEATHER_STATIONS)

        self.rtty_scan_active = True
        self.app.carrier_scan_active = True
        self.scan_started_mono = time.monotonic()
        self.current_activity = "SCAN"
        self.active_pipeline = "RTTY"
        self.flush_audio_backlogs()
        self.app.set_busy_state(True, f"SCAN RTTY QUALITÉ ({len(candidates)} fréquences)...")
        self.app.log_event(
            f"🔍 [Scan RTTY Pondéré Qualité] Test de {len(candidates)} fréquences {[s['id'] for s in candidates]} "
            f"(mode {'JOUR' if is_day_utc else 'NUIT'} UTC)..."
        )

        results = []

        def _step():
            if not candidates or not self.rtty_scan_active:
                _finish()
                return
            st = candidates.pop(0)
            try:
                self.app.radio.set_wefax_frequency(st["freq"], apply_usb_offset=True)
                self.app._sync_ui_from_hardware()
                if hasattr(self.app, "bulletins_ui"):
                    self.app.bulletins_ui.refresh_status(scanning_station=st)
            except Exception:
                pass
            self.app.root.after(1450, lambda s=st: _measure(s, []))

        def _measure(st, samples):
            if not self.rtty_scan_active:
                _finish()
                return
            q = RTTYITA2Decoder.evaluate_rtty_quality_on_chunk(
                self.app.audio_ring.copy(),
                self.app.audio_fs,
                center_hz=st["center_hz"],
                shift_hz=st["shift_hz"],
            )
            samples.append(q)
            if len(samples) < 2:
                self.app.root.after(550, lambda: _measure(st, samples))
                return
            qual_pct, ok_fsk, med_m, med_s, weighted_score = self.rtty_quality_pct(samples, st["freq"])
            valid_cnt = 1 if ok_fsk else 0
            tag = (
                f"Qualité {qual_pct}% · ÉMISSION ACTIVE"
                if valid_cnt >= 1
                else f"Qualité {qual_pct}% · Silence"
            )
            self.rtty_snr_map[st["id"]] = f"M:{med_m:+.1f}/S:{med_s:+.1f}dB ({tag})"
            results.append((valid_cnt >= 1, qual_pct, weighted_score, st))
            self.prop.update(
                st["id"],
                st["freq"],
                "NAVTEX" if "NAVTEX" in st.get("protocol", "") else "RTTY",
                qual_pct,
                valid_cnt >= 1,
                f"M {med_m:+.1f} / S {med_s:+.1f} dB",
                source="scan",
            )
            self.app.log_event(
                f"SCAN_RTTY {st['id']} ({st['freq']:.1f} kHz) : Mark={med_m:+.1f}dB Space={med_s:+.1f}dB "
                f"Qualité_Estimée={qual_pct}% ({tag})"
            )
            self.app.root.after(120, _step)

        def _finish():
            self.prop.save()
            if hasattr(self.app, "_refresh_propagation_views"):
                self.app._refresh_propagation_views()
            self.rtty_scan_active = False
            self.app.carrier_scan_active = False
            self.app.set_busy_state(False)
            self.flush_audio_backlogs()
            best = max(results, key=lambda item: (item[0], item[1], item[2])) if results else None
            chosen_st = best[3] if best else RTTY_WEATHER_STATIONS[1]
            best_q = best[1] if best else 15
            active_ok = bool(best and best[0])
            if active_ok:
                self.app.log_event(
                    f"✅ [Scan RTTY terminé] Émission RTTY active retenue : {chosen_st['id']} "
                    f"({chosen_st['freq']:.1f} kHz · Qualité Estimée={best_q}%)"
                )
            else:
                self.app.log_event(
                    f"ℹ️ [Scan RTTY terminé] Aucune émission RTTY active à cette minute (prochain bulletin selon horaire UTC) — Veille sur {chosen_st['id']} ({chosen_st['freq']:.1f} kHz)"
                )
            self.switch_to_rtty_pipeline(chosen_st, reason=f"Sélection scan RTTY ({best_q}%)")
            if hasattr(self.app, "bulletins_ui"):
                self.app.bulletins_ui.sync_station_combo()
                self.app.bulletins_ui.refresh_status()
            if on_complete_cb:
                on_complete_cb(chosen_st)

        _step()

    def switch_to_rtty_pipeline(self, station_dict: dict = None, reason: str = "Passage en mode RTTY"):
        if getattr(self.app, "carrier_scan_active", False) or getattr(self.app, "connection_busy", False):
            return False

        self.remember_wefax_station_if_valid()

        if self.active_pipeline == "WEFAX":
            if int(getattr(self.app, "rx_current_line", 0)) > 30 and not getattr(
                self.app, "waiting_after_stop", False
            ):
                self.app._finalize_completed_wefax_chart("Sauvegarde avant passage en RTTY")

        st = station_dict or self.active_rtty_station
        self.active_rtty_station = st
        self.current_activity = "TRANSITION"
        self.active_pipeline = "RTTY"
        self.last_transition_mono = time.monotonic()
        self.disarm_base_periodic_scan_timers()

        self.rtty.configure(
            sample_rate=self.app.audio_fs,
            baud=st["baud"],
            shift_hz=st["shift_hz"],
            center_hz=st["center_hz"],
            protocol=st.get("protocol", "RTTY_ITA2"),
        )
        self.rtty.reset()
        self.rtty_last_logged_len = len(self.rtty_raw_buffer)
        self.rtty_segment = ""
        self.rtty_session_start_utc = self.workspace.begin_document_reception()

        self.flush_audio_backlogs()
        self.app.rx_current_line = 0
        self.app.rx_sheet_initialized_for_live = False

        if self.app.radio.port_open and self.app.radio.handshake_ok:
            self.app.radio.set_wefax_frequency(st["freq"], apply_usb_offset=True)
        else:
            self.app.radio.actual_freq_khz = float(st["freq"])
            self.app.radio.actual_dial_khz = round(float(st["freq"]) + self.app.radio.usb_dial_offset_khz, 2)
            self.app.radio.update_station_metadata_by_freq(float(st["freq"]))
        self.app._sync_ui_from_hardware()
        mode = (
            "NAVTEX"
            if "NAVTEX" in st.get("protocol", "")
            else ("RTTY_LF" if st["shift_hz"] < 200 else "RTTY")
        )
        self.app.root.after(2500, lambda m=mode: self.app._check_audio_passband(m))

        self.current_activity = "RECEPTION_RTTY"
        if hasattr(self.app, "show_teleprinter"):
            try:
                self.app.show_teleprinter(True, st, self.current_item)
            except Exception:
                pass
        self.app.log_event(
            f"📠 [Mode RTTY Actif] {reason} -> Poste accordé sur {st['id']} ({st['freq']:.1f} kHz | "
            f"{st['baud']:.0f} Bd / shift {st['shift_hz']:.0f} Hz)."
        )
        return True

    def switch_to_wefax_pipeline(
        self,
        reason: str = "Retour aux cartes WEFAX",
        launch_prescan: bool = False,
        target_family: str = "DWD",
        code: str = "",
        when_str: str = "",
    ):
        if getattr(self.app, "carrier_scan_active", False) or getattr(self.app, "connection_busy", False):
            return False

        # On ne sauvegarde automatiquement en quittant le RTTY que si le bulletin est exploitable (pas du bruit)
        if self.active_pipeline == "RTTY" and len(self.rtty_segment.strip()) >= 45:
            if self.rtty.last_metrics.get("lexical_quality", 0.0) >= 0.4:
                self.save_current_rtty_bulletin(trigger_reason=reason, text=self.rtty_segment)
        self.rtty_raw_buffer = ""
        self.rtty_segment = ""
        self.rtty_last_logged_len = 0

        self.current_activity = "TRANSITION"
        self.active_pipeline = "WEFAX"
        if hasattr(self.app, "show_teleprinter"):
            try:
                self.app.show_teleprinter(False)
            except Exception:
                pass
        self.last_transition_mono = time.monotonic()
        self.disarm_base_periodic_scan_timers()
        self.app.current_snr_db = 0.0

        is_day = 7 <= datetime.now(timezone.utc).hour <= 17
        family_default = (
            (8040.0 if is_day else 4610.0) if target_family == "GYA" else (13882.5 if is_day else 7880.0)
        )
        target_wefax_freq = (
            self.wefax_return_freq_khz if is_wefax_frequency(self.wefax_return_freq_khz) else family_default
        )

        if (not launch_prescan) or is_rtty_frequency(getattr(self.app.radio, "actual_freq_khz", 0.0)):
            if self.app.radio.port_open and self.app.radio.handshake_ok:
                self.app.radio.set_wefax_frequency(target_wefax_freq, apply_usb_offset=True)
            else:
                self.app.radio.actual_freq_khz = float(target_wefax_freq)
                self.app.radio.update_station_metadata_by_freq(float(target_wefax_freq))
            self.app._sync_ui_from_hardware()

        self.flush_audio_backlogs()
        self.app.waiting_after_stop = False
        self.app.rx_decoding_active = True
        self.app.btn_rx_start.set_state(True)
        self.app.btn_top_rx.set_state(True)
        self._style_wefax_toggle_button()
        self.current_activity = "SURVEILLANCE"
        self.app.log_event(f"🗺️ [Mode WEFAX Actif] {reason}")

        if launch_prescan and self.app.radio.handshake_ok and self.app.audio_live_connected:
            self.trigger_targeted_wefax_prescan(target_family, code, when_str)
        return True

    def _style_wefax_toggle_button(self):
        if hasattr(self.app, "btn_top_rx"):
            on = bool(getattr(self.app, "rx_decoding_active", True))
            try:
                self.app.btn_top_rx.configure(
                    text="[ON] 🟢 Réception WEFAX" if on else "[OFF] ⚪ Réception WEFAX",
                    bg="#059669" if on else "#334155",
                    fg="#ffffff" if on else "#cbd5e1",
                )
            except Exception:
                pass

    # ================================================================== plan de réception
    def _load_plan(self):
        plan = {
            "programs": list(DEFAULT_PROGRAMS),
            "categories": list(DEFAULT_INTEREST),
            "rtty_enabled": True,
            "veille_enabled": True,
            "athens_enabled": True,
            "spectral_watch": True,
            "qth": list(DEFAULT_QTH),
            "radius_km": 500,
        }
        try:
            if self.plan_path.is_file():
                data = json.loads(self.plan_path.read_text(encoding="utf-8"))
                for k in plan:
                    if k in data:
                        plan[k] = data[k]
        except (OSError, ValueError):
            pass
        plan["categories"] = [c for c in plan["categories"] if c in CATEGORIES] or list(DEFAULT_INTEREST)
        plan["programs"] = [p for p in plan["programs"] if p in (1, 2)] or list(DEFAULT_PROGRAMS)
        return plan

    def save_plan(self, plan):
        self.plan.update(plan)
        self.scheduler.programs = tuple(self.plan["programs"])
        self.scheduler.categories = tuple(self.plan["categories"])
        self.scheduler.rtty_enabled = bool(self.plan["rtty_enabled"])
        try:
            from wefax_station.storage.atomic import atomic_json

            atomic_json(self.plan_path, self.plan)
        except Exception:
            pass
        self.app.log_event(
            "🗓️ Plan de réception enregistré : "
            + ", ".join(CATEGORIES[c].split(" (")[0] for c in self.plan["categories"])
            + f" · programmes RTTY {self.plan['programs']} · veille {'active' if self.plan['veille_enabled'] else 'désactivée'}"
        )

    @staticmethod
    def _is_day(now=None):
        return 6 <= (now or datetime.now(timezone.utc)).hour < 18

    @staticmethod
    def _period_ok(st, is_day):
        per = str(st.get("period", "JOUR/NUIT"))
        if "JOUR/NUIT" in per or "/" in per and "4H" in per:
            return True
        return ("JOUR" in per) if is_day else ("NUIT" in per)

    def _rtty_station(self, sid):
        return next((s for s in RTTY_WEATHER_STATIONS if s["id"] == sid), None)

    def program_station_ids(self, programs=None, is_day=None):
        is_day = self._is_day() if is_day is None else is_day
        ids = []
        for p in programs or self.plan["programs"]:
            for sid in PROGRAM_STATIONS.get(p, ()):
                st = self._rtty_station(sid)
                if st is not None and self._period_ok(st, is_day):
                    ids.append(sid)
        return ids

    # ------------------------------------------------------------------ suivi du texte RTTY
    def _reset_rtty_tracking(self):
        self._text_status_mono = None
        now = time.monotonic()
        self._rtty_recent = ""
        self.rtty_service_since = None
        self.rtty_last_text_mono = 0.0
        self.rtty_nosig_since = now
        self.rtty_end_marker = False
        self.rtty_end_mono = None
        self._chars_since_zczc = 0
        self._last_zczc_mono = -1e9
        self._last_nnnn_mono = -1e9

    END_MIN_CHARS = 500  # un NNNN ne clôt le bulletin d'intérêt que s'il ferme un vrai texte…
    END_MIN_ELAPSED_S = 240  # … ou si le créneau a commencé depuis plus de 4 min

    def _nnnn_closes_item(self):
        """Le NNNN reçu termine-t-il le bulletin attendu (et pas la note de service qui le précède) ?"""
        if getattr(self, "_chars_since_zczc", 0) >= self.END_MIN_CHARS:
            return True
        it = self.current_item
        if it is None:
            return True
        return (datetime.now(timezone.utc) - it.start).total_seconds() >= self.END_MIN_ELAPSED_S

    def on_rtty_text(self, chars):
        now = time.monotonic()
        self._rtty_recent = (self._rtty_recent + chars)[-200:]
        # 2.8.9 — début / fin de chaque bulletin du flux (le DWD les enchaîne sans boucle de service)
        self._chars_since_zczc = getattr(self, "_chars_since_zczc", 0) + len(chars)
        tail = self._rtty_recent[-40:]
        if marker_received(tail, "ZCZC") and now - getattr(self, "_last_zczc_mono", -1e9) > 20:
            self._last_zczc_mono = now
            self._chars_since_zczc = 0
        if marker_received(tail, "NNNN") and now - getattr(self, "_last_nnnn_mono", -1e9) > 20:
            self._last_nnnn_mono = now
            if not self.rtty_end_marker and self._nnnn_closes_item():
                self.rtty_end_marker = True
                self.rtty_end_mono = now
        r = service_ratio(self._rtty_recent[-90:])
        if r >= 0.6:
            if self.rtty_service_since is None:
                self.rtty_service_since = now
        elif r <= 0.3:
            self.rtty_service_since = None
            if any(c.isalnum() for c in chars):
                self.rtty_last_text_mono = now

    TEXT_STATUS_PERIOD_S = 60.0

    def _log_text_listening_status(self, mono):
        """2.9.0 — pendant une écoute texte, une ligne d'état par minute tant qu'aucun caractère n'arrive.

        Le 18/11, de 18:49 à 19:01 sur 518 kHz puis de 19:02 à 19:11 sur 490 kHz, le journal ne contenait
        aucune ligne : impossible de savoir si le poste entendait une émission FSK, du bruit, ou rien."""
        buf_len = len(self.rtty_raw_buffer)
        last = getattr(self, "_text_status_mono", None)
        if last is None:
            self._text_status_mono, self._text_status_len = mono, buf_len
            return
        if mono - last < self.TEXT_STATUS_PERIOD_S:
            return
        new_chars = buf_len - getattr(self, "_text_status_len", 0)
        self._text_status_mono, self._text_status_len = mono, buf_len
        if new_chars > 40:
            return  # le texte reçu est déjà journalisé (📠 RTTY RX)
        m = self.rtty.last_metrics or {}
        st = self.active_rtty_station or {}
        r = self.app.radio
        pamp = getattr(r, "actual_preamp", None)
        self.app.log_event(
            # 2.9.3 — nom de l'émetteur attendu (« NAVTEX-FR » désignait aussi La Maddalena I sur 490 kHz)
            f"📡 Écoute {self._listening_name(st)} {float(st.get('freq', 0)):.1f} kHz : "
            + ("FSK reconnue" if m.get("signal_compatible") else f"aucune FSK {float(st.get('shift_hz', 0)):.0f} Hz reconnue")
            + f" (Mark {m.get('f_mark_hz', 0):.0f} Hz {m.get('mark_snr_db', 0):+.1f} dB · Space {m.get('f_space_hz', 0):.0f} Hz "
            f"{m.get('space_snr_db', 0):+.1f} dB) · {new_chars} car. en 1 min · "
            f"P.AMP {'OFF' if pamp == 0 else pamp} · S-mètre {getattr(r, 's_meter_label', '') or '—'}"
        )

    # ------------------------------------------------------------------ décision
    def evaluate_hybrid_schedule(self, initial_launch: bool = False):
        if getattr(self.app, "carrier_scan_active", False):
            if (
                not self.veille_active
                and self.scan_started_mono > 0
                and (time.monotonic() - self.scan_started_mono) > 70.0
            ):
                self.rtty_scan_active = False
                self.app.carrier_scan_active = False
                self.app.set_busy_state(False)
                self.flush_audio_backlogs()
                self.app.log_event(
                    "🛡️ [Watchdog] Scan expiré (> 70 s) — interface déverrouillée automatiquement."
                )
            else:
                self.current_activity = "SCAN"
                return
        self.disarm_base_periodic_scan_timers()
        if (
            self.manual_hold
            or self.requested_mode == "RELECTURE"
            or getattr(self.app, "connection_busy", False)
            or self.veille_active
        ):
            return
        if not getattr(self.app.radio, "handshake_ok", False) or not self.app.audio_live_connected:
            return

        now = datetime.now(timezone.utc)
        mono = time.monotonic()
        chart_drawing = bool(
            self.active_pipeline == "WEFAX"
            and int(getattr(self.app, "rx_current_line", 0)) >= 3
            and not getattr(self.app, "waiting_after_stop", False)
            and getattr(self.app, "rx_image_armed", False)
        )
        if chart_drawing:
            self.last_chart_mono = mono
        try:
            self._observe_programme(now, chart_drawing)
        except Exception:
            pass

        if self.requested_mode == "BULLETINS":
            self.current_activity = "RECEPTION_RTTY"
            return

        if self.active_pipeline == "RTTY":
            if self.rtty.last_metrics.get("signal_compatible"):
                self.rtty_nosig_since = None
            elif self.rtty_nosig_since is None:
                self.rtty_nosig_since = mono
            self._log_text_listening_status(mono)

        # démarrage : mesure des fréquences RTTY / NAVTEX dès que le poste est libre
        tier_here = getattr(self.app, "_scan_signal_ranks", {}).get(self.app.radio.active_station_id, 0)
        quiet_gap = (
            bool(getattr(self.app, "waiting_after_stop", False)) or (mono - self.last_chart_mono) >= 300
        )
        if (
            self.startup_survey_pending
            and self.active_pipeline == "WEFAX"
            and not chart_drawing
            and self.plan["rtty_enabled"]
            and (tier_here < 3 or quiet_gap)
            and mono - getattr(self.app, "last_scan_request", 0.0) > 15
        ):
            self.startup_survey_pending = False
            ids = self.program_station_ids(programs=(1, 2))
            self.run_veille(ids, reason="Démarrage : mesure des fréquences RTTY", max_stations=6)
            return

        st = ScheduleState(
            now=now,
            pipeline=self.active_pipeline,
            chart_drawing=chart_drawing,
            seconds_since_chart=mono - self.last_chart_mono,
            rtty_text_active=(mono - self.rtty_last_text_mono) < 30.0,
            rtty_service_s=(mono - self.rtty_service_since) if self.rtty_service_since else 0.0,
            rtty_no_signal_s=(mono - self.rtty_nosig_since) if self.rtty_nosig_since else 0.0,
            rtty_end_marker=self.rtty_end_marker,
            rtty_end_age_s=(mono - self.rtty_end_mono) if getattr(self, "rtty_end_mono", None) else None,
            current_item=self.current_item,
            done_keys=tuple(self.done_items),
            is_day=self._is_day(now),
            wefax_family=(get_wefax_station_by_freq(float(getattr(self.app.radio, "actual_freq_khz", 0.0))) or {}).get(
                "family", ""
            )
            if self.active_pipeline == "WEFAX"
            else "",
            athens_enabled=bool(self.plan.get("athens_enabled", True)) and self.requested_mode != "RTTY",
            chart_slots=tuple((getattr(self.app, "schedule_data", None) or {}).get(self.upcoming_wefax_family(), ())),
            received_recent=self.received_recent_labels(),
            preferred_family=self.preferred_family(),
            pref_slots=tuple((getattr(self.app, "schedule_data", None) or {}).get(self.preferred_family(), ())),
            athens_unconfirmed=mono < float(getattr(self, "ath_unconfirmed_until_mono", 0.0) or 0.0),
            chart_from_start=bool(getattr(self.app, "rx_sheet_had_start", True)),
            chart_reliable_pct=self._chart_reliable_pct(),
        )
        if self.requested_mode == "WEFAX":
            self.scheduler.rtty_enabled = False
        else:
            self.scheduler.rtty_enabled = bool(self.plan["rtty_enabled"])
        d = self.scheduler.decide(st)
        hold = self.manual_hold_active(mono)  # évalué à chaque tour : la limite de 45 min libère à l'heure
        if d.action != "STAY" and hold:
            # 2.11.0 — choix opérateur (bouton « Stations ») : pas de changement de fréquence automatique
            d = Decision("STAY", f"Choix opérateur {self.operator_choice['station']} maintenu (au lieu de : {d.reason})")
        self.last_decision = d.reason
        # 2.8.9 — chaque changement de décision est écrit au journal : on saura toujours POURQUOI le poste
        # reste en RTTY (ou en WEFAX)
        key = (self.active_pipeline, d.action, d.reason)
        if key != getattr(self, "_last_logged_decision", None):
            self._last_logged_decision = key
            self.app.log_event(f"🤖 AUTOMATISME [{self.active_pipeline}] {d.action} — {d.reason}")
        if d.action == "STAY":
            if self.active_pipeline == "WEFAX":
                self.current_activity = "RECEPTION_WEFAX" if chart_drawing else "SURVEILLANCE"
            else:
                self.current_activity = "RECEPTION_RTTY"
            return
        if d.action == "GO_RTTY":
            self.start_rtty_item(d.item, d.reason)
        elif d.action == "NEXT_RTTY":
            self.continue_with_item(d.item, d.reason)
        elif d.action == "GO_WEFAX":
            self.end_rtty_and_return(d.reason)
        elif d.action == "VEILLE":
            if not self.plan.get("veille_enabled", True):
                self.scheduler.last_veille = mono
                return
            if not quiet_gap:
                return  # uniquement dans le temps mort après un STOP (ou sans carte depuis 5 min)
            self.run_veille(None, reason=d.reason)
        elif d.action in ("GO_ATHENS", "LEAVE_ATHENS"):
            # 2.8.7 — bascule de famille WEFAX (jamais pendant une carte : décidé seulement hors tracé)
            go = d.action == "GO_ATHENS"
            # 2.9.3 — en quittant Athènes : famille de référence (DWD) et sa meilleure fréquence, plus Northwood
            fam = "ATH" if go else self.preferred_family()
            self.app.log_event(f"🏛️ {d.reason}.")
            if go:
                target = 8105.0 if self._is_day(now) else 4481.0
                self._ath_check_pending = True
            else:
                st_best = self.best_family_station(fam)
                target = float(st_best["freq"]) if st_best else (13882.5 if self._is_day(now) else 7880.0)
            self.wefax_return_freq_khz = target
            if self.app.radio.port_open and self.app.radio.handshake_ok:
                self.app.radio.set_wefax_frequency(target, apply_usb_offset=True)
            else:
                self.app.radio.actual_freq_khz = float(target)
            self.app.radio.update_station_metadata_by_freq(float(target))
            self.app._sync_ui_from_hardware()
            self.scheduler.last_wefax_recheck = mono
            if self.app.radio.handshake_ok and self.app.audio_live_connected:
                # 2.9.3 — contrôle forcé : juste après le QSY, l'indice de qualité décrit encore l'ancienne
                # station (le 19/11 à 08:43, « Qualité déjà optimale sur SVJ4 (79 %) » venait de DDK3)
                self.trigger_targeted_wefax_prescan(fam, "ATH" if go else "RETOUR", "maintenant", force=True)
        elif d.action == "WEFAX_RECHECK":
            self.scheduler.last_wefax_recheck = mono
            cur = get_wefax_station_by_freq(float(getattr(self.app.radio, "actual_freq_khz", 0.0)))
            cur_fam = cur["family"] if cur else "DWD"
            fam = self.recheck_family(cur_fam, now)
            # 2.9.5 — changement de famille : arriver juste avant l'heure de la carte suivante de cette famille
            # pour la prendre dès son START (le 19/11 à 11:56, arrivée sur Northwood au milieu d'une carte)
            if fam != cur_fam:
                nxt = self._next_family_slot(fam, now)
                if nxt is not None:
                    wait_s = (nxt - now).total_seconds() - self.FAMILY_ARRIVAL_LEAD_S
                    if wait_s > 20:
                        self.scheduler.last_wefax_recheck = (
                            mono + wait_s - self.scheduler.WEFAX_SILENCE_RECHECK_S
                        )
                        self.app.log_event(
                            f"⏳ Contrôle de {fam} reporté à {now + timedelta(seconds=wait_s):%H:%M:%S} UTC : arrivée "
                            f"juste avant la carte de {nxt:%H:%M} pour la recevoir entière."
                        )
                        return
            self.app.log_event(f"🔁 {d.reason} ({fam}" + (f", depuis {cur_fam}" if fam != cur_fam else "") + ").")
            self.trigger_targeted_wefax_prescan(fam, "CONTROLE", "maintenant")
        elif d.action == "GO_FAMILY":
            # 2.9.1 — retour sur la famille de référence avant l'heure de sa carte
            fam = self.preferred_family()
            self.app.log_event(f"🗓️ {d.reason}.")
            # 2.9.5 — carte prise en cours de route encore en tracé : archivée (fragment ou carte) avant le QSY
            if (
                int(getattr(self.app, "rx_current_line", 0) or 0) > 100
                and not getattr(self.app, "waiting_after_stop", False)
                and hasattr(self.app, "_finalize_completed_wefax_chart")
            ):
                try:
                    self.app._finalize_completed_wefax_chart("Carte prise en cours de route, cédée à la carte " + fam)
                    self.app._reset_blank_rx_sheet()
                    self.app.waiting_after_stop = True
                except Exception as exc:
                    self.app.log_event("Archivage avant retour " + fam + " : " + repr(exc))
            st_best = self.best_family_station(fam)
            target = float(st_best["freq"]) if st_best else (13882.5 if self._is_day(now) else 7880.0)
            self.wefax_return_freq_khz = target
            if self.app.radio.port_open and self.app.radio.handshake_ok:
                self.app.radio.set_wefax_frequency(target, apply_usb_offset=True)
            else:
                self.app.radio.actual_freq_khz = float(target)
            self.app.radio.update_station_metadata_by_freq(float(target))
            self.app._sync_ui_from_hardware()
            self.scheduler.last_wefax_recheck = mono
            if self.app.radio.handshake_ok and self.app.audio_live_connected:
                self.trigger_targeted_wefax_prescan(fam, "PROGRAMME", "avant la carte", force=True)

    def plan_summary(self, n=3):
        """(ligne « maintenant », ligne « ensuite ») pour l'interface."""
        now = datetime.now(timezone.utc)
        if self.veille_active:
            cur = "Veille de propagation en cours"
        elif self.active_pipeline == "RTTY":
            st = self.active_rtty_station
            what = self.current_item.label if self.current_item else "écoute choisie par l'opérateur"
            cur = f"RTTY {st['id']} {st['freq']:.1f} kHz · {what}"
        else:
            lines = int(getattr(self.app, "rx_current_line", 0))
            drawing = lines >= 3 and not getattr(self.app, "waiting_after_stop", False)
            cur = (
                f"Carte WEFAX en cours ({lines} lignes)"
                if drawing
                else "WEFAX : attente de la carte suivante"
            )
        entries = self.upcoming_entries(now, n=n + 2)
        if entries:
            later = " · ".join(entries)
        elif self.requested_mode == "WEFAX":
            later = "Mode cartes seules : aucun bulletin texte planifié"
        else:
            later = "Aucun bulletin d'intérêt dans les 4 h (voir Réglages › Plan de réception)"
        return cur, later

    def preferred_family(self):
        from wefax_station.core.schedules import PREFERRED_WEFAX_FAMILY

        return str(self.plan.get("wefax_famille_reference", PREFERRED_WEFAX_FAMILY) or PREFERRED_WEFAX_FAMILY)

    def preferred_chart_soon(self, now=None, before_s=1800, after_s=600):
        """Carte de la famille de référence commencée il y a moins de `after_s` ou prévue dans `before_s`."""
        from wefax_station.core.schedules import chart_slots_around

        now = now or datetime.now(timezone.utc)
        slots = (getattr(self.app, "schedule_data", None) or {}).get(self.preferred_family(), ())
        soon = chart_slots_around(slots, now, before_s=before_s, after_s=after_s)
        return soon[0] if soon else None

    def recheck_family(self, cur_fam, now=None):
        """2.9.1 — famille à contrôler après 8 min sans carte.

        Carte de référence (DWD) en cours ou prévue dans les 30 min : on contrôle le DWD, même depuis une autre
        famille (avant : seulement la famille courante, d'où le poste resté sur Northwood le 18/11). Sinon, dans
        un trou du programme DWD (22:12-04:30 par exemple), on contrôle Northwood, qui émet 24 h/24."""
        pref = self.preferred_family()
        if cur_fam == "ATH":
            return cur_fam
        if self.preferred_chart_soon(now) is not None:
            return pref
        return "GYA" if cur_fam == pref else cur_fam

    def upcoming_wefax_family(self):
        if self.active_pipeline == "WEFAX":
            cur = get_wefax_station_by_freq(float(getattr(self.app.radio, "actual_freq_khz", 0.0)))
            if cur:
                return cur.get("family", "DWD")
        st = get_wefax_station_by_freq(float(getattr(self, "wefax_return_freq_khz", 0.0) or 0.0))
        return (st or {}).get("family", "DWD")

    def upcoming_entries(self, now=None, n=5):
        """2.9.0 — prochains bulletins d'intérêt ET prochaines cartes, dans l'ordre des heures (UTC).

        Jusqu'en 2.8.9, « Ensuite : » ne citait que les bulletins texte ; les cartes à venir n'y figuraient pas."""
        from wefax_station.core.schedules import chart_short_label, upcoming_charts

        now = now or datetime.now(timezone.utc)
        ev = []
        if self.scheduler.rtty_enabled:
            for it in self.scheduler.next_items(now, n=n):
                ev.append((it.start, 1, f"{it.start:%H:%M} {it.label}"))
        if self.requested_mode != "BULLETINS":
            fam = self.upcoming_wefax_family()
            slots = (getattr(self.app, "schedule_data", None) or {}).get(fam, [])
            for t, code, desc in upcoming_charts(slots, now, horizon_min=240, n=3):
                ev.append((t, 0, f"{t:%H:%M} {chart_short_label(code, desc)}"))
        ev.sort(key=lambda e: (e[0], e[1]))
        return [txt for _, _, txt in ev[:n]]

    # ------------------------------------------------------------------ bascules
    def start_rtty_item(self, item, reason):
        # 2.8.6 — bulletin DWD ignoré si toutes ses fréquences ont été mesurées muettes récemment : le
        # 17/11 à 02:59, le poste est parti sur DDK9 (9 %) pour un texte illisible et la carte GYA de 03:00
        # a été perdue entière. Les créneaux NAVTEX sont toujours écoutés.
        if not item.is_navtex:
            ids = self.program_station_ids(programs=(item.program,))
            recent = [self.prop.get(i) for i in ids]
            recent = [e for e in recent if e is not None and e.age_s() <= 45 * 60]
            if recent and len(recent) == len(ids) and max(e.quality for e in recent) < 15:
                self.done_items.add(item.key)
                self.app.log_event(
                    f"⏭️ {item.describe()} ignoré : aucune fréquence du programme audible "
                    f"(meilleure mesure {max(e.quality for e in recent)} % il y a moins de 45 min) — les cartes continuent."
                )
                return
        self.current_item = item
        self._item_chars_start = len(self.rtty_raw_buffer or "")
        self._reset_rtty_tracking()
        if item.is_navtex:
            st = self._rtty_station(item.program)
            if st is not None:
                self.switch_to_rtty_pipeline(st, reason=reason)
            return
        ids = self.program_station_ids(programs=(item.program,))
        best = self.prop.best(ids, max_age_s=1800)
        if best:
            e = self.prop.get(best)
            self.switch_to_rtty_pipeline(
                self._rtty_station(best),
                reason=f"{reason} — {best} retenu d'après la table de propagation ({e.quality} %, "
                f"mesuré il y a {int(e.age_s() // 60)} min)",
            )
        else:
            # 2.8.9 — station vue forte sur le spectre il y a moins de 5 min : pas besoin de scan
            hint = self.app.spectral_best(ids) if hasattr(self.app, "spectral_best") else None
            if hint is not None:
                sid, r = hint
                self.switch_to_rtty_pipeline(
                    self._rtty_station(sid),
                    reason=f"{reason} — {sid} vu {r['label']} sur le spectre ({r['contrast']:+.0f}, il y a "
                    f"{int((time.time() - r['ts']) // 60)} min) : pris sans scan",
                )
                self._reset_rtty_tracking()
                return
            self.app.log_event(f"📠 {reason} — mesure des fréquences du programme avant la bascule.")
            self.trigger_rtty_frequency_scan(station_ids=ids)
        self._reset_rtty_tracking()

    def continue_with_item(self, item, reason):
        """Bulletin d'intérêt suivant juste après un NNNN : on reste sur la même fréquence si c'est le
        même programme, sinon on passe par le choix de fréquence habituel."""
        if self.current_item is not None:
            self.done_items.add(self.current_item.key)
            self._record_text_station_result(self.current_item)
        same = (
            self.current_item is not None
            and not item.is_navtex
            and item.program == self.current_item.program
            and self.active_pipeline == "RTTY"
        )
        self.app.log_event(f"📠 {reason}" + (" — même fréquence." if same else ""))
        if (
            not same
            and self.active_pipeline == "RTTY"
            and len(self.rtty_segment.strip()) >= 45
            and self.rtty.last_metrics.get("lexical_quality", 0.0) >= 0.4
        ):
            # le message en cours (sans NNNN) est archivé avant de changer de station
            self.save_current_rtty_bulletin(trigger_reason="Changement de créneau", text=self.rtty_segment)
            self.rtty_segment = ""
        if same:
            self.current_item = item
            self._item_chars_start = len(self.rtty_raw_buffer or "")
            self._reset_rtty_tracking()
            return
        self.start_rtty_item(item, reason)

    def _record_text_station_result(self, item, now=None):
        """2.9.2 — bilan du créneau pour la station : réussite (≥ 40 caractères), échec (créneau écouté jusqu'au
        bout sans texte) ou non concluant (créneau écourté). Journalise la mise en sommeil et la reprise."""
        from wefax_station.hybrid.text_station_health import STATION_NAMES, station_key

        health = getattr(self, "text_health", None)
        key = station_key(item)
        if health is None or key is None:
            return None
        now = now or datetime.now(timezone.utc)
        buf = self.rtty_raw_buffer or ""
        start = int(getattr(self, "_item_chars_start", 0) or 0)
        chars = len(buf[start:].strip()) if 0 <= start <= len(buf) else len(buf.strip())
        complete = now >= item.end - timedelta(seconds=90)
        res = health.record(key, chars, complete=complete)
        name = STATION_NAMES.get(key, key)
        if res == "SOMMEIL":
            self.app.log_event(
                f"💤 [STATIONS TEXTE] {name} : aucun texte sur plusieurs créneaux complets — mise en sommeil "
                f"({health.status_text(key)}). Les cartes restent prioritaires ; Réglages › Plan de réception pour "
                "la réactiver."
            )
        elif res == "REPRISE":
            self.app.log_event(f"✅ [STATIONS TEXTE] {name} reçue à nouveau : station réactivée.")
        elif res == "ECHEC":
            self.app.log_event(f"ℹ️ [STATIONS TEXTE] {name} : créneau sans texte ({health.status_text(key)}).")
        return res

    def best_family_station(self, fam, now_ts=None):
        """2.9.2 — meilleure fréquence d'une famille WEFAX : mesure de propagation (≤ 30 min) ET spectre du
        poste (≤ 5 min). Une observation spectrale plus récente que la mesure retenue, ou une mesure qui
        n'a pas reconnu d'émission, cède la place à la station vue forte sur le spectre. Le 19/11 à 06:33,
        au retour du RTTY, le poste est allé sur DDK6 (ancienne mesure) alors que DDK3 était fort."""
        ids = [s["id"] for s in WEFAX_STATIONS if s.get("family") == fam]
        best = self.prop.best(ids, max_age_s=1800)
        reason = f"mesure de propagation ({best})" if best else ""
        hint = None
        if hasattr(self.app, "spectral_best"):
            try:
                hint = self.app.spectral_best(ids)
            except Exception:
                hint = None
        if hint is not None:
            sid, r = hint
            e = self.prop.get(best) if best else None
            if e is None or not e.active or float(r.get("ts", 0)) >= float(e.measured or 0) or sid == best:
                if sid != best:
                    reason = f"{sid} vu fort sur le spectre ({r.get('label', '')}, {r.get('contrast', 0):+.0f}) " + (
                        f"plus récemment que la mesure de {best}" if best else ""
                    )
                best = sid
        e = self.prop.get(best) if best else None
        if hint is None and (e is None or not e.active):
            # 2.10.0 — aucune émission reconnue dans la famille : la mesure la plus récente n'est pas un
            # critère (le 19/11 à 20:01 UTC, retour sur DDK6 13 882,5 kHz, fréquence de jour, parce que
            # c'était la dernière mesurée). On prend la fréquence adaptée à l'heure (jour / nuit).
            suited = self.suited_family_station(ids, now_ts=now_ts)
            if suited and suited != best:
                reason = f"{suited} : aucune émission reconnue récemment, fréquence adaptée à l'heure"
                best = suited
        st = next((s for s in WEFAX_STATIONS if s["id"] == best), None) if best else None
        self.last_family_choice_reason = reason.strip()
        return st

    def _chart_reliable_pct(self):
        """2.11.0 — % de lignes fiables de la carte en cours (None avant 2 min de tracé)."""
        app = self.app
        traced = int(getattr(app, "_chart_traced_lines", 0) or 0)
        if traced < 240:
            return None
        return 100.0 * int(getattr(app, "_chart_valid_lines", 0) or 0) / traced

    def suited_family_station(self, ids, now_ts=None):
        """Station de la famille la mieux adaptée à l'heure UTC (période JOUR / NUIT, bonus de propagation)."""
        from datetime import datetime, timezone

        when = datetime.fromtimestamp(now_ts, timezone.utc) if now_ts else datetime.now(timezone.utc)
        is_day = 7 <= when.hour <= 17
        current = getattr(self, "wefax_return_freq_khz", None)

        def score(st):
            period = str(st.get("period", "")).upper()
            fits = ("JOUR" in period) if is_day else ("NUIT" in period)
            e = self.prop.get(st["id"])
            q = e.quality if (e is not None and e.age_s() <= 1800) else 0
            return (
                fits,
                WeatherReliabilityEstimator.propagation_bonus_db(st["freq"], when.hour),
                q,
                current is not None and abs(float(st["freq"]) - float(current)) < 1.0,
            )

        cands = [s for s in WEFAX_STATIONS if s["id"] in ids]
        return max(cands, key=score)["id"] if cands else None

    def best_wefax_return(self):
        fam_st = get_wefax_station_by_freq(self.wefax_return_freq_khz)
        fam = fam_st["family"] if fam_st else "DWD"
        return self.best_family_station(fam)

    def end_rtty_and_return(self, reason):
        st = self.active_rtty_station
        if self.current_item is not None:
            self.done_items.add(self.current_item.key)
            self._record_text_station_result(self.current_item)
        try:
            rel = WeatherReliabilityEstimator.compute_rtty_reliability(self.rtty, self.rtty_raw_buffer)
            if len(self.rtty_raw_buffer.strip()) >= 40:
                self.prop.update(
                    st["id"],
                    st["freq"],
                    "NAVTEX" if "NAVTEX" in st.get("protocol", "") else "RTTY",
                    rel["score_pct"],
                    True,
                    rel.get("label", ""),
                    source="réception",
                )
                self.prop.save()
        except Exception:
            pass
        # 2.9.0 — le bulletin est archivé dans switch_to_wefax_pipeline : on garde son créneau sous la main
        self._ending_item = self.current_item
        self.current_item = None
        best = self.best_wefax_return()
        if best is not None:
            self.wefax_return_freq_khz = float(best["freq"])
            self.wefax_return_station = best["id"]
            why = getattr(self, "last_family_choice_reason", "")
            if why:
                self.app.log_event(f"📡 Retour aux cartes sur {best['id']} ({best['freq']} kHz) : {why}.")
        try:
            self.switch_to_wefax_pipeline(reason=reason)
        finally:
            self._ending_item = None

    # ------------------------------------------------------------------ propagation
    @staticmethod
    def rtty_quality_pct(samples, freq_khz):
        med_score = float(np.median([x["score_db"] for x in samples]))
        med_m = float(np.median([x["mark_snr_db"] for x in samples]))
        med_s = float(np.median([x["space_snr_db"] for x in samples]))
        valid_cnt = sum(1 for x in samples if x["valid_fsk"])
        weighted = med_score + WeatherReliabilityEstimator.propagation_bonus_db(freq_khz)
        if valid_cnt >= 1:
            q = int(round(max(45.0, min(100.0, (weighted + 4.0) * 2.5))))
        else:
            q = int(round(max(5.0, min(25.0, max(med_m, med_s) * 1.5))))
        return q, valid_cnt >= 1, med_m, med_s, weighted

    def record_wefax_scan(self, station, tier, score, proxy_db):
        q = {3: 70 + int(min(29, max(0, score))), 2: 50, 1: 25}.get(int(tier), 5)
        status = {
            3: "carte reconnue",
            2: "modulation compatible",
            1: "porteuse 1900 Hz",
            0: "rien d'exploitable",
        }
        self.prop.update(
            station["id"],
            station["freq"],
            "WEFAX",
            q,
            tier >= 2,
            (
                f"{status.get(int(tier), '?')} · {proxy_db:+.1f} dB"
                if proxy_db is not None
                else status.get(int(tier), "?")
            ),
            source="scan",
        )
        self.prop.save()

    # ------------------------------------------------------------------ choix manuel (2.11.0)
    # 2.11.1 — le choix opérateur a son propre attribut. En 2.11.0 il réutilisait « manual_hold », qui
    # existait déjà (pause manuelle / mode MANUEL) et qui bloque TOUT l'automatisme : le 24/11 après 22:22,
    # plus aucune décision ni aucun contrôle de fréquence de la nuit, et la limite de 45 min jamais atteinte.
    MANUAL_HOLD_MAX_S = 45 * 60

    def set_manual_hold(self, station_id):
        """Choix opérateur depuis le bouton « Stations » : l'automatisme ne change plus de fréquence jusqu'à la
        fin de la carte suivante (ou 45 min sans carte), ou jusqu'à « Rendre la main à l'automatique »."""
        self.operator_choice = {
            "station": station_id,
            "since": time.monotonic(),
            "charts": int(getattr(self, "charts_received_count", 0)),
        }
        self.app.log_event(
            f"🖐 Choix opérateur : {station_id} gardé jusqu'à la fin de la carte suivante (automatisme suspendu)."
        )

    def release_manual_hold(self, reason="Main rendue à l'automatique"):
        if getattr(self, "operator_choice", None):
            self.operator_choice = None
            self.app.log_event(f"🤖 {reason} : l'automatisme reprend le choix des fréquences.")
            cb = getattr(self.app, "_on_manual_hold_changed", None)
            if cb:
                try:
                    cb()
                except Exception:
                    pass

    def manual_hold_active(self, mono=None):
        h = getattr(self, "operator_choice", None)
        if not h:
            return False
        mono = time.monotonic() if mono is None else mono
        if int(getattr(self, "charts_received_count", 0)) > h["charts"]:
            self.release_manual_hold("Carte suivante reçue sur le choix opérateur")
            return False
        if mono - h["since"] > self.MANUAL_HOLD_MAX_S:
            self.release_manual_hold("45 min sans carte sur le choix opérateur")
            return False
        return True

    def record_chart_received(self, station_id, freq_khz, pixels_pct):
        self.charts_received_count = int(getattr(self, "charts_received_count", 0)) + 1
        if station_id and pixels_pct is not None:
            self.prop.update(
                station_id,
                freq_khz,
                "WEFAX",
                int(pixels_pct),
                True,
                f"carte reçue · {pixels_pct:.0f} % de pixels fiables",
                source="réception",
            )
            self.prop.save()

    def run_veille(self, station_ids=None, reason="Veille de propagation", max_stations=4):
        """Mesure rapide (≈ 3 s par fréquence, sans profil RF complet) de quelques fréquences périmées.

        Utilisée au démarrage (fréquences RTTY) et dans le temps mort après un STOP. Le poste revient
        ensuite sur la fréquence de départ ; aucune carte n'est en cours à ce moment-là.
        """
        is_day = self._is_day()
        max_age = ReceptionScheduler.VEILLE_DAY_S if is_day else ReceptionScheduler.VEILLE_NIGHT_S
        self.scheduler.last_veille = time.monotonic()
        if station_ids is None:
            cur = get_wefax_station_by_freq(float(getattr(self.app.radio, "actual_freq_khz", 0.0)))
            fam = cur["family"] if cur else "DWD"
            wefax_alts = [
                s["id"]
                for s in WEFAX_STATIONS
                if s["family"] == fam and (cur is None or s["id"] != cur["id"]) and self._period_ok(s, is_day)
            ]
            rtty = self.program_station_ids(is_day=is_day) if self.plan["rtty_enabled"] else []
            station_ids = self.prop.stale(wefax_alts + rtty, max_age)
        station_ids = list(station_ids)[:max_stations]
        if not station_ids or getattr(self.app, "carrier_scan_active", False):
            return
        origin_freq = float(getattr(self.app.radio, "actual_freq_khz", 0.0))
        self.veille_active = True
        self.app.carrier_scan_active = True
        self.scan_started_mono = time.monotonic()
        self.flush_audio_backlogs()
        self.app.log_event(f"🛰️ {reason} : {', '.join(station_ids)} (≈ 3 s par fréquence).")
        todo = list(station_ids)
        lookup = {s["id"]: ("WEFAX", s) for s in WEFAX_STATIONS}
        lookup.update({s["id"]: ("RTTY", s) for s in RTTY_WEATHER_STATIONS})

        def step():
            if not todo or self.app.closing:
                finish()
                return
            sid = todo.pop(0)
            mode, st = lookup.get(sid, (None, None))
            if st is None:
                self.app.root.after(10, step)
                return
            try:
                self.app.set_busy_state(True, f"VEILLE : mesure de {sid} ({st['freq']:.1f} kHz)")
                self.app.radio.set_wefax_frequency(st["freq"], apply_usb_offset=True)
            except Exception:
                pass
            self.app.root.after(1400, lambda: measure(sid, mode, st, []))

        def measure(sid, mode, st, samples):
            try:
                ring = self.app.audio_ring.copy()
                if mode == "WEFAX":
                    samples.append(assess_scan_audio(ring, self.app.audio_fs))
                else:
                    samples.append(
                        RTTYITA2Decoder.evaluate_rtty_quality_on_chunk(
                            ring, self.app.audio_fs, center_hz=st["center_hz"], shift_hz=st["shift_hz"]
                        )
                    )
            except Exception:
                pass
            if len(samples) < 2:
                self.app.root.after(700, lambda: measure(sid, mode, st, samples))
                return
            if mode == "WEFAX":
                mod = sum(1 for r in samples if r.get("candidate"))
                proxy = float(np.median([r.get("proxy_db") or 0.0 for r in samples]))
                q = int(min(90, 40 + 2 * proxy)) if mod else int(max(5, min(30, proxy)))
                self.prop.update(
                    sid, st["freq"], "WEFAX", q, mod >= 1, f"veille · {proxy:+.1f} dB", source="veille"
                )
            elif samples:
                q, ok, m, sp, _w = self.rtty_quality_pct(samples, st["freq"])
                self.rtty_snr_map[sid] = f"M:{m:+.1f}/S:{sp:+.1f}dB (veille {q}%)"
                self.prop.update(
                    sid, st["freq"], "RTTY", q, ok, f"M {m:+.1f} / S {sp:+.1f} dB", source="veille"
                )
            self.app.root.after(50, step)

        def finish():
            try:
                self.app.radio.set_wefax_frequency(origin_freq, apply_usb_offset=True)
                self.app._sync_ui_from_hardware()
            except Exception:
                pass
            self.prop.save()
            self.flush_audio_backlogs()
            try:
                self.app.dsp.reset_filter_states()
            except Exception:
                pass
            self.veille_active = False
            self.app.carrier_scan_active = False
            self.app.set_busy_state(False)
            summary = []
            for sid in station_ids:
                e = self.prop.get(sid)
                if e is not None:
                    summary.append(f"{sid} {e.quality} %{' ✓' if e.active else ''}")
            self.app.log_event(
                "🛰️ Veille terminée : " + " · ".join(summary) + " — retour sur la fréquence de départ."
            )
            if hasattr(self.app, "_refresh_propagation_views"):
                self.app._refresh_propagation_views()

        step()

    def save_current_rtty_bulletin(
        self, trigger_reason: str = "Fin de bulletin", manual: bool = False, text: str = None
    ) -> tuple:
        raw_text = (self.rtty_raw_buffer if text is None else text) or ""
        # 2.8.5 — même bulletin jamais archivé deux fois (le 16/11 chaque bulletin DDK9 l'a été trois fois,
        # chaque fichier reprenant en plus tous les bulletins précédents de la session).
        digest = hash(re.sub(r"\s+", " ", raw_text).strip())
        if not manual and digest == getattr(self, "_last_saved_rtty_digest", None):
            return None, None
        self._last_saved_rtty_digest = digest
        # bulletin = texte jusqu'au dernier NNNN, sans la boucle de service (RY / CQ / FREQUENCIES)
        up = raw_text.upper()
        end_mark = find_marker(up, "NNNN", last=True)
        if end_mark is not None:
            raw_text = raw_text[: end_mark[1]]
        if not manual:
            raw_text = strip_service(raw_text)
        min_chars = 8 if manual else 45
        if not raw_text or len(raw_text.strip()) < min_chars:
            return None, None

        self.last_archived_rtty_summary = raw_text.strip()[-600:]
        start_utc = self.rtty_session_start_utc or datetime.now(timezone.utc)
        end_utc = datetime.now(timezone.utc)
        st = self.active_rtty_station
        seg = BulletinSegmenter.analyze_and_segment(
            raw_text, station_id=st["id"], freq_khz=st["freq"], decoder_metrics=self.rtty.last_metrics
        )
        rel = WeatherReliabilityEstimator.compute_rtty_reliability(self.rtty, raw_text)
        # 2.8.6 — fiabilité plafonnée par la proportion de lignes de prévision réellement lisibles (le
        # bulletin Méditerranée du 17/11, au tiers illisible, était noté 99 % [A]).
        from wefax_station.weather.rtty_repair import repair_bulletin

        _rep_txt, rep = repair_bulletin(raw_text)
        if rep.get("step_lines", 0) >= 8 and rep["readable_pct"] < rel["score_pct"]:
            rel = WeatherReliabilityEstimator._format_grade(rep["readable_pct"], readability_summary(rep))
        tr_res = self.translator.translate_preserve_critical(raw_text)

        day_dir = self.workspace.reception_day_dir(start_utc)
        stamp = start_utc.strftime("%Y%m%d_%H%M%S")
        doc_id = f"RTTY_{st['id']}_{stamp}Z"

        # 2.8.3 — UN FICHIER PAR BULLETIN. L'heure de début n'était fixée qu'à l'entrée en mode RTTY : tous
        # les bulletins d'une même session portaient le même identifiant et s'écrasaient (15/11, DDH7 :
        # avis de coup de vent WODL45, NODL41 et prévision FEAE75 remplacés par le « NIL » reçu en dernier).
        # Le bulletin suivant commence maintenant ; un fichier existant n'est jamais remplacé.
        self.rtty_session_start_utc = end_utc
        # 2.11.0 — original et traduction côte à côte dans « bulletins » (avant : bulletins_radio + traductions)
        from wefax_station.storage import layout as _layout

        bdir = _layout.bulletins_dir(day_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        base_id, k = doc_id, 1
        while (bdir / f"{doc_id}_original.txt").exists():
            k += 1
            doc_id = f"{base_id}_{k}"

        orig_path = bdir / f"{doc_id}_original.txt"
        trad_path = bdir / f"{doc_id}_traduction_fr.txt"

        header_orig = (
            f"=== BULLETIN RADIO HF ORIGINAL ({SOFTWARE_BRAND}) ===\n"
            f"Document ID : {doc_id} | Station : {st['id']} ({st['freq']:.1f} kHz)\n"
            f"Protocole   : {self.rtty.last_metrics.get('protocol')} ({st['baud']} Bd / shift {st['shift_hz']} Hz)\n"
            f"Début UTC   : {start_utc.isoformat()} | Fin UTC : {end_utc.isoformat()}\n"
            f"Fiabilité   : {rel['score_pct']}% [Grade {rel['grade']} - {rel['label']}]\n"
            f"Qualification : Signal={self.rtty.last_metrics.get('signal_compatible')} | "
            f"Horloge={self.rtty.last_metrics.get('bit_clock_locked')} | "
            f"Caractères acceptés={int(self.rtty.last_metrics.get('accepted_char_ratio', 0)*100)}% | "
            f"État={seg['completeness']} | Exploitable={seg['exploitable']}\n"
            f"Produit     : {seg['product']} | Zones : {', '.join(seg['zones']) or 'Non spécifiées'}\n"
            + (f"Lisibilité  : {readability_summary(rep)}\n" if rep.get("step_lines") else "")
            + f"{'='*78}\n\n"
        )
        # retours chariot RTTY (CR CR LF) ramenés à une fin de ligne : plus de ligne vide entre chaque ligne
        orig_path.write_text(header_orig + clean_raw(raw_text) + "\n", encoding="utf-8")
        trad_path.write_text(tr_res["translated"], encoding="utf-8")

        self.workspace.register_document_record(
            category="bulletins_radio",
            doc_id=doc_id,
            start_utc=start_utc,
            end_utc=end_utc,
            station=st["id"],
            freq_khz=st["freq"],
            params={"baud": st["baud"], "shift_hz": st["shift_hz"], "center_hz": st["center_hz"]},
            quality={
                **self.rtty.last_metrics,
                **seg,
                "reliability_pct": rel["score_pct"],
                "reliability_grade": rel["grade"],
            },
            source_files=[orig_path],
            derived_files=[trad_path],
            status=seg["completeness"],
        )
        # 2.9.0 — bulletin d'intérêt reçu en entier (NNNN, ou au moins 500 caractères) : mémorisé 12 h
        item = self.current_item or getattr(self, "_ending_item", None)
        if item is not None and not item.is_navtex and (end_mark is not None or len(raw_text) >= 500):
            self.mark_bulletin_received(item.label)
        self.app.log_event(
            f"💾 [BULLETIN RTTY SAUVEGARDÉ] {orig_path.name} ({len(raw_text)} car. | Fiabilité {rel['score_pct']}% [{rel['grade']}] | {seg['product']})"
        )
        # 2.10.0 — aperçu du secteur à 3-6 h recalculé avec ce nouveau bulletin (une minute plus tard)
        root = getattr(self.app, "root", None)
        if root is not None and hasattr(self.app, "_sector_outlook_tick"):
            try:
                root.after(60000, lambda: self.app._sector_outlook_tick(force=True))
            except Exception:
                pass
        return orig_path, trad_path
