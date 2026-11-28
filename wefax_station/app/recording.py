"""Enregistrement WAV des réceptions et relecture dans la chaîne de décodage (essais terrain)."""

import time
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk

import numpy as np

from wefax_station.core.stations import RTTY_WEATHER_STATIONS, is_rtty_frequency
from wefax_station.storage.recorder import AudioRecorder, read_wav
from wefax_station.ui.theme import UITheme


class RecordingMixin:
    # ----------------------------------------------------------- installation
    def _init_recording(self):
        self.audio_recorder = AudioRecorder(log=self.log_event)
        self.replay_active = False
        self.auto_record_var = tk.BooleanVar(master=self.root, value=False)
        if hasattr(self, "controls_slot25"):
            self.btn_rec = tk.Button(
                self.controls_slot25,
                text="⏺ REC",
                command=self._toggle_recording,
                bg="#334155",
                fg="#ffffff",
                font=("Segoe UI", 8, "bold"),
                bd=1,
                relief="raised",
                padx=6,
                pady=2,
                cursor="hand2",
            )
            self.btn_rec.pack(side="left", padx=2)
            try:
                self._register_tip25(
                    self.btn_rec,
                    "audio",
                    "BOUTON COMMUTATEUR : enregistre l'audio brut reçu (WAV) pour le rejouer "
                    "et analyser une réception difficile.",
                )
            except Exception:
                pass
        try:
            menubar = self.root.nametowidget(self.root.cget("menu"))
            menu = tk.Menu(menubar, tearoff=False, bg=UITheme.BG_PANEL, fg=UITheme.TEXT_PRIMARY)
            menu.add_command(
                label="⏺ Démarrer / arrêter l'enregistrement audio", command=self._toggle_recording
            )
            menu.add_checkbutton(
                label="Enregistrer automatiquement chaque carte WEFAX (START → fin)",
                variable=self.auto_record_var,
            )
            menu.add_separator()
            menu.add_command(
                label="▶ Rejouer un enregistrement WAV dans le décodeur…", command=self._replay_wav_dialog
            )
            menu.add_command(
                label="⏹ Arrêter la relecture", command=lambda: self._stop_replay("Arrêt opérateur")
            )
            menu.add_separator()
            menu.add_command(
                label="📂 Ouvrir le dossier des enregistrements", command=self._open_recordings_dir
            )
            menubar.add_cascade(label="Enregistrements", menu=menu)
        except tk.TclError:
            pass

    def _recordings_dir(self):
        ws = getattr(self, "portable_ws", None)
        return (
            (ws.root_dir / "enregistrements")
            if ws is not None
            else Path(self.archive_dir) / "enregistrements"
        )

    def _open_recordings_dir(self):
        d = self._recordings_dir()
        d.mkdir(parents=True, exist_ok=True)
        self._open_local(str(d)) if hasattr(self, "_open_local") else None

    # ------------------------------------------------------------ enregistrement
    def _current_mode_label(self):
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None and arb.active_pipeline == "RTTY":
            st = arb.active_rtty_station or {}
            return "NAVTEX" if "NAVTEX" in st.get("protocol", "") else "RTTY", st
        return "WEFAX", None

    def _start_recording(self, reason="Opérateur"):
        if not self.audio_live_connected or self.replay_active:
            messagebox.showinfo(
                "Enregistrement", "Aucun flux audio réel : connecter l'entrée audio du poste."
            )
            return
        mode, st = self._current_mode_label()
        ws = getattr(self, "portable_ws", None)
        meta = {
            "mode": mode,
            "station": (st or {}).get("id", self.radio.active_station_id),
            "frequence_khz": self.radio.actual_freq_khz,
            "cadran_khz": self.radio.actual_dial_khz,
            "mode_radio": self.radio.actual_mode_str,
            "filtre": self.radio.actual_filter_str,
            "agc": self.radio.actual_agc_str,
            "protocole": (st or {}).get("protocol", "WEFAX_IOC576_120"),
            "horloge_audio_ppm": round(float(self.dsp.clock_ppm), 2),
            "peripherique_audio": self._audio_device_key() if hasattr(self, "_audio_device_key") else "",
            "motif": reason,
        }
        self.audio_recorder.start(
            self._recordings_dir(),
            self.audio_fs,
            meta,
            # 2.8.5 : au moins 25 min / 140 Mo (une carte de 20 min ne tenait pas dans la limite de 15 min)
            max_minutes=max(25, getattr(ws, "raw_audio_max_minutes", 25) if ws else 25),
            max_mb=max(140, getattr(ws, "raw_audio_max_mb", 140) if ws else 140),
        )
        self._style_rec_button()
        # 2.9.1 — l'enregistrement du 18/11 (« GYA2 ») contenait en fait GYA2, GYA3 puis NAVTEX 490 kHz : chaque
        # changement de fréquence pendant l'enregistrement est désormais noté dans le .json (instant, station)
        self._rec_t0 = time.monotonic()
        self._rec_last_freq = self.radio.actual_freq_khz
        self.audio_recorder.meta.setdefault("changements", [])
        self._watch_recording()

    def _note_recording_qsy(self):
        rec = self.audio_recorder
        f = getattr(self.radio, "actual_freq_khz", None)
        if not rec.active or f is None or f == getattr(self, "_rec_last_freq", f):
            return
        self._rec_last_freq = f
        mode, st = self._current_mode_label()
        rec.meta.setdefault("changements", []).append(
            {
                "t_s": round(time.monotonic() - getattr(self, "_rec_t0", time.monotonic()), 1),
                "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "station": (st or {}).get("id", self.radio.active_station_id),
                "frequence_khz": f,
                "mode": mode,
            }
        )

    def _watch_recording(self):
        """Surveille la limite de l'enregistrement : arrêt annoncé et bouton REC remis à jour."""
        rec = self.audio_recorder
        try:
            self._note_recording_qsy()
        except Exception:
            pass
        if rec.finish_if_limit():
            self._style_rec_button()
            return
        if rec.active:
            self.root.after(2000, self._watch_recording)

    def _stop_recording(self, reason="Arrêt opérateur"):
        self.audio_recorder.stop(reason)
        self._style_rec_button()

    def _toggle_recording(self):
        if self.audio_recorder.active:
            self._stop_recording()
        else:
            self._start_recording()

    def _style_rec_button(self):
        if hasattr(self, "btn_rec"):
            on = self.audio_recorder.active
            self.btn_rec.configure(text="⏺ REC ON" if on else "⏺ REC", bg="#b91c1c" if on else "#334155")

    def _auto_record_chart_start(self):
        if self.auto_record_var.get() and not self.audio_recorder.active and self.audio_live_connected:
            self._start_recording("Automatique : APT START")

    def _auto_record_chart_end(self, reason):
        if self.auto_record_var.get() and self.audio_recorder.active:
            self._stop_recording("Automatique : " + str(reason))

    # ---------------------------------------------------------------- relecture
    def _replay_wav_dialog(self):
        path = filedialog.askopenfilename(
            title="Rejouer un enregistrement audio",
            initialdir=str(self._recordings_dir()),
            filetypes=[("Audio WAV", "*.wav"), ("Tous", "*.*")],
        )
        if path:
            self._start_replay(path)

    def _start_replay(self, path, speed=1.0):
        if self.replay_active:
            self._stop_replay("Nouvelle relecture")
        try:
            x, fs, meta = read_wav(path)
        except Exception as exc:
            messagebox.showerror("Relecture", f"Lecture impossible : {exc}")
            return False
        if self.audio_recorder.active:
            self._stop_recording("Relecture d'un fichier")
        self._replay_saved = {
            "audio_fs": self.audio_fs,
            "ppm": float(self.dsp.clock_ppm),
            "live": self.audio_live_connected,
        }
        # les cartes archivées pendant la relecture portent la station et la fréquence de l'enregistrement
        self._replay_saved["station"] = (
            self.radio.active_station_id,
            self.radio.actual_freq_khz,
            getattr(self.radio, "actual_dial_khz", None),
        )
        if meta.get("station"):
            self.radio.active_station_id = str(meta["station"])
        if meta.get("frequence_khz"):
            try:
                self.radio.actual_freq_khz = float(meta["frequence_khz"])
                self.radio.actual_dial_khz = float(meta.get("cadran_khz") or self.radio.actual_freq_khz - 1.9)
            except (TypeError, ValueError):
                pass
        if fs != self.audio_fs:
            self.audio_fs = fs
            self.dsp.set_sample_rate(fs)
            self.audio_ring = np.zeros(int(fs * 0.6), dtype=np.float32)
        if "horloge_audio_ppm" in meta:
            self.dsp.clock_ppm = float(meta["horloge_audio_ppm"])
        mode = str(meta.get("mode", "WEFAX"))
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            if mode in ("RTTY", "NAVTEX"):
                st = next((s for s in RTTY_WEATHER_STATIONS if s["id"] == meta.get("station")), None)
                if st is None and meta.get("frequence_khz") and is_rtty_frequency(meta["frequence_khz"]):
                    st = next(
                        s
                        for s in RTTY_WEATHER_STATIONS
                        if abs(s["freq"] - float(meta["frequence_khz"])) < 0.8
                    )
                if st is not None:
                    arb.switch_to_rtty_pipeline(st, reason="Relecture d'un enregistrement")
            elif arb.active_pipeline == "RTTY":
                arb.switch_to_wefax_pipeline(reason="Relecture d'un enregistrement WEFAX")
            # la planification automatique ne doit pas changer de mode pendant la relecture
            self._replay_saved["requested_mode"] = arb.requested_mode
            arb.requested_mode = "RELECTURE"
        if hasattr(self, "rtty_decoder"):
            self.rtty_decoder.configure(sample_rate=self.audio_fs)
        with self.rx_audio_queue.mutex:
            self.rx_audio_queue.queue.clear()
        self.rx_sample_accumulator = np.zeros(0, np.float32)
        self.dsp.reset_filter_states()
        self._replay = {"x": x, "pos": 0, "speed": float(speed), "path": str(path), "t0": time.monotonic()}
        self.replay_active = True
        self.audio_live_connected = True
        self.log_event(
            f"▶ Relecture : {Path(path).name} ({len(x) / fs:.0f} s, {fs} Hz, mode {mode}"
            + (f", station {meta.get('station')}" if meta.get("station") else "")
            + ")"
        )
        self.root.after(100, self._replay_tick)
        return True

    def _replay_tick(self):
        if not self.replay_active or self.closing:
            return
        r = self._replay
        n = int(self.audio_fs * 0.1 * r["speed"])
        blk = r["x"][r["pos"] : r["pos"] + n]
        r["pos"] += n
        if len(blk) == 0:
            self._stop_replay("Fin du fichier")
            return
        m = len(blk)
        if m < len(self.audio_ring):
            self.audio_ring[:-m] = self.audio_ring[m:]
            self.audio_ring[-m:] = blk
        else:
            self.audio_ring[:] = blk[-len(self.audio_ring) :]
        lr = getattr(self, "audio_long_ring", None)
        if lr is None or len(lr) != int(self.audio_fs * 4.5):
            lr = self.audio_long_ring = np.zeros(int(self.audio_fs * 4.5), dtype=np.float32)
        if m < len(lr):
            lr[:-m] = lr[m:]
            lr[-m:] = blk
        self.last_audio_callback = time.monotonic()
        try:
            self.rx_audio_queue.put_nowait(blk.astype(np.float32))
        except Exception:
            self.audio_drop_count += 1
        self.root.after(100, self._replay_tick)

    def _stop_replay(self, reason="Fin"):
        if not self.replay_active:
            return
        self.replay_active = False
        saved = getattr(self, "_replay_saved", {})
        self.audio_live_connected = bool(saved.get("live", False))
        if saved.get("audio_fs") and saved["audio_fs"] != self.audio_fs:
            self.audio_fs = saved["audio_fs"]
            self.dsp.set_sample_rate(self.audio_fs)
            self.audio_ring = np.zeros(int(self.audio_fs * 0.6), dtype=np.float32)
        if "ppm" in saved:
            self.dsp.clock_ppm = saved["ppm"]
        if saved.get("station"):
            self.radio.active_station_id, self.radio.actual_freq_khz, dial = saved["station"]
            if dial is not None:
                self.radio.actual_dial_khz = dial
        if hasattr(self, "rtty_decoder"):
            self.rtty_decoder.configure(sample_rate=self.audio_fs)
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None and saved.get("requested_mode"):
            arb.requested_mode = saved["requested_mode"]
        self.log_event(f"⏹ Relecture terminée ({reason}).")
