"""Assistant Winlink : état de l'installation, choix de passerelle, session (poste libéré), demande et
lecture des fichiers GRIB.

2.8.7 — Station WEFAX ne remplace pas Winlink Express : elle prépare le poste, indique la meilleure
passerelle à l'heure voulue, rédige la demande Saildocs, puis lit les fichiers reçus et les ajoute au
dossier météo. Pendant la session, l'application libère le port CI-V et la carte son de l'IC-705
(sinon VARA ne peut pas commander l'émission), puis reprend la réception d'un clic.
"""

import json
import subprocess
import sys
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from wefax_station.weather import grib as grib_mod
from wefax_station.winlink import express as wlx
from wefax_station.ui.placement import show_over_root
from wefax_station.winlink import saildocs

BG = "#0f172a"
PANEL = "#111c33"
FG = "#e2e8f0"
DIM = "#94a3b8"
AMBER = "#f5c46b"
LEVEL_COLORS = {"OK": "#34d399", "INFO": "#93c5fd", "ATTENTION": "#fbbf24", "BLOQUANT": "#f87171"}

GUIDE = """PREMIERS PAS AVEC WINLINK PAR HF (VARA)

Winlink est une messagerie par radio. Votre poste joint une « passerelle » (RMS) tenue par un autre
radioamateur ; elle transmet vos messages vers Internet et vous remet ceux qui vous attendent. En HF,
la passerelle n'a pas besoin d'être proche : entre 300 et 1 000 km, c'est même l'idéal.

UNE FOIS POUR TOUTES
   • Brancher l'IC-705 en USB AVANT de lancer VARA HF.
   • IC-705 : SET › Connectors › MOD Input › DATA MOD = USB ; USB MOD Level ≈ 50 %.
   • VARA HF › Settings › Soundcard : entrée « Microphone (USB Audio CODEC) », sortie
     « Haut-parleurs (USB Audio CODEC) ».
   • Winlink Express › session « Vara HF Winlink » › Settings › Radio Setup : modèle IC-705 s'il est
     proposé, adresse CI-V A4, port série du poste (celui de Station WEFAX, COM14 chez F4NMK), mode
     USB-D (données), commande d'émission (PTT) par CAT plutôt que par VOX.
   • Niveau d'émission : bouton « Tune » de VARA, ALC du poste au seuil (indication nulle ou très
     faible). Si le Drive de VARA doit descendre très bas (ex. -25 dB) pour éviter l'ALC, c'est en
     général que USB MOD Level est trop haut : le baisser sur le poste et remonter le Drive.
   • Puissance : réduite pour les modes numériques (émission continue). À vérifier sur votre station.
   • Le bouton « Installation » en haut de l'assistant vérifie ces réglages (sans rien modifier).
   • Station WEFAX PRO n'émet jamais : c'est VARA HF qui émet, quand vous cliquez « Start ».

À CHAQUE SESSION : trois étapes dans l'assistant
   1. Choisir la passerelle (la meilleure pour l'heure est déjà sélectionnée).
   2. « CONNEXION À WINLINK » : le poste est réglé et libéré, Winlink Express s'ouvre, l'indicatif de
      la passerelle est copié. L'assistant affiche ensuite quoi faire dans Winlink Express :
      Open Session « Vara HF Winlink » › Channel Selection › la passerelle › Start.
      Écoutez avant d'émettre : si la fréquence est occupée, attendez ou prenez la suivante.
   3. Une fois « Disconnected », fermer la fenêtre VARA HF Winlink, puis « DÉCONNEXION · RÉCUPÉRER LE
      GRIB · RETOUR WEFAX / RTTY » : les fichiers reçus sont lus et la réception météo reprend seule.

DEMANDER UNE PRÉVISION (GRIB) À SAILDOCS — facultatif
   • « Demander une prévision GRIB » (étape 2) : régler la zone, copier la demande.
   • Winlink Express › Message › New Message. À : query@saildocs.com ; Objet : meteo ; coller la
     demande dans le texte. « Post to Outbox ».
   • La demande part à la connexion ; la réponse arrive en général à la session suivante.

BON À SAVOIR
   • Version gratuite de VARA : débit réduit, mais une demande GRIB bien dosée (quelques ko) passe
     en quelques minutes. Les passerelles « VARA HF 2750 » peuvent refuser la version gratuite.
   • Gardez les messages petits : au-delà de 100 ko, ce n'est plus raisonnable par radio.
   • Le GRIB est une prévision brute de modèle (GFS) : utile pour la tendance, à comparer toujours
     aux bulletins officiels.
"""


