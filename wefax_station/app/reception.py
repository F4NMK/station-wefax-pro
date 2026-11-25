"""Chaîne de réception WEFAX : boucle temps réel, feuille de réception, START/PHASE/STOP, fin de carte.

Le cœur du décodage (_rx_decode_step) est le code historique de la version 2.0, inchangé.
Les étapes qui l'entourent sont appliquées dans l'ordre historique :
  boucle : pré-traitement socle hybride/RTTY → décodage → bandeau → masquage overlays
  fin de carte : préparation dossier portable → bandeau → géométrie 2.4 → sauvegarde 2.3 → bandeau → indexation
"""

import json
import queue
import time
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox
import numpy as np
import cv2
from wefax_station.core.stations import is_rtty_frequency
from wefax_station.storage.atomic import atomic_json, atomic_png
from wefax_station.storage import layout
from wefax_station.ui.theme import UITheme
from wefax_station.version import SOFTWARE_VERSION
from wefax_station.weather.geometry import estimate_geometry
from wefax_station.weather.reliability import WeatherReliabilityEstimator
from wefax_station.dsp.chart_restore import find_frame_line, find_wrap_cut, trim_blank_rows
from wefax_station.dsp.wefax_signature import is_chart_structure, line_structure
from wefax_station.dsp.chart_end import ChartEndDetector


def phase_run_is_steady(positions, tol=0.03):
    """2.11.0 — Vrai si l'impulsion de phasage reste au même endroit sur toute la série (± tol de la ligne).

    Un vrai phasage WEFAX place son impulsion toujours à la même position ; une légende, un cadre ou un
    aplat de carte qui ressemble par hasard à une ligne de phasage ne le fait pas. Positions inconnues
    (None) : on ne peut pas confirmer, la carte continue."""
    pos = [float(p) % 1.0 for p in positions if p is not None]
    if len(pos) < max(3, int(0.8 * len(positions))):
        return False
    ref = pos[0]
    return all(min(abs(p - ref), 1.0 - abs(p - ref)) <= tol for p in pos)


