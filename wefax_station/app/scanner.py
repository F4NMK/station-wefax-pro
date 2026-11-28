"""Scan des fréquences WEFAX : QSY, préparation RF vérifiée, mesures, sélection finale.

Séquence : _trigger_carrier_scan → _start_scan → [_scan_next → (thread) QSY + RFVerified705
→ _rf_prepared → _rf_begin_measure → _scan_measure ×6] × stations → _finish_scan
→ (thread) QSY final → _rf_final_complete → _rf_final_resume.
"""

import queue
import threading
import time
from datetime import datetime, timezone
from tkinter import messagebox
import numpy as np
from wefax_station.core.stations import WEFAX_STATIONS
from wefax_station.dsp.scan_diagnostics import assess_scan_audio
from wefax_station.radio.rf_verify import RFVerified705

SCAN_REFERENCE_PAMP = 1  # 2.9.0 : P.AMP de référence pendant les mesures du scan
from wefax_station.dsp.wefax_signature import wefax_signature


class ScannerMixin:
    # ------------------------------------------------------------ lancement
    def _trigger_carrier_scan(self):
        if self.connection_busy:
            return
        if self.carrier_scan_active:
            return
        if not self.radio.handshake_ok or not self.audio_live_connected:
            messagebox.showwarning(
                "Scan impossible", "Une liaison CAT vérifiée et un flux audio réel sont nécessaires."
            )
            return
        if self.rx_current_line > 25:
            if not messagebox.askyesno(
                "Interruption de réception",
                "Un seul récepteur : le scan interrompt la carte. Archiver le fragment puis tester toutes les fréquences ?",
            ):
                return
            self._finalize_completed_wefax_chart("Fragment avant scan")
        self._start_scan()

    def _start_scan(self):
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            # Si une carte est déjà en train de se dessiner (L >= 15) avec un vrai signal, on interdit de la couper
            lines = int(getattr(self, "rx_current_line", 0))
            if (
                lines >= 15
                and not getattr(self, "waiting_after_stop", False)
                and float(getattr(self, "current_snr_db", 0.0)) >= 6.0
            ):
                arb.disarm_base_periodic_scan_timers()
                self.log_event(
                    f"🛡️ [Protection Carte Active] Scan ignoré : carte en cours à L.{lines} sur {self.radio.active_station_id}."
                )
                return None
            arb.deliberate_wefax_scan_authorized = True
            arb.scan_started_mono = time.monotonic()
            arb.flush_audio_backlogs()
        self.waiting_after_stop = False
        self.scan_origin = self.radio.actual_freq_khz
        self.scan_offset = bool(self.apply_usb_offset.get())
        self.scan_candidates = list(WEFAX_STATIONS)
        self.scan_results = []
        self.rx_current_line = 0
        self.rx_sheet_initialized_for_live = False
        self.carrier_scan_active = True
        self.last_periodic_scan_ts = time.monotonic()
        self.set_busy_state(True, "SCAN : toutes les fréquences, plusieurs mesures par fréquence")
        self.log_event("Debut scan integral ; reception image suspendue")
        self._scan_next()

    # ------------------------------------------------- station suivante
    def _scan_next(self):
        """Garde-fou anti-scission : un scan non autorisé ne coupe jamais une carte en cours."""
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None and not arb.deliberate_wefax_scan_authorized:
            lines = int(getattr(self, "rx_current_line", 0))
            if lines >= 15 and not getattr(self, "waiting_after_stop", False):
                self.carrier_scan_active = False
                self.set_busy_state(False)
                arb.disarm_base_periodic_scan_timers()
                self.log_event(
                    f"🛡️ [ANTI-SCISSION WEFAX] Scan périodique bloqué à L.{lines} sur {self.radio.active_station_id} "
                    "— La carte continue sans interruption jusqu'au signal APT STOP !"
                )
                return None
        if not getattr(self, "scan_candidates", None):
            if arb is not None:
                arb.deliberate_wefax_scan_authorized = False
        if self.closing:
            return
        try:
            self._scan_next_station()
        except Exception as exc:
            self.carrier_scan_active = False
            self.set_busy_state(False)
            self.log_event("ECHEC SCAN : " + repr(exc))

    def _scan_next_station(self):
        if not self.scan_candidates:
            self._finish_scan()
            return
        self.scan_station = self.scan_candidates.pop(0)
        self.set_busy_state(True, "SCAN : QSY / verification RF")
        auto = bool(self.auto_rf_loop_active)
        station = self.scan_station.copy()
        offset = self.scan_offset
        self._rf_phase = "preparation"

        def worker():
            error = None
            try:
                if not self.radio.set_wefax_frequency(station["freq"], offset):
                    raise RuntimeError("QSY non confirme")
                self._prepare_rf(auto)
            except Exception as exc:
                error = repr(exc)
            self.ui_events.put(lambda e=error: self._rf_prepared(e))

        threading.Thread(target=worker, daemon=True).start()

    def _prepare_rf(self, auto):
        """IC-705 : profil RF écrit puis relu (RFVerified705). Yaesu : profil CAT réception appliqué au QSY."""
        if "ICOM" in self.radio.protocol:
            # 2.9.0 — P.AMP 1 comme référence de toutes les mesures du scan
            RFVerified705(self.radio).prepare(auto, reference_pamp=SCAN_REFERENCE_PAMP)
        else:
            self.radio.apply_optimal_wefax_rx_profile(filter_idx=1)

    def _rf_prepared(self, error):
        if getattr(self, "closing", False):
            return
        if error:
            self.log_event("RF_REJECT " + self.scan_station["id"] + " : " + error)
            self._rf_phase = "rejet"
            self.root.after(50, self._scan_next)
            return
        self._sync_ui_from_hardware()
        self.scan_values = []
        self._scan_diag_samples = []
        self._wefax_scan_samples = []
        now = time.monotonic()
        self._scan_diag_after = now
        self._scan_diag_last = now
        self._wefax_scan_after = now
        self._wefax_scan_last = now
        self._rf_phase = "stabilisation"
        self.set_busy_state(True, "SCAN : RF relu conforme / stabilisation 1.8 s")
        self.root.after(1800, lambda: self._rf_begin_measure())

    def _rf_begin_measure(self):
        if getattr(self, "closing", False):
            return
        self._rf_phase = "mesure"
        self.log_event("RF_FREEZE parametres fixes pendant les mesures du scan")
        self.set_busy_state(True, "SCAN : mesure / AUTO RF suspendu")
        self._scan_measure()

    # --------------------------------------------------------- mesures
    def _scan_measure(self):
        if self.closing:
            return
        try:
            if self.last_audio_callback and time.monotonic() - self.last_audio_callback > 3:
                raise RuntimeError("Flux audio interrompu")
            self._scan_measure_window()
        except Exception as exc:
            self.carrier_scan_active = False
            self.set_busy_state(False)
            self.log_event("ECHEC MESURE : " + repr(exc))

    def _scan_measure_window(self):
        now = time.monotonic()
        cb = getattr(self, "last_audio_callback", 0)
        age = now - cb if cb else None
        fresh = bool(
            self.audio_live_connected
            and cb > self._scan_diag_after
            and cb > self._scan_diag_last
            and age is not None
            and 0 <= age < 1
        )
        if fresh:
            r = assess_scan_audio(self.audio_ring.copy(), self.audio_fs)
            self._scan_diag_last = cb
        else:
            r = dict(
                candidate=False, center_candidate=False, reasons=["stale_or_missing_audio"], proxy_db=None
            )
        self._scan_diag_samples.append(r)
        self.scan_values.append(r.get("proxy_db") if r.get("proxy_db") is not None else 0.0)

        def fmt(value):
            return "nd" if value is None else f"{value:.2f}"

        self.log_event(
            f"SCAN_DETAIL {self.scan_station['id']} window={len(self.scan_values)}/6 fresh={fresh} "
            f"proxy_db={fmt(r.get('proxy_db'))} peak_hz={fmt(r.get('peak_hz'))} "
            f"peak_db={fmt(r.get('peak_contrast_db'))} center_hz={fmt(r.get('center_hz'))} "
            f"center_prominence_db={fmt(r.get('center_prominence_db'))} "
            f"center_fraction={fmt(r.get('center_fraction'))} occupancy={fmt(r.get('occupancy'))} "
            f"span_hz={fmt(r.get('span_hz'))} rms_dbfs={fmt(r.get('rms_dbfs'))} "
            f"clip_ratio={fmt(r.get('clip_ratio'))} modulation={r.get('candidate',False)} "
            f"center_candidate={r.get('center_candidate',False)} reasons={','.join(r.get('reasons',[])) or 'none'}"
        )
        if len(self.scan_values) < 6:
            self.root.after(700, self._scan_measure)
            return
        samples = self._scan_diag_samples
        mod = [v for v in samples if v.get("candidate")]
        tones = [v for v in samples if v.get("center_candidate")]
        stable_center = len(tones) >= 4 and float(np.std([v["center_hz"] for v in tones])) <= 12
        tier = 2 if len(mod) >= 4 else (1 if stable_center else 0)
        score = (
            float(np.median([v["proxy_db"] for v in mod]))
            if tier == 2
            else float(np.median([v["center_prominence_db"] for v in tones])) if tier == 1 else float("-inf")
        )
        # Niveau 3 : structure WEFAX reconnue selon la spécification (continuité de ligne à 120 l/min,
        # START/STOP/phasage) sur les 4 dernières secondes. Une raie fixe ou un brouilleur n'y parvient pas.
        sig = self._scan_wefax_signature()
        if sig is not None:
            self.log_event(
                f"SCAN_SIGNATURE {self.scan_station['id']} {sig['verdict']} ; corr_ligne={sig['line_corr']:+.2f} "
                f"occupation={sig['occupancy']:.2f} ecart_video={sig['video_std']:.0f} apt={sig['apt']}"
            )
            if sig["confirmed"]:
                tier = 3
                score = 20.0 + 10.0 * sig["line_corr"] + 5.0 * sig["occupancy"]
        ranks = getattr(self, "_scan_signal_ranks", {})
        ranks[self.scan_station["id"]] = tier
        self._scan_signal_ranks = ranks
        self.scan_results.append((score, self.scan_station.copy()))
        status = {0: "non confirme", 1: "1900 a confirmer", 2: "modulation compatible?", 3: "WEFAX reconnu"}[
            tier
        ]
        valid = [v["proxy_db"] for v in samples if v.get("proxy_db") is not None]
        proxy = float(np.median(valid)) if valid else None
        self.station_snr_map[self.scan_station["id"]] = (
            f"{proxy:+.1f} / {status}" if proxy is not None else "audio indisponible"
        )
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            arb.record_wefax_scan(self.scan_station, tier, score if np.isfinite(score) else 0.0, proxy)
        self._populate_freq_table()
        self.log_event(
            f"SCAN {self.scan_station['id']} tier={tier} modulation={len(mod)}/6 "
            f"center={len(tones)}/6 stable_center={stable_center} status={status}"
            + ("" if tier == 3 else " ; WEFAX non identifie")
        )
        self.root.after(50, self._scan_next)

    def _scan_wefax_signature(self):
        ring = getattr(self, "audio_long_ring", None)
        cb = getattr(self, "last_audio_callback", 0.0)
        if ring is None or not self.audio_live_connected or not cb or time.monotonic() - cb > 1.0:
            return None
        n = int(4.0 * self.audio_fs)
        if len(ring) < n:
            return None
        shift = 850.0 if self.scan_station.get("family") == "DWD" else 800.0
        try:
            return wefax_signature(ring[-n:].copy(), self.audio_fs, shift_hz=shift)
        except Exception as exc:
            self.log_event("Signature WEFAX : " + repr(exc))
            return None

    # ------------------------------------------------- sélection finale
    def _finish_scan(self):
        eligible = [r for r in self.scan_results if np.isfinite(r[0])]
        ranks = getattr(self, "_scan_signal_ranks", {})
        best = max(eligible, key=lambda r: (ranks.get(r[1]["id"], 0), r[0])) if eligible else None
        # 2.9.1 — aucune modulation WEFAX reconnue nulle part (rang < 2 : au mieux une porteuse fixe à 1900 Hz) :
        # on ne quitte pas la famille de référence (DWD) pour cette porteuse si une carte DWD est en cours ou
        # prévue dans les 30 min. Le 18/11 à 20:44, une porteuse fixe sur 8040 kHz a envoyé le poste sur
        # Northwood pour la soirée.
        arb = getattr(self, "hybrid_arbiter", None)
        if best is not None and ranks.get(best[1]["id"], 0) < 2 and arb is not None:
            pref = arb.preferred_family()
            pref_rows = [r for r in eligible if r[1].get("family") == pref]
            if pref_rows and best[1].get("family") != pref and arb.preferred_chart_soon() is not None:
                old_best = best
                best = max(pref_rows, key=lambda r: (ranks.get(r[1]["id"], 0), r[0]))
                self.log_event(
                    f"SCAN_PREFERENCE {old_best[1]['id']} (rang {ranks.get(old_best[1]['id'], 0)}, sans modulation WEFAX) "
                    f"écarté : carte {pref} au programme, retour sur {best[1]['id']}"
                )
        # 2.9.3 — contrôle limité à une famille (Athènes) : l'arbitre en tient compte
        fams = {r[1].get("family") for r in eligible}
        if arb is not None and len(fams) == 1 and hasattr(arb, "note_family_scan"):
            try:
                arb.note_family_scan(fams.pop(), ranks.get(best[1]["id"], 0) if best else 0)
            except Exception:
                pass
        target = best[1]["freq"] if best else self.scan_origin
        auto = bool(self.auto_rf_loop_active)
        self.connection_busy = True
        self.carrier_scan_active = True
        self.set_busy_state(True, "QSY final : verification RF")
        self.log_event(
            f"SCAN_SELECTION target_khz={target} tier={ranks.get(best[1]['id'],0) if best else 0} "
            "(3=structure WEFAX reconnue, 2=modulation compatible, 1=1900 persistant, 0=retour)"
        )

        def worker():
            error = None
            try:
                if not self.radio.set_wefax_frequency(target, self.scan_offset):
                    raise RuntimeError("QSY final non confirme")
                self._prepare_rf(auto)
            except Exception as exc:
                error = repr(exc)
            self.ui_events.put(lambda e=error: self._rf_final_complete(best, e))

        threading.Thread(target=worker, daemon=True).start()

    def _rf_final_complete(self, best, error):
        if self.closing:
            return
        self.scan_reference = None
        self.scan_wefax_reference = best[0] if best else None
        self.rx_sample_accumulator = np.zeros(0, np.float32)
        self.dsp.reset_filter_states()
        self._sync_ui_from_hardware()
        if error:
            self.log_event("RF_FINAL_REJECT : " + error)
            self.rx_decoding_active = False
            self.btn_rx_start.set_state(False)
            self.btn_top_rx.set_state(False)
            self.connection_busy = False
            self.carrier_scan_active = False
            self.last_scan_request = time.monotonic()
            self.set_busy_state(False)
            return
        self.log_event("RF_FINAL_READY stabilisation 1.8s")
        self.root.after(1800, lambda: self._rf_final_resume())

    def _rf_final_resume(self):
        if self.closing:
            return
        self.rx_sample_accumulator = np.zeros(0, np.float32)
        while True:
            try:
                self.rx_audio_queue.get_nowait()
            except queue.Empty:
                break
        self.dsp.reset_filter_states()
        self.connection_busy = False
        self.carrier_scan_active = False
        self.last_scan_request = time.monotonic()
        self.set_busy_state(False)
        self.log_event("RF_FINAL_RESUME profil verifie ; attente confirmation WEFAX")
        self.root.after(1500, lambda: self._check_audio_passband("WEFAX"))

    def _check_day_night_schedule(self):
        utc_h = datetime.now(timezone.utc).hour
        if 6 <= utc_h < 18:
            self.lbl_daynight_badge.config(text=f"☀️ JOUR UTC ({utc_h:02d}h)", bg="#0284c7")
        else:
            self.lbl_daynight_badge.config(text=f"🌙 NUIT UTC ({utc_h:02d}h)", bg="#4338ca")
        self._sync_ui_from_hardware()

    def _toggle_auto_daynight(self):
        self.auto_day_night_active = not self.auto_day_night_active
        self.btn_daynight.set_state(self.auto_day_night_active)

    # ------------------------------------------------ table des stations
    def _populate_freq_table(self):
        for item in self.tree_freqs.get_children():
            self.tree_freqs.delete(item)
        offset = self.radio.usb_dial_offset_khz if self.apply_usb_offset.get() else 0.0
        for st in WEFAX_STATIONS:
            dial = st["freq"] + offset
            snr_val = self.station_snr_map.get(st["id"], "-- dB")
            self.tree_freqs.insert(
                "",
                "end",
                iid=st["id"],
                values=(st["id"], st["station"], f"{st['freq']:.1f}", f"{dial:.2f}", st["period"], snr_val),
            )
        self._highlight_station()

    def _highlight_station(self):
        if not hasattr(self, "tree_freqs"):
            return
        self.tree_freqs.tag_configure(
            "active_station", background="#155e75", foreground="#ffffff", font=("Segoe UI", 9, "bold")
        )
        for item in self.tree_freqs.get_children():
            self.tree_freqs.item(
                item, tags=("active_station",) if item == self.radio.active_station_id else ()
            )

    def _on_station_row_clicked(self, event=None):
        if self.connection_busy or self.carrier_scan_active:
            return
        if self.rx_current_line > 25:
            if not messagebox.askyesno(
                "Changement de fréquence", "Archiver la carte partielle avant le changement ?"
            ):
                return
            self._finalize_completed_wefax_chart("QSY manuel")
            self.rx_current_line = 0
            self.rx_sheet_initialized_for_live = False
        sel = self.tree_freqs.selection()
        if not sel:
            return
        for st in WEFAX_STATIONS:
            if st["id"] == sel[0]:
                self.radio.set_wefax_frequency(st["freq"], self.apply_usb_offset.get())
                self._sync_ui_from_hardware()
                self._refresh_canvas()
                break