class WinlinkDeskMixin:
    # ------------------------------------------------------------- configuration
    def _wl_cfg_path(self):
        return Path(self.portable_ws.root_dir) / "configuration" / "winlink.json"

    def _wl_cfg(self):
        try:
            return json.loads(self._wl_cfg_path().read_text(encoding="utf-8"))
        except (OSError, ValueError, AttributeError):
            return {}

    def _wl_save_cfg(self, cfg):
        try:
            p = self._wl_cfg_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def winlink_info(self):
        cfg = self._wl_cfg()
        return wlx.locate(cfg.get("rms_dir") or None, cfg.get("vara_dir") or None)

    def winlink_grib_dir(self):
        return Path(self.portable_ws.operator_dir()) / "grib"

    # ------------------------------------------------------------- GRIB → dossier
    def winlink_poll_gribs(self, quiet=True):
        info = self.winlink_info()
        udir = wlx.user_dir(info)
        if udir is None:
            return []
        try:
            new = saildocs.collect_gribs(udir, self.winlink_grib_dir())
        except Exception as exc:
            if not quiet:
                self.log_event(f"⚠️ Lecture des messages Winlink impossible : {exc!r}")
            return []
        for g in new:
            self.log_event(f"📨 GRIB reçu par Winlink ({g['received']:%d/%m %H:%M} UTC) : {Path(g['path']).name}")
        return new

    def winlink_grib_rows(self, qth, radius_km, now=None):
        """2.10.0 — (lignes summarize, heure de réception) du GRIB le plus récent de moins de 36 h, sinon (None, None)."""
        now = now or datetime.now(timezone.utc)
        f = saildocs.latest_grib(self.winlink_grib_dir())
        if f is None:
            return None, None
        try:
            received = datetime.strptime(f.name[:14], "%Y%m%d_%H%MZ").replace(tzinfo=timezone.utc)
        except ValueError:
            received = None
        if received is not None and now - received > timedelta(hours=36):
            return None, received
        try:
            fields = grib_mod.read_messages(f.read_bytes())
        except Exception:
            return None, received
        return grib_mod.summarize(fields, qth, radius_km=min(150, radius_km)), received

    def winlink_grib_section(self, qth, radius_km, now=None):
        """(titre, lignes, source) du GRIB le plus récent de moins de 36 h, ou None."""
        now = now or datetime.now(timezone.utc)
        f = saildocs.latest_grib(self.winlink_grib_dir())
        if f is None:
            return None
        try:
            received = datetime.strptime(f.name[:14], "%Y%m%d_%H%MZ").replace(tzinfo=timezone.utc)
        except ValueError:
            received = None
        if received is not None and now - received > timedelta(hours=36):
            return None
        try:
            fields = grib_mod.read_messages(f.read_bytes())
        except Exception as exc:
            return ("PRÉVISION NUMÉRIQUE (GRIB reçu par Winlink)", [f" • Fichier {f.name} illisible : {exc}"], None)
        rows = grib_mod.summarize(fields, qth, radius_km=min(150, radius_km))
        lines = grib_mod.report_lines(rows, received=received, now=now)
        src = ("GRIB Saildocs (Winlink)", f"{received:%d/%m %H:%M} UTC" if received else "?", f.name)
        return ("PRÉVISION NUMÉRIQUE AU CANNET ET ALENTOURS (GRIB GFS reçu par Winlink)", lines, src)

    def _wl_poll_loop(self):
        """Toutes les 10 min : nouveaux GRIB reçus par Winlink (lecture de quelques fichiers seulement)."""
        try:
            if not getattr(self, "closing", False):
                self.winlink_poll_gribs(quiet=True)
        finally:
            if not getattr(self, "closing", False):
                self.root.after(600000, self._wl_poll_loop)

    # ------------------------------------------------------------- session : poste libéré
    def winlink_session_start(self, gw):
        if getattr(self, "winlink_session_active", False):
            return
        if 20 < getattr(self, "rx_current_line", 0) and getattr(self, "rx_decoding_active", False):
            if not messagebox.askyesno(
                "Session Winlink",
                "Une carte WEFAX est en cours de réception. L'interrompre pour la session Winlink ?",
                parent=getattr(self, "_wl_win", None) or self.root,
            ):
                return
        dial = float(gw["dial_khz"])
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            arb.manual_hold = True
            arb.current_activity = "WINLINK"
        if getattr(self, "rx_decoding_active", False):
            try:
                self._toggle_rx_decoding_base()
            except Exception:
                self.rx_decoding_active = False
        try:
            if self.radio.port_open and self.radio.handshake_ok:
                self.radio.set_wefax_frequency(dial, apply_usb_offset=False)
            else:
                self.radio.actual_freq_khz = dial
        except Exception as exc:
            self.log_event(f"⚠️ Réglage de la fréquence Winlink : {exc!r}")
        self._wl_saved_link = {
            "port": self.cmb_port.get() if hasattr(self, "cmb_port") else "",
            "baud": self.cmb_baud.get() if hasattr(self, "cmb_baud") else "19200",
            "proto": self.cmb_proto.get() if hasattr(self, "cmb_proto") else "ICOM CI-V",
            "civ": self.ent_civ.get() if hasattr(self, "ent_civ") else "A4",
            "audio": self.cmb_audio.get() if hasattr(self, "cmb_audio") else "",
            "had_cat": bool(self.radio.port_open),
            "had_audio": bool(getattr(self, "audio_live_connected", False)),
        }
        if getattr(self, "audio_recorder", None) is not None and self.audio_recorder.active:
            self.audio_recorder.stop("Session Winlink")
        if getattr(self, "audio_stream", None) is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
            self.audio_stream = None
            self.audio_live_connected = False
        self.radio.disconnect()
        self.winlink_session_active = True
        self.log_event(
            f"📮 Session Winlink : poste réglé sur {gw['call']} {dial:.1f} kHz (USB-D), réception en pause, "
            "port CI-V et carte son libérés pour VARA HF."
        )
        self._wl_gw_active = gw
        self._wl_show_banner(gw)
        try:
            self._sync_ui_from_hardware()
        except Exception:
            pass

    def winlink_session_end(self):
        if not getattr(self, "winlink_session_active", False):
            return
        s = getattr(self, "_wl_saved_link", {}) or {}
        self.winlink_session_active = False
        self._wl_hide_banner()
        if hasattr(self, "_connect_serialized"):
            # 2.8.8 : même boucle que « radio absente au démarrage » : essais silencieux toutes les 15 s
            # tant que Winlink Express garde le port (fenêtre de session VARA encore ouverte), sans
            # boîte d'erreur, puis audio USB et scan dès que le poste répond.
            self._wl_reconnect_hint = True
            self._startup_waiting_radio = False
            self._startup_radio_warned = False
            self._startup_cat_autostart()
        elif s.get("had_cat") and s.get("port"):  # pragma: no cover (ancien chemin)
            try:
                self.radio.connect(s["port"], int(s.get("baud") or 19200), s.get("proto"), s.get("civ") or "A4")
            except Exception as exc:
                self.log_event(f"⚠️ Reconnexion CAT après Winlink : {exc!r}")
        try:
            self._sync_ui_from_hardware()
        except Exception:
            pass
        new = self.winlink_poll_gribs(quiet=False)
        self._wl_last_new_gribs = new
        self.log_event(
            "▶️ Fin de session Winlink : réception météo reprise"
            + (f" ; {len(new)} GRIB reçu(s) ajouté(s) au dossier météo." if new else ".")
        )
        if not getattr(self, "rx_decoding_active", False):
            try:
                self._toggle_rx_decoding_base()
            except Exception:
                self.rx_decoding_active = True
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            arb.resume_automation()

    def _wl_show_banner(self, gw):
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        fr = getattr(self, "_wl_banner", None)
        if fr is None:
            fr = tk.Frame(canvas.master, bg="#0b1324", highlightthickness=1, highlightbackground="#334155")
            self._wl_banner = fr
            self._wl_banner_lbl = tk.Label(fr, bg="#0b1324", fg=FG, font=("Segoe UI", 12), justify="left", anchor="w")
            self._wl_banner_lbl.pack(fill="both", expand=True, padx=24, pady=(24, 8))
            tk.Button(
                fr,
                text="⏹  Terminer la session Winlink (retour météo)",
                command=self._wl_banner_finish,
                bg="#047857",
                fg="white",
                relief="flat",
                padx=16,
                pady=6,
                font=("Segoe UI", 11, "bold"),
            ).pack(anchor="w", padx=24, pady=(0, 24))
        self._wl_banner_lbl.configure(
            text=(
                f"📮  SESSION WINLINK — poste libéré pour VARA HF\n\n"
                f"Passerelle conseillée : {gw['call']} ({gw['grid']}, {gw['dist_km']:.0f} km, azimut {gw['bearing']:.0f}°)\n"
                f"Fréquence d'affichage : {gw['dial_khz']:.1f} kHz USB-D   (centre {gw['center_khz']:.1f} kHz · "
                f"{', '.join(gw['modes'])})\n\n"
                "Les étapes à suivre dans Winlink Express sont affichées dans l'assistant Winlink.\n"
                "Écoutez d'abord : si la fréquence est occupée, attendez ou prenez la passerelle suivante.\n\n"
                "La réception météo est en pause ; le port CI-V et la carte son sont libres."
            )
        )
        fr.place(in_=canvas, relx=0, rely=0, relwidth=1, relheight=1)
        fr.lift()

    def _wl_banner_finish(self):
        if getattr(self, "_wl_win", None) is not None and self._wl_win.winfo_exists():
            self._wl_finish()
            self._wl_win.deiconify()
            self._wl_win.lift()
        else:
            self.winlink_session_end()

    def _wl_hide_banner(self):
        fr = getattr(self, "_wl_banner", None)
        if fr is not None:
            fr.place_forget()
        try:
            self._wl_update_steps()
        except (tk.TclError, AttributeError):
            pass

    # ------------------------------------------------------------- Winlink Express (lancement)
    def _wl_express_running(self):
        """True / False sous Windows, None si on ne peut pas savoir."""
        if sys.platform != "win32":
            return None
        try:
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq RMS Express.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            return "RMS Express.exe".lower() in out.lower()
        except (OSError, subprocess.SubprocessError):
            return None

    def _wl_launch_express(self):
        info = self.winlink_info()
        rms = info.get("rms_dir")
        if rms is None:
            return "introuvable"
        if self._wl_express_running():
            return "déjà ouvert"
        exe = Path(rms) / "RMS Express.exe"
        if sys.platform != "win32" or not exe.exists():
            return "non lancé"
        try:
            subprocess.Popen([str(exe)], cwd=str(rms))
            return "lancé"
        except OSError as exc:
            self.log_event(f"⚠️ Lancement de Winlink Express impossible : {exc!r}")
            return "non lancé"

    # ------------------------------------------------------------- fenêtre (2.8.8 : assistant en 3 étapes)
    def _open_winlink_desk(self, tab=0):
        """Une seule fenêtre, trois étapes : passerelle → CONNEXION → FIN DE SESSION (GRIB + retour météo)."""
        win = getattr(self, "_wl_win", None)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            self._wl_update_steps()
            return
        win = tk.Toplevel(self.root)
        win.title("Winlink par VARA HF — assistant")
        win.configure(bg=BG)
        win.geometry("920x800")
        show_over_root(win, self.root)
        win.minsize(780, 640)
        self._wl_win = win

        # ---- en-tête : identité + état de l'installation
        head = tk.Frame(win, bg=BG)
        head.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(head, text="📮  Winlink par VARA HF", bg=BG, fg=AMBER, font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Button(head, text="❓ Premiers pas", command=self._wl_show_guide, relief="flat", bg=PANEL, fg=FG, padx=8).pack(
            side="right"
        )
        self._wl_install_btn = tk.Button(
            head, text="", command=self._wl_show_install, relief="flat", bg=PANEL, fg=FG, padx=8
        )
        self._wl_install_btn.pack(side="right", padx=6)
        self._wl_ident = tk.Label(win, text="", bg=BG, fg=DIM, anchor="w", font=("Segoe UI", 9))
        self._wl_ident.pack(fill="x", padx=16)

        # ---- étape 1 : passerelle
        c1 = self._wl_card(win, "1", "Choisir la passerelle")
        top = tk.Frame(c1, bg=PANEL)
        top.pack(fill="x", pady=(0, 4))
        tk.Label(top, text="Heure UTC :", bg=PANEL, fg=DIM).pack(side="left")
        self._wl_hour = tk.Spinbox(top, from_=0, to=23, width=4, wrap=True, command=self._wl_refresh_gw)
        self._wl_hour.delete(0, "end")
        self._wl_hour.insert(0, str(datetime.now(timezone.utc).hour))
        self._wl_hour.pack(side="left", padx=6)
        self._wl_free_var = tk.BooleanVar(master=self.root, value=bool(self._wl_cfg().get("prefer_free", True)))
        tk.Checkbutton(
            top,
            text="VARA gratuit : passerelles « VARA HF » standard d'abord",
            variable=self._wl_free_var,
            command=self._wl_refresh_gw,
            bg=PANEL,
            fg=FG,
            selectcolor=BG,
            activebackground=PANEL,
        ).pack(side="left", padx=10)
        cols = ("call", "freq", "band", "dist", "score", "modes")
        tv = ttk.Treeview(c1, columns=cols, show="headings", height=4, selectmode="browse")
        for c, w, h in (
            ("call", 100, "Passerelle"),
            ("freq", 120, "Affichage IC-705"),
            ("band", 60, "Bande"),
            ("dist", 150, "Distance · azimut"),
            ("score", 110, "Liaison prévue"),
            ("modes", 170, "Mode"),
        ):
            tv.heading(c, text=h)
            tv.column(c, width=w, anchor="center")
        tv.pack(fill="x")
        tv.bind("<<TreeviewSelect>>", lambda e: self._wl_update_steps())
        self._wl_tv = tv
        self._wl_gw_rows = []
        self._wl_gw_note = tk.Label(c1, text="", bg=PANEL, fg=DIM, justify="left", anchor="w", wraplength=820)
        self._wl_gw_note.pack(fill="x", pady=(4, 0))

        # ---- étape 3 : fin
        c3 = self._wl_card(win, "3", "Terminer et revenir à la météo", side="bottom")
        row = tk.Frame(c3, bg=PANEL)
        row.pack(fill="x")
        self._wl_btn_end = tk.Button(
            row,
            text="⏹  DÉCONNEXION · RÉCUPÉRER LE GRIB · RETOUR WEFAX / RTTY",
            command=self._wl_finish,
            bg="#1d4ed8",
            fg="white",
            activebackground="#1e40af",
            relief="flat",
            padx=18,
            pady=8,
            font=("Segoe UI", 11, "bold"),
        )
        self._wl_btn_end.pack(side="left")
        tk.Button(row, text="📂 GRIB reçus…", command=self._wl_show_received, relief="flat", bg=BG, fg=FG, padx=10, pady=6).pack(
            side="left", padx=10
        )
        self._wl_end_lbl = tk.Label(c3, text="", bg=PANEL, fg=DIM, justify="left", anchor="w", wraplength=820)
        self._wl_end_lbl.pack(fill="x", pady=(6, 0))

        # ---- étape 2 : connexion
        c2 = self._wl_card(win, "2", "Se connecter")
        row = tk.Frame(c2, bg=PANEL)
        row.pack(fill="x")
        self._wl_btn_connect = tk.Button(
            row,
            text="📡  CONNEXION À WINLINK",
            command=self._wl_connect,
            bg="#047857",
            fg="white",
            activebackground="#065f46",
            relief="flat",
            padx=18,
            pady=8,
            font=("Segoe UI", 11, "bold"),
        )
        self._wl_btn_connect.pack(side="left")
        tk.Button(
            row,
            text="📝 Demander une prévision GRIB (facultatif)…",
            command=self._wl_show_request,
            relief="flat",
            bg=BG,
            fg=FG,
            padx=10,
            pady=6,
        ).pack(side="left", padx=10)
        self._wl_steps_txt = self._wl_text(c2, 11)
        self._wl_steps_txt.pack(fill="both", expand=True, pady=(8, 0))

        self._wl_refresh_identity()
        self._wl_refresh_gw()
        win.bind("<Escape>", lambda e: win.withdraw())

    def _wl_card(self, parent, num, title, side="top"):
        outer = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground="#24324d")
        outer.pack(side=side, fill="both", expand=(num == "2"), padx=14, pady=6)
        hd = tk.Frame(outer, bg=PANEL)
        hd.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(hd, text=f" {num} ", bg=AMBER, fg="#111827", font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(hd, text="  " + title, bg=PANEL, fg=FG, font=("Segoe UI", 11, "bold")).pack(side="left")
        body = tk.Frame(outer, bg=PANEL)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        return body

    def _wl_text(self, parent, height=16):
        t = tk.Text(parent, bg=BG, fg=FG, font=("Consolas", 10), wrap="word", relief="flat", height=height, padx=8, pady=6)
        for lvl, col in LEVEL_COLORS.items():
            t.tag_configure(lvl, foreground=col, font=("Consolas", 10, "bold"))
        t.tag_configure("dim", foreground=DIM)
        t.tag_configure("amber", foreground=AMBER, font=("Consolas", 10, "bold"))
        return t

    def _wl_fill(self, t, parts):
        t.configure(state="normal")
        t.delete("1.0", "end")
        for text, tag in parts:
            t.insert("end", text, tag or ())
        t.configure(state="disabled")

    # ---- état
    def _wl_refresh_identity(self):
        info = self.winlink_info()
        diag = wlx.diagnose(info, cat_port=self.cmb_port.get() if hasattr(self, "cmb_port") else None)
        bad = [d for d in diag if d[0] in ("BLOQUANT", "ATTENTION")]
        block = any(d[0] == "BLOQUANT" for d in diag)
        self._wl_install_btn.configure(
            text=("⛔ " if block else "⚠️ ") + f"{len(bad)} point(s) à vérifier" if bad else "✅ Installation prête",
            fg=LEVEL_COLORS["BLOQUANT" if block else "ATTENTION"] if bad else LEVEL_COLORS["OK"],
        )
        self._wl_ident.configure(
            text=f"Indicatif {info.get('callsign') or '?'} · locator {info.get('grid') or '?'} · "
            f"Winlink Express {'trouvé' if info.get('rms_dir') else 'introuvable'} · "
            f"VARA HF {'trouvé' if info.get('vara_dir') else 'introuvable'}"
        )

    def _wl_refresh_gw(self):
        if not hasattr(self, "_wl_tv"):
            return
        info = self.winlink_info()
        udir = wlx.user_dir(info)
        cfg = self._wl_cfg()
        cfg["prefer_free"] = bool(self._wl_free_var.get())
        self._wl_save_cfg(cfg)
        tv = self._wl_tv
        tv.delete(*tv.get_children())
        try:
            h = int(self._wl_hour.get())
        except ValueError:
            h = datetime.now(timezone.utc).hour
        rows = wlx.rank_gateways(udir, info.get("grid"), h, prefer_free=bool(self._wl_free_var.get())) if udir else []
        self._wl_gw_rows = rows
        for r in rows:
            tv.insert(
                "",
                "end",
                values=(
                    r["call"],
                    f"{r['dial_khz']:.1f} kHz USB-D",
                    wlx.band_name(r["center_khz"]),
                    f"{r['dist_km']:.0f} km · {r['bearing']:.0f}°",
                    f"{r['score']}/100" if r["score"] is not None else "—",
                    ", ".join(r["modes"]),
                ),
            )
        if rows:
            tv.selection_set(tv.get_children()[0])
        self._wl_gw_note.configure(
            text=(
                "Classées par la prévision de liaison de Winlink Express pour l'heure choisie (moins de 60 km : "
                "écartées). Liste à jour : Winlink Express › Channel Selection › Update Table Via Internet."
                if rows
                else "Aucune passerelle : Winlink Express introuvable, locator absent, ou liste des canaux jamais "
                "téléchargée (Winlink Express › Channel Selection › Update Table Via Internet)."
            )
        )
        self._wl_update_steps()

    def _wl_selected(self):
        try:
            sel = self._wl_tv.selection()
            if sel and self._wl_gw_rows:
                return self._wl_gw_rows[self._wl_tv.index(sel[0])]
        except (tk.TclError, IndexError, AttributeError):
            pass
        return None

    def _wl_update_steps(self):
        if not hasattr(self, "_wl_steps_txt"):
            return
        active = bool(getattr(self, "winlink_session_active", False))
        gw = getattr(self, "_wl_gw_active", None) if active else self._wl_selected()
        self._wl_btn_connect.configure(state="disabled" if active or gw is None else "normal")
        self._wl_btn_end.configure(state="normal" if active else "disabled")
        if not active:
            if gw is None:
                self._wl_fill(self._wl_steps_txt, [("Choisissez d'abord une passerelle (étape 1).", "dim")])
            else:
                self._wl_fill(
                    self._wl_steps_txt,
                    [
                        ("Le bouton « Connexion à Winlink » va :\n", "amber"),
                        (
                            f"  • régler l'IC-705 sur {gw['dial_khz']:.1f} kHz USB-D ({gw['call']}) ;\n"
                            "  • mettre la réception météo en pause et libérer le port CI-V et la carte son ;\n"
                            "  • ouvrir Winlink Express s'il est fermé, et copier l'indicatif de la passerelle ;\n"
                            "  • vous afficher ici, pas à pas, quoi faire dans Winlink Express.\n",
                            None,
                        ),
                        ("Rien n'est émis par Station WEFAX : c'est VARA qui émet, quand vous cliquez « Start ».", "dim"),
                    ],
                )
            return
        self._wl_fill(
            self._wl_steps_txt,
            [
                (f"SESSION EN COURS — {gw['call']} · {gw['dial_khz']:.1f} kHz USB-D · poste libéré pour VARA\n\n", "OK"),
                ("Dans Winlink Express :\n", "amber"),
                ("  1. En haut, liste « Open Session » : choisir « Vara HF Winlink », puis « Open Session ».\n", None),
                (
                    f"  2. Fenêtre VARA HF Winlink › « Channel Selection » : double-cliquer {gw['call']}\n"
                    f"     (ou coller l'indicatif déjà copié — Ctrl+V — dans la case de la passerelle).\n",
                    None,
                ),
                (f"  3. Vérifier que l'IC-705 affiche {gw['dial_khz']:.1f} kHz. Écouter 30 s : fréquence libre ?\n", None),
                ("  4. « Start » : VARA appelle la passerelle ; les messages s'échangent tout seuls.\n", None),
                ("  5. Après « Disconnected », FERMER la fenêtre VARA HF Winlink (elle tient le port de l'IC-705).\n", None),
                ("  6. Ici : étape 3.\n\n", None),
                (
                    "Pendant l'émission, l'indicateur Po de l'IC-705 doit monter. S'il reste à zéro : "
                    "SET › Connectors › MOD Input › DATA MOD = USB, et USB MOD Level ≈ 50 %.",
                    "dim",
                ),
            ],
        )

    # ---- actions
    def _wl_connect(self):
        gw = self._wl_selected()
        if gw is None:
            return
        self.winlink_session_start(gw)
        if not getattr(self, "winlink_session_active", False):
            return
        self._wl_gw_active = gw
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(gw["call"])
        except tk.TclError:
            pass
        state = self._wl_launch_express()
        self.log_event(f"📮 Winlink Express {state} ; indicatif {gw['call']} copié dans le presse-papiers.")
        self._wl_end_lbl.configure(text="")
        self._wl_update_steps()

    def _wl_finish(self):
        self.winlink_session_end()
        new = getattr(self, "_wl_last_new_gribs", [])
        arb = getattr(self, "hybrid_arbiter", None)
        qth = tuple(arb.plan.get("qth", (43.57, 7.0))) if arb else (43.57, 7.0)
        sec = self.winlink_grib_section(qth, 150) if new else None
        if sec:
            msg = f"✅ {len(new)} fichier(s) GRIB reçu(s), ajouté(s) au rapport météo.\n" + "\n".join(sec[1][:6])
        else:
            msg = (
                "Aucun nouveau GRIB. Une réponse Saildocs arrive souvent quelques minutes après la demande : "
                "elle sera récupérée à la prochaine session (ou vérifiée automatiquement toutes les 10 min)."
            )
        self._wl_end_lbl.configure(text=msg + "\n▶️ Réception météo reprise : reconnexion de l'IC-705 en cours.")
        self._wl_update_steps()

    # ---- petites fenêtres
    def _wl_dialog(self, title, w=760, h=520):
        d = tk.Toplevel(self._wl_win if getattr(self, "_wl_win", None) else self.root)
        d.title(title)
        d.configure(bg=BG)
        d.geometry(f"{w}x{h}")
        d.transient(self._wl_win if getattr(self, "_wl_win", None) else self.root)
        d.bind("<Escape>", lambda e: d.destroy())
        return d

    def _wl_show_guide(self):
        d = self._wl_dialog("Premiers pas avec Winlink", 820, 640)
        t = self._wl_text(d, 30)
        t.pack(fill="both", expand=True, padx=10, pady=10)
        self._wl_fill(t, [(GUIDE, None)])

    def _wl_show_install(self):
        d = self._wl_dialog("Vérifier l'installation Winlink / VARA HF", 860, 600)
        cfg = self._wl_cfg()
        top = tk.Frame(d, bg=BG)
        top.pack(fill="x", padx=10, pady=8)
        rms_v = tk.StringVar(master=self.root, value=cfg.get("rms_dir", ""))
        vara_v = tk.StringVar(master=self.root, value=cfg.get("vara_dir", ""))
        for r, (lbl, var) in enumerate(
            (("Dossier Winlink Express (vide = automatique)", rms_v), ("Dossier VARA HF (vide = automatique)", vara_v))
        ):
            tk.Label(top, text=lbl, bg=BG, fg=DIM).grid(row=r, column=0, sticky="w")
            tk.Entry(top, textvariable=var, width=40, bg=PANEL, fg=FG, insertbackground=FG).grid(row=r, column=1, padx=6)
            tk.Button(top, text="Parcourir…", command=lambda v=var: v.set(filedialog.askdirectory(parent=d) or v.get())).grid(
                row=r, column=2
            )
        txt = self._wl_text(d, 22)

        def refresh():
            c = self._wl_cfg()
            c["rms_dir"], c["vara_dir"] = rms_v.get().strip(), vara_v.get().strip()
            self._wl_save_cfg(c)
            info = self.winlink_info()
            parts = [("Diagnostic (lecture seule : rien n'est modifié sur votre PC)\n\n", "amber")]
            for lvl, what, fix in wlx.diagnose(info, cat_port=self.cmb_port.get() if hasattr(self, "cmb_port") else None):
                parts += [(f"[{lvl}] ", lvl), (what + "\n", None)]
                if fix:
                    parts.append((f"        → {fix}\n", "dim"))
            self._wl_fill(txt, parts)
            self._wl_refresh_identity()
            self._wl_refresh_gw()

        tk.Button(top, text="Vérifier", command=refresh, bg="#1d4ed8", fg="white", relief="flat", padx=12).grid(
            row=0, column=3, rowspan=2, padx=10
        )
        txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        refresh()

    def _wl_show_request(self):
        d = self._wl_dialog("Demander une prévision GRIB à Saildocs", 820, 560)
        zone = self.analysis_zone() if hasattr(self, "analysis_zone") else None
        arb = getattr(self, "hybrid_arbiter", None)
        qth = (zone["lat"], zone["lon"]) if zone else tuple(arb.plan.get("qth", (43.57, 7.0))) if arb else (43.57, 7.0)
        box = tk.Frame(d, bg=BG)
        box.pack(fill="x", padx=10, pady=8)
        vars_ = {}
        for c, (key, label, vals, default) in enumerate(
            (
                ("half", "Zone", ("petite (±1,5°)", "moyenne (±2,5°)", "grande (±4°)"), "moyenne (±2,5°)"),
                ("step", "Maille", ("0.5", "1"), "1"),
                ("hours", "Horizon", ("48 h", "72 h", "120 h"), "72 h"),
                ("every", "Pas", ("3 h", "6 h", "12 h"), "6 h"),
            )
        ):
            tk.Label(box, text=label, bg=BG, fg=DIM).grid(row=0, column=2 * c, sticky="w", padx=(0 if c == 0 else 10, 4))
            v = tk.StringVar(master=self.root, value=default)
            cb = ttk.Combobox(box, textvariable=v, values=vals, width=14, state="readonly")
            cb.grid(row=0, column=2 * c + 1)
            vars_[key] = v
        waves = tk.BooleanVar(master=self.root, value=True)
        txt = self._wl_text(d, 14)
        state = {}

        def update(*_):
            half = {"petite (±1,5°)": (1.5, 2.5), "moyenne (±2,5°)": (2.5, 4.0), "grande (±4°)": (4.0, 6.0)}[vars_["half"].get()]
            line, kb = saildocs.build_request(
                qth,
                half_lat=half[0],
                half_lon=half[1],
                step_deg=float(vars_["step"].get()),
                hours=int(vars_["hours"].get().split()[0]),
                every_h=int(vars_["every"].get().split()[0]),
                waves=bool(waves.get()),
            )
            state["line"] = line
            self._wl_req_line = line
            parts = [
                ("Message à créer dans Winlink Express (Message › New Message)\n\n", "amber"),
                (f"À      : {saildocs.SAILDOCS_ADDRESS}\nObjet  : meteo\nTexte  :\n\n", None),
                (f"    {line}\n\n", "amber"),
                (
                    f"Réponse estimée ≈ {kb:.0f} ko, soit ≈ {saildocs.transfer_minutes(kb):.0f} min en VARA HF gratuit.\n",
                    None,
                ),
            ]
            if kb > 25:
                parts.append(("Fichier lourd pour la radio : réduire la zone, la maille ou l'horizon.\n", "ATTENTION"))
            parts.append(
                (
                    "\n« Post to Outbox », puis connexion (étape 2) : la demande part. La réponse arrive à une "
                    "session suivante ; Station WEFAX la lit toute seule et l'ajoute au rapport météo.",
                    "dim",
                )
            )
            self._wl_fill(txt, parts)

        for v in vars_.values():
            v.trace_add("write", update)
        tk.Checkbutton(
            box, text="vagues", variable=waves, command=update, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG
        ).grid(row=0, column=8, padx=10)
        txt.pack(fill="both", expand=True, padx=10)

        def copy():
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(state.get("line", ""))
                self.log_event("📋 Demande Saildocs copiée dans le presse-papiers.")
                btn.configure(text="✅ Copiée — collez-la dans le message Winlink")
            except tk.TclError:
                pass

        btn = tk.Button(d, text="📋  Copier la demande", command=copy, bg="#1d4ed8", fg="white", relief="flat", padx=12, pady=4)
        btn.pack(anchor="w", padx=10, pady=8)
        update()

    def _wl_show_received(self):
        d = self._wl_dialog("Fichiers GRIB reçus par Winlink", 820, 560)
        txt = self._wl_text(d, 24)
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        self.winlink_poll_gribs(quiet=False)
        files = sorted(self.winlink_grib_dir().glob("*.grb"), key=lambda p: p.name, reverse=True)
        arb = getattr(self, "hybrid_arbiter", None)
        qth = tuple(arb.plan.get("qth", (43.57, 7.0))) if arb else (43.57, 7.0)
        sec = self.winlink_grib_section(qth, 150, now=datetime.now(timezone.utc))
        parts = []
        if sec:
            parts += [(sec[0] + "\n", "amber"), ("\n".join(sec[1]) + "\n\n", None)]
        if not files:
            parts.append(("Aucun fichier GRIB reçu pour l'instant.\n", "dim"))
        for p in files[:15]:
            parts.append((f" • {p.name}  ({p.stat().st_size / 1024:.1f} ko)\n", None))
        self._wl_fill(txt, parts)
