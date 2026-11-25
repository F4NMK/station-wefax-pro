"""Synchronisation des horaires (local / Internet) et planification."""

import json
import threading
import time
from datetime import datetime, timezone
from wefax_station.core.schedules import (
    BROADCAST_SCHEDULES_UTC,
    SCHEDULE_REV,
    TEXT_BULLETIN_SCHEDULES_UTC,
    merge_saved_schedules,
    next_schedule25,
)
from wefax_station.core.stations import RTTY_WEATHER_STATIONS, WEFAX_STATIONS
from wefax_station.hybrid import official_sources as OS
from wefax_station.storage.atomic import atomic_json
from wefax_station.version import SOFTWARE_VERSION


class ScheduleSyncAndPlanner:
    def __init__(self, app, workspace):
        self.app = app
        self.workspace = workspace
        self.text_schedules = list(TEXT_BULLETIN_SCHEDULES_UTC)
        self.last_web_sync_mono = 0.0
        self.last_web_sync_status = "Vérification initiale..."
        self.sync_in_progress = False
        self.network_cut_off_manual = False
        self.schedule_file = self.workspace.root_dir / "configuration" / "horaires_wefax_rtty_officiels.json"
        self.last_sources_records = []
        # 2.9.2 — programmes acceptés par l'opérateur (source officielle) : disponibles hors ligne
        try:
            OS.apply_accepted(self.workspace.root_dir)
        except Exception:
            pass
        self._load_local_schedules()

    def _load_local_schedules(self):
        if self.schedule_file.is_file():
            try:
                data = json.loads(self.schedule_file.read_text(encoding="utf-8"))
                if isinstance(data.get("text_bulletins_utc"), list) and len(data["text_bulletins_utc"]) >= 8:
                    stored = [tuple(x) for x in data["text_bulletins_utc"]]
                    # 2.8.6 — les créneaux NAVTEX viennent toujours du programme (anciens horaires faux)
                    self.text_schedules = [x for x in stored if not str(x[3]).startswith("NAVTEX")] + [
                        x for x in TEXT_BULLETIN_SCHEDULES_UTC if str(x[3]).startswith("NAVTEX")
                    ]
                if isinstance(data.get("wefax_schedules_utc"), dict):
                    # 2.9.0 — familles révisées (DWD) : le programme intégré remplace une copie d'une autre
                    # révision (l'ancienne table DWD était recopiée ici depuis des versions)
                    saved = {
                        fam: slots
                        for fam, slots in data["wefax_schedules_utc"].items()
                        if isinstance(slots, list) and len(slots) >= 4
                    }
                    merged = merge_saved_schedules(saved, data.get("schedule_rev"))
                    for fam, slots in merged.items():
                        self.app.schedule_data[fam] = slots
                    if data.get("schedule_rev") != SCHEDULE_REV:
                        self._schedule_rev_upgraded = True
                self.last_web_sync_status = data.get("sync_status", "Horaires locaux chargés")
            except Exception:
                pass
        else:
            self._save_local_schedules()

    def _save_local_schedules(self, extra_meta: dict = None):
        payload = {
            "schema": "StationWEFAXPro-Schedules-1.0",
            "version": SOFTWARE_VERSION,
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "sync_status": self.last_web_sync_status,
            "wefax_stations": WEFAX_STATIONS,
            "rtty_navtex_stations": RTTY_WEATHER_STATIONS,
            "schedule_rev": SCHEDULE_REV,
            "wefax_schedules_utc": getattr(self.app, "schedule_data", BROADCAST_SCHEDULES_UTC),
            "text_bulletins_utc": self.text_schedules,
        }
        if extra_meta:
            payload["web_provenance"] = extra_meta
        try:
            atomic_json(self.schedule_file, payload)
        except Exception:
            pass

    def set_manual_network_cutoff(self, cut_off: bool):
        self.network_cut_off_manual = bool(cut_off)
        if self.network_cut_off_manual:
            self.last_web_sync_status = "Réseau coupé (base locale active)"
            self.app.log_event(
                "🔒 [RÉSEAU] Coupe-circuit réseau activé — Base horaire et lexique hors-ligne actifs."
            )
        else:
            self.app.log_event(
                "🌐 [RÉSEAU] Accès Internet autorisé (liaison nominale ou secours 4G/Starlink)."
            )
            self.trigger_web_schedule_sync(manual=True)

    def trigger_web_schedule_sync(self, manual: bool = False):
        """2.9.2 — téléchargement des documents officiels (fil séparé, délais et taille bornés) et comparaison
        avec les programmes utilisés. Hors ligne : une seule ligne au journal, rien n'est bloqué, les
        programmes intégrés (ou acceptés par l'opérateur) restent utilisés."""
        if self.network_cut_off_manual:
            if manual:
                self.app.log_event(
                    "ℹ️ [SOURCES] Requête ignorée : coupe-circuit réseau actif (programmes locaux utilisés)."
                )
            return
        if self.sync_in_progress:
            if manual:
                self.app.log_event("ℹ️ [SOURCES] Téléchargement déjà en cours (en arrière-plan).")
            return
        now_m = time.monotonic()
        if not manual and self.last_web_sync_mono > 0 and (now_m - self.last_web_sync_mono) < 6 * 3600:
            return

        self.sync_in_progress = True
        self.last_web_sync_mono = now_m
        root_dir = self.workspace.root_dir
        snapshot = {k: list(v) for k, v in (getattr(self.app, "schedule_data", None) or BROADCAST_SCHEDULES_UTC).items()}
        if manual:
            self.app.log_event(
                "🌐 [SOURCES] Téléchargement des programmes officiels en arrière-plan — la réception continue."
            )

        def _worker():
            records, errors = [], []
            try:
                sources = [s for s in OS.load_registry(root_dir) if s.get("enabled", True)]
            except Exception as exc:
                sources, errors = [], [f"registre : {exc.__class__.__name__}"]
            for src in sources:
                try:
                    data = self._download(src["url"])
                    if OS.looks_html(data):
                        # 2.9.4 — page HTML au lieu du PDF (dwd.de, 19/11) : on suit une fois le lien PDF
                        link = OS.find_pdf_link(data, src["url"])
                        if link:
                            data = self._download(link)
                            src = dict(src, url=link)
                    records.append(OS.process_source(root_dir, src, data, snapshot))
                except Exception as exc:
                    errors.append(f"{src['id']} : {exc.__class__.__name__}")
            try:
                OS.save_state(root_dir, records, bool(records), errors)
            except Exception:
                pass
            self.app.ui_events.put(lambda: self._sources_done(records, errors, manual))

        threading.Thread(target=_worker, daemon=True, name="sources-officielles").start()

    # Point d'injection pour les tests (aucun accès réseau dans l'autotest).
    def _download(self, url):
        return OS.download(url)

    def _sources_done(self, records, errors, manual):
        self.sync_in_progress = False
        now_iso = datetime.now(timezone.utc).isoformat()
        data = getattr(self.app, "schedule_data", BROADCAST_SCHEDULES_UTC)
        wefax_cnt = sum(len(v) for v in data.values())
        accepted = sorted(OS.load_accepted(self.workspace.root_dir))
        base = "programmes intégrés" + (f" (+ acceptés : {', '.join(accepted)})" if accepted else "")
        self.last_sources_records = records
        if not records:
            self.last_web_sync_status = "Hors ligne — programmes locaux"
            self._save_local_schedules({"last_offline_fallback_utc": now_iso, "errors": errors})
            self.app.log_event(
                f"📴 [SOURCES] Internet non joignable ({' ; '.join(errors) or 'aucune source'}) : {base} utilisés "
                f"({wefax_cnt} cartes WEFAX, {len(self.text_schedules)} bulletins texte). La réception continue "
                "normalement, sans Internet."
            )
        else:
            stamp = datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC")
            self.last_web_sync_status = f"Sources vérifiées ({stamp})"
            self._save_local_schedules(
                {"last_online_check_utc": now_iso, "sources": [
                    {k: r[k] for k in ("id", "url", "sha256", "size_bytes", "download_utc")} for r in records
                ], "errors": errors}
            )
            pending = self.pending_differences(records)
            parts = []
            for r in records:
                for a in r.get("analyses") or []:
                    parts.append(OS.describe_analysis(a))
            self.app.log_event(
                f"🌐 [SOURCES] Documents officiels téléchargés ({', '.join(r['id'] + ' ' + str(max(1, r['size_bytes'] // 1024)) + ' Ko' for r in records)}"
                + (f" ; échecs : {' ; '.join(errors)}" if errors else "")
                + "). "
                + " | ".join(parts)
                + (
                    f" ⚠ {len(pending)} différence(s) à examiner : menu Bulletins ▸ Programmes : sources officielles."
                    if pending
                    else ""
                )
            )
        if manual:
            try:
                self.open_sources_window(refresh=False)
            except Exception as exc:
                self.app.log_event("Fenêtre des sources officielles : " + repr(exc))
        elif getattr(self, "_sources_window", None) is not None:
            self._fill_sources_window()
        if hasattr(self.app, "bulletins_ui"):
            try:
                self.app.bulletins_ui.refresh_status()
            except Exception:
                pass

    def pending_differences(self, records=None):
        """(source, famille, analyse, sha) dont les différences n'ont pas encore été acceptées ni refusées."""
        root_dir = self.workspace.root_dir
        if records is None:
            records = list((OS.load_state(root_dir).get("sources") or {}).values())
        out = []
        for r in records:
            for a in r.get("analyses") or []:
                if a.get("plausible") and not a.get("conforme") and not OS.decision_for(
                    root_dir, r["id"], r["sha256"], a["family"]
                ):
                    out.append((r, a["family"], a, r["sha256"]))
        return out

    def accept_source_family(self, record, family):
        a = next((x for x in record.get("analyses") or [] if x.get("family") == family), None)
        if a is None or not a.get("plausible"):
            return False
        cur = list((getattr(self.app, "schedule_data", None) or BROADCAST_SCHEDULES_UTC).get(family, []))
        slots = OS.proposed_slots(cur, a)
        ok = OS.accept_family(self.workspace.root_dir, family, slots, record["id"], record["sha256"])
        self.app.schedule_data[family] = slots
        self._save_local_schedules()
        self.app.log_event(
            f"✅ [SOURCES] Programme {family} accepté par l'opérateur d'après {record['id']} "
            f"(SHA {record['sha256'][:8]}, {len(slots)} cartes) — conservé pour le fonctionnement hors ligne."
            + ("" if ok else " ⚠ enregistrement sur disque impossible.")
        )
        try:
            self.app._update_programme()
        except Exception:
            pass
        return True

    def refuse_source_family(self, record, family):
        OS.record_decision(self.workspace.root_dir, record["id"], record["sha256"], "refuse", family)
        self.app.log_event(
            f"🚫 [SOURCES] Différences {family} de {record['id']} refusées par l'opérateur : programme inchangé."
        )

    def open_source_document(self, record):
        path = OS.sources_dir(self.workspace.root_dir) / record.get("file", "")
        try:
            import os
            import webbrowser

            if hasattr(os, "startfile"):
                os.startfile(str(path))  # Windows
            else:
                webbrowser.open(path.as_uri())
        except Exception as exc:
            self.app.log_event("Ouverture du document impossible : " + repr(exc))

    def open_sources_window(self, refresh=True):
        """Fenêtre « Programmes : sources officielles » : état, différences, Accepter / Refuser / Ouvrir."""
        import tkinter as tk

        from wefax_station.ui.placement import show_over_root

        win = getattr(self, "_sources_window", None)
        try:
            if win is None or not win.winfo_exists():
                raise tk.TclError
        except tk.TclError:
            win = tk.Toplevel(self.app.root)
            win.title("Programmes : sources officielles")
            win.protocol("WM_DELETE_WINDOW", self._close_sources_window)
            self._sources_window = win
        self._fill_sources_window()
        show_over_root(win, self.app.root)
        if refresh:
            self.trigger_web_schedule_sync(manual=True)
        return win

    def _close_sources_window(self):
        win = getattr(self, "_sources_window", None)
        self._sources_window = None
        try:
            win.destroy()
        except Exception:
            pass

    def _fill_sources_window(self):
        import tkinter as tk

        win = getattr(self, "_sources_window", None)
        if win is None:
            return
        for w in win.winfo_children():
            w.destroy()
        root_dir = self.workspace.root_dir
        st = OS.load_state(root_dir)
        accepted = OS.load_accepted(root_dir)
        head = (
            "Les programmes intégrés au logiciel suffisent pour recevoir sans Internet. Les documents officiels "
            "sont téléchargés en arrière-plan et comparés ; rien n'est modifié sans votre accord.\n"
            f"Dernière tentative : {st.get('last_attempt_utc', 'jamais')[:16].replace('T', ' ')} UTC — "
            + ("en ligne" if st.get("online") else "hors ligne")
            + (f" — échecs : {' ; '.join(st.get('errors') or [])}" if st.get("errors") else "")
            + ("\nProgrammes acceptés : " + ", ".join(
                f"{f} ({v.get('source')}, {str(v.get('accepted_utc', ''))[:10]})" for f, v in accepted.items()
            ) if accepted else "")
        )
        tk.Label(win, text=head, justify="left", wraplength=640, anchor="w").pack(fill="x", padx=10, pady=(10, 6))
        recs = list((st.get("sources") or {}).values())
        if not recs:
            tk.Label(win, text="Aucun document téléchargé pour l'instant.", anchor="w").pack(fill="x", padx=10)
        for r in recs:
            fr = tk.LabelFrame(win, text=f"{r.get('label') or r['id']}")
            fr.pack(fill="x", padx=10, pady=4)
            tk.Label(
                fr,
                text=f"{r['url']}\nTéléchargé le {r['download_utc'][:16].replace('T', ' ')} UTC — "
                f"{max(1, r['size_bytes'] // 1024)} Ko — SHA-256 {r['sha256'][:16]}…",
                justify="left", anchor="w", wraplength=620,
            ).pack(fill="x", padx=6)
            for a in r.get("analyses") or []:
                row = tk.Frame(fr)
                row.pack(fill="x", padx=6, pady=2)
                dec = OS.decision_for(root_dir, r["id"], r["sha256"], a["family"])
                txt = OS.describe_analysis(a) + (f" — décision : {dec}" if dec else "")
                tk.Label(row, text=txt, justify="left", anchor="w", wraplength=440).pack(side="left", fill="x", expand=True)
                if a.get("plausible") and not a.get("conforme") and not dec:
                    tk.Button(row, text="Refuser", command=lambda r=r, f=a["family"]: (
                        self.refuse_source_family(r, f), self._fill_sources_window())).pack(side="right", padx=2)
                    tk.Button(row, text=f"Accepter {a['family']}", command=lambda r=r, f=a["family"]: (
                        self.accept_source_family(r, f), self._fill_sources_window())).pack(side="right", padx=2)
            tk.Button(fr, text="Ouvrir le document", command=lambda r=r: self.open_source_document(r)).pack(
                anchor="e", padx=6, pady=(0, 4)
            )
        # 2.9.3 — programme observé : créneaux réellement reçus ou restés muets à l'écoute
        obs = getattr(getattr(self.app, "hybrid_arbiter", None), "observed", None)
        if obs is not None:
            fr = tk.LabelFrame(win, text="Programme observé à votre station (START reçus / créneaux muets)")
            fr.pack(fill="x", padx=10, pady=4)
            lines = []
            for fam in ("DWD", "GYA"):
                recu, muet = obs.summary(fam)
                if recu or muet:
                    lines.append(f"{fam} — reçus : {', '.join(recu) or 'aucun'}")
                    if muet:
                        lines.append(f"{fam} — muets à l'écoute (jamais reçus) : {', '.join(muet)}")
            sus = obs.suspects()
            if sus:
                lines.append(
                    "À vérifier (muets au moins 3 jours, jamais reçus) : "
                    + ", ".join(f"{f} {hm}" for f, hm, _d in sus)
                    + ". Rien n'est retiré du programme sans vous."
                )
            tk.Label(fr, text="\n".join(lines) or "Pas encore de relevé.", justify="left", anchor="w",
                     wraplength=620).pack(fill="x", padx=6, pady=2)
        bar = tk.Frame(win)
        bar.pack(fill="x", padx=10, pady=8)
        tk.Button(bar, text="Télécharger maintenant", command=lambda: self.trigger_web_schedule_sync(manual=True)).pack(side="left")
        tk.Button(bar, text="Fermer", command=self._close_sources_window).pack(side="right")

    def get_upcoming_wefax_across_all_families(self, now_utc: datetime = None) -> dict:
        now = now_utc or datetime.now(timezone.utc)
        cur_sec = now.hour * 3600 + now.minute * 60 + now.second
        data = getattr(self.app, "schedule_data", BROADCAST_SCHEDULES_UTC)
        best = None
        min_since_last = 999999

        fams = ("DWD", "GYA", "ATH") if getattr(getattr(self.app, "hybrid_arbiter", None), "plan", {}).get(
            "athens_enabled", True
        ) else ("DWD", "GYA")
        for fam in fams:
            slots = data.get(fam, BROADCAST_SCHEDULES_UTC.get(fam, []))
            for item in slots:
                slot_sec = int(item[0]) * 60
                since = (cur_sec - slot_sec) % 86400
                if since < min_since_last:
                    min_since_last = since
            try:
                res = next_schedule25(slots, now)
                if res is None:
                    continue
                event, delay_sec = res
                when_str = f"{event[0] // 60:02d}:{event[0] % 60:02d} UTC"
                cand = {
                    "family": fam,
                    "delay_sec": int(delay_sec),
                    "elapsed_since_last_start_sec": int(min_since_last),
                    "code": event[1],
                    "description": event[2],
                    "when_str": when_str,
                }
                if best is None or cand["delay_sec"] < best["delay_sec"]:
                    best = cand
            except Exception:
                continue

        if best is not None:
            best["elapsed_since_last_start_sec"] = int(min_since_last)
            return best
        return {
            "family": "DWD",
            "delay_sec": 3600,
            "elapsed_since_last_start_sec": 3600,
            "code": "N/D",
            "description": "Aucun horaire",
            "when_str": "--:-- UTC",
        }

    def get_active_or_next_text_bulletin(self, now_utc: datetime = None) -> dict:
        now = now_utc or datetime.now(timezone.utc)
        sec_of_day = now.hour * 3600 + now.minute * 60 + now.second

        best_active = None
        best_next = None
        min_delay = 999999

        for h, m, dur_min, family, code, desc in self.text_schedules:
            start_sec = int(h) * 3600 + int(m) * 60
            elapsed = (sec_of_day - start_sec) % 86400
            if 0 <= elapsed < int(dur_min) * 60:
                rem = int(dur_min) * 60 - elapsed
                cand = {
                    "active_now": True,
                    "seconds_until_start": 0,
                    "seconds_remaining": rem,
                    "start_str": f"{int(h):02d}:{int(m):02d} UTC",
                    "duration_min": int(dur_min),
                    "family": family,
                    "code": code,
                    "description": desc,
                }
                if best_active is None or ("NAVTEX" in family and "NAVTEX" not in best_active["family"]):
                    best_active = cand

            delay = (start_sec - sec_of_day) % 86400
            if 0 < delay < min_delay:
                min_delay = delay
                best_next = {
                    "active_now": False,
                    "seconds_until_start": int(delay),
                    "seconds_remaining": int(dur_min) * 60,
                    "start_str": f"{int(h):02d}:{int(m):02d} UTC",
                    "duration_min": int(dur_min),
                    "family": family,
                    "code": code,
                    "description": desc,
                }

        return best_active if best_active is not None else best_next
