"""Liaison radio : CAT / CI-V, entrée audio USB, réglages RF et boucle RF automatique."""

import ctypes
import queue
import sys
import threading
import time
from tkinter import messagebox
import numpy as np
from wefax_station.core.stations import is_rtty_frequency
from wefax_station.deps import HAS_AUDIO, HAS_SERIAL, sd, serial
from wefax_station.weather.reliability import WeatherReliabilityEstimator
from wefax_station.dsp.passband import measure_passband
from wefax_station.radio.profiles import REQUIRED_AUDIO_BAND
from wefax_station.radio.auto_preamp import AutoPreamp
from wefax_station.radio import auto_rf_gain as _arg


def is_radio_audio_input(name) -> bool:
    """Entrée audio du poste (IC-705 : « USB Audio CODEC »), d'après son nom Windows."""
    up = str(name or "").upper()
    return "USB AUDIO CODEC" in up or "IC-705" in up or "ICOM" in up


class RadioLinkMixin:
    # --------------------------------------------------------- connexion
    STARTUP_RADIO_RETRY_MS = 15000

    def _startup_cat_autostart(self):
        """Démarrage : connexion CAT puis scan de toutes les fréquences pour retenir la meilleure carte.

        Si la radio est éteinte (ou le câble absent), aucune boîte bloquante : l'application réessaie
        toutes les 15 s et lance le scan dès que la radio répond.
        """
        if self.radio.port_open and self.radio.handshake_ok:
            self._startup_waiting_radio = False
            return
        if getattr(self, "carrier_scan_active", False):
            return
        if getattr(self, "winlink_session_active", False):  # 2.8.7 : le poste est prêté à VARA HF
            self.root.after(self.STARTUP_RADIO_RETRY_MS, self._startup_cat_autostart)
            return
        first = not getattr(self, "_startup_waiting_radio", False)
        self._startup_waiting_radio = True
        if first:
            self.log_event("Démarrage : connexion CAT automatique puis scan des fréquences WEFAX...")
        if self.connection_busy:
            self.root.after(self.STARTUP_RADIO_RETRY_MS, self._startup_cat_autostart)
            return
        # après Winlink : pas de scan, l'automatisme reprend lui-même le plan de réception
        self._connect_serialized(scan_after=not getattr(self, "_wl_reconnect_hint", False))

    def _startup_retry_later(self, msg):
        if not getattr(self, "_startup_waiting_radio", False):
            return False
        if getattr(self, "_wl_reconnect_hint", False):
            if not getattr(self, "_startup_radio_warned", False):
                self._startup_radio_warned = True
                self.log_event(
                    "📮 Après Winlink : l'IC-705 ne répond pas encore (" + str(msg) + "). Si la fenêtre "
                    "« Vara HF Winlink » est encore ouverte dans Winlink Express, fermez-la : elle garde le port. "
                    "Nouvel essai toutes les 15 s."
                )
            try:
                self.lbl_status.configure(text="Retour de Winlink : fermez la fenêtre « Vara HF Winlink »… nouvel essai toutes les 15 s")
            except Exception:
                pass
            self.root.after(self.STARTUP_RADIO_RETRY_MS, self._startup_cat_autostart)
            return True
        if not getattr(self, "_startup_radio_warned", False):
            self._startup_radio_warned = True
            self.log_event(
                "📻 Radio non détectée (" + str(msg) + "). Allumez la radio : nouvelle tentative "
                "automatique toutes les 15 s, puis scan des fréquences dès qu'elle répond."
            )
        try:
            self.lbl_status.configure(
                text="En attente de la radio HF (allumez le poste)… nouvel essai toutes les 15 s"
            )
        except Exception:
            pass
        self.root.after(self.STARTUP_RADIO_RETRY_MS, self._startup_cat_autostart)
        return True

    def _one_click(self):
        if self.connection_busy or self.carrier_scan_active:
            return
        self._startup_waiting_radio = False  # l'opérateur reprend la main
        if self.rx_current_line > 25 and not self.waiting_after_stop:
            if not messagebox.askyesno("Réception", "Archiver la carte partielle et relancer le scan ?"):
                return
            self._finalize_completed_wefax_chart("Relance operateur")
        self.rx_current_line = 0
        self.rx_sheet_initialized_for_live = False
        self._connect_serialized(True)

    def _wait_cat(self, count):
        if self.radio.handshake_ok and self.audio_live_connected:
            self._apply_optimal_defaults_preset()
            self._trigger_carrier_scan()
        elif count < 20:
            self.root.after(1000, lambda: self._wait_cat(count + 1))
        else:
            messagebox.showwarning(
                "Connexion incomplète",
                "CAT ou audio non disponible. Vérifier port, adresse CI-V et périphérique USB. Aucune mesure simulée n'est utilisée.",
            )

    def _run_auto_detect_cat_and_audio(self):
        self._connect_serialized(False)

    def _connect_serialized(self, scan_after):
        if self.connection_busy or self.carrier_scan_active:
            return
        self.connection_busy = True
        self.connection_scan_after = scan_after
        if not self.audio_live_connected:  # 2.8.8 : ne coupe plus un flux audio qui fonctionne
            self._auto_connect_ic705_audio()
        proto = self.cmb_proto.get()
        civ = self.ent_civ.get().strip()
        self.set_busy_state(True, "Connexion CAT (tentative automatique)...")

        def worker():
            result = (False, "", 19200, "Tentatives épuisées")
            for attempt in range(1, 4):
                try:
                    if (
                        self.radio.port_open
                        and self.radio.protocol == proto
                        and self.radio.verify_radio_handshake()
                    ):
                        result = (
                            True,
                            self.radio.ser.port,
                            self.radio.ser.baudrate,
                            f"Connexion existante vérifiée (tentative {attempt})",
                        )
                        break
                    self.radio.disconnect()
                    result = self.radio.auto_detect_port_and_connect(proto, civ)
                    if result[0]:
                        break
                except Exception as exc:
                    result = (False, "", 19200, repr(exc))
                import time as _t

                _t.sleep(1.5)
            self.ui_events.put(lambda r=result: self._connection_done(r))

        threading.Thread(target=worker, daemon=True).start()

    def _connection_done(self, result):
        ok, port, baud, msg = result
        self.connection_busy = False
        self.set_busy_state(False)
        if port:
            self.cmb_port.set(port)
            self.cmb_baud.set(str(baud))
        self._sync_ui_from_hardware()
        self.log_event("Connexion terminée : " + str(msg))
        if not ok:
            if self._startup_retry_later(msg):
                return
            messagebox.showwarning("Connexion CAT échouée", "CAT non établi après 3 tentatives.\n" + str(msg))
            return
        self._wl_reconnect_hint = False
        if getattr(self, "_startup_waiting_radio", False):
            self._startup_waiting_radio = False
            if getattr(self, "_startup_radio_warned", False):
                self.log_event("📻 Radio détectée : connexion établie, lancement du scan des fréquences.")
        self.radio.apply_optimal_wefax_rx_profile(filter_idx=1)
        scan = self.connection_scan_after
        self.connection_scan_after = False
        if not self.audio_live_connected:
            # 2.8.8 : la carte son USB du poste apparaît souvent quelques secondes après le port COM
            self.log_event("CAT OK : recherche de l'entrée audio USB du poste (jusqu'à 30 s)…")
            self._await_audio_then_scan(0, scan)
            return
        if scan:
            self._apply_optimal_defaults_preset()
            self._trigger_carrier_scan()  # vérifie CAT + audio réel et protège une carte en cours

    AUDIO_WAIT_STEPS = 10  # 10 × 3 s

    def _await_audio_then_scan(self, step, scan):
        if getattr(self, "closing", False) or getattr(self, "winlink_session_active", False):
            return
        if not self.audio_live_connected:
            self._auto_connect_ic705_audio()
        if self.audio_live_connected:
            self.log_event("🎙️ Entrée audio du poste retrouvée : " + self.cmb_audio.get())
            if scan:
                self._apply_optimal_defaults_preset()
                self._trigger_carrier_scan()
            return
        if step + 1 < self.AUDIO_WAIT_STEPS:
            self.root.after(3000, lambda: self._await_audio_then_scan(step + 1, scan))
            return
        self.log_event(
            "⚠️ CAT OK mais aucune entrée audio USB du poste. Vérifiez le câble USB "
            "(il transporte le son et la CAT) ou choisissez l'entrée dans Réglages > Audio RX."
        )
        try:
            self.lbl_status.configure(text="CAT OK — entrée audio du poste introuvable (voir Réglages > Audio RX)")
        except Exception:
            pass

    # ------------------------------------------- surveillance branchement à chaud
    HOTPLUG_PERIOD_MS = 5000

    def _radio_hotplug_watch(self):
        """2.8.8 : surveille le branchement / débranchement du câble USB du poste.

        - radio absente puis ports COM qui changent → reconnexion automatique (CAT + audio + scan) ;
        - flux audio muet depuis plus de 6 s (câble arraché) → bascule propre en « radio absente »,
          puis reprise automatique dès que le câble revient.
        """
        if getattr(self, "closing", False):
            return
        try:
            self._radio_hotplug_check()
        except Exception as exc:
            self.log_event(f"Surveillance USB : {exc!r}")
        self.root.after(self.HOTPLUG_PERIOD_MS, self._radio_hotplug_watch)

    def _com_signature(self):
        if not HAS_SERIAL:
            return ()
        try:
            return tuple(sorted(p.device for p in serial.tools.list_ports.comports()))
        except Exception:
            return ()

    def _radio_hotplug_check(self):
        if (
            getattr(self, "winlink_session_active", False)
            or getattr(self, "replay_active", False)
            or self.connection_busy
            or getattr(self, "carrier_scan_active", False)
        ):
            return
        sig = self._com_signature()
        prev = getattr(self, "_hotplug_com_sig", None)
        self._hotplug_com_sig = sig
        cat_ok = self.radio.port_open and self.radio.handshake_ok
        # câble arraché : plus aucun bloc audio
        cb = getattr(self, "last_audio_callback", 0.0)
        if self.audio_live_connected and cb and time.monotonic() - cb > 6.0:
            self.log_event("🔌 Plus de son du poste depuis 6 s : câble USB débranché ? Passage en attente radio.")
            self._close_audio_stream()
            if cat_ok and not self.radio.verify_radio_handshake():
                self.radio.disconnect()
                cat_ok = False
            self._sync_ui_from_hardware()
            self._hotplug_pending = True
            return  # reconnexion au tick suivant (le temps que Windows retire le périphérique)
        if cat_ok and self.audio_live_connected:
            self._hotplug_pending = False
            return
        if getattr(self, "_startup_waiting_radio", False):
            return  # la boucle « en attente de la radio » (essai toutes les 15 s) s'en occupe déjà
        changed = prev is not None and sig != prev and len(sig) >= len(prev)
        if changed or getattr(self, "_hotplug_pending", False):
            self._hotplug_pending = False
            self.log_event("🔌 Poste à rebrancher / rebranché : reconnexion automatique CAT + audio…")
            # 2.12.0 — forcer la fermeture du port "fantôme" (l'objet serial peut encore
            # indiquer port_open=True après un débranchement/rebranchement USB rapide).
            if self.radio.port_open:
                try:
                    self.radio.disconnect()
                except Exception:
                    pass
            # même mécanique que le démarrage : essais silencieux toutes les 15 s, scan dès que ça répond
            self._startup_waiting_radio = False
            self._startup_radio_warned = False
            self._startup_cat_autostart()

    def _toggle_manual_cat(self):
        if not self.connection_busy and not self.carrier_scan_active:
            self._toggle_manual_cat_base()

    def _toggle_manual_cat_base(self):
        if self.radio.port_open:
            self.radio.disconnect()
            self._sync_ui_from_hardware()
            self.log_event("🔌 Liaison CAT déconnectée.")
            return
        port = self.cmb_port.get().strip()
        baud = int(self.cmb_baud.get().strip() or "19200")
        self.set_busy_state(True, "CONNEXION CAT...")
        try:
            self.radio.connect(port, baud, self.cmb_proto.get(), self.ent_civ.get().strip())
            self._sync_ui_from_hardware()
        finally:
            self.set_busy_state(False)

    def _refresh_com_ports_list(self):
        if not HAS_SERIAL:
            return
        ports = [p.device for p in serial.tools.list_ports.comports()] or ["COM14", "COM5", "COM3"]
        self.cmb_port["values"] = ports
        self.cmb_port.set(ports[0])
        self.log_event(f"🔄 Ports COM actualisés : {ports}")

    # ------------------------------------------------------------- audio
    def _refresh_portaudio(self) -> bool:
        """2.8.8 : PortAudio ne relit la liste des cartes son qu'à son initialisation.

        Une radio branchée APRÈS le lancement restait donc invisible (repli SIMU) jusqu'au
        redémarrage du logiciel. On ré-initialise PortAudio quand aucun flux n'est ouvert.
        """
        if not HAS_AUDIO or getattr(self, "audio_stream", None) is not None:
            return False
        try:
            sd._terminate()
            sd._initialize()
            return True
        except Exception as exc:
            self.log_event(f"Rafraîchissement de la liste audio impossible : {exc!r}")
            return False

    def _enumerate_audio_input_devices(self, refresh=False) -> list:
        dev_list = ["SIMU : Décodeur Synthétique Interne"]
        if not HAS_AUDIO:
            return dev_list
        if refresh:
            self._refresh_portaudio()
        try:
            devices = sd.query_devices()
            for idx, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    name = d.get("name", f"Device {idx}")
                    dev_list.append(f"{idx}: {name}")
        except Exception:
            pass
        return dev_list

    def _on_audio_device_selected(self, event=None):
        sel = self.cmb_audio.get()
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
            self.audio_live_connected = False

        if sel.startswith("SIMU") or not HAS_AUDIO:
            self.audio_fs = 11025
            self.dsp.set_sample_rate(self.audio_fs)
            self.lbl_spectrum_header.config(text="📈 SPECTRE BF [MODE SIMULATION SYNTHÉTIQUE]")
            return

        try:
            dev_id = int(sel.split(":", 1)[0].strip())
            dev_info = sd.query_devices(dev_id, "input")
            native_fs = int(dev_info.get("default_samplerate", 44100))
            self.audio_fs = native_fs
            self.dsp.set_sample_rate(self.audio_fs)
            self._load_clock_calibration()
            self.audio_ring = np.zeros(int(self.audio_fs * 0.6), dtype=np.float32)
            self.audio_long_ring = np.zeros(int(self.audio_fs * 4.5), dtype=np.float32)

            def _audio_cb(indata, frames, time_info, status):
                if status:
                    self.audio_status_count = getattr(self, "audio_status_count", 0) + 1
                mono = indata[:, 0].copy()
                rec = getattr(self, "audio_recorder", None)
                if rec is not None and rec.active:
                    rec.push(mono)
                if getattr(self, "replay_active", False):
                    return  # pendant une relecture, le flux du poste n'alimente pas le décodeur
                self.last_audio_callback = time.monotonic()
                n = len(mono)
                if n < len(self.audio_ring):
                    self.audio_ring[:-n] = self.audio_ring[n:]
                    self.audio_ring[-n:] = mono
                else:
                    self.audio_ring[:] = mono[-len(self.audio_ring) :]
                lr = self.audio_long_ring
                if n < len(lr):
                    lr[:-n] = lr[n:]
                    lr[-n:] = mono
                try:
                    self.rx_audio_queue.put_nowait(mono)
                except queue.Full:
                    self.audio_drop_count = getattr(self, "audio_drop_count", 0) + 1

            self.audio_stream = sd.InputStream(
                device=dev_id,
                channels=1,
                samplerate=self.audio_fs,
                dtype="float32",
                blocksize=int(self.audio_fs * 0.10),
                callback=_audio_cb,
            )
            self.audio_stream.start()
            self.audio_live_connected = True
            self.lbl_spectrum_header.config(text=f"SPECTRE BF [AUDIO LIVE : {sel[:26]} @ {self.audio_fs} Hz]")
            # 2.9.0 — le message disait « Flux Audio USB » même pour le micro du PC (18/11, 19:32:38 :
            # « Réseau de microphones » annoncé comme flux USB). On nomme l'interface Windows (MME, WASAPI…)
            # et on prévient quand l'entrée n'est pas celle du poste.
            api = ""
            try:
                api = sd.query_hostapis(int(dev_info.get("hostapi", 0))).get("name", "")
            except Exception:
                pass
            api_txt = f", {api}" if api else ""
            if is_radio_audio_input(sel):
                self.log_event(f"✅ Entrée audio du poste connectée : {sel} ({self.audio_fs} Hz{api_txt}).")
            else:
                self.log_event(
                    f"⚠️ Entrée audio connectée : {sel} ({self.audio_fs} Hz{api_txt}) — ce n'est PAS l'entrée du "
                    "poste (USB Audio CODEC) : le décodage écoute ce périphérique. Réglages › Audio RX pour changer."
                )
        except Exception as exc:
            self.audio_live_connected = False
            self.log_event(f"⚠️ Ouverture audio '{sel}' impossible ({exc}) -> Repli Simulation.")

    def _close_audio_stream(self):
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
        self.audio_live_connected = False

    def _auto_connect_ic705_audio(self):
        """Choisit l'entrée audio du poste ; relit la liste des cartes son (radio branchée à chaud)."""
        if not HAS_AUDIO:
            self.log_event("ℹ️ Module sounddevice absent — Décodage en mode Simulation interne.")
            return False
        if getattr(self, "replay_active", False):
            return self.audio_live_connected
        self._close_audio_stream()
        dev_list = self._enumerate_audio_input_devices(refresh=True)
        self.cmb_audio["values"] = dev_list

        best_idx = 0
        for i, item in enumerate(dev_list):
            up = item.upper()
            if is_radio_audio_input(item):
                best_idx = i
                break
            elif "USB" in up and best_idx == 0:
                best_idx = i

        self.cmb_audio.current(best_idx)
        self._on_audio_device_selected()
        return bool(self.audio_live_connected)

    # ----------------------------------------------------- réglages RF
    def _apply_optimal_defaults_preset(self):
        self.fft_notch_var.set(True)
        self.tensor_var.set(True)
        self.adapt_bin_var.set(False)
        self.qrn_blanker_var.set(True)
        self.upstream_hf_cond_active = True
        self.auto_margin_once_active = True
        self.auto_save_png_active = True
        self.auto_rf_loop_active = True
        self.rx_decoding_active = True

        self.btn_fft2d.set_state(True)
        self.btn_tensor.set_state(True)
        self.btn_bin.set_state(False)
        self.btn_qrn_blanker.set_state(True)
        self.btn_hf_cond.set_state(True)
        self.btn_auto_margin_once.set_state(True)
        self.btn_autosave_png.set_state(True)
        self.btn_auto_rf.set_state(True)
        self.btn_rx_start.set_state(True)
        self.btn_top_rx.set_state(True)

        self.radio.set_attenuator(False)
        self.radio.set_preamp(1)
        self.radio.apply_optimal_wefax_rx_profile(filter_idx=1)
        self.grp_if_filter.set_value(1, trigger_callback=False)
        self.grp_display_mode.set_value("PROCESSED", trigger_callback=True)
        self._sync_ui_from_hardware()
        self._apply_full_restoration()
        self.lbl_status.config(
            text="⭐ Réglages Optimaux rétablis (USB-D/FIL1/AGC-FAST + Conditionneur HF 2D + Auto-Marge).",
            fg="#34d399",
        )
        self.log_event(
            "⭐ Réglages Optimaux appliqués (USB-D/FIL1/AGC-FAST + Conditionneur HF Live + Restauration active)."
        )

    def _set_rf_preamp(self, level: int):
        self.set_busy_state(True, f"P.AMP {level}...")
        try:
            self.radio.set_preamp(level)
            if level == 0 and self.radio.s_meter_raw < 70:
                self._warn_suboptimal_user_action(
                    "P.AMP 0 (IPO) sur signal modéré/faible : risque de perte de rapport signal/bruit (P.AMP 1 recommandé)."
                )
            elif level == 2 and self.radio.s_meter_raw > 140:
                self._warn_suboptimal_user_action(
                    "P.AMP 2 sur signal fort : risque de saturation ADC (OVF) et d'intermodulation."
                )
            self._sync_ui_from_hardware()
        finally:
            self.set_busy_state(False)

    def _toggle_rf_att(self):
        self.set_busy_state(True, "ATTÉNUATEUR...")
        try:
            new_att = not self.radio.actual_att
            self.radio.set_attenuator(new_att)
            if new_att and not self.radio.ovf_active and self.radio.s_meter_raw < 150:
                self._warn_suboptimal_user_action(
                    "Atténuateur -20 dB activé sans surcharge OVF : cela réduit fortement le SNR du signal WEFAX !"
                )
            self._sync_ui_from_hardware()
        finally:
            self.set_busy_state(False)

    def _on_if_filter_changed(self, fil_idx: int):
        self.radio.set_if_filter(fil_idx)
        self._sync_ui_from_hardware()

    def _toggle_auto_rf_loop(self):
        self.auto_rf_loop_active = not self.auto_rf_loop_active
        self.btn_auto_rf.set_state(self.auto_rf_loop_active)
        if not self.auto_rf_loop_active:
            self._restore_operator_rf_gain("boucle RF automatique coupée")
            self._warn_suboptimal_user_action(
                "Contre-réaction RF automatique désactivée : le récepteur ne s'adaptera plus tout seul aux surcharges OVF."
            )

    # ------------------------------------------- gain RF automatique (2.14.1)
    def _auto_rf_gain_obj(self):
        rg = getattr(self, "auto_rf_gain", None)
        if rg is None:
            rg = self.auto_rf_gain = _arg.AutoRfGain()
        return rg

    def _toggle_auto_rf_gain(self, save=True):
        self.auto_rf_gain_active = not bool(getattr(self, "auto_rf_gain_active", False))
        self._apply_auto_rf_gain(save=save)

    def _apply_auto_rf_gain(self, save=True):
        on = bool(getattr(self, "auto_rf_gain_active", False))
        if hasattr(self, "btn_auto_rf_gain"):
            self.btn_auto_rf_gain.set_state(on)
        rg = self._auto_rf_gain_obj()
        if on and "ICOM" not in self.radio.protocol:
            self.log_event("ℹ️ Gain RF automatique : réservé aux postes Icom (CI-V) ; sans effet sur ce poste.")
        if on:
            known = self.radio.port_open and self.radio.handshake_ok
            rg.set_enabled(True, int(self.radio.actual_rf_gain) if known else None, time.monotonic())
            self.log_event(
                "📶 [Gain RF auto] Activé : essais par paliers de 10 % hors tracé de carte, gardés seulement si le "
                "SNR ne baisse pas ; descente en cas de surcharge OVF ; jamais au-dessus de votre réglage."
            )
        else:
            rg.set_enabled(False, int(self.radio.actual_rf_gain), time.monotonic())
            self._restore_operator_rf_gain("gain RF automatique désactivé")
        if save and hasattr(self, "_save_preferences"):
            self._save_preferences()

    def _restore_operator_rf_gain(self, why):
        rg = getattr(self, "auto_rf_gain", None)
        if rg is None or not rg.lowered_by_auto:
            return
        if int(self.radio.actual_rf_gain) == rg.expected_gain and self.radio.port_open:
            self.radio.set_rf_gain(rg.base_gain)
            self.log_event(f"📶 [Gain RF auto] {why} → retour à votre gain RF {_arg.pct(rg.base_gain)} %.")
        rg.expected_gain = int(self.radio.actual_rf_gain)
        rg.lowered_by_auto = False
        rg.phase = "IDLE"

    def _auto_rf_gain_tick(self, mode, snr, chart_active, now):
        """Renvoie le gain appliqué, ou None. Ne fait rien hors Icom ou si l'option est désactivée."""
        rg = self._auto_rf_gain_obj()
        if "ICOM" not in self.radio.protocol or not rg.enabled:
            return None
        ap = getattr(self, "auto_preamp", None)
        n_tot = rg.events_total
        target = rg.step(
            now,
            snr,
            int(self.radio.actual_rf_gain),
            ovf=bool(self.radio.ovf_active),
            s_raw=int(self.radio.s_meter_raw),
            preamp=int(self.radio.actual_preamp),
            att=bool(self.radio.actual_att),
            chart_active=chart_active,
            other_trial=bool(ap is not None and ap.phase != "IDLE"),
            signal_present=bool(getattr(self, "_ap_present_now", False)),
            qsy_id=int(getattr(self.radio, "qsy_count", 0)),
        )
        n_new = min(len(rg.events), max(0, rg.events_total - n_tot))
        for _, txt in (rg.events[-n_new:] if n_new else []):
            self.log_event(f"📶 [Gain RF auto {mode}] {txt}")
        if target is not None and target != int(self.radio.actual_rf_gain):
            got = self.radio.set_rf_gain(target)
            rg.expected_gain = int(got)
            self.radio.last_auto_rf_action_ts = time.time()
            return got
        return None

    VFO_FOLLOW_MS = 1000

    def _vfo_follow_tick(self):
        """2.14.1 — chaque seconde : le VFO est relu (lecture seule) et l'affichage suit l'opérateur qui
        change de fréquence sur le poste. Le reste de l'état du poste garde la cadence du chien de garde (6 s)."""
        try:
            busy = (
                self.connection_busy
                or self.carrier_scan_active
                or getattr(self, "winlink_session_active", False)
            )
            if not busy and self.radio.port_open and self.radio.handshake_ok:
                if self.radio.poll_vfo_only():
                    self._sync_ui_from_hardware()
        except Exception as exc:
            self.log_event("⚠️ Suivi du VFO : " + repr(exc))
        self.root.after(self.VFO_FOLLOW_MS, self._vfo_follow_tick)

    # Boucle RF automatique : P.AMP automatique (RTTY et WEFAX) + atténuateur sur surcharge
    def _execute_closed_loop_rf_control(self):
        if self.connection_busy or self.carrier_scan_active or getattr(self, "winlink_session_active", False):
            return
        arb = getattr(self, "hybrid_arbiter", None)
        mode = "RTTY" if (arb is not None and arb.active_pipeline == "RTTY") else "WEFAX"
        valid = self.radio.poll_hardware_state()
        self._sync_ui_from_hardware()
        if mode == "WEFAX" and self.upstream_hf_cond_active and self.audio_live_connected:
            if self.current_snr_db < 8.0:
                self.dsp.qsb_env_threshold_ratio = 0.36
            elif self.current_snr_db > 15.0:
                self.dsp.qsb_env_threshold_ratio = 0.22
            else:
                self.dsp.qsb_env_threshold_ratio = 0.28
        if not self.auto_rf_loop_active or not valid or not self.radio.handshake_ok:
            return
        self._auto_preamp_tick(mode)

    def _auto_preamp_snr(self, mode):
        """SNR utile du mode en cours, ou None s'il n'y a pas d'émission à suivre.
        2.14.1 — mémorise aussi dans self._ap_present_now si l'émission est entendue À CET INSTANT."""
        now = time.monotonic()
        self._ap_present_now = False
        if not self.audio_live_connected or getattr(self, "replay_active", False):
            return None
        if mode == "RTTY":
            dec = getattr(self, "rtty_decoder", None)
            if dec is None:
                return None
            q = dec.evaluate_rtty_quality_on_chunk(
                self.audio_long_ring.copy(), self.audio_fs, dec.center_hz, dec.shift_hz
            )
            snr = 0.5 * (q["mark_snr_db"] + q["space_snr_db"])
            present = bool(q["valid_fsk"])
        else:
            snr = float(self.current_snr_db)
            present = bool(getattr(self, "carrier_locked", False)) or (
                self.rx_current_line > 0 and not getattr(self, "waiting_after_stop", False)
            )
        if present:
            self._ap_last_present = now
        self._ap_present_now = bool(present)
        # on suit le fading tant que l'émission a été entendue il y a moins de 3 min
        if now - getattr(self, "_ap_last_present", -1e9) > 180:
            return None
        return snr

    def _auto_preamp_chart_active(self, mode):
        """2.9.2 — carte WEFAX en cours de tracé (START reçu, lignes en cours, pas encore de STOP)."""
        if mode != "WEFAX":
            return False
        return (
            bool(getattr(self, "rx_image_armed", False))
            and int(getattr(self, "rx_current_line", 0) or 0) > 0
            and not getattr(self, "waiting_after_stop", False)
        )

    def _auto_preamp_tick(self, mode):
        ap = getattr(self, "auto_preamp", None)
        if ap is None:
            ap = self.auto_preamp = AutoPreamp()
        freq = round(float(self.radio.actual_freq_khz), 1)
        if mode != ap.mode or freq != getattr(self, "_ap_freq", None):
            # 2.8.9 — changement de station : un P.AMP 2 posé par l'automatisme sur l'ancienne fréquence ne
            # suit pas sur la nouvelle (le 18/11, retour en WEFAX à 18:35 resté en P.AMP 2)
            if (ap.boosted_by_auto or ap.phase != "IDLE") and self.radio.actual_preamp != ap.base_level:
                if not self.radio.ovf_active:
                    self.log_event(f"📶 [P.AMP auto] Nouvelle station : retour au réglage de base P.AMP {ap.base_level}.")
                    self.radio.set_preamp(ap.base_level)
            ap.set_mode(mode)
            ap.reset()
            # 2.14.1 — nouvelle station : le gain RF réduit par l'automatisme revient au réglage de l'opérateur
            self._restore_operator_rf_gain("nouvelle station")
            self._auto_rf_gain_obj().reset()
            self._ap_freq = freq
            self._ap_last_present = -1e9
        now = time.monotonic()
        snr = self._auto_preamp_snr(mode)
        chart_active = self._auto_preamp_chart_active(mode)
        rg = self._auto_rf_gain_obj()
        n_tot = getattr(ap, "events_total", 0)
        target = ap.step(
            now,
            # 2.14.1 — pendant un essai de gain RF, le P.AMP automatique ne juge pas le SNR (il varie à cause
            # de l'essai, pas du fading)
            None if rg.phase != "IDLE" else snr,
            self.radio.actual_preamp,
            int(self.radio.s_meter_raw),
            bool(self.radio.ovf_active),
            chart_active=chart_active,
        )
        # 2.9.3 — le 19/11 après 07:21, le P.AMP changeait sans aucune ligne au journal : la liste des
        # événements, plafonnée à 20, gardait la même longueur et « events[n:] » était toujours vide
        n_new = min(len(ap.events), max(0, getattr(ap, "events_total", 0) - n_tot))
        for _, txt in (ap.events[-n_new:] if n_new else []):
            self.log_event(f"📶 [P.AMP auto {mode}] {txt}")
        rf_target = None
        preamp_applied = target is not None and target != self.radio.actual_preamp
        if preamp_applied:
            self.radio.set_preamp(target)
            self.radio.last_auto_rf_action_ts = time.time()
            ap.expected_level = self.radio.actual_preamp
        else:
            rf_target = self._auto_rf_gain_tick(mode, snr, chart_active, now)
        # surcharge persistante : l'ATT n'intervient qu'après le gain RF automatique (s'il est activé) arrivé
        # à son plancher
        rf_floor = (not rg.enabled) or int(self.radio.actual_rf_gain) <= _arg.MIN_GAIN or "ICOM" not in self.radio.protocol
        if preamp_applied or rf_target is not None:
            pass
        elif target is None and self.radio.ovf_active and self.radio.actual_preamp == 0 and not self.radio.actual_att and rf_floor:
            if time.time() - self.radio.last_auto_rf_action_ts > 6:
                self.log_event("⚡ [Auto-RF] Surcharge persistante en P.AMP 0 -> Activation ATT (-20 dB).")
                self.radio.set_attenuator(True)
                self.radio.last_auto_rf_action_ts = time.time()
        elif self.radio.actual_att and not self.radio.ovf_active and self.radio.s_meter_raw < 65:
            if time.time() - self.radio.last_auto_rf_action_ts > 30:
                self.log_event("🔁 [Auto-RF] Signal faible -> Désactivation ATT (-20 dB).")
                self.radio.set_attenuator(False)
                self.radio.last_auto_rf_action_ts = time.time()
        self._sync_ui_hardware_widgets()

    # ------------------------------------------- synchronisation affichage
    def _sync_ui_from_hardware(self):
        self._sync_ui_cockpit()
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            arb.remember_wefax_station_if_valid()
            arb._style_wefax_toggle_button()
        is_rtty = bool(
            (arb is not None and arb.active_pipeline == "RTTY")
            or is_rtty_frequency(self.radio.actual_freq_khz)
        )
        net_ok = not bool(getattr(getattr(self, "schedule_planner", None), "network_cut_off_manual", False))

        freq_txt = f"{self.radio.actual_freq_khz:,.1f} kHz".replace(",", " ")
        self.lbl_freq_display.configure(
            text=f"📻  {self.radio.active_station_id}   ·   {freq_txt}",
            font=("Consolas", 20, "bold"),
            fg="#fef08a",
            pady=2,
        )

        rel = (
            WeatherReliabilityEstimator.compute_rtty_reliability(self.rtty_decoder, arb.rtty_raw_buffer)
            if (is_rtty and hasattr(self, "rtty_decoder") and arb is not None)
            else WeatherReliabilityEstimator.compute_wefax_reliability(self)
        )

        if hasattr(self, "_update_vfo"):
            self._update_vfo()
        if hasattr(self, "btn_net_toggle"):
            self.btn_net_toggle.configure(
                text="[ON] 🌐 Réseau" if net_ok else "[OFF] 🔒 Hors-Ligne",
                bg="#059669" if net_ok else "#7f1d1d",
                fg="#ffffff",
            )

        details_txt = (
            f"{self.radio.active_station_name}   |   Cadran {self.radio.actual_dial_khz:.2f} kHz   |   "
            f"{self.radio.actual_mode_str} · {self.radio.actual_filter_str} · AGC {self.radio.actual_agc_str}   |   "
            f"🛡️ {rel['badge_text']}"
        )
        if is_rtty:
            self.lbl_radio_details.configure(
                text=f" 📠  TÉLÉSCRIPTEUR RTTY / NAVTEX ACTIF   —   {details_txt} ",
                bg="#b45309",
                fg="#ffffff",
                font=("Segoe UI", 9, "bold"),
                padx=8,
                pady=3,
            )
        else:
            self.lbl_radio_details.configure(
                text=f" 🗺️  RÉCEPTION CARTES MÉTÉO WEFAX (120 RPM)   —   {details_txt} ",
                bg="#92400e",
                fg="#fef3c7",
                font=("Segoe UI", 9, "bold"),
                padx=8,
                pady=3,
            )
        self._update_auto_btn()

    # 2.12.0 — bouton « Rendre la main à l'automatique »
    def _update_auto_btn(self):
        """Affiche le bouton ⟳ Auto uniquement quand le contrôle automatique est suspendu.

        Trois cas couverts :
        - mode MANUEL ou RELECTURE (requested_mode explicitement non-automatique)
        - manual_hold = True (pause manuelle entre deux cartes)
        - operator_choice non nul (choix de station depuis la fenêtre Stations)
        """
        btn = getattr(self, "btn_auto_restore", None)
        if btn is None:
            return
        arb = getattr(self, "hybrid_arbiter", None)
        manual_active = False
        if arb is not None:
            manual_active = (
                arb.requested_mode in ("MANUEL", "RELECTURE")
                or getattr(arb, "manual_hold", False)
                or getattr(arb, "operator_choice", None) is not None
            )
        try:
            if manual_active:
                btn.configure(bg="#b45309", fg="#ffffff", relief="raised")
                btn.grid()       # rendre visible
            else:
                btn.grid_remove()  # cacher
        except Exception:
            pass

    def _give_back_to_auto(self):
        """Réactive le mode automatique HYBRIDE depuis n'importe quel état manuel.

        Couvre les trois cas possibles :
        - mode MANUEL / RELECTURE → resume_automation + set_requested_mode("HYBRIDE")
        - manual_hold actif → idem
        - choix de station (operator_choice) → release_manual_hold + callback _on_manual_hold_changed
        """
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is None:
            return
        try:
            # Libérer le choix de station (operator_choice) si actif
            if getattr(arb, "operator_choice", None) is not None:
                arb.release_manual_hold("Bouton ⟳ Auto : main rendue à l'automatique")
            # Rendre la main dans tous les cas (sans effet secondaire si déjà en HYBRIDE)
            arb.resume_automation()
            arb.set_requested_mode("HYBRIDE", user_initiated=True)
        except Exception as exc:
            self.log_event(f"⚠️ Impossible de rendre la main à l'automatique : {exc!r}")
        self._update_auto_btn()

    def _sync_ui_cockpit(self):
        self._sync_ui_hardware_widgets()
        if hasattr(self, "grp_if_filter"):
            fil_num = 3 if "3" in self.radio.actual_filter_str else 1
            self.grp_if_filter.set_value(fil_num, trigger_callback=False)
        self._update_startup_readiness_banner25()

    def _sync_ui_hardware_widgets(self):
        if not hasattr(self, "btn_cat_conn"):
            return
        self.grp_preamp.set_value(self.radio.actual_preamp, trigger_callback=False)
        self.btn_att.set_state(self.radio.actual_att)
        connected = self.radio.port_open and self.radio.handshake_ok
        self.btn_cat_conn.set_state(connected, custom_label="CAT vérifié" if connected else "Connexion CAT")
        self.lbl_cat_badge.configure(
            text=f"CAT OK · {self.radio.cat_label}" if connected else "CAT non connecté",
            bg="#174936" if connected else "#334155",
            fg="white",
        )
        self.lbl_freq_display.configure(
            text=f"{self.radio.active_station_id}  ·  {self.radio.actual_freq_khz:,.1f} kHz".replace(",", " ")
        )
        self.lbl_radio_details.configure(
            text=f"{self.radio.active_station_name}  |  cadran {self.radio.actual_dial_khz:.2f} kHz  |  {self.radio.actual_mode_str} · {self.radio.actual_filter_str} · AGC {self.radio.actual_agc_str}"
        )
        self._update_programme()
        self._highlight_station()

    def _set_power(self, active):
        if sys.platform != "win32":
            return
        if active == self.power_held:
            return
        try:
            flags = 0x80000000 | (0x00000001 if active else 0)
            if not ctypes.windll.kernel32.SetThreadExecutionState(flags):
                raise OSError("SetThreadExecutionState a échoué")
            self.power_held = active
            self.log_event(
                "Protection veille " + ("ACTIVE ; extinction ecran autorisee" if active else "liberee")
            )
        except Exception as exc:
            self.log_event("ERREUR protection veille : " + repr(exc))

    # ------------------------------------------------ contrôle de la bande passante
    def _check_audio_passband(self, mode="WEFAX"):
        """Mesure la bande passante audio réelle (forme du bruit) et vérifie la bande utile du mode."""
        if not self.audio_live_connected:
            return None
        res = measure_passband(
            self.audio_ring.copy(), self.audio_fs, REQUIRED_AUDIO_BAND.get(mode, (1450, 2350))
        )
        self.last_passband = res
        if res is None:
            return None
        lo, hi = res["required"]
        if res["ok"]:
            self.log_event(
                f"PASSBANDE {mode} : {res['low_hz']}–{res['high_hz']} Hz à −6 dB ; bande utile {lo:.0f}–{hi:.0f} Hz "
                f"incluse (pente {res['tilt_db']} dB)"
            )
        else:
            self.log_event(
                f"⚠️ PASSBANDE {mode} : {res['low_hz']}–{res['high_hz']} Hz à −6 dB : "
                f"la bande utile {lo:.0f}–{hi:.0f} Hz n'est pas entièrement couverte — vérifier filtre FI / PBT / IF SHIFT"
            )
        return res