class ReceptionMixin:
    # ------------------------------------------------- boucle temps réel
    def _realtime_rx_and_spectrum_loop(self):
        cur_h = datetime.now(timezone.utc).hour
        self.current_day_period_state = 6 <= cur_h < 18

        # Continuité du flux : aucun échantillon n'est jeté après un ralentissement de l'interface
        # (sauvegarde d'une carte, fenêtre ouverte…). Jeter de l'audio décalerait toutes les lignes
        # suivantes de la carte. Garde-fou mémoire uniquement au-delà de 30 s de retard.
        if hasattr(self, "rx_audio_queue") and self.rx_audio_queue.qsize() > 300:
            while self.rx_audio_queue.qsize() > 200:
                try:
                    self.rx_audio_queue.get_nowait()
                except Exception:
                    break
            self.log_event("⚠️ Retard de traitement > 30 s : audio le plus ancien abandonné")
        max_acc = int(self.audio_fs * 30.0)
        if hasattr(self, "rx_sample_accumulator") and len(self.rx_sample_accumulator) > max_acc:
            self.rx_sample_accumulator = self.rx_sample_accumulator[-max_acc:]

        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            arb.disarm_base_periodic_scan_timers()

        self._hide_main_canvas_roi_overlays()

        if arb is not None and arb.active_pipeline == "RTTY":
            try:
                if not self.carrier_scan_active and not getattr(self, "connection_busy", False):
                    if self.rtty_decoder.fs != self.audio_fs:
                        self.rtty_decoder.configure(sample_rate=self.audio_fs)
                    chunks = []
                    while not self.rx_audio_queue.empty():
                        try:
                            chunks.append(self.rx_audio_queue.get_nowait())
                        except queue.Empty:
                            break
                    if chunks:
                        # tout le flux est transmis au décodeur (aucune troncature : pas de caractère perdu)
                        audio_block = np.concatenate(chunks)
                        decoded_txt, metrics = self.rtty_decoder.feed_audio(
                            audio_block, ring_buffer_2s=self.audio_ring
                        )
                        self._log_new_navtex_messages()
                        if decoded_txt and hasattr(self, "bulletins_ui"):
                            self.bulletins_ui.append_live_rtty_text(decoded_txt)
                    if self.audio_live_connected and self.rtty_decoder.spectral_eval_decim == 1:
                        spec_info = self.dsp.analyze_live_audio_spectrum(
                            self.audio_ring, auto_afc_enabled=False
                        )
                        self.last_spectrum_info = spec_info
                        m = self.rtty_decoder.last_metrics
                        self.current_snr_db = max(
                            float(m.get("mark_snr_db", 0.0)), float(m.get("space_snr_db", 0.0))
                        )
                    m = self.rtty_decoder.last_metrics
                    rel_rt = WeatherReliabilityEstimator.compute_rtty_reliability(
                        self.rtty_decoder, arb.rtty_raw_buffer
                    )
                    if hasattr(self, "lbl_rx_line_counter"):
                        self.lbl_rx_line_counter.configure(
                            text=(
                                f"📠 ÉCOUTE RTTY : {arb.active_rtty_station['id']} ({arb.active_rtty_station['freq']:.1f} kHz) | "
                                f"Squelch:{'OUVERT' if m.get('signal_compatible') else 'FERMÉ'} | "
                                f"Car.:{self.rtty_decoder.accepted_chars} | {rel_rt['badge_text']}"
                            )
                        )
                    self._draw_three_quality_bargraphs()
                    self._draw_permanent_top_signal_curve()
                    if hasattr(self, "bulletins_ui"):
                        self.bulletins_ui.refresh_status()
            except Exception as exc:
                self.log_event("ERREUR boucle RTTY : " + repr(exc))
            # 2.8.5 — en mode bulletins, le bandeau ne parle plus de carte (« WEFAX non identifié ») : il dit
            # ce que fait réellement le poste.
            b = getattr(self, "rx_step_banner", None)
            if b is not None:
                try:
                    st = self.hybrid_arbiter.active_rtty_station
                    n = len(self.hybrid_arbiter.rtty_raw_buffer)
                    b.set_step("AUDIO", "confirmed", "Flux recent", log_transition=False)
                    b.set_step(
                        "SIGNAL",
                        "confirmed" if n else "candidate",
                        f"Bulletin texte {st['id']} : {n} car. (Telescripteur)",
                        log_transition=False,
                    )
                except Exception:
                    pass
            self.root.after(180, self._realtime_rx_and_spectrum_loop)
            return

        # 2.9.0 — archive consultée et NOUVELLE carte commencée depuis (START) : retour à la vue en direct
        # après 5 lignes. Une carte déjà en cours au moment d'ouvrir l'archive ne la referme pas.
        if (
            getattr(self, "viewing_archived_file", None)
            and getattr(self, "_live_return_pending", False)
            and int(getattr(self, "rx_current_line", 0)) >= 5
            and not getattr(self, "waiting_after_stop", False)
        ):
            self._live_return_pending = False
            self._return_to_live_rx_view()
        elif hasattr(self, "_consultation_idle_check"):
            # 2.9.2 — consultation (archive ou « Dernière carte ») oubliée pendant une réception
            try:
                self._consultation_idle_check()
            except Exception:
                pass

        res = self._rx_loop_with_banner()
        self._hide_main_canvas_roi_overlays()
        return res

    def _rx_loop_with_banner(self):
        res = self._rx_decode_step()
        b = getattr(self, "rx_step_banner", None)
        if b is not None:
            aud_ok = bool(getattr(self, "audio_live_connected", False))
            b.set_step(
                "AUDIO",
                "confirmed" if aud_ok else "idle",
                "Flux recent" if aud_ok else "Inactif",
                log_transition=False,
            )
            lines = int(getattr(self, "rx_current_line", 0))
            snr = float(getattr(self, "current_snr_db", 0.0))
            snr_shown = float(getattr(self, "raw_snr_db", snr))
            if lines >= 1 and not getattr(self, "waiting_after_stop", False):
                b.set_step("IMAGE", "active", f"{lines} lignes tracees", log_transition=(lines == 1))
                b.set_step("SIGNAL", "confirmed", f"SNR {snr_shown:+.1f} dB", log_transition=False)
            elif snr >= 6.0:
                b.set_step("SIGNAL", "candidate", "Candidat radio, WEFAX non identifie")
            else:
                b.set_step("SIGNAL", "idle", "Pas de candidat actuel")
        return res

    def _rx_decode_step(self):
        """
        Boucle temps réel :
        1. Détecte START (300.0 ± 3.5 Hz) : exige 5 lignes consécutives si une carte est déjà en cours (>90 lignes)
           afin d'empêcher toute coupure (split) sur des traits d'isobares.
        2. Détecte PHASE : cale automatiquement l'offset de marge (`line_phase_offset_px`) sur l'impulsion de synchro.
        3. Détecte STOP (450.0 ± 4.5 Hz) : sauvegarde la carte, prépare une nouvelle feuille vierge et met le tracé
           en attente (`waiting_after_stop = True`) jusqu'au prochain vrai START/PHASE pour ne jamais empiler deux cartes.
        """
        try:
            if self.carrier_scan_active or getattr(self, "connection_busy", False):
                while not self.rx_audio_queue.empty():
                    try:
                        self.rx_audio_queue.get_nowait()
                    except queue.Empty:
                        break
                self.rx_sample_accumulator = np.zeros(0, np.float32)
                self.root.after(180, self._realtime_rx_and_spectrum_loop)
                return

            # durée de ligne exacte, corrigée de l'erreur d'horloge de la carte son mesurée au phasage
            exact_samples_per_line = self.dsp.samples_per_line()

            if self.audio_live_connected:
                chunks = []
                while not self.rx_audio_queue.empty():
                    try:
                        chunks.append(self.rx_audio_queue.get_nowait())
                    except queue.Empty:
                        break
                if chunks:
                    new_audio = np.concatenate(chunks)
                    self.rx_sample_accumulator = np.concatenate([self.rx_sample_accumulator, new_audio])
            elif getattr(self, "demo_enabled", False):
                if self.rx_decoding_active and self.rx_sheet_initialized_for_live:
                    ref_h = self.reference_sim_chart.shape[0]
                    sim_line_px = self.reference_sim_chart[self.rx_current_line % ref_h, :]
                    n_gen = int(round(exact_samples_per_line))
                    sim_audio = self.dsp.synthesize_wefax_fm_line(sim_line_px, n_gen)
                    self.audio_ring = sim_audio
                    self.rx_sample_accumulator = np.concatenate([self.rx_sample_accumulator, sim_audio])

            if self.audio_live_connected or (self.rx_decoding_active and self.rx_sheet_initialized_for_live):
                spec_info = self.dsp.analyze_live_audio_spectrum(
                    self.audio_ring, auto_afc_enabled=self.upstream_hf_cond_active
                )
                self.last_spectrum_info = spec_info
                self.current_snr_db = spec_info["snr_db"]
                self.raw_snr_db = float(spec_info.get("snr_raw_db", spec_info["snr_db"]))
                verdict = self.dsp.assess_wefax_signal(self.audio_ring)
                self.wefax_signal_verdict = verdict["verdict"]
                self.carrier_locked = verdict["verdict"] == "wefax_synced"
                self.station_snr_map[self.radio.active_station_id] = f"{self.current_snr_db:+.1f} dB"

                if not self.carrier_locked and self.rx_current_line == 0:
                    self._set_wefax_protocol_stage("PORTEUSE")
                elif spec_info.get("carrier_2300") and self.rx_current_line < 15:
                    self._set_wefax_protocol_stage("TEST_BLANC")
                elif spec_info.get("carrier_1500") and self.rx_current_line < 15:
                    self._set_wefax_protocol_stage("TEST_NOIR")

            lines_decoded_this_tick = 0
            while len(self.rx_sample_accumulator) >= int(exact_samples_per_line):
                n_take = int(exact_samples_per_line + self.rx_fractional_rem)
                self.rx_fractional_rem = (exact_samples_per_line + self.rx_fractional_rem) - n_take

                line_audio = self.rx_sample_accumulator[:n_take]
                self.rx_sample_accumulator = self.rx_sample_accumulator[n_take:]

                signal_above_squelch = (self.current_snr_db >= self.snr_squelch_threshold_db) or (
                    not self.audio_live_connected
                )
                if not signal_above_squelch and self.rx_current_line < 25:
                    self._set_wefax_protocol_stage("PORTEUSE")

                if self.rx_decoding_active and not self.carrier_scan_active:
                    self.dsp.fm_center_hz = 1900.0
                    self.dsp.fm_shift_hz = float(
                        getattr(
                            self,
                            "wefax_shift_override_hz",
                            850.0 if self.radio.active_station_family == "DWD" else 800.0,
                        )
                    )
                    px_row, apt_tone = self.dsp.demodulate_line_fm(
                        line_audio,
                        line_width=1809,
                        qrn_blanker=self.qrn_blanker_var.get(),
                        upstream_conditioner=self.upstream_hf_cond_active,
                    )
                    self._track_clock_calibration()
                    image_evidence = self._update_image_evidence(px_row, apt_tone)

                    observation = getattr(self.dsp, "protocol_observation", {})
                    protocol_state = apt_tone or "NONE"
                    if protocol_state != getattr(self, "_last_protocol_state", None):
                        self._last_protocol_state = protocol_state
                        self.log_event(
                            f"WEFAX_OBSERVE state={protocol_state} "
                            f"valid={observation.get('valid')} shift={self.dsp.fm_shift_hz} "
                            f"mod_hz={observation.get('apt_modulation_hz')} "
                            f"phase_stable={observation.get('phase_stable')} synchronized={observation.get('synchronized', False)}"
                        )

                    if apt_tone == "START_576":
                        self._set_wefax_protocol_stage("START")
                    elif apt_tone == "PHASE":
                        self._set_wefax_protocol_stage("PHASE")
                    elif apt_tone == "TEST_BLANC":
                        self._set_wefax_protocol_stage("TEST_BLANC")
                    elif apt_tone == "TEST_NOIR":
                        self._set_wefax_protocol_stage("TEST_NOIR")
                    elif apt_tone == "STOP":
                        self._set_wefax_protocol_stage("STOP")

                    if self.apt_auto_start_active:
                        # 1. Gestion de START : 3 lignes sur 4 en début/veille, mais 5 lignes consécutives exigées
                        # si une carte est déjà en cours (>90 lignes) pour interdire tout split intempestif !
                        self._start_window = (
                            getattr(self, "_start_window", []) + [1 if apt_tone == "START_576" else 0]
                        )[-6:]
                        if apt_tone == "START_576":
                            self._start_absent_lines = 0
                            self.apt_start_hits += 1
                        else:
                            self.apt_start_hits = 0
                            self._start_absent_lines = getattr(self, "_start_absent_lines", 0) + 1
                            if self._start_absent_lines >= 4:
                                self._start_burst_handled = False

                        in_mid_chart = (90 <= self.rx_current_line <= 1050) and not getattr(
                            self, "waiting_after_stop", False
                        )
                        start_confirmed = (
                            (self.apt_start_hits >= 5)
                            if in_mid_chart
                            else (self.apt_start_hits >= 3 or sum(self._start_window[-4:]) >= 3)
                        )

                        if start_confirmed and not getattr(self, "_start_burst_handled", False):
                            self._start_burst_handled = True
                            self.apt_start_hits = max(3, self.apt_start_hits)
                            self.log_event(
                                "🔔 APT START : commutation FM 300 Hz confirmée ; nouvelle feuille initialisée."
                            )
                            try:
                                arb_ = getattr(self, "hybrid_arbiter", None)
                                if arb_ is not None and hasattr(arb_, "note_chart_start"):
                                    arb_.note_chart_start()
                            except Exception:
                                pass
                            if self.rx_current_line > 100 and not getattr(self, "waiting_after_stop", False):
                                self._finalize_completed_wefax_chart(
                                    "Nouveau START ; carte précédente archivée"
                                )
                            self.waiting_after_stop = False
                            self.pin_completed = False
                            self._reset_blank_rx_sheet()
                            self.rx_image_armed = True
                            self.rx_sheet_had_start = True
                            self._auto_record_chart_start()
                            if not self.rx_decoding_active:
                                self.rx_decoding_active = True
                                self.btn_rx_start.set_state(True)
                                self.btn_top_rx.set_state(True)
                            self._set_wefax_protocol_stage("START")
                            self._mark_banner_step("START", "START 300 Hz recu")
                            continue

                        # 2. Synchronisation directe de la marge sur l'impulsion de PHASAGE en début de carte
                        # 2.8.3 — PHASAGE reçu EN COURS DE CARTE : le STOP de la carte en cours et le START de
                        # la suivante ont été manqués (fading). 6 lignes de phasage consécutives (3 s) ne
                        # peuvent pas être du dessin : la carte en cours est close (sans ses lignes de fin
                        # inexploitables) et la suivante démarre calée sur ce phasage. (Carte GYA3 du 15/11
                        # 19:48 UTC : phasage détecté puis ignoré, carte suivante commencée sans calage.)
                        # 2.11.0 — RÈGLE DE BASE : une carte en cours n'est jamais coupée sur un doute. Le
                        # 20/11 à 07:17 (DDK3), 6 lignes prises pour un phasage à L.1182 (légende et cadre
                        # du bas de la carte DWD) avaient coupé une carte complète en deux fichiers. Un vrai
                        # phasage dure 30 s (60 lignes) avec une impulsion TOUJOURS au même endroit : il faut
                        # désormais PHASE_SPLIT_LINES lignes de phasage consécutives dont l'impulsion ne bouge
                        # pas (± 3 % de la ligne) pour clore la carte en cours.
                        if apt_tone == "PHASE":
                            self._phase_run = getattr(self, "_phase_run", 0) + 1
                            pos = observation.get("phase_position")
                            self._phase_run_pos = (getattr(self, "_phase_run_pos", []) + [pos])[-self.PHASE_SPLIT_LINES :]
                        else:
                            self._phase_run = 0
                            self._phase_run_pos = []
                        if (
                            self._phase_run >= self.PHASE_SPLIT_LINES
                            and self.rx_current_line > 100
                            and not getattr(self, "waiting_after_stop", False)
                            and phase_run_is_steady(self._phase_run_pos)
                        ):
                            n_before = int(self.rx_current_line)
                            drop = self._phase_run + 3 + int(getattr(self, "_low_snr_tail_lines", 0))
                            self.log_event(
                                f"🔔 Phasage de la carte suivante reçu à L.{n_before} (STOP et START non reçus) : "
                                "carte en cours archivée, nouvelle feuille calée sur ce phasage."
                            )
                            self._crop_sheet_rows(0, max(1, n_before - drop))
                            if self.rx_current_line >= 200:
                                self._finalize_completed_wefax_chart(
                                    "Phasage de la carte suivante (fin de carte non reçue)"
                                )
                            self.pin_completed = False
                            self._reset_blank_rx_sheet()
                            self.rx_image_armed = True
                            self.rx_sheet_had_start = True
                            self._auto_record_chart_start()
                            self._phase_run = 0
                        if apt_tone == "PHASE" and self.rx_current_line < 65:
                            if getattr(self, "waiting_after_stop", False):
                                self.waiting_after_stop = False
                                self.pin_completed = False
                                self._reset_blank_rx_sheet()
                            self.rx_image_armed = True  # phasage = début de carte normalisé
                            self.rx_sheet_had_start = True  # 2.9.5 — carte prise depuis son début
                            phase_pos = observation.get("phase_position")
                            if phase_pos is not None and not getattr(self, "phase_locked_from_header", False):
                                phase_px = int(round(float(phase_pos) * 1809.0)) % 1809
                                self.line_phase_offset_px = phase_px
                                self.phase_locked_from_header = True
                                self.last_margin_confidence_pct = 96.0
                                self.log_event(
                                    f"🎯 [Synchro Phasage WEFAX] Origine de ligne verrouillée sur l'impulsion de phase (offset={phase_px} px)."
                                )
                                self._mark_banner_step("PHASE", f"Cale a {phase_px} px")
                            continue

                        # 3. Gestion de STOP : 2 lignes à 450 Hz sur 4 après L.100 -> sauvegarde + attente stricte du prochain START
                        self._stop_window = (
                            getattr(self, "_stop_window", []) + [1 if apt_tone == "STOP" else 0]
                        )[-4:]
                        if apt_tone == "STOP" and self.rx_decoding_active and self.rx_current_line > 100:
                            self.apt_stop_hits += 1
                        elif sum(self._stop_window) == 0:
                            self.apt_stop_hits = 0

                        # STOP d'une carte qui n'a pas été suivie (feuille vide ou presque) : rien à archiver,
                        # la station repasse au repos -> attente du prochain START (spécification OMM).
                        if (
                            sum(self._stop_window) >= 2
                            and self.rx_current_line <= 100
                            and not getattr(self, "waiting_after_stop", False)
                        ):
                            self._stop_window = []
                            self.log_event(
                                "🏁 APT STOP d'une carte non suivie (feuille de "
                                f"{self.rx_current_line} lignes non archivée) : attente du prochain START."
                            )
                            self._reset_blank_rx_sheet()
                            self.rx_sheet_initialized_for_live = False
                            self.waiting_after_stop = True
                            continue

                        if (
                            self.rx_decoding_active
                            and self.rx_current_line > 100
                            and (self.apt_stop_hits >= 2 or sum(self._stop_window) >= 2)
                        ):
                            self.apt_stop_hits = 0
                            self._stop_window = []
                            self.log_event(
                                "🏁 APT STOP : commutation FM 450 Hz confirmée ; sauvegarde et attente de la carte suivante."
                            )
                            self._finalize_completed_wefax_chart(trigger_reason="APT STOP 450Hz")
                            self._reset_blank_rx_sheet()
                            self.rx_sheet_initialized_for_live = False
                            self.waiting_after_stop = True
                            self.pin_completed = False
                            break

                    # Tant que waiting_after_stop est actif, on n'empile aucune ligne parasite avant le prochain
                    # START/PHASE — sauf si une vraie carte est déjà en cours (START manqué pendant un fading) :
                    # 8 lignes consécutives avec la structure d'une carte.
                    if getattr(self, "waiting_after_stop", False):
                        if image_evidence and self.rx_decoding_active and signal_above_squelch:
                            self.waiting_after_stop = False
                            self.pin_completed = False
                            self._reset_blank_rx_sheet()
                            self.rx_image_armed = True
                            self.rx_sheet_had_evidence = True
                            self.log_event(
                                "🖼️ Carte en cours détectée sans START (structure WEFAX sur 8 lignes) : "
                                "tracé repris en cours de route."
                            )
                        else:
                            continue

                    # Le reste de la salve START (5 s = 10 lignes) n'est pas de l'image : il n'est plus tracé
                    # en haut de carte (bande hachurée observée sur la carte DDK6 du 15/11 07:54).
                    if apt_tone == "START_576" and self.rx_current_line < 30:
                        continue

                    if self.rx_decoding_active and (
                        signal_above_squelch
                        or self.rx_current_line >= 25
                        or getattr(self, "rx_image_armed", False)
                    ):
                        # Rien n'est tracé tant qu'aucune carte n'est identifiée : START, phasage, ou structure de
                        # carte (lignes successives corrélées). Une porteuse non modulée (repos entre deux cartes),
                        # du bruit ou un signal RTTY ne remplissent plus la feuille.
                        if not getattr(self, "rx_image_armed", False):
                            if image_evidence and signal_above_squelch:
                                self.rx_image_armed = True
                                self.rx_sheet_had_evidence = True
                                self.log_event(
                                    "🖼️ Carte en cours détectée (structure WEFAX sur 8 lignes) : tracé en cours de route."
                                )
                            else:
                                self._set_wefax_protocol_stage("PORTEUSE")
                                continue
                        if self._flat_carrier_lines >= self.FLAT_CARRIER_END_LINES:
                            n_done = self.rx_current_line
                            self.log_event(
                                f"🏁 Porteuse non modulée depuis 2 min à L.{n_done} (STOP non reçu) : "
                                + ("carte archivée." if n_done >= 200 else "feuille non archivée.")
                                + " Attente du prochain START."
                            )
                            if n_done >= 200:
                                self._finalize_completed_wefax_chart(
                                    trigger_reason="Fin de carte (porteuse non modulée)"
                                )
                            self._reset_blank_rx_sheet()
                            self.rx_sheet_initialized_for_live = False
                            self.waiting_after_stop = True
                            self.pin_completed = False
                            break
                        if not self.rx_sheet_initialized_for_live and self.audio_live_connected:
                            self.pin_completed = False
                            flags = (
                                getattr(self, "rx_sheet_had_start", False),
                                getattr(self, "rx_sheet_had_evidence", False),
                            )
                            self._reset_blank_rx_sheet()
                            self.rx_image_armed = True
                            self.rx_sheet_had_start, self.rx_sheet_had_evidence = flags

                        if self.raw_wefax_img.shape[1] != 1809:
                            self._reset_blank_rx_sheet()

                        # Filet de sécurité si le STOP a été manqué : 1 min sans signal exploitable (station
                        # perdue), ou hauteur maximale. Une zone blanche DANS la carte ne la coupe plus
                        # (carte « Sea Surface Temperatures » du 15/11 coupée à L.1496 avant son cartouche).
                        if not (signal_above_squelch or image_evidence):
                            self._low_snr_tail_lines = getattr(self, "_low_snr_tail_lines", 0) + 1
                        else:
                            self._low_snr_tail_lines = 0
                        # 2.8.6 — une carte commencée par un START n'est plus coupée par un évanouissement
                        # avant sa durée normale (≈ 1 300 lignes à Northwood) : 4 min de silence sont tolérées
                        # au lieu de 80 s. La nuit du 16-17/11, cinq cartes ont été coupées en deux morceaux
                        # (le premier jeté s'il faisait moins de 200 lignes) alors que l'enregistrement,
                        # décodé d'un trait, donne la carte entière.
                        tail_limit = (
                            480
                            if (getattr(self, "rx_sheet_had_start", False) or getattr(self, "rx_sheet_had_evidence", False))
                            and self.rx_current_line < self.EXPECTED_CHART_LINES
                            else 160
                        )
                        if self._low_snr_tail_lines >= tail_limit or self.rx_current_line >= self.MAX_CHART_LINES:
                            reason = (
                                f"Fin de carte (signal perdu depuis {self._low_snr_tail_lines // 2} s)"
                                if self.rx_current_line < self.MAX_CHART_LINES
                                else f"Fin de carte (hauteur maximale {self.MAX_CHART_LINES} lignes)"
                            )
                            self.log_event(
                                f"🏁 {reason} à L.{self.rx_current_line} — Sauvegarde et mise en attente du prochain START."
                            )
                            if self._low_snr_tail_lines >= tail_limit and self.rx_current_line > 200:
                                # 2.8.3 : les lignes ne sont plus remplacées par du gris ; la queue sans
                                # signal (80 s) est retirée ici au lieu d'être archivée.
                                self._crop_sheet_rows(
                                    0, max(1, self.rx_current_line - self._low_snr_tail_lines + 12)
                                )
                            if self.rx_current_line >= 200:
                                self._finalize_completed_wefax_chart(trigger_reason=reason)
                            self._reset_blank_rx_sheet()
                            self.rx_sheet_initialized_for_live = False
                            self.waiting_after_stop = True
                            self.pin_completed = False
                            break

                        if self.rx_current_line >= self.raw_wefax_img.shape[0]:
                            pad = np.full((250, 1809), 248, np.uint8)
                            self.raw_wefax_img = np.vstack((self.raw_wefax_img, pad))
                            self.processed_wefax_img = np.vstack((self.processed_wefax_img, pad.copy()))
                            self.rx_confidence_img = np.vstack(
                                (self.rx_confidence_img, np.zeros((250, 1809), np.uint8))
                            )

                        total_shift = int(self.line_phase_offset_px) % 1809
                        if total_shift != 0:
                            px_row = np.roll(px_row, -total_shift)

                        conf_row = np.asarray(getattr(self.dsp, "last_row_confidence", np.ones(1809)))
                        if len(conf_row) != 1809:
                            conf_row = np.ones(1809)
                        if total_shift != 0:
                            conf_row = np.roll(conf_row, -total_shift)
                        # 2.8.3 — Une ligne démodulée n'est PLUS JAMAIS remplacée par du gris. L'indicateur
                        # de squelch (SNR spectral moins pénalité de fading) passait sous le seuil sur un
                        # tiers des lignes d'une carte reçue S9 (15/11, GYA3 19:36 UTC : 404 lignes sur 1250
                        # effacées alors que le démodulateur les avait décodées). La confiance par pixel du
                        # démodulateur renseigne déjà la restauration et la carte de confiance.
                        self._chart_snr_sum = getattr(self, "_chart_snr_sum", 0.0) + float(
                            getattr(self, "raw_snr_db", self.current_snr_db)
                        )
                        self._chart_traced_lines = getattr(self, "_chart_traced_lines", 0) + 1
                        if observation.get("valid"):
                            self._chart_valid_lines = getattr(self, "_chart_valid_lines", 0) + 1
                        if apt_tone is None and self.current_wefax_stage != "IMAGE":
                            self._set_wefax_protocol_stage("IMAGE")
                        self.rx_confidence_img[self.rx_current_line, :] = np.clip(
                            conf_row * 255.0, 0, 255
                        ).astype(np.uint8)
                        self.raw_wefax_img[self.rx_current_line, :] = px_row
                        self.processed_wefax_img[self.rx_current_line, :] = px_row

                        self.rx_current_line += 1
                        lines_decoded_this_tick += 1

                        # 2.11.0 — STOP manqué : fin de carte quand la structure disparaît (bruit seul
                        # pendant 1 min, au-delà de 60 % de la durée normale). La queue de bruit est
                        # retirée avant l'archivage (cartes DDK3 du 20/11 : 1 000 lignes de bruit).
                        det = getattr(self, "_chart_end_det", None)
                        if det is None:
                            det = self._chart_end_det = ChartEndDetector()
                        det.update(self.rx_current_line, px_row)
                        if det.should_end(self.rx_current_line, self.EXPECTED_CHART_LINES):
                            cut = det.crop_line(self.rx_current_line)
                            self.log_event(
                                f"🏁 Fin de carte (plus de structure d'image depuis 1 min, STOP non reçu) à "
                                f"L.{self.rx_current_line} : bruit retiré, carte gardée jusqu'à L.{cut}."
                            )
                            self._crop_sheet_rows(0, max(1, cut))
                            if self.rx_current_line >= 200:
                                self._finalize_completed_wefax_chart(
                                    trigger_reason="Fin de carte (structure perdue, STOP non reçu)"
                                )
                            self._reset_blank_rx_sheet()
                            self.rx_sheet_initialized_for_live = False
                            self.waiting_after_stop = True
                            self.pin_completed = False
                            break

                        # RECADRAGE EN COURS DE CARTE (cartes prises en cours de route, sans phasage) :
                        # coupe au milieu de la bande blanche verticale (voir dsp/chart_restore.find_wrap_cut).
                        # Avec phasage reçu, le début de ligne est déjà exact : rien n'est déplacé.
                        if (
                            self.auto_margin_once_active
                            and not self.auto_margin_locked_for_chart
                            and self.rx_current_line in (300, 600, 900)
                        ):
                            self._live_recenter_chart()
                        # Restauration 2D temps réel toutes les 25 lignes
                        if self.rx_current_line >= 25 and (self.rx_current_line % 25 == 0):
                            sub = self.raw_wefax_img[: self.rx_current_line, :].copy()
                            sl = float(self.sld_slant.get())
                            if abs(sl) > 1e-6:
                                for rownum in range(len(sub)):
                                    sub[rownum] = np.roll(sub[rownum], -int(round(rownum * sl * 25.0)))
                            csub = None
                            if abs(sl) <= 1e-6 and hasattr(self, "rx_confidence_img"):
                                csub = self.rx_confidence_img[: self.rx_current_line]
                            self.processed_wefax_img[: self.rx_current_line, :] = self.dsp.restore_image_v1_9(
                                sub,
                                use_fft_notch=self.fft_notch_var.get(),
                                use_structure_tensor=self.tensor_var.get(),
                                use_adaptive_bin=self.adapt_bin_var.get(),
                                conf=csub,
                            )
                else:
                    if len(self.rx_sample_accumulator) > int(exact_samples_per_line * 2):
                        self.rx_sample_accumulator = self.rx_sample_accumulator[
                            -int(exact_samples_per_line) :
                        ]
                    break

            if lines_decoded_this_tick > 0:
                total_h = self.raw_wefax_img.shape[0]
                gate_tag = "Brute gardée" if self.dsp.kept_raw_fallback else "Retraitée OK"
                mrg_tag = (
                    f"Marge:{self.last_margin_confidence_pct:.0f}%"
                    if self.last_margin_confidence_pct > 0
                    else "Marge:Veille"
                )
                self.lbl_rx_line_counter.config(
                    text=f"🟢 RX L.{self.rx_current_line}/{total_h} | AFC:{self.dsp.afc_white_freq_hz:.0f}Hz | {mrg_tag} | {gate_tag}"
                )
                self.lbl_busy_badge.config(
                    text=f"📡 RX LIGNE {self.rx_current_line}", bg="#0284c7", fg="#ffffff"
                )
                self._refresh_canvas()
            else:
                if getattr(self, "waiting_after_stop", False):
                    self.lbl_rx_line_counter.config(
                        text=f"🏁 Carte terminée et archivée — En attente du prochain signal START (300 Hz) | AFC:{self.dsp.afc_white_freq_hz:.0f}Hz"
                    )
                elif self.rx_decoding_active and self.rx_current_line == 0:
                    sq_state = (
                        "🟢 Signal OK"
                        if self.current_snr_db >= self.snr_squelch_threshold_db
                        else f"⏳ Attente SNR >= {self.snr_squelch_threshold_db}dB"
                    )
                    self.lbl_rx_line_counter.config(
                        text=f"{sq_state} (SNR:{self.current_snr_db:+.1f}dB) | AFC:{self.dsp.afc_white_freq_hz:.0f}Hz"
                    )

            self._draw_three_quality_bargraphs()
            self._draw_permanent_top_signal_curve()
        except Exception as exc:
            self.log_event("ERREUR boucle reception: " + repr(exc))

        self.root.after(180, self._realtime_rx_and_spectrum_loop)

    # ------------------------------------------------ feuille de réception
    def _reset_blank_rx_sheet(self):
        self._chart_end_det = ChartEndDetector()
        self.rx_image_armed = False
        self.rx_sheet_had_start = False
        self.rx_sheet_had_evidence = False
        self._evidence_rows = []
        self._flat_carrier_lines = 0
        if hasattr(self, "portable_ws"):
            self.portable_ws.begin_document_reception()
        if getattr(self, "viewing_archived_file", None):
            # 2.9.0 — l'archive reste affichée ; la boucle de réception revient au direct après 5 lignes
            self._live_return_pending = True
        res = self._reset_sheet_with_banner()
        self._hide_main_canvas_roi_overlays()
        return res

    def _reset_sheet_with_banner(self):
        res = self._reset_sheet_counters()
        b = getattr(self, "rx_step_banner", None)
        if b is not None:
            b.set_step(
                "AUDIO",
                "confirmed" if getattr(self, "audio_live_connected", False) else "idle",
                "Flux recent",
            )
            b.set_step("START", "idle", "Attente 300 Hz", log_transition=False)
            b.set_step("PHASE", "idle", "Attente synchro", log_transition=False)
            b.set_step("IMAGE", "idle", "Feuille vierge", log_transition=False)
            b.set_step("STOP", "idle", "Attente 450 Hz", log_transition=False)
        return res

    def _reset_sheet_counters(self):
        self._reset_sheet_keep_pending_audio()
        self.generation += 1
        self.apt_stop_hits = 0
        self.waiting_after_stop = False
        self.rotation_quarters = 0
        if hasattr(self, "sld_slant"):
            self.sld_slant.set(0.0)

    def _reset_sheet_keep_pending_audio(self):
        pending = getattr(self, "rx_sample_accumulator", np.zeros(0, np.float32))
        self._reset_sheet_blank_image()
        self.rx_sample_accumulator = pending
        self.rx_fractional_rem = 0.0
        self.last_quality_line = -1
        self.last_good_audio = time.monotonic()

    def _reset_sheet_blank_image(self):
        self.rx_confidence_img = np.zeros((1200, 1809), dtype=np.uint8)
        self.raw_wefax_img = np.full((1200, 1809), 248, dtype=np.uint8)
        self.processed_wefax_img = self.raw_wefax_img.copy()
        self.rx_current_line = 0
        self.line_phase_offset_px = 0
        self.auto_margin_locked_for_chart = False
        self.phase_locked_from_header = False
        self.last_margin_confidence_pct = 0.0
        self.rx_sheet_initialized_for_live = True
        self.rx_sample_accumulator = np.zeros(0, dtype=np.float32)
        self._start_window = []
        self._stop_window = []
        self._low_snr_tail_lines = 0
        self._phase_run = 0
        self._chart_snr_sum = 0.0
        self._chart_traced_lines = 0
        self._chart_valid_lines = 0
        self.dsp.reset_filter_states()
        self._recompute_roi_from_qth()
        self._set_wefax_protocol_stage("PORTEUSE")
        self._refresh_canvas()
        self.log_event("🆕 Feuille de réception WEFAX vierge (1809x1200 px) prête.")

    # ------------------------------------------------ marche / arrêt
    def _toggle_rx_decoding(self):
        res = self._toggle_rx_decoding_base()
        if hasattr(self, "hybrid_arbiter"):
            self.hybrid_arbiter._style_wefax_toggle_button()
            if not self.rx_decoding_active:
                self.hybrid_arbiter.notify_manual_stop()
            else:
                self.hybrid_arbiter.resume_automation()
        return res

    def _toggle_rx_decoding_base(self):
        self.rx_decoding_active = not self.rx_decoding_active
        self.btn_rx_start.set_state(self.rx_decoding_active)
        self.btn_top_rx.set_state(self.rx_decoding_active)

        if self.rx_decoding_active:
            self.waiting_after_stop = False
            with self.rx_audio_queue.mutex:
                self.rx_audio_queue.queue.clear()
            self.rx_sample_accumulator = np.zeros(0, dtype=np.float32)
            self.dsp.reset_filter_states()
            src_name = self.cmb_audio.get() if self.audio_live_connected else "Synthétiseur FM Simulation"
            self.log_event(
                f"📡 DÉCODAGE WEFAX 120 RPM ARMÉ sur [{src_name}] (Squelch SNR >= {self.snr_squelch_threshold_db} dB)."
            )
        else:
            if 20 < self.rx_current_line < 1100:
                self._warn_suboptimal_user_action(
                    "Vous avez coupé le Décodage 120 RPM alors qu'une carte est en cours de réception !"
                )
            self.log_event(f"⏹️ Décodage WEFAX mis en pause à la ligne {self.rx_current_line}.")
            if self.rx_current_line > 20:
                self._finalize_completed_wefax_chart(trigger_reason="Arrêt Manuel")

    def _resume_midchart(self):
        if self.carrier_scan_active or self.connection_busy:
            return
        if self.rx_current_line > 25 and not self.waiting_after_stop:
            if not messagebox.askyesno("Reprendre", "Archiver le fragment actuel ?"):
                return
            self._finalize_completed_wefax_chart("Reprise operateur")
        self.rx_sample_accumulator = np.zeros(0, np.float32)
        self.waiting_after_stop = False
        self.pin_completed = False
        self._reset_blank_rx_sheet()
        self.rx_decoding_active = True
        self.btn_rx_start.set_state(True)
        self.btn_top_rx.set_state(True)
        self._show_live()

    def _mark_banner_step(self, step, detail):
        """Étape du bandeau acquise pour la carte en cours (reste affichée jusqu'à la feuille suivante)."""
        b = getattr(self, "rx_step_banner", None)
        if b is not None:
            stamp = datetime.now(timezone.utc).strftime("%H:%M")
            b.set_step(step, "confirmed", f"{detail} - {stamp} UTC")

    def chart_quality(self):
        """Qualité de la carte en cours, mesurée sur TOUTES ses lignes tracées (et non à l'instant présent).

        Retourne (SNR spectral moyen en dB, part des lignes exploitables 0..1, nombre de lignes mesurées).
        """
        n = int(getattr(self, "_chart_traced_lines", 0))
        if n <= 0:
            return float(getattr(self, "raw_snr_db", getattr(self, "current_snr_db", 0.0))), 0.0, 0
        return (
            float(self._chart_snr_sum) / n,
            float(getattr(self, "_chart_valid_lines", 0)) / n,
            n,
        )

    def _set_wefax_protocol_stage(self, stage_code: str):
        self.current_wefax_stage = stage_code
        for code, lbl_widget in self.stage_badge_widgets.items():
            if code == stage_code:
                lbl_widget.config(bg="#f59e0b", fg="#020617", font=("Consolas", 8, "bold"))
            else:
                lbl_widget.config(bg="#1e293b", fg="#94a3b8", font=("Consolas", 7))

    def _validate_margin_shift(self, mx: int):
        self.set_busy_state(True, "RECALAGE MARGE...")
        try:
            mx = int(mx) % self.raw_wefax_img.shape[1]
            self.raw_wefax_img = np.roll(self.raw_wefax_img, -mx, axis=1)
            self._roll_confidence(-mx)
            self.processed_wefax_img = np.roll(self.processed_wefax_img, -mx, axis=1)
            self.line_phase_offset_px = (self.line_phase_offset_px + mx) % self.raw_wefax_img.shape[1]
            self.auto_margin_locked_for_chart = True
            self.pending_margin_x = None
            self.canvas_tool_mode = "NONE"
            self.btn_mode_margin.set_state(False)
            self._apply_full_restoration()
            self.log_event(
                f"✅ Marge manuelle recalée (-{mx} px) et phase verrouillée pour la suite de la carte."
            )
        finally:
            self.set_busy_state(False)

    def _toggle_apt_auto(self):
        self.apt_auto_start_active = not self.apt_auto_start_active
        self.btn_apt_auto.set_state(self.apt_auto_start_active)
        if not self.apt_auto_start_active:
            self._warn_suboptimal_user_action(
                "Auto-Start/Stop APT désactivé : la détection automatique des tonalités 300 Hz / 450 Hz est coupée."
            )

    def _toggle_upstream_hf_cond(self):
        self.upstream_hf_cond_active = not self.upstream_hf_cond_active
        self.btn_hf_cond.set_state(self.upstream_hf_cond_active)
        if not self.upstream_hf_cond_active:
            self._warn_suboptimal_user_action(
                "Conditionneur HF & Anti-QSB 2D désactivé : risque de stries noires sur fading et dérive AFC !"
            )
        else:
            self.log_event("🛡️ Conditionneur HF Live en amont (AGC/AFC/Anti-QSB 2D) : ACTIVÉ.")

    def _toggle_qrn_blanker(self):
        self.qrn_blanker_var.set(not self.qrn_blanker_var.get())
        self.btn_qrn_blanker.set_state(self.qrn_blanker_var.get())
        if not self.qrn_blanker_var.get():
            self._warn_suboptimal_user_action(
                "Blanker QRN amont coupé : les impulsions atmosphériques (orages/statiques) ne seront plus écrêtées."
            )

    def _toggle_auto_save_png(self):
        self.auto_save_png_active = not self.auto_save_png_active
        self.btn_autosave_png.set_state(self.auto_save_png_active)
        self.log_event(
            f"💾 Auto-Save PNG en fin de carte ({self.archive_dir}) : "
            f"{'ACTIVÉ' if self.auto_save_png_active else 'DÉSACTIVÉ'}."
        )

    def _toggle_auto_margin_once(self):
        self.auto_margin_once_active = not self.auto_margin_once_active
        self.btn_auto_margin_once.set_state(self.auto_margin_once_active)
        self.log_event(
            f"📐 Auto-Marge unique en début de carte : "
            f"{'ACTIVÉE' if self.auto_margin_once_active else 'DÉSACTIVÉE'}."
        )

    # ------------------------------------------------------- fin de carte
    def _finalize_completed_wefax_chart(self, trigger_reason="Fin de carte"):
        if not self._sheet_has_wefax_content():
            self.log_event(
                f"Feuille de {self.rx_current_line} lignes sans carte WEFAX identifiable (ni START, ni structure "
                f"de carte sur 1 min) : non archivée ({trigger_reason})."
            )
            self._auto_record_chart_end(trigger_reason)
            return None
        # 2.9.5 — carte prise en cours de route (sans START) et trop courte : ce n'est qu'un fragment. Le 19/11,
        # la carte de 07:04 (505 lignes, reprise à 07:11 après le NAVTEX) et celle de Northwood vue à 11:57
        # (arrivée au milieu de la carte) étaient rangées parmi les cartes : l'opérateur les a crues tronquées.
        # Les fragments sont gardés à part (cartes_partielles) et « Dernière carte » reste la dernière complète.
        fragment = self._is_chart_fragment()
        if hasattr(self, "portable_ws"):
            start_utc = self.portable_ws.active_rx_start_utc or datetime.now(timezone.utc)
            day_dir = self.portable_ws.reception_day_dir(start_utc)
            # 2.11.0 — cartes/partielles (au lieu d'un dossier cartes_partielles à côté de cartes)
            self.archive_dir = str(layout.partial_dir(day_dir) if fragment else layout.cards_dir(day_dir))
            Path(self.archive_dir).mkdir(parents=True, exist_ok=True)
        else:
            start_utc = datetime.now(timezone.utc)

        rel_wf = WeatherReliabilityEstimator.compute_wefax_reliability(self)
        before_path = getattr(self, "last_saved_path", None)
        prev_completed = (getattr(self, "completed_rgb", None), getattr(self, "completed_raw", None))
        n_lines = int(self.rx_current_line)
        res = self._finalize_with_banner(trigger_reason=trigger_reason)
        after_path = getattr(self, "last_saved_path", None)
        if fragment:
            if prev_completed[0] is not None:
                self.completed_rgb, self.completed_raw = prev_completed
            self.log_event(
                f"🧩 Carte prise en cours de route ({n_lines} lignes sur ≈ {self.EXPECTED_CHART_LINES}, sans START : "
                "haut de carte manquant) : rangée dans cartes/partielles, pas parmi les cartes ; « Dernière carte » reste la dernière carte "
                "complète. La carte suivante sera prise dès son START."
            )
            if hasattr(self, "portable_ws"):
                self.archive_dir = str(layout.cards_dir(day_dir))
            self._auto_record_chart_end(trigger_reason)
            if getattr(self, "saved_generation", -1) == getattr(self, "generation", 0):
                self._clear_safety_checkpoint()
            return res

        if hasattr(self, "portable_ws") and after_path and str(after_path) != str(before_path):
            try:
                meta_p = getattr(self, "current_metadata_path", None)
                meta = (
                    json.loads(Path(meta_p).read_text(encoding="utf-8"))
                    if meta_p and Path(meta_p).is_file()
                    else {}
                )
                files = [Path(after_path).parent / fn for fn in meta.get("files", [])]
                sources = [p for p in files if "_decodee" in p.name]
                derived = [p for p in files if "_decodee" not in p.name]
                st_id = (
                    self.hybrid_arbiter.wefax_return_station
                    if is_rtty_frequency(self.radio.actual_freq_khz)
                    else self.radio.active_station_id
                )
                f_khz = (
                    self.hybrid_arbiter.wefax_return_freq_khz
                    if is_rtty_frequency(self.radio.actual_freq_khz)
                    else self.radio.actual_freq_khz
                )
                doc_id = f"WEFAX_{st_id}_{start_utc.strftime('%Y%m%d_%H%M%SZ')}"
                self.portable_ws.register_document_record(
                    category="cartes",
                    doc_id=doc_id,
                    start_utc=start_utc,
                    end_utc=datetime.now(timezone.utc),
                    station=st_id,
                    freq_khz=f_khz,
                    params={"filter": self.radio.actual_filter_str, "mode": self.radio.actual_mode_str},
                    quality={
                        "snr_proxy_db": round(self.chart_quality()[0], 1),
                        "lines": int(meta.get("lines", 0)),
                        "reliability_pct": rel_wf["score_pct"],
                        "reliability_grade": rel_wf["grade"],
                    },
                    source_files=sources,
                    derived_files=derived,
                    status="COMPLET" if "STOP" in str(trigger_reason).upper() else "PARTIEL",
                )
            except Exception as exc:
                self.log_event("Indexation document : " + repr(exc))
        self._auto_record_chart_end(trigger_reason)
        if getattr(self, "saved_generation", -1) == getattr(self, "generation", 0):
            self._clear_safety_checkpoint()
        return res

    # 2.9.5 — sans START, moins de 55 % d'une carte : fragment.
    # 2.9.8 — décision F4NMK du 19/11 (« les cartes doivent être complètes ») : sans START ni phasage, une carte
    # n'est rangée parmi les cartes que si elle a au moins 92 % de la longueur d'une carte (START manqué par
    # fading alors que le poste écoutait déjà). La carte GYA H+48 de 17:24, reprise à 17:26:49 (1 016 lignes, haut
    # manquant), était rangée parmi les cartes.
    FRAGMENT_MAX_FRACTION = 0.92

    def _chart_programme_meta(self, stamp, n_lines):
        """{"utc_debut", "programme_code", "programme"} d'après l'heure de fin, le nombre de lignes et la cadence."""
        try:
            from datetime import timedelta as _td

            from wefax_station.core.schedules import programme_of_chart
            from wefax_station.core.stations import get_wefax_station_by_freq

            lpm = 120.0
            start = stamp - _td(seconds=60.0 * float(n_lines) / lpm)
            st = get_wefax_station_by_freq(float(self.radio.actual_freq_khz))
            prog = programme_of_chart(st["family"] if st else "", start)
            out = {"utc_debut": start.isoformat()}
            if prog:
                out.update({"programme_code": prog[0], "programme": prog[1]})
            return out
        except Exception:
            return {}

    START_FRAGMENT_FRACTION = 0.5

    def _is_chart_fragment(self):
        """Carte incomplète ? Sans START : moins de 92 % de la durée normale. 2.11.0 — avec START mais signal
        perdu avant la moitié de la carte (DDK6 du 20/11 à 15:12 : 327 lignes) : rangée aussi parmi les
        cartes partielles au lieu de passer pour une carte complète."""
        n = int(self.rx_current_line)
        if not getattr(self, "rx_sheet_had_start", False):
            return n < int(self.FRAGMENT_MAX_FRACTION * self.EXPECTED_CHART_LINES)
        return n < int(self.START_FRAGMENT_FRACTION * self.EXPECTED_CHART_LINES)

    FLAT_CARRIER_END_LINES = 240  # 2 min de porteuse uniforme : repos entre deux cartes
    MAX_CHART_LINES = 2400  # 20 min : aucune carte DWD / Northwood n'est plus longue
    PHASE_SPLIT_LINES = 40  # 2.11.0 — 20 s de phasage stable pour clore une carte en cours (vrai phasage : 30 s)
    EXPECTED_CHART_LINES = 1250  # durée habituelle d'une carte (Northwood ≈ 1 300 lignes, DWD ≈ 1 200)

    def _crop_sheet_rows(self, top, bottom):
        """Ne garde que les lignes [top, bottom) de la feuille en cours (image, image traitée, confiance)."""
        for name in ("raw_wefax_img", "processed_wefax_img", "rx_confidence_img"):
            arr = getattr(self, name, None)
            if arr is not None and len(arr) >= bottom:
                setattr(self, name, np.ascontiguousarray(arr[top:bottom]))
        self.rx_current_line = int(bottom - top)

    def _live_recenter_chart(self):
        n = int(self.rx_current_line)
        if getattr(self, "phase_locked_from_header", False):
            self.auto_margin_locked_for_chart = True
            return
        conf = self.rx_confidence_img[:n] if hasattr(self, "rx_confidence_img") else None
        cut, width, score = find_wrap_cut(self.raw_wefax_img[:n], conf)
        self.last_margin_confidence_pct = max(self.last_margin_confidence_pct, score)
        if cut is None or score < 70.0:
            if n >= 900:
                self.auto_margin_locked_for_chart = True
                self.log_event(
                    "📐 Recadrage automatique non appliqué (pas de bande blanche verticale nette) : "
                    "carte laissée telle que reçue, réglable à la main."
                )
            return
        self.auto_margin_locked_for_chart = True
        if min(cut, 1809 - cut) <= 10:
            return
        self.raw_wefax_img[:n, :] = np.roll(self.raw_wefax_img[:n, :], -cut, axis=1)
        self._roll_confidence(-cut, n)
        self.line_phase_offset_px = (self.line_phase_offset_px + cut) % 1809
        self.log_event(
            f"📐 Recadrage automatique : coupe au milieu d'une bande blanche de {width} px "
            f"(décalage {cut} px, confiance {score:.0f} %)."
        )

    def _finalize_with_banner(self, trigger_reason="Fin de carte"):
        b = getattr(self, "rx_step_banner", None)
        if b is not None:
            if "STOP" in str(trigger_reason).upper():
                b.set_step("STOP", "confirmed", "STOP 450 Hz valide")
            b.set_step("SAVED", "active", "Verification fichier...")
        res = self._finalize_geometry_and_save(trigger_reason=trigger_reason)
        if b is not None and getattr(self, "last_saved_path", None):
            b.set_step("SAVED", "confirmed", str(self.last_saved_path).split("\\")[-1])
        return res

    SLANT_MIN_PX_PER_LINE = 0.008  # en dessous (< 10 px sur une carte) : pente non corrigée
    SLANT_MIN_LINES = 400

    def _finalize_geometry_and_save(self, trigger_reason="Fin de carte"):
        # Pente : mesurée sur toute la hauteur de la carte. L'horloge est déjà suivie par le démodulateur ;
        # on ne corrige l'image que si une pente nette et fiable subsiste.
        if self.rx_current_line >= self.SLANT_MIN_LINES:
            _m, slope_full, score_full = estimate_geometry(self.raw_wefax_img[: self.rx_current_line])
            if score_full >= 65.0 and abs(slope_full) >= self.SLANT_MIN_PX_PER_LINE:
                self._accept_auto_slant(slope_full, score_full)
            else:
                self.log_event(
                    f"Pente résiduelle {slope_full:+.4f} px/ligne (score {score_full:.0f}/100) : "
                    "carte laissée droite."
                )
        n = int(self.rx_current_line)
        conf = self.rx_confidence_img[:n] if hasattr(self, "rx_confidence_img") else None
        # 1. lignes uniformes en tête / queue (porteuse de repos avant le START ou après le STOP manqué) ;
        #    une ligne contenant du dessin n'est jamais retirée.
        if n >= 200:
            top, bottom = trim_blank_rows(self.raw_wefax_img[:n], conf)
            if top > 0 or bottom < n:
                self._crop_sheet_rows(top, bottom)
                self.log_event(f"✂️ Lignes vides retirées : {top} en tête, {n - bottom} en queue.")
                n = int(self.rx_current_line)
                conf = self.rx_confidence_img[:n] if hasattr(self, "rx_confidence_img") else None
        # 2. recadrage horizontal final (carte sans phasage) sur toute la hauteur
        if n >= 200 and not getattr(self, "phase_locked_from_header", False):
            cut, width, score = find_wrap_cut(self.raw_wefax_img[:n], conf)
            if cut is not None and score >= 60.0 and min(cut, 1809 - cut) > 10:
                self.raw_wefax_img[:n] = np.roll(self.raw_wefax_img[:n], -cut, axis=1)
                self._roll_confidence(-cut, n)
                self.line_phase_offset_px = (self.line_phase_offset_px + cut) % 1809
                self.log_event(
                    f"📐 Recadrage final : coupe au milieu d'une bande blanche de {width} px "
                    f"(décalage {cut} px, confiance {score:.0f} %)."
                )
        # 3. 2.9.7 — bord droit replié à gauche du trait de cadre (Northwood dessine jusque dans l'impulsion
        #    de phasage : 82 px de la carte GYA3 du 19/11 17:12 étaient à gauche du cadre). La marge blanche
        #    des cartes DWD n'est jamais concernée (aucun dessin à gauche).
        if n >= 400:
            k, fscore = find_frame_line(self.raw_wefax_img[:n], float(self.sld_slant.get()) * 25.0)
            if k is not None and fscore >= 70.0:
                cut = max(0, k - 2)
                self.raw_wefax_img[:n] = np.roll(self.raw_wefax_img[:n], -cut, axis=1)
                self._roll_confidence(-cut, n)
                self.line_phase_offset_px = (self.line_phase_offset_px + cut) % 1809
                self.log_event(
                    f"📐 Bord droit replié à gauche du cadre ({cut} px) : carte remise d'un seul tenant "
                    f"(trait de cadre net, confiance {fscore:.0f} %)."
                )
        self.auto_margin_locked_for_chart = True
        self._save_completed_chart(trigger_reason)

    def _save_completed_chart(self, trigger_reason="Fin de carte"):
        n = self.rx_current_line
        if n < 1 or self.saved_generation == self.generation:
            return
        raw = self.raw_wefax_img[:n].copy()
        work = raw.copy()
        slope = float(self.sld_slant.get()) * 25.0
        for i in range(n):
            shift = int(round(i * slope))
            if shift:
                work[i] = np.roll(work[i], -shift)
        conf_work = None
        if hasattr(self, "rx_confidence_img") and len(self.rx_confidence_img) >= n:
            conf_work = self.rx_confidence_img[:n].copy()
            for i in range(n):
                shift = int(round(i * slope))
                if shift:
                    conf_work[i] = np.roll(conf_work[i], -shift)
        processed = self.dsp.restore_image_v1_9(
            work,
            use_fft_notch=self.fft_notch_var.get(),
            use_structure_tensor=self.tensor_var.get(),
            use_adaptive_bin=self.adapt_bin_var.get(),
            conf=conf_work,
        )
        body = np.rot90(processed, k=-self.rotation_quarters) if self.rotation_quarters else processed
        stamp = datetime.now(timezone.utc)
        signed = self._signed(body, stamp, trigger_reason)
        self.completed_rgb = signed
        self.completed_raw = raw
        self.pin_completed = trigger_reason == "Arrêt Manuel"
        self.raw_wefax_img = raw
        self.processed_wefax_img = processed
        try:
            if self.auto_save_png_active:
                stem = Path(self.archive_dir) / (
                    stamp.strftime("%Y%m%d_%H%M%S_%f") + "_" + self.radio.active_station_id
                )
                confidence = self.rx_confidence_img[:n].copy() if hasattr(self, "rx_confidence_img") else None
                outputs = [("_decodee.png", raw), ("_traitee.png", body)]
                if confidence is not None and len(confidence) == n:
                    # carte de confiance : blanc = pixel mesuré de façon fiable, noir = pixel reconstitué / absent
                    outputs.append(("_confiance.png", confidence))
                outputs.append(("_carte.png", signed))
                # 2.11.0 — seule la carte finale reste à côté de sa fiche ; les images techniques
                # (décodée, traitée, confiance) vont dans le sous-dossier « details »
                det_dir = Path(self.archive_dir) / layout.DETAILS
                files = []
                for suffix, array in outputs:
                    target = (det_dir / (stem.name + suffix)) if layout.is_tech_file(suffix) else Path(str(stem) + suffix)
                    if target.parent != stem.parent:
                        target.parent.mkdir(parents=True, exist_ok=True)
                    files.append(Path(atomic_png(str(target), array)))
                meta = {
                    "version": SOFTWARE_VERSION,
                    "station": self.radio.active_station_id,
                    "carrier_khz": self.radio.actual_freq_khz,
                    "dial_khz": self.radio.actual_dial_khz,
                    "utc_reception_fin": stamp.isoformat(),
                    "validite_meteo": None,
                    "lines": n,
                    "width_px": int(raw.shape[1]),
                    "reason": trigger_reason,
                    # 2.9.8 — START ou phasage reçu : la carte a son haut
                    "debut_recu": bool(getattr(self, "rx_sheet_had_start", False)),
                    # 2.10.0 — carte du programme reconnue d'après l'heure de début
                    **self._chart_programme_meta(stamp, n),
                    "snr_proxy_db": round(self.chart_quality()[0], 1),
                    "lignes_exploitables_pct": round(self.chart_quality()[1] * 100.0, 1),
                    "nettete": str(getattr(self.dsp.stream, "SHARPNESS", "AUTO")),
                    "snr_enveloppe_db": round(float(getattr(self.dsp.stream, "snr_env_db", 0.0) or 0.0), 1),
                    "profil_filtre_fin_de_carte": int(getattr(self.dsp.stream, "bw_index", 0)),
                    "audio_drops": self.audio_drop_count,
                    "audio_status_count": self.audio_status_count,
                    "slant_px_per_line": slope,
                    "margin_px": self.line_phase_offset_px,
                    "rotation_quarters": self.rotation_quarters,
                    "weather_confidence": None,
                    "pixels_fiables_pct": (
                        round(float(np.mean(confidence >= 128)) * 100.0, 1)
                        if confidence is not None
                        else None
                    ),
                    "ioc": getattr(self, "rx_detected_ioc", 576),
                    "horloge_audio_ppm": round(float(self.dsp.clock_ppm), 2),
                    "afc_hz": round(float(getattr(self.dsp.stream, "afc_hz", 0.0)), 1),
                    "source": "image demodulee/corrigee ; non audio brut",
                    "files": [str(Path(p).relative_to(stem.parent)).replace("\\", "/") for p in files],
                }
                atomic_json(str(stem) + ".json", meta)
                arb = getattr(self, "hybrid_arbiter", None)
                if arb is not None and not getattr(self, "replay_active", False):
                    arb.record_chart_received(
                        self.radio.active_station_id, self.radio.actual_freq_khz, meta["pixels_fiables_pct"]
                    )
                self.last_saved_path = files[-1]
                self.current_metadata_path = Path(str(stem) + ".json")
                self.log_event("SAUVEGARDE VERIFIEE : " + str(files[-1]))
                self.lbl_archive_state.configure(text="Enregistrée : " + files[-1].name)
            else:
                self.lbl_archive_state.configure(text="Carte en mémoire ; sauvegarde automatique désactivée")
            self.saved_generation = self.generation
        except Exception as exc:
            self.log_event("ECHEC SAUVEGARDE : " + repr(exc))
            messagebox.showerror("Sauvegarde", str(exc) + "\nCarte conservée en mémoire : Exporter PNG.")
        self._set_wefax_protocol_stage("FIN")
        self._refresh_canvas()

    # ----------------------------------------------- image de démonstration
    def _update_image_evidence(self, px_row, apt_tone=None):
        """Structure de carte sur les 8 dernières lignes démodulées (voir dsp/wefax_signature.py).

        Met aussi à jour le compteur de lignes « plates » (porteuse non modulée) consécutives.
        """
        if apt_tone is not None:
            # lignes START / phasage / STOP : identiques d'une ligne à l'autre par construction, ce ne sont
            # pas des lignes de carte -> la preuve repart de zéro
            self._evidence_rows = []
            self._flat_carrier_lines = 0
            return False
        conf = np.asarray(getattr(self.dsp, "last_row_confidence", np.ones(len(px_row))))
        if len(conf) != len(px_row):
            conf = np.ones(len(px_row))
        rows = getattr(self, "_evidence_rows", [])
        rows.append((np.asarray(px_row, dtype=np.float64), conf))
        self._evidence_rows = rows[-8:]
        good = conf > 0.5
        flat = bool(np.sum(good) > 900 and float(np.std(np.asarray(px_row, dtype=np.float64)[good])) < 6.0)
        self._flat_carrier_lines = (getattr(self, "_flat_carrier_lines", 0) + 1) if flat else 0
        if len(self._evidence_rows) < 8:
            return False
        corr, std = line_structure([r for r, _ in self._evidence_rows], [c for _, c in self._evidence_rows])
        self.rx_image_structure = (corr, std)
        return is_chart_structure(corr, std)

    def _sheet_has_wefax_content(self):
        """Une feuille sans START n'est archivée que si elle contient au moins 1 min de vraie carte."""
        n = int(self.rx_current_line)
        if getattr(self, "rx_sheet_had_start", False):
            return True
        if n < 120:
            return False
        if getattr(self, "rx_sheet_had_evidence", False):
            return True  # structure de carte reconnue en direct (8 lignes) puis ≥ 1 min tracée
        rows = self.raw_wefax_img[:n].astype(np.float64)
        conf = (
            (self.rx_confidence_img[:n].astype(np.float64) / 255.0)
            if hasattr(self, "rx_confidence_img")
            else (np.ones_like(rows))
        )
        idx = np.linspace(0, n - 2, min(60, n - 1)).astype(int)
        corrs, stds = [], []
        for i in idx:
            c, sd = line_structure(rows[i : i + 2], conf[i : i + 2])
            corrs.append(c)
            stds.append(sd)
        return is_chart_structure(float(np.median(corrs)), float(np.median(stds)))

    def _roll_confidence(self, shift, rows=None):
        conf = getattr(self, "rx_confidence_img", None)
        if conf is None:
            return
        if rows is None:
            self.rx_confidence_img = np.roll(conf, shift, axis=1)
        else:
            conf[:rows, :] = np.roll(conf[:rows, :], shift, axis=1)

    def _log_new_navtex_messages(self):
        """Journalise chaque message NAVTEX complet (ZCZC … NNNN) avec son taux d'erreur."""
        msgs = getattr(self.rtty_decoder, "navtex_messages", []) or []
        done = getattr(self, "_navtex_logged", 0)
        if len(msgs) < done:
            done = 0
        for m in msgs[done:]:
            self.log_event(
                f"📠 NAVTEX reçu : émetteur {m['b1']} · objet {m['b2']} ({m['subject']}) · n° {m['serial']} · "
                f"erreurs {m['error_rate'] * 100:.1f} %"
                + (" · doublon déjà reçu correctement" if m.get("duplicate") else "")
            )
        self._navtex_logged = len(msgs)

    # ------------------------------------------------ horloge de la carte son
    def _clock_store_path(self):
        ws = getattr(self, "portable_ws", None)
        base = ws.root_dir / "configuration" if ws is not None else Path(self.archive_dir)
        return Path(base) / "horloge_audio.json"

    def _audio_device_key(self):
        try:
            return self.cmb_audio.get().split(":", 1)[-1].strip() or "defaut"
        except Exception:
            return "defaut"

    def _load_clock_calibration(self):
        """Recharge l'erreur d'horloge mémorisée pour la carte son sélectionnée."""
        try:
            data = json.loads(self._clock_store_path().read_text(encoding="utf-8"))
            ppm = float(data.get(self._audio_device_key(), {}).get("ppm", 0.0))
        except (OSError, ValueError, TypeError, AttributeError):
            ppm = 0.0
        self.dsp.clock_ppm = ppm
        self._last_logged_ppm = ppm
        if abs(ppm) > 0.5:
            self.log_event(
                f"Horloge carte son : correction mémorisée {ppm:+.1f} ppm ({self._audio_device_key()})"
            )

    def _track_clock_calibration(self):
        """Journalise et mémorise une nouvelle mesure d'horloge faite pendant le phasage."""
        ppm = float(self.dsp.clock_ppm)
        obs = getattr(self.dsp, "protocol_observation", {}) or {}
        if obs.get("ioc"):
            self.rx_detected_ioc = obs["ioc"]
        if abs(ppm - getattr(self, "_last_logged_ppm", 0.0)) < 0.5:
            return
        self._last_logged_ppm = ppm
        self.log_event(f"⏱️ Horloge carte son mesurée sur le phasage : {ppm:+.1f} ppm (correction appliquée)")
        if getattr(self, "replay_active", False):
            return  # mesure propre à la carte son de l'enregistrement : non mémorisée pour le poste
        try:
            path = self._clock_store_path()
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            data[self._audio_device_key()] = {
                "ppm": round(ppm, 2),
                "fs_nominal": int(self.audio_fs),
                "mesure_utc": datetime.now(timezone.utc).isoformat(),
            }
            atomic_json(path, data)
        except Exception as exc:
            self.log_event("Mémorisation horloge audio impossible : " + repr(exc))

    def _generate_realistic_test_wefax(self, mode: str = "ANA") -> np.ndarray:
        h, w = 1020, 1400
        img = np.full((h, w), 244, dtype=np.uint8)
        img[:, 0:24] = 20
        img[:, 24:46] = 252

        for y in range(120, h - 60, 150):
            for x in range(70, w - 40, 12):
                img[y : y + 2, x : x + 5] = 145
        for x in range(160, w - 50, 170):
            for y in range(70, h - 50, 12):
                img[y : y + 5, x : x + 2] = 145

        coast = [
            np.array(
                [
                    [360, 500],
                    [450, 480],
                    [530, 400],
                    [620, 370],
                    [670, 460],
                    [630, 560],
                    [710, 640],
                    [780, 660],
                    [840, 720],
                    [900, 810],
                    [860, 840],
                    [760, 720],
                    [680, 690],
                    [590, 710],
                    [500, 790],
                    [390, 780],
                    [370, 670],
                    [450, 610],
                ],
                dtype=np.int32,
            )
        ]
        cv2.polylines(img, coast, False, 55, 2, cv2.LINE_AA)
        cv2.ellipse(img, (845, 775), (14, 28), 8, 0, 360, 50, 2)

        shift = 90 if mode == "H24" else (180 if mode in ("H48", "H84") else 0)
        low_c = (420 + shift, 330 + shift // 3)
        for idx, r in enumerate(range(50, 360, 42)):
            cv2.ellipse(img, low_c, (int(r * 1.3), r), -15, 0, 360, 22, 2, cv2.LINE_AA)
            cv2.putText(
                img,
                str(988 + idx * 4),
                (low_c[0] + int(r * 0.75), low_c[1] - int(r * 0.45)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                15,
                2,
            )
        cv2.putText(img, "LOW 988", (low_c[0] - 42, low_c[1] + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.72, 10, 2)

        high_c = (830 + shift // 2, 720)
        for idx, r in enumerate(range(60, 330, 52)):
            cv2.ellipse(img, high_c, (int(r * 1.25), r), 12, 0, 360, 30, 2, cv2.LINE_AA)
        cv2.putText(img, "H 1024", (high_c[0] - 38, high_c[1] + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.75, 15, 2)

        front_pts = np.array(
            [[low_c[0], low_c[1]], [510 + shift, 450], [590 + shift, 560], [480 + shift, 660]], dtype=np.int32
        )
        cv2.polylines(img, [front_pts], False, 12, 5, cv2.LINE_AA)

        cv2.rectangle(img, (75, 30), (680, 112), 255, -1)
        cv2.rectangle(img, (75, 30), (680, 112), 15, 2)
        cv2.putText(
            img,
            f"DWD PINNEBERG (DDK3 7880 kHz) - CARTE {mode}",
            (90, 62),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            10,
            2,
        )
        cv2.putText(
            img,
            f"UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:00Z')} - IOC 576 / 120 RPM",
            (90, 96),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            30,
            1,
        )

        rng = np.random.default_rng(42)
        noise = rng.normal(0, 12, size=(h, w)).astype(np.int16)
        for y_s in range(140, h, 65):
            noise[y_s : y_s + 2, :] -= 45
        return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
