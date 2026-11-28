"""Cycle de vie : journal, file d'événements, tâches périodiques, fermeture, compilation."""

import csv
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from wefax_station.version import LAUNCHER_SCRIPT, PROJECT_ROOT
from wefax_station.storage.atomic import atomic_png


class LifecycleMixin:
    # ------------------------------------------------------------- journal
    def log_event(self, text):
        """Journal unique : affichage (onglet Diagnostics), CSV de session, journal tournant.

        Appelable depuis n'importe quel thread : hors thread Tk, l'événement est remis
        à la file d'événements de l'interface.
        """
        if threading.get_ident() != self.main_thread:
            self.ui_events.put(lambda t=text: self.log_event(t))
            return
        msg_str = str(text)
        # Anti-spam des messages SIGNAL du bandeau de réception
        if "RX_BANNER SIGNAL status=" in msg_str:
            now_m = time.monotonic()
            last_sig_log = getattr(self, "_last_rx_banner_sig_log_mono", 0.0)
            last_sig_msg = getattr(self, "_last_rx_banner_sig_msg", "")
            if int(getattr(self, "rx_current_line", 0)) >= 3 and not getattr(
                self, "waiting_after_stop", False
            ):
                return
            if msg_str == last_sig_msg or (now_m - last_sig_log) < 12.0:
                return
            self._last_rx_banner_sig_log_mono = now_m
            self._last_rx_banner_sig_msg = msg_str
        self._append_log_widget(text)
        self._append_log_csv(text)
        ws = getattr(self, "portable_ws", None)
        if ws is not None and ws.rotating_logger is not None:
            try:
                stamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                ws.rotating_logger.info(f"[{stamp}] {msg_str}")
            except Exception:
                pass
        for log_attr in ("txt_log", "log_text", "txt_diagnostics"):
            w_log = getattr(self, log_attr, None)
            if w_log is not None:
                try:
                    line_cnt = int(str(w_log.index("end-1c")).split(".")[0])
                    if line_cnt > 1500:
                        w_log.delete("1.0", f"{line_cnt - 1200}.0")
                except Exception:
                    pass

    def _build_permanent_log_dock(self, parent):
        frame = tk.LabelFrame(
            parent, text="Journal CAT / Audio / Scan - diagnostics", bg="#090d16", fg="#38bdf8"
        )
        frame.pack(fill="both", expand=True, padx=6, pady=4)
        bar = tk.Frame(frame, bg="#090d16")
        bar.pack(fill="x")
        tk.Button(bar, text="Export log", command=lambda: self._diag_export_log()).pack(
            side="right", padx=4, pady=4
        )
        tk.Button(bar, text="Effacer", command=lambda: self.txt_logs.delete("1.0", "end")).pack(
            side="right", padx=4
        )
        follow = tk.BooleanVar(master=frame, value=True)
        self._diag_log_follow = follow
        tk.Checkbutton(
            bar, text="Suivre la fin", variable=follow, bg="#090d16", fg="#cbd5e1", selectcolor="#1e293b"
        ).pack(side="left")
        body = tk.Frame(frame)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.txt_logs = tk.Text(
            body, wrap="none", height=16, width=40, bg="#020617", fg="#38bdf8", font=("Consolas", 9)
        )
        ys = ttk.Scrollbar(body, orient="vertical", command=self.txt_logs.yview)
        xs = ttk.Scrollbar(body, orient="horizontal", command=self.txt_logs.xview)
        self.txt_logs.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.txt_logs.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")

    def _diag_export_log(self):
        p = filedialog.asksaveasfilename(
            parent=self.txt_logs.winfo_toplevel(),
            title="Exporter le journal visible",
            defaultextension=".txt",
            initialfile="WEFAX_log_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ") + ".txt",
            filetypes=[("Journal texte UTF-8", "*.txt")],
        )
        if not p:
            return
        try:
            content = self.txt_logs.get("1.0", "end-1c")
            with open(p, "w", encoding="utf-8-sig") as f:
                f.write("Station WEFAX - export UTC " + datetime.now(timezone.utc).isoformat() + "\n")
                f.write("Journal visible ; Effacer retire les anciennes lignes de cet export.\n")
                f.write("Le CSV de session peut contenir des evenements supplementaires.\n\n")
                f.write(content + "\n")
            self.log_event("Export log termine : " + p)
        except OSError as exc:
            messagebox.showerror("Export log", str(exc), parent=self.txt_logs.winfo_toplevel())

    def _append_log_widget(self, text):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        try:
            self.txt_logs.insert("end", f"[{ts} UTC] {text}\n")
            if not hasattr(self, "_diag_log_follow") or self._diag_log_follow.get():
                self.txt_logs.see("end")
        except tk.TclError:
            pass
        except AttributeError:
            pass

    def _append_log_csv(self, text):
        if not self.csv_path:
            return
        try:
            new = not self.csv_path.exists()
            with self.csv_path.open("a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                if new:
                    writer.writerow(
                        [
                            "utc",
                            "station",
                            "carrier_khz",
                            "dial_khz",
                            "snr_proxy_db",
                            "line",
                            "audio_drops",
                            "event",
                        ]
                    )
                writer.writerow(
                    [
                        datetime.now(timezone.utc).isoformat(),
                        self.radio.active_station_id,
                        self.radio.actual_freq_khz,
                        self.radio.actual_dial_khz,
                        self.current_snr_db,
                        self.rx_current_line,
                        self.audio_drop_count,
                        text,
                    ]
                )
        except OSError as exc:
            self._append_log_widget("ERREUR journal disque : " + str(exc))

    # ------------------------------------------------- événements / périodiques
    def _pump_events(self):
        for _ in range(30):
            try:
                action = self.ui_events.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            except Exception as exc:
                self.log_event("ERREUR interface : " + repr(exc))
        if not self.closing:
            self.root.after(100, self._pump_events)

    def _housekeeping(self):
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            arb.disarm_base_periodic_scan_timers()
        res = self._housekeeping_base()
        if hasattr(self, "_update_vfo"):
            try:
                self._update_vfo()
            except Exception:
                pass
        if arb is not None and not self.closing:
            self._sector_outlook_tick()
            try:
                arb.evaluate_hybrid_schedule()
                if hasattr(self, "schedule_planner"):
                    self.schedule_planner.trigger_web_schedule_sync(manual=False)
                if hasattr(self, "bulletins_ui"):
                    self.bulletins_ui.refresh_status()
            except Exception as exc:
                self.log_event("Arbitre hybride : " + repr(exc))
        return res

    # ------------------------------------------------------------------ 2.10.0 : aperçu du secteur
    SECTOR_OUTLOOK_PERIOD_S = 600.0
    _OUTLOOK_COLORS = {"VERT": "#166534", "JAUNE": "#a16207", "ORANGE": "#c2410c", "ROUGE": "#b91c1c"}
    _OUTLOOK_DOTS = {"VERT": "🟢", "JAUNE": "🟡", "ORANGE": "🟠", "ROUGE": "🔴"}

    def _sector_outlook_tick(self, force=False):
        """Toutes les 10 min (et après chaque bulletin archivé) : situation et prévision 3-6 h recalculées
        hors de l'interface, puis affichées sur le bouton « Météo & bulletin »."""
        import threading
        import time as _time

        arb = getattr(self, "hybrid_arbiter", None)
        if arb is None or getattr(self, "_outlook_busy", False):
            return
        now = _time.monotonic()
        if not force and now - getattr(self, "_outlook_ts", -1e9) < self.SECTOR_OUTLOOK_PERIOD_S:
            return
        self._outlook_ts = now
        self._outlook_busy = True
        try:
            inputs = arb.nowcast_inputs()  # variables Tk et fichiers texte : lus ici, dans le fil de l'interface
        except Exception:
            self._outlook_busy = False
            return

        def work():  # GRIB et calcul : hors de l'interface
            try:
                nc = arb.compute_nowcast(**inputs)
            except Exception as exc:
                nc = exc
            self.ui_events.put(lambda: self._show_sector_outlook(nc))

        threading.Thread(target=work, daemon=True, name="apercu-secteur").start()

    def _show_sector_outlook(self, nc):
        self._outlook_busy = False
        btn = getattr(self, "btn_meteo_desk", None)
        if isinstance(nc, Exception) or btn is None:
            return
        self.last_nowcast = nc
        if getattr(self, "hybrid_arbiter", None) is not None:
            self.hybrid_arbiter.last_nowcast = nc
        rel = nc["reliability"]
        lvl = nc.get("level")
        if lvl:
            text = f"Météo & bulletin\n{self._OUTLOOK_DOTS.get(lvl, '')} 3-6 h · fiab. {rel['score']} % [{rel['grade']}]"
            bg = self._OUTLOOK_COLORS.get(lvl, "#334155")
        else:
            text = f"Météo & bulletin\n3-6 h : pas de prévision reçue"
            bg = "#334155"
        try:
            btn.configure(text=text, bg=bg, fg="#ffffff", activebackground=bg, font=("Segoe UI", 8, "bold"))
            if hasattr(self, "_register_tip25"):
                from wefax_station.weather.nowcast import nowcast_lines

                self._register_tip25(btn, "meteo", "\n".join(nowcast_lines(nc)[:14]))
        except Exception:
            pass

    def _housekeeping_base(self):
        if self.closing:
            return
        self._update_programme()
        self._slant_label()
        self._highlight_station()
        active = self.prevent_sleep.get() and (
            self.connection_busy
            or self.carrier_scan_active
            or (self.rx_decoding_active and self.audio_live_connected)
        )
        self._set_power(active)
        try:
            self._save_draft()
        except OSError as exc:
            self.log_event("Brouillon non sauve : " + repr(exc))
        self.root.after(15000, self._housekeeping)

    def _periodic_watchdog_tick(self):
        if self.connection_busy or self.carrier_scan_active:
            self.root.after(6000, self._periodic_watchdog_tick)
            return
        try:
            self._check_day_night_schedule()
            if self.auto_rf_loop_active or (self.radio.port_open and self.radio.handshake_ok):
                self._execute_closed_loop_rf_control()
        except Exception:
            pass
        self.root.after(6000, self._periodic_watchdog_tick)

    def _supervisor(self):
        """Toutes les 10 s.

        * Aucun scan n'est déclenché ici : les scans sont pilotés par HybridModeArbiter (T-120 s avant carte).
        * Sauvegarde de sécurité : toutes les 60 s pendant une carte, l'image décodée est écrite dans
          « reception_en_cours.png » (écriture atomique). En cas de coupure (batterie, plantage), la
          carte n'est pas perdue. Le fichier est supprimé quand la carte est archivée normalement.
        """
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            arb.disarm_base_periodic_scan_timers()
        try:
            self._safety_checkpoint()
        except Exception as exc:
            self.log_event("Sauvegarde de sécurité impossible : " + repr(exc))
        if not getattr(self, "closing", False):
            self.root.after(10000, self._supervisor)

    def _checkpoint_path(self):
        return Path(self.archive_dir) / "reception_en_cours.png"

    def _safety_checkpoint(self):
        n = int(getattr(self, "rx_current_line", 0))
        if (
            n < 60
            or getattr(self, "waiting_after_stop", False)
            or getattr(self, "carrier_scan_active", False)
        ):
            return
        now = time.monotonic()
        if now - getattr(self, "last_checkpoint", 0.0) < 60.0:
            return
        self.last_checkpoint = now
        atomic_png(self._checkpoint_path(), self.raw_wefax_img[:n])
        self.log_event(f"💾 Sauvegarde de sécurité : {n} lignes ({self._checkpoint_path().name})")

    def _clear_safety_checkpoint(self):
        try:
            self._checkpoint_path().unlink()
        except OSError:
            pass

    def set_busy_state(self, busy: bool, label_text: str = ""):
        self.is_busy = busy
        if busy:
            self.root.config(cursor="watch")
            self.canvas.config(cursor="watch")
            self.lbl_busy_badge.config(text=f"⏳ {label_text or 'CALCUL...'}", bg="#f59e0b", fg="#000000")
        else:
            self.root.config(cursor="")
            cur = "crosshair" if self.canvas_tool_mode != "NONE" else "fleur"
            self.canvas.config(cursor=cur)
            rx_txt = (
                f"📡 RX L.{self.rx_current_line}"
                if (self.rx_decoding_active and self.rx_current_line > 0)
                else "🟢 ARMÉ 120 RPM"
            )
            self.lbl_busy_badge.config(text=rx_txt, bg="#064e3b", fg="#6ee7b7")
        self.root.update_idletasks()

    def _warn_suboptimal_user_action(self, warning_msg: str):
        self.log_event(f"⚠️ [ALERTE OPTIMUM] {warning_msg}")
        self.lbl_status.config(text=f"⚠️ ATTENTION RÉGLAGE SOUS-OPTIMAL : {warning_msg}", fg="#fbbf24")

    # ------------------------------------------------------------ fermeture
    def _close(self):
        if self.connection_busy:
            messagebox.showwarning("Connexion", "Attendre la fin de la connexion.")
            return
        if self.carrier_scan_active and not messagebox.askyesno("Scan", "Fermer pendant le scan ?"):
            return
        if self.rx_current_line > 25 and self.saved_generation != self.generation:
            self._finalize_completed_wefax_chart("Fermeture ; fragment")
            if self.saved_generation != self.generation and not messagebox.askyesno(
                "Sauvegarde échouée", "Fermer malgré la carte non sauvegardée ?"
            ):
                return
        self._save_preferences()
        try:
            self._save_draft()
        except OSError as exc:
            self.log_event("Brouillon non sauve : " + repr(exc))
        self._set_power(False)
        self.closing = True
        if getattr(self, "audio_recorder", None) is not None and self.audio_recorder.active:
            self.audio_recorder.stop("Fermeture du programme")
        self.replay_active = False
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception as exc:
                self.log_event("Fermeture audio : " + repr(exc))
        self.radio.disconnect()
        self.root.destroy()

    # ----------------------------------------------------------- compilation
    def _compile_exe(self):
        if not messagebox.askyesno(
            "Compiler",
            "Compiler cette version avec PyInstaller installé localement ? Le résultat est une base de test, non certifiée.",
        ):
            return
        source = str(LAUNCHER_SCRIPT)
        dest = str(Path(self.archive_dir) / "Compilation")

        def worker():
            cmd = [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onedir",
                "--windowed",
                "--name",
                "StationWEFAXPro",
                "--distpath",
                dest,
                "--workpath",
                dest + "_build",
                "--specpath",
                dest + "_spec",
                "--paths",
                str(PROJECT_ROOT),
                source,
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
                )
                Path(self.archive_dir, "compilation.log").write_text(
                    result.stdout + result.stderr, encoding="utf-8"
                )
                self.log_event(
                    "Compilation terminee : "
                    + (dest if result.returncode == 0 else "ECHEC : voir compilation.log")
                )
            except Exception as exc:
                self.log_event("ERREUR compilation : " + repr(exc))

        threading.Thread(target=worker, daemon=True).start()
