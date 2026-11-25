"""Veille spectrale (2.8.9) : niveau des autres stations de la bande, lu sur le spectre du poste.

Toutes les 2 min, pendant la réception (carte, bulletin ou attente), un balayage du spectre ±250 kHz est
lu par CI-V dans un fil séparé ; la réception audio n'est jamais interrompue. Les stations connues
visibles dans la fenêtre sont mesurées (écart au bruit) et le résultat :
* s'affiche dans la fenêtre « Fréquences » (colonne « Spectre ») ;
* sert à l'automatisme : un bulletin RTTY dont la station est vue forte sur le spectre il y a moins de
  5 min est pris directement, sans scan préalable ;
* est écrit au journal quand la situation change (station apparue, disparue, renforcée).
"""

import threading
import time

from wefax_station.core.stations import RTTY_WEATHER_STATIONS, WEFAX_STATIONS
from wefax_station.radio import scope

SPECTRAL_PERIOD_MS = 120000
SPECTRAL_FIRST_MS = 60000
SPECTRAL_SPAN_HZ = 250000
SPECTRAL_MAX_FAILS = 3


class SpectralWatchMixin:
    def spectral_enabled(self):
        arb = getattr(self, "hybrid_arbiter", None)
        return bool(arb.plan.get("spectral_watch", True)) if arb is not None else True

    def _spectral_stations(self):
        return [s for s in WEFAX_STATIONS] + [s for s in RTTY_WEATHER_STATIONS if float(s["freq"]) > 1000]

    def _spectral_watch_start(self):
        self.spectral_seen = getattr(self, "spectral_seen", {})
        self._spectral_fails = 0
        self.root.after(SPECTRAL_FIRST_MS, self._spectral_tick)

    def _spectral_can_run(self):
        r = self.radio
        return bool(
            self.spectral_enabled()
            and r.port_open
            and r.handshake_ok
            and "ICOM" in str(r.protocol)
            and not getattr(self, "connection_busy", False)
            and not getattr(self, "carrier_scan_active", False)
            and not getattr(self, "winlink_session_active", False)
            and not getattr(self, "replay_active", False)
            and not getattr(getattr(self, "hybrid_arbiter", None), "veille_active", False)
            and not getattr(self, "_spectral_running", False)
            and getattr(self, "_spectral_fails", 0) < SPECTRAL_MAX_FAILS
        )

    def _spectral_tick(self):
        if getattr(self, "closing", False):
            return
        try:
            if self._spectral_can_run():
                self._spectral_running = True
                threading.Thread(target=self._spectral_worker, daemon=True).start()
        finally:
            self.root.after(SPECTRAL_PERIOD_MS, self._spectral_tick)

    def _spectral_worker(self):
        try:
            sweep = self.radio.read_scope_sweep(span_hz=SPECTRAL_SPAN_HZ)
        except Exception as exc:  # jamais d'exception dans le fil
            sweep = None
            self.ui_events.put(lambda e=exc: self.log_event(f"Veille spectrale : {e!r}"))
        self.ui_events.put(lambda s=sweep: self._spectral_done(s))

    def _spectral_done(self, sweep, now=None):
        self._spectral_running = False
        if sweep is None:
            self._spectral_fails = getattr(self, "_spectral_fails", 0) + 1
            if self._spectral_fails == SPECTRAL_MAX_FAILS:
                stats = getattr(self.radio, "last_scope_stats", None) or {}
                if stats.get("bytes", 0) > 0:
                    # 2.9.0 — des octets arrivent : ce n'est PAS le poste qui refuse (diagnostic faux en 2.8.9)
                    why = (
                        f"{stats['bytes']} octets reçus mais aucun balayage complet reconnu "
                        "(format inattendu : envoyer la ligne « 🔭 Spectre » du journal pour analyse)"
                    )
                else:
                    why = (
                        "aucune donnée de spectre reçue (vérifier sur l'IC-705 : SET › Connectors › CI-V : "
                        "« CI-V USB Port » et la sortie des données de l'écran)"
                    )
                self.log_event(f"🔭 Veille spectrale arrêtée après {SPECTRAL_MAX_FAILS} essais : {why}. La réception n'est pas affectée.")
            return
        self._spectral_fails = 0
        if sweep.get("blank"):
            if not getattr(self, "_spectral_blank_logged", False):
                self._spectral_blank_logged = True
                self.log_event(
                    f"🔭 Veille spectrale : balayage reçu (±{sweep['span_hz'] / 1000:.0f} kHz autour de "
                    f"{sweep['center_hz'] / 1000:.1f} kHz) mais entièrement à zéro — niveau de référence de "
                    "l'écran du poste trop bas ? Aucune mesure tirée de ce balayage."
                )
            return
        now = time.time() if now is None else now
        res = scope.analyze_sweep(sweep["points"], sweep["center_hz"], sweep["span_hz"], self._spectral_stations())
        seen = getattr(self, "spectral_seen", {})
        changes = []
        for sid, r in res.items():
            old = seen.get(sid)
            r = dict(r, ts=now, center_khz=sweep["center_hz"] / 1000.0)
            seen[sid] = r
            if old is None or old["label"] != r["label"]:
                changes.append(sid)
        self.spectral_seen = seen
        self.last_spectral = {"ts": now, "center_khz": sweep["center_hz"] / 1000.0, "span_khz": sweep["span_hz"] / 1000.0, "ids": list(res)}
        if changes or now - getattr(self, "_spectral_logged", 0) > 900:
            self._spectral_logged = now
            parts = [f"{sid} {res[sid]['freq']:.1f} {res[sid]['label']} ({res[sid]['contrast']:+.0f})" for sid in sorted(res, key=lambda k: res[k]["freq"])]
            self.log_event(
                f"🔭 Veille spectrale ±{sweep['span_hz'] / 1000:.0f} kHz autour de {sweep['center_hz'] / 1000:.1f} kHz : "
                + (" · ".join(parts) if parts else "aucune station connue dans la fenêtre")
            )
        try:
            self._refresh_propagation_views()
        except Exception:
            pass

    # ------------------------------------------------------------------ pour l'automatisme et l'affichage
    def spectral_info(self, sid, max_age_s=600, now=None):
        r = getattr(self, "spectral_seen", {}).get(sid)
        now = time.time() if now is None else now
        if r is None or now - r["ts"] > max_age_s:
            return None
        return r

    def spectral_best(self, ids, max_age_s=300, min_contrast=10, now=None):
        """Station la plus forte vue récemment sur le spectre parmi `ids`, ou None."""
        best = None
        for sid in ids:
            r = self.spectral_info(sid, max_age_s, now)
            if r is not None and r["contrast"] >= min_contrast and (best is None or r["contrast"] > best[1]["contrast"]):
                best = (sid, r)
        return best

    def spectral_cell(self, sid, now=None):
        r = self.spectral_info(sid, max_age_s=1800, now=now)
        if r is None:
            return "—"
        mins = int(((time.time() if now is None else now) - r["ts"]) // 60)
        return f"{r['label']} ({r['contrast']:+.0f}) · {mins} min"
