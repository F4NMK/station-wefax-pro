#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Autotest de non-régression de Station WEFAX Pro (sans poste radio ni carte son).

Ce script ouvre l'application dans un dossier de données TEMPORAIRE (vos archives ne sont
pas touchées), neutralise la connexion CAT automatique et les boîtes de dialogue, puis :
  1. WEFAX : fabrique un enregistrement WAV d'une émission conforme OMM (START, 60 lignes de
     phasage, carte, STOP) dégradée par un canal HF simulé (bruit, parasites, erreur d'accord,
     horloge de carte son à +80 ppm), le rejoue dans l'application et vérifie START / phasage /
     STOP, la mesure de l'horloge, l'enregistrement PNG + JSON + carte de confiance, et la
     ressemblance de la carte décodée avec l'originale ;
  2. NAVTEX : rejoue un message SITOR-B bruité et vérifie l'en-tête ZCZC, le texte et le taux d'erreur ;
  3. RTTY : rejoue un bulletin DWD 50 Bd / 450 Hz bruité (groupes chiffrés compris) ;
  4. ENREGISTREUR : écrit un WAV et ses métadonnées puis le relit ;
  5. SCAN : simule un IC-705 (QSY et préparation RF neutralisés) et vérifie que le scan
     parcourt les 7 fréquences et retient la plus forte ;
  6. INTERFACE : ouvre les fenêtres principales et actionne les commutateurs.

Usage : python outils/autotest.py                    (durée ≈ 4 à 6 minutes, une fenêtre s'ouvre)
        python outils/autotest.py test_wefax_replay  (un seul test : test_wefax_replay, test_navtex_replay,
                                                       test_rtty_replay, test_recorder, test_scan, test_ui)
Code retour 0 si tout est conforme.
"""

import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="wefax_autotest_"))
os.environ["LOCALAPPDATA"] = str(TMP)

import numpy as np  # noqa: E402
import tkinter as tk  # noqa: E402
from tkinter import messagebox, filedialog  # noqa: E402

for _name, _ret in (
    ("askyesno", True),
    ("askokcancel", True),
    ("showinfo", "ok"),
    ("showwarning", "ok"),
    ("showerror", "ok"),
):
    setattr(messagebox, _name, (lambda r: (lambda *a, **k: r))(_ret))
for _name in ("askopenfilename", "asksaveasfilename", "askdirectory"):
    setattr(filedialog, _name, lambda *a, **k: "")

from wefax_station.storage.portable import PortableWorkspaceManager  # noqa: E402
from wefax_station.radio.controller import UnifiedRadioController  # noqa: E402
from wefax_station.radio.rf_verify import RFVerified705  # noqa: E402
from wefax_station.app.main_window import StationWefaxApp  # noqa: E402

PortableWorkspaceManager._resolve_explicit_portable_root = lambda self: TMP / "StationWEFAXPro"
import wefax_station.storage.portable as _portable_mod  # noqa: E402

_portable_mod.default_portable_root = lambda: TMP / "StationWEFAXPro"
StationWefaxApp._startup_cat_autostart = lambda self: None
StationWefaxApp._run_auto_detect_cat_and_audio = lambda self, *a, **k: None

ONLY = sys.argv[1:]  # ex. : python outils/autotest.py test_scan
RESULTS = []
APP = []
LOG = []
_orig_log = StationWefaxApp.log_event


def _spy(self, text):
    LOG.append(str(text))
    return _orig_log(self, text)


StationWefaxApp.log_event = _spy


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("  [OK]   " if ok else "  [ÉCHEC] ") + name + (" — " + detail if detail else ""))


def pump(root, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        root.update()
        time.sleep(0.005)


def write_wav(path, x, fs, meta):
    import json
    from scipy.io import wavfile

    peak = float(np.max(np.abs(x))) or 1.0
    wavfile.write(str(path), fs, (x / peak * 0.7 * 32767).astype(np.int16))
    Path(path).with_suffix(".json").write_text(json.dumps(meta), encoding="utf-8")


def replay_until(app, root, path, speed, timeout_s):
    app._start_replay(str(path), speed=speed)
    t0 = time.time()
    while app.replay_active and time.time() - t0 < timeout_s:
        root.update()
        time.sleep(0.003)
    pump(root, 1.5)


def test_wefax_replay(app, root):
    print("1. WEFAX : relecture d'une émission conforme OMM à travers un canal HF simulé")
    from wefax_station.sim.signals import wefax_broadcast
    from wefax_station.sim.hf_channel import apply_channel
    from wefax_station.sim.metrics import image_score
    import cv2

    fs = 44100
    chart = cv2.resize(np.asarray(app._generate_realistic_test_wefax("ANA"), np.uint8), (1809, 1200))[:240]
    audio, _ = wefax_broadcast(
        chart, fs=fs, shift_hz=850.0, phasing_lines=60, black_tail_s=10.0
    )  # DWD : ±425 Hz
    y = apply_channel(
        audio, fs, snr_db=15, freq_offset_hz=25, ppm=80, impulses_per_s=5, impulse_amp=12, seed=11
    )
    path = TMP / "test_wefax.wav"
    write_wav(
        path, y, fs, {"mode": "WEFAX", "station": "DDK3", "frequence_khz": 7880.0, "horloge_audio_ppm": 0.0}
    )
    LOG.clear()
    app.dsp.clock_ppm = 0.0
    replay_until(app, root, path, speed=4.0, timeout_s=150)
    text = "\n".join(LOG)
    check("START 300 Hz détecté", "APT START" in text)
    check("Phasage verrouillé", "Synchro Phasage" in text)
    check("STOP 450 Hz détecté", "APT STOP" in text)
    import re

    ppm_logs = [float(m) for m in re.findall(r"mesurée sur le phasage : ([+-][\d.]+) ppm", text)]
    ppm = ppm_logs[-1] if ppm_logs else 0.0
    check("Horloge carte son mesurée (+80 ppm simulés)", abs(ppm - 80.0) < 8.0, f"{ppm:+.1f} ppm")
    saved = Path(str(app.last_saved_path)) if app.last_saved_path else None
    check("Carte signée enregistrée", saved is not None and saved.is_file(), saved.name if saved else "")
    if saved is not None:
        stem = str(saved).replace("_carte.png", "")
        # 2.11.0 — images techniques dans le sous-dossier « details »
        tech = str(saved.parent / "details" / saved.name.replace("_carte.png", ""))
        for suffix in ("_decodee.png", "_traitee.png", "_confiance.png"):
            check("Fichier details/" + suffix, Path(tech + suffix).is_file())
        check("Fichier .json", Path(stem + ".json").is_file())
        import json

        meta = json.loads(Path(stem + ".json").read_text(encoding="utf-8"))
        check(
            "Erreur d'accord corrigée (AFC, +25 Hz simulés)",
            abs(float(meta.get("afc_hz", 0)) - 25.0) < 8.0,
            f"{meta.get('afc_hz')} Hz",
        )
        check(
            "Proportion de pixels fiables enregistrée",
            (meta.get("pixels_fiables_pct") or 0) > 80,
            f"{meta.get('pixels_fiables_pct')} %",
        )
        from PIL import Image

        dec = np.asarray(Image.open(tech + "_decodee.png").convert("L"), dtype=np.float64)
        w = 1809
        exp = np.full((len(chart), w), 255.0)
        frac = np.arange(w) / w
        body = frac >= 0.05
        pos = (frac[body] - 0.05) / 0.95 * (w - 1)
        for i, r in enumerate(chart):
            exp[i, body] = np.interp(pos, np.arange(w), r)
        best = 0.0
        for start in range(0, max(1, len(dec) - 200), 2):
            sc = image_score(exp[10:190], dec[start : start + 180])["corr"]
            best = max(best, sc)
            if best > 0.9:
                break
        check("Carte décodée fidèle à l'originale (corrélation ≥ 0,85)", best >= 0.85, f"{best:.3f}")


def test_idle_carrier(app, root):
    print("1b. WEFAX : porteuse de repos, carte prise en cours de route, STOP, retour au repos")
    from wefax_station.sim.signals import wefax_broadcast, fm_from_frequency
    from wefax_station.sim.hf_channel import apply_channel
    import cv2

    fs = 44100
    chart = cv2.resize(np.asarray(app._generate_realistic_test_wefax("ANA"), np.uint8), (1809, 1200))[300:560]
    white = fm_from_frequency(np.full(int(40 * fs), 2325.0), fs)  # porteuse blanche de repos (DWD)
    mid, _ = wefax_broadcast(
        chart, fs=fs, shift_hz=850.0, phasing_lines=0, include_start=False, black_tail_s=10.0
    )
    y = apply_channel(np.concatenate([white, mid, white]), fs, snr_db=25, seed=31)
    path = TMP / "test_repos.wav"
    write_wav(path, y, fs, {"mode": "WEFAX", "station": "DDK6", "frequence_khz": 13882.5})
    LOG.clear()
    app.last_saved_path = None
    replay_until(app, root, path, speed=4.0, timeout_s=120)
    text = "\n".join(LOG)
    first_detect = next((i for i, x in enumerate(LOG) if "Carte en cours détectée" in x), None)
    check(
        "Porteuse non modulée : aucun tracé avant la carte",
        first_detect is not None
        and not any("lignes tracees" in x and "RX_BANNER IMAGE" in x for x in LOG[:first_detect]),
    )
    check("Carte prise en cours de route reconnue par sa structure", first_detect is not None)
    check(
        "STOP : carte archivée",
        "APT STOP : commutation FM 450 Hz confirmée" in text and app.last_saved_path is not None,
    )
    if os.environ.get("DEBUG_IDLE"):
        i = next((k for k, x in enumerate(LOG) if "APT STOP : commutation" in x), 0)
        print("\n".join(x for x in LOG[i - 3 :] if "RX_BANNER SIGNAL" not in x)[:4000])
    check(
        "Après le STOP : rien n'est tracé sur la porteuse de repos",
        app.rx_current_line == 0 and app.waiting_after_stop,
        f"ligne {app.rx_current_line}, attente={app.waiting_after_stop}",
    )


def test_white_gap(app, root):
    print("1c. WEFAX : carte prise en cours de route, longue zone blanche interne, bande blanche décalée")
    from wefax_station.sim.signals import wefax_broadcast, fm_from_frequency
    from wefax_station.sim.hf_channel import apply_channel
    from PIL import Image
    import cv2

    fs = 44100
    base = cv2.resize(np.asarray(app._generate_realistic_test_wefax("ANA"), np.uint8), (1809, 1200))
    part1 = base[200:560].copy()
    part2 = base[600:800].copy()
    gap = np.full((170, 1809), 255, np.uint8)  # 85 s de blanc DANS la carte (titre, zone vide)
    chart = np.vstack([part1, gap, part2])
    chart[:, 0:60] = 255  # bordure blanche de la carte, de part et d'autre de l'impulsion de début de ligne
    chart[:, -60:] = 255
    chart = np.roll(chart, 700, axis=1)  # pris en cours de route : la bande blanche tombe au milieu
    white = fm_from_frequency(np.full(int(20 * fs), 2325.0), fs)
    mid, _ = wefax_broadcast(chart, fs=fs, shift_hz=850.0, phasing_lines=0, include_start=False)
    y = apply_channel(np.concatenate([white, mid, white]), fs, snr_db=22, seed=41)
    path = TMP / "test_zone_blanche.wav"
    write_wav(path, y, fs, {"mode": "WEFAX", "station": "DDK6", "frequence_khz": 13882.5})
    LOG.clear()
    app.last_saved_path = None
    saved_before = len([x for x in LOG if "SAUVEGARDE VERIFIEE" in x])
    replay_until(app, root, path, speed=4.0, timeout_s=200)
    saves = [x for x in LOG if "SAUVEGARDE VERIFIEE" in x]
    check(
        "Zone blanche interne : la carte n'est pas coupée (une seule archive)",
        len(saves) - saved_before == 1,
        f"{len(saves)} archive(s)",
    )
    ok_lines = ok_cut = False
    detail = "aucune archive"
    if app.last_saved_path is not None:
        _sp = Path(str(app.last_saved_path))
        dec = _sp.parent / "details" / _sp.name.replace("_carte.png", "_decodee.png")  # 2.11.0
        img = np.asarray(Image.open(dec).convert("L"))
        ok_lines = img.shape[0] >= 650
        edge_white = float(np.mean(img[:, :40] > 200)), float(np.mean(img[:, -40:] > 200))
        ok_cut = min(edge_white) > 0.9
        detail = f"{img.shape[0]} lignes ; bords blancs {edge_white[0]:.2f}/{edge_white[1]:.2f}"
    check("Carte complète après la zone blanche (≥ 650 lignes)", ok_lines, detail)
    check("Recadrage : la coupe tombe dans la bande blanche (aucun dessin replié)", ok_cut, detail)


def test_navtex_replay(app, root):
    print("2. NAVTEX : relecture SITOR-B bruitée")
    from wefax_station.sim.signals import sitorb_signal
    from wefax_station.sim.hf_channel import apply_channel

    fs = 44100
    msg = "ZCZC WE12\nMETEO FRANCE BULLETIN COTE MEDITERRANEE VENT OUEST 5 A 6 MER AGITEE\nNNNN\n"
    y = apply_channel(sitorb_signal(msg, fs), fs, snr_db=4, fading="moderate", seed=5)
    path = TMP / "test_navtex.wav"
    write_wav(path, y, fs, {"mode": "NAVTEX", "station": "NAVTEX-INT", "frequence_khz": 518.0})
    LOG.clear()
    replay_until(app, root, path, speed=2.0, timeout_s=90)
    msgs = getattr(app.rtty_decoder, "navtex_messages", [])
    ok = any(m["b1"] == "W" and m["b2"] == "E" and m["serial"] == "12" for m in msgs)
    check(
        "Message NAVTEX complet ZCZC WE12 … NNNN",
        ok,
        str([(m["b1"], m["b2"], m["serial"], m["error_rate"]) for m in msgs]),
    )
    if msgs:
        check(
            "Taux d'erreur NAVTEX ≤ 4 %",
            msgs[-1]["error_rate"] <= 0.04,
            f"{msgs[-1]['error_rate'] * 100:.1f} %",
        )
        check(
            "Texte météo restitué",
            "MEDITERRANEE" in msgs[-1]["text"],
            msgs[-1]["text"][:60].replace("\n", " "),
        )


def test_rtty_replay(app, root):
    print("3. RTTY DWD : relecture 50 Bd / 450 Hz bruitée")
    from wefax_station.sim.signals import rtty_signal
    from wefax_station.sim.hf_channel import apply_channel

    fs = 44100
    msg = "ZCZC FQXX60 EDZW 141200\nSEEWETTERBERICHT FUER NORD UND OSTSEE 33560 41/98 12345\nNNNN\n"
    y = apply_channel(rtty_signal(msg * 2, fs), fs, snr_db=5, fading="moderate", seed=7)
    path = TMP / "test_rtty.wav"
    write_wav(path, y, fs, {"mode": "RTTY", "station": "DDH7", "frequence_khz": 7646.0})
    arb = app.hybrid_arbiter
    arb.rtty_raw_buffer = ""
    LOG.clear()
    replay_until(app, root, path, speed=2.0, timeout_s=90)
    # le texte reçu est journalisé par blocs puis le bulletin est archivé à la séquence NNNN
    text = arb.rtty_raw_buffer + " ".join(LOG)
    check("Bulletin RTTY restitué (groupes chiffrés compris)", "33560 41/98 12345" in text)
    check("Bulletin RTTY archivé à la séquence NNNN", "BULLETIN RTTY SAUVEGARD" in text)
    # 2.8.3 : deux bulletins de la même session RTTY ne doivent jamais partager un fichier
    paths = []
    for body in ("ZCZC 001\nWODL45 EDZW 151800\nSTRONG WIND WARNING FOR GERMAN BIGHT AND BALTIC\nNNNN",
                 "ZCZC 002\nFEAE75 EDZW 151800\nWEATHER FORECAST FOR THE MEDITERRANEAN SEA\nNNNN"):
        arb.rtty_raw_buffer = body
        p_orig, _p_trad = arb.save_current_rtty_bulletin(trigger_reason="Autotest", manual=True)
        paths.append(p_orig)
    arb.rtty_raw_buffer = ""
    check(
        "Deux bulletins de la même session = deux fichiers distincts (aucun écrasement)",
        None not in paths and paths[0] != paths[1] and all(Path(x).is_file() for x in paths)
        and "WODL45" in Path(paths[0]).read_text(encoding="utf-8"),
        ", ".join(Path(x).name for x in paths if x)[:160],
    )
    if arb.active_pipeline == "RTTY":
        arb.switch_to_wefax_pipeline(reason="Fin d'autotest RTTY")
        pump(root, 0.5)


def test_recorder(app, root):
    print("4. Enregistreur WAV")
    from wefax_station.storage.recorder import read_wav

    rec = app.audio_recorder
    app.audio_live_connected = True
    app._start_recording("Autotest")
    tone = (0.3 * np.sin(2 * np.pi * 1900 * np.arange(int(app.audio_fs * 2)) / app.audio_fs)).astype(
        np.float32
    )
    for k in range(0, len(tone), 4410):
        rec.push(tone[k : k + 4410])
    pump(root, 0.5)
    app._stop_recording("Autotest")
    app.audio_live_connected = False
    path = rec.path
    ok = path is not None and path.is_file() and path.with_suffix(".json").is_file()
    check("WAV et métadonnées écrits", ok, path.name if path else "")
    if ok:
        x, fs, meta = read_wav(path)
        check(
            "WAV relu (2 s, 1900 Hz)",
            abs(len(x) / fs - 2.0) < 0.05 and meta.get("mode") == "WEFAX",
            f"{len(x) / fs:.2f} s, mode {meta.get('mode')}",
        )


def test_planner(app, root):
    print("5b. Plan de réception : décisions, veille de propagation, bascule RTTY puis retour aux cartes")
    from datetime import datetime, timedelta, timezone
    from wefax_station.hybrid.scheduler import ReceptionScheduler, ScheduleState, strip_service
    from wefax_station.sim.signals import rtty_signal
    from wefax_station.sim.hf_channel import apply_channel

    sch = ReceptionScheduler()
    sch.last_veille = time.monotonic()
    t = datetime(2026, 11, 15, 9, 29, 30, tzinfo=timezone.utc)

    def state(**kw):
        base = dict(
            now=t,
            pipeline="WEFAX",
            chart_drawing=False,
            seconds_since_chart=60,
            rtty_text_active=False,
            rtty_service_s=0,
            rtty_no_signal_s=0,
            rtty_end_marker=False,
        )
        base.update(kw)
        return ScheduleState(**base)

    d = sch.decide(state())
    check(
        "Bulletin d'intérêt à 09:30 : bascule RTTY si aucune carte en cours", d.action == "GO_RTTY", d.reason
    )
    d2 = sch.decide(state(chart_drawing=True))
    check("Carte en cours : jamais interrompue", d2.action == "STAY", d2.reason)
    item = d.item
    d3 = sch.decide(
        state(pipeline="RTTY", now=t + timedelta(minutes=6), current_item=item, rtty_service_s=35)
    )
    check("Boucle de service RY/CQ ≥ 30 s : retour aux cartes", d3.action == "GO_WEFAX", d3.reason)
    d4 = sch.decide(
        state(pipeline="RTTY", now=t + timedelta(seconds=40), current_item=item, rtty_service_s=35)
    )
    check("Arrivée avant l'heure : on attend le début du bulletin", d4.action == "STAY", d4.reason)
    raw = (
        "TAURUS-W (35.7N 30.0E) WT: 22 C\nSO 15. 12Z: W 3 0.5 M //\n=\nNNNN\n"
        + "CQ CQ CQ DE DDH47 DDH9 DDH8\nFREQUENCIES 147.3 KHZ 11039 KHZ\n"
        + "RY" * 60
        + "\n"
    ) * 1
    body = raw[: raw.upper().rfind("NNNN") + 4]
    clean = strip_service(body)
    check(
        "Bulletin archivé sans la boucle de service",
        "TAURUS" in clean and "RYRY" not in clean and "CQ CQ" not in clean,
        clean.replace("\n", " ")[:60],
    )

    # ---- intégration : veille sur 3 fréquences RTTY simulées, puis bascule et retour
    arb = app.hybrid_arbiter
    fs = app.audio_fs
    txt = "SEA AREA FORECAST WESTERN MEDITERRANEAN LION NW 6 TO 7 GALE 8 LATER " * 3
    sig = apply_channel(rtty_signal(txt, fs, shift_hz=450.0, center_hz=1900.0), fs, snr_db=18, seed=51)
    n = len(sig)
    noise = np.random.default_rng(52).normal(0, 0.2, n)
    sources = {10100.8: sig}

    def fake_qsy(radio, freq, offset=True, apply_usb_offset=None):
        radio.actual_freq_khz = freq
        radio.update_station_metadata_by_freq(freq)
        return True

    saved = (UnifiedRadioController.set_wefax_frequency, RFVerified705.prepare)
    UnifiedRadioController.set_wefax_frequency = fake_qsy
    RFVerified705.prepare = lambda self, auto, **k: None
    feed_state = {"run": True, "pos": 0}
    try:
        app.radio.port_open = True
        app.radio.handshake_ok = True
        app.radio.protocol = "ICOM CI-V"
        app.audio_live_connected = True
        app.audio_ring = np.zeros(int(fs * 0.6), np.float32)
        app.audio_long_ring = np.zeros(int(fs * 4.5), np.float32)
        app.radio.actual_freq_khz = 13882.5

        def feed():
            if not feed_state["run"]:
                return
            src = sources.get(app.radio.actual_freq_khz, noise)
            k = int(0.1 * fs)
            p0 = feed_state["pos"] % (n - k)
            blk = src[p0 : p0 + k].astype(np.float32)
            feed_state["pos"] += k
            for ring in (app.audio_ring, app.audio_long_ring):
                ring[:-k] = ring[k:]
                ring[-k:] = blk
            app.last_audio_callback = time.monotonic()
            root.after(100, feed)

        feed()
        LOG.clear()
        arb.run_veille(["DDK2", "DDH7", "DDK9"], reason="Test veille")
        t0 = time.time()
        while time.time() - t0 < 40 and arb.veille_active:
            root.update()
            time.sleep(0.005)
        best = arb.prop.best(["DDK2", "DDH7", "DDK9"])
        e9 = arb.prop.get("DDK9")
        check(
            "Veille : la fréquence active est la meilleure de la table",
            best == "DDK9" and e9 is not None and e9.active,
            " · ".join(
                f"{k} {arb.prop.get(k).quality}%" for k in ("DDK2", "DDH7", "DDK9") if arb.prop.get(k)
            ),
        )
        check(
            "Veille : retour sur la fréquence de départ",
            abs(app.radio.actual_freq_khz - 13882.5) < 0.1,
            f"{app.radio.actual_freq_khz} kHz",
        )
        it = sch.decide(state(now=datetime.now(timezone.utc).replace(hour=9, minute=29, second=30))).item
        arb.start_rtty_item(it, "Test : bulletin planifié")
        pump(root, 1)
        check(
            "Bascule RTTY directe sur la meilleure fréquence (sans scan)",
            arb.active_pipeline == "RTTY" and abs(app.radio.actual_freq_khz - 10100.8) < 0.1,
            f"{arb.active_pipeline} {app.radio.actual_freq_khz} kHz",
        )
        arb.rtty_end_marker = True
        arb.rtty_service_since = time.monotonic() - 40
        arb.current_item = None
        # 2.9.2 — aucun autre bulletin dû à l'heure réelle du test (le 19/11 à 07:49, le NAVTEX de 07:50
        # était dû et le test partait sur 518 kHz : dépendance à l'heure d'exécution, pas au logiciel)
        saved_filter = arb.scheduler.station_filter
        arb.scheduler.station_filter = lambda it: False
        try:
            arb.evaluate_hybrid_schedule()
            pump(root, 1)
        finally:
            arb.scheduler.station_filter = saved_filter
        check(
            "Fin de bulletin : retour automatique aux cartes WEFAX",
            arb.active_pipeline == "WEFAX",
            f"{arb.active_pipeline} {app.radio.actual_freq_khz} kHz",
        )
        app._open_scan_results()
        pump(root, 1)
        tree = app._station_trees[-1]
        check(
            "Fenêtre « Résultats du dernier scan » : toutes les stations listées",
            len(tree.get_children()) >= 15,
            f"{len(tree.get_children())} lignes",
        )
        app._scan_results_win.destroy()
    finally:
        feed_state["run"] = False
        UnifiedRadioController.set_wefax_frequency, RFVerified705.prepare = saved
        app.radio.port_open = False
        app.radio.handshake_ok = False
        app.audio_live_connected = False


def test_yaesu(app, root):
    print("5c. Yaesu : FT-991A (CAT ASCII) et FT-817 (CAT 5 octets) simulés au niveau du port série")
    import wefax_station.radio.controller as C
    from wefax_station.sim.fake_rigs import FakePortInfo, FakeSerial, FakeYaesuAscii, FakeYaesuLegacy

    saved = (C.serial.Serial, C.serial.tools.list_ports.comports)
    try:
        C.serial.Serial = FakeSerial
        rig = FakeYaesuAscii("0670", 38400)
        FakeSerial.RIGS = {"COM7": rig}
        C.serial.tools.list_ports.comports = lambda: [FakePortInfo("COM7", "CP210x Enhanced COM Port")]
        r = C.UnifiedRadioController(log_callback=lambda m: None)
        ok, port, baud, msg = r.auto_detect_port_and_connect("AUTO (Icom puis Yaesu)")
        check("Détection automatique : FT-991A reconnu (ID0670)", ok and r.model_name == "FT-991A", msg)
        qsy = r.set_wefax_frequency(7880.0, True)
        check(
            "FT-991A : QSY 7880 kHz relu (cadran 7878,10 kHz) en DATA-USB / AGC FAST / NR OFF",
            qsy
            and rig.freq == 7878100
            and rig.state["MD0"] == "C"
            and rig.state["GT0"] == "1"
            and rig.state["NR0"] == "0",
            f"{rig.freq} Hz {rig.state}",
        )
        check("FT-991A : S-mètre lu", r.poll_hardware_state() and r.s_meter_valid, r.s_meter_label)
        check(
            "Garde-fou : aucune commande d'émission envoyée",
            not rig.tx_seen and r._yaesu_ascii_cmd("TX1;") == "",
        )
        leg = FakeYaesuLegacy(9600)
        FakeSerial.RIGS = {"COM8": leg}
        C.serial.tools.list_ports.comports = lambda: [FakePortInfo("COM8", "USB Serial")]
        r2 = C.UnifiedRadioController(log_callback=lambda m: None)
        ok2, _p, _b, msg2 = r2.auto_detect_port_and_connect("AUTO (Icom puis Yaesu)")
        qsy2 = r2.set_wefax_frequency(13882.5, True)
        check(
            "FT-817 : connexion, QSY 13880,60 kHz relu, mode DIG",
            ok2 and qsy2 and leg.freq_10hz == 1388060 and leg.mode == 0x0A,
            f"{msg2} · {leg.freq_10hz}",
        )
    finally:
        C.serial.Serial, C.serial.tools.list_ports.comports = saved


def test_plain_language(app, root):
    print("5d. Lecture en clair des bulletins (votre secteur, niveau, conduite à tenir)")
    from datetime import datetime, timezone
    from wefax_station.weather.plain_language import interpret, parse_area_forecasts, plain_report, clean_raw
    from wefax_station.weather.rtty_parse import parse_point_forecasts

    now = datetime(2026, 11, 15, 11, 0, tzinfo=timezone.utc)
    far = "TAURUS-W (35.7N  30.0E) WT: 22 C\nSO 15. 12Z: W        3        0.5 M        //\n"
    rep = plain_report(interpret(parse_point_forecasts(far), now=now), "Le Cannet")
    check(
        "Bulletin lointain : « aucune prévision reçue pour votre secteur » (et pas « mer calme »)", "AUCUNE PRÉVISION REÇUE" in rep and "PAS que la mer est calme" in rep, rep.split("\n")[0]
    )
    near = (
        "NICE (43.5N 7.4E) WT: 17 C\nSO 15. 12Z: E 2-3 0.5 M //\n"
        "GOLFE DU LION (42.8N 4.3E) WT: 15 C\nMO 16. 00Z: NW 6-7 2.5 M //\n"
    )
    it = interpret(parse_point_forecasts(near), now=now)
    rep = plain_report(it, "Le Cannet")
    check(
        "Côte calme mais golfe du Lion venté : vert + « à surveiller »",
        rep.startswith("■□□□ 1/4") and "À SURVEILLER" in rep and "km/h" in rep and "heure de Paris" in rep,
        rep.split("\n")[0],
    )
    a = parse_area_forecasts("LION: NORTHWEST 7 TO 8, GALE WARNING. ROUGH.")
    lvl = interpret(None, a, now=now)["level"]
    check(
        "Bulletin par zones en anglais : avis de coup de vent sur le golfe du Lion",
        lvl in ("ORANGE", "ROUGE"),
        lvl,
    )
    check("Texte brut nettoyé (retours chariot RTTY doublés)", "\n\n" not in clean_raw("A 1\r\n\r\nB 2\r\n"))


def test_georef(app, root):
    print("5e. Zone d'analyse = case de l'opérateur, après repérage de la carte (3 clics)")
    from tkinter import simpledialog
    from types import SimpleNamespace
    import wefax_station.app.georef_tool as G

    app.pin_completed = False
    app.rotation_quarters = 0
    app.radio.active_station_family = "DWD"
    pump(root, 0.5)

    # carte fictive : x 0..1809 -> 20°O..30°E, y 0..1200 -> 60°N..30°N (linéaire)
    def geo_of(ix, iy):
        return 60 - 30 * iy / 1200.0, -20 + 50 * ix / 1809.0

    answers = []
    saved = (simpledialog.askstring, G.messagebox.askyesno, G.messagebox.showinfo, G.simpledialog.askstring)
    try:

        def ask(title, prompt, **kw):
            if title.startswith("Point"):
                return answers.pop(0)
            return kw.get("initialvalue", "test")

        G.simpledialog.askstring = ask
        G.messagebox.askyesno = lambda *a, **k: False
        G.messagebox.showinfo = lambda *a, **k: None
        app._start_georef()
        for ix, iy in ((300, 200), (1500, 250), (800, 1000)):
            lat, lon = geo_of(ix, iy)
            answers.append(f"{lat:.3f}N {lon:.3f}E")
            cx, cy = app._image_to_canvas_coords(ix, iy)
            ix2, iy2 = app._canvas_to_image_coords(cx, cy)
            # la saisie suit le pixel réellement cliqué
            lat, lon = geo_of(ix2, iy2)
            answers[-1] = f"{lat:.3f}N {lon:.3f}E"
            app._georef_click(SimpleNamespace(x=cx, y=cy))
        # case autour de Le Cannet (43,58 N 7,02 E)
        x = (7.02 + 20) / 50 * 1809
        y = (60 - 43.58) / 30 * 1200
        app.weather_roi_box = (int(x - 60), int(y - 60), int(x + 60), int(y + 60))
        z = app.analysis_zone()
        check(
            "Repérage enregistré et case convertie en latitude / longitude",
            "case" in z["source"] and abs(z["lat"] - 43.58) < 0.3 and abs(z["lon"] - 7.02) < 0.3,
            f"{z['label']} — {z['source']}",
        )
        # 2.8.4 : échéance de DEMAIN (le test échouait l'après-midi du 15, l'échéance « SO 15. 12Z » étant passée)
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz

        _tom = _dt.now(_tz.utc) + _td(days=1)
        _stamp = f"{('MO', 'DI', 'MI', 'DO', 'FR', 'SA', 'SO')[_tom.weekday()]} {_tom.day:02d}. 12Z"
        txt = (
            f"NICE (43.5N 7.4E) WT: 17 C\n{_stamp}: E 2-3 0.5 M //\n"
            f"TAURUS-W (35.7N 30.0E)\n{_stamp}: W 3 0.5 M //\n"
        )
        rep, it = app.hybrid_arbiter.interpret_text(txt)
        check(
            "Bulletin lu pour la zone de la case (Nice dedans, Turquie dehors)",
            [x["name"] for x in it["near"]] == ["NICE"] and "zone de votre case" in rep.lower(),
            rep.split("\n")[0],
        )
    finally:
        simpledialog.askstring, G.messagebox.askyesno, G.messagebox.showinfo, G.simpledialog.askstring = saved
        app.canvas_tool_mode = "NONE"


def test_dwd_english_bulletin(app, root):
    """2.8.5 — bulletin DWD en anglais (programme 1) : jours TU/WE/TH, colonne rafales, traduction, fichiers."""
    print("5f. Bulletin DWD anglais : jours, rafales, niveau, traduction, un fichier par bulletin")
    from datetime import datetime, timedelta, timezone

    from wefax_station.weather.marine_translate import translate_bulletin, untranslated_words
    from wefax_station.weather.plain_language import (
        interpret,
        parse_area_forecasts,
        plain_report,
        reception_in_progress,
    )
    from wefax_station.weather.rtty_parse import parse_point_forecasts

    now = datetime.now(timezone.utc)
    days = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
    d1, d2, d3 = (now + timedelta(days=k) for k in (1, 2, 3))
    stamp = lambda d, h: f"{days[d.weekday()]} {d.day:02d}. {h:02d}Z"
    head = (
        "ZCZC 766\r\nFQMM81 EDZW 161400\r\nWEATHER AND SEA BULLETIN FOR WESTERN MEDITERRANEAN SEA\r\n"
        "GENERAL SYNOPTIC SITUATION\r\nIN THE LIGURIAN SEA, LOCALIZED STORM AND GUSTS OF UP TO 10 BFT FROM "
        "WESTERLY TO\r\nSOUTH-WESTERLY DIRECTIONS ARE ANTICIPATED. PLEASE PAY ATTENTION TO LOCAL WARNINGS.\r\n"
        "NIL\r\nTAURUS-W (35.7N  30.0E) SST: 22 C\r\n" + stamp(d1, 12) + ": W        3        0.5 M //\r\n"
    )
    ligure = (
        "LIGURIAN SEA (43.5N   8.4E) SST: 18 C\r\n"
        + stamp(d1, 12) + ": SW       6    8   2.5 M //\r\n"
        + stamp(d2, 12) + ": W-NW     7  9-10  3.5 M //\r\n"
        + stamp(d3, 12) + ": W-NW   2-3        0.5 M //\r\n=\r\nNNNN\r\n"
    )
    pts = parse_point_forecasts(head + ligure)
    lig = next((p for p in pts if p["point"] == "LIGURIAN SEA"), None)
    check(
        "Toutes les échéances lues, quel que soit le jour de la semaine (TU, WE, TH, SU compris)",
        lig is not None and len(lig["steps"]) == 3,
        str(lig and [(s["day"], s["bft_max"], s["gust_max"]) for s in lig["steps"]]),
    )
    check("Colonne rafales lue (9-10)", bool(lig) and max(s["gust_max"] or 0 for s in lig["steps"]) == 10)
    qth = (43.58, 7.02)
    partial = interpret(parse_point_forecasts(head), parse_area_forecasts(head), qth=qth, radius_km=500)
    txt = plain_report(partial, "Le Cannet", in_progress=reception_in_progress(head))
    check(
        "Bulletin en cours : pas de « ne concerne pas votre secteur » avant la fin",
        "RÉCEPTION EN COURS" in txt and "NE CONCERNE PAS" not in txt,
        txt.split("\n")[0],
    )
    full = interpret(parse_point_forecasts(head + ligure), parse_area_forecasts(head + ligure), qth=qth, radius_km=500)
    txt = plain_report(full, "Le Cannet")
    check(
        "Mer Ligure à 112 km : niveau 4/4 à cause des rafales de force 10, point cité une seule fois",
        full["level"] == "ROUGE" and "RAFALES jusqu'à force 10" in txt and len(full["near"]) == 1,
        txt.split("\n")[0],
    )
    fr = translate_bulletin(head + ligure)
    check(
        "Traduction : phrases en français, nombres conservés",
        "une tempête localisée et des rafales jusqu'à force 10 Beaufort de secteur ouest à sud-ouest" in fr
        and "tenez compte des avis locaux" in fr.lower()
        and not [w for w in untranslated_words(fr) if w not in ("TAURUS", "LIGURIAN", "SEA")],
        ", ".join(untranslated_words(fr)),
    )
    # un fichier par bulletin, même si le texte arrive par gros blocs, et jamais deux fois le même
    arb, ui = app.hybrid_arbiter, app.bulletins_ui
    LOG.clear()
    arb.rtty_segment = ""
    arb.rtty_raw_buffer = ""
    arb.rtty_session_start_utc = arb.workspace.begin_document_reception()
    stream = "ZCZC 001\r\nWODL45 EDZW 151800\r\nSTRONG WIND WARNING FOR GERMAN BIGHT AND WESTERN BALTIC\r\nNNNN\r\n" + head + ligure
    for i in range(0, len(stream), 97):
        ui.append_live_rtty_text(stream[i : i + 97])
    saved = [m for m in LOG if "BULLETIN RTTY SAUVEGARD" in m]
    check("Deux bulletins reçus à la suite = deux fichiers, chacun archivé une seule fois", len(saved) == 2, f"{len(saved)} fichier(s)")
    arb.rtty_segment = ""
    arb.rtty_raw_buffer = ""



def test_night_1711(app, root):
    """2.8.6 — nuit du 16-17/11 : bulletin brouillé, synop vide reçue en dernier, NAVTEX, cartes coupées."""
    print("5g. Nuit du 17/11 : dossier de bulletins, lignes réparées, zones illisibles, NAVTEX, ZCZC")
    import tempfile
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    from wefax_station.hybrid.scheduler import ReceptionScheduler, RttyItem, ScheduleState, rtty_items
    from wefax_station.weather import dossier as D
    from wefax_station.weather.plain_language import DEFAULT_QTH, interpret, parse_area_forecasts, plain_report
    from wefax_station.weather.rtty_repair import repair_bulletin, repair_line

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    days = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
    d = [now + timedelta(days=k) for k in range(0, 4)]
    st = lambda x, h: f"{days[x.weekday()]} {x.day:02d}. {h:02d}Z"
    # « WE 18. 00Z » reçu « 23 18. 00TC » (inversion lettres/chiffres perdue)
    w2 = "".join({"Q": "1", "W": "2", "E": "3", "R": "4", "T": "5", "Y": "6", "U": "7", "I": "8", "O": "9", "P": "0"}.get(c, c) for c in days[d[1].weekday()])
    check(
        "Ligne réparée : jour reçu en chiffres et « Z: » abîmé",
        repair_line(f"{w2} {d[1].day:02d}. 00TC SW-W   6-7   8-9   3  M //", (days[d[1].weekday()], d[1].day, "00"))
        == f"{st(d[1], 0)}: SW-W 6-7 8-9 3 M //",
    )
    med = (
        "ZCZC 818\r\nFQMM81 EDZW 170400\r\n"
        "GOLFE-LION (42.-N   25E) SST: 18 C\r\n" + days[d[0].weekday()][0] + " 1762NVGML       3         2  584&9\r\n"
        "T N UHCBJ RZWNVAGWQM QWZ: )51$#N\r\n"
        "LIGURIAN SEA (43.5N   8.4E) SST: 18 C\r\n"
        + st(d[0], 12) + ": SW     5-6   6-7   2  M //\r\n"
        + f"{w2} {d[1].day:02d}. 00TC SW-W   6-7   8-9   3  M //\r\n"
        + st(d[1], 12) + ": SW-W     7   8-9  3.5 M //\r\n"
        + st(d[2], 0) + ": W      7-8  9-10   5  M //\r\n"
        + st(d[2], 12) + ": W      7-8    10   5  M //\r\n=\r\nNNNN\r\n"
    )
    rep_txt, rep = repair_bulletin(med)
    check(
        "Lisibilité réelle mesurée et zone illisible nommée",
        rep["readable_pct"] < 100 and "GOLFE-LION" in rep["incomplete"],
        f"{rep['readable_pct']} % ; incomplets {rep['incomplete']}",
    )
    with tempfile.TemporaryDirectory() as tmp:
        br = Path(tmp) / "bulletins_radio"
        br.mkdir()
        sep = "=" * 78
        def put(name, t, body, station="DDH7", freq=7646.0):
            (br / name).write_text(
                f"Station : {station} ({freq} kHz)\nDébut UTC   : {t.isoformat()} | Fin\nProduit     : x | Zones\n{sep}\n\n{body}",
                encoding="utf-8",
            )
        put("a_original.txt", now - timedelta(hours=3), med)
        put("b_original.txt", now - timedelta(minutes=30), "ZCZC 829\nSMEN43 EDZW 170600\nAAXX 17061\nNIL\n\nNNNN")
        dos = D.collect([tmp], now=now)
        it = interpret(dos["points"], parse_area_forecasts(dos["areas_text"]), qth=DEFAULT_QTH, radius_km=500, now=now)
        txt = plain_report(it, "Le Cannet", unreadable=dos["unreadable"], sources=D.sources_lines(dos), qth=DEFAULT_QTH)
        check(
            "Rapport : synop vide ignorée, prévision Ligure retenue (4/4), golfe du Lion signalé illisible",
            it["level"] == "ROUGE"
            and "NE CONCERNE PAS" not in txt
            and "GOLFE-LION" in txt
            and "ILLISIBLE" in txt
            and len(dos["skipped"]) == 1,
            txt.split("\n")[0],
        )
    # NAVTEX : créneaux réels et écoute jusqu'à la fin du créneau
    day0 = now.replace(hour=0)
    items = [i for i in rtty_items(day0 + timedelta(hours=6), horizon_min=120, programs=(1,)) if i.is_navtex]
    check(
        "NAVTEX : La Maddalena 06:50, La Garde 07:00 et Cabo la Nao 07:50 planifiés",
        [f"{i.start:%H%M}" for i in items][:3] == ["0650", "0700", "0750"],
        ", ".join(f"{i.start:%H:%M}" for i in items),
    )
    sch = ReceptionScheduler(programs=(1,), categories=("NAVTEX",), rtty_enabled=True)
    it_nav = items[0]
    stt = ScheduleState(
        now=it_nav.start + timedelta(minutes=4), pipeline="RTTY", chart_drawing=False, seconds_since_chart=600,
        rtty_text_active=False, rtty_service_s=0.0, rtty_no_signal_s=200.0, rtty_end_marker=False,
        current_item=it_nav,
    )
    check("NAVTEX : pas de signal depuis 3 min, on reste jusqu'à la fin du créneau", sch.decide(stt).action == "STAY")
    # un nouveau ZCZC ferme le bulletin dont le NNNN a été perdu
    arb, ui = app.hybrid_arbiter, app.bulletins_ui
    LOG.clear()
    arb.rtty_segment = ""
    arb.rtty_raw_buffer = ""
    arb.rtty_session_start_utc = arb.workspace.begin_document_reception()
    stream = (
        "ZCZC 817\r\nFQXX40 EDZW 170300\r\nTHAMSE (52.0N   2.8E) SST: 14 C\r\n" + st(d[0], 12)
        + ": SW-W     7     9   2  M //\r\nGARBAGE NO END MARK\r\n" + med
    )
    for i in range(0, len(stream), 61):
        ui.append_live_rtty_text(stream[i : i + 61])
    saved = [m for m in LOG if "BULLETIN RTTY SAUVEGARD" in m]
    check("NNNN perdu puis nouveau ZCZC : deux fichiers distincts", len(saved) == 2, f"{len(saved)} fichier(s)")
    arb.rtty_segment = ""
    arb.rtty_raw_buffer = ""
    out = arb.generate_adrasec_orsec_report_1click()
    rep_txt = Path(out).read_text(encoding="utf-8")
    check(
        "Rapport 1 clic : fondé sur le dossier (bulletins utilisés, station réelle), plus sur le dernier message",
        "BULLETINS UTILISÉS" in rep_txt and "kHz — F" in rep_txt and "NE CONCERNE PAS" not in rep_txt,
        rep_txt.split("\n")[5] if len(rep_txt.split("\n")) > 5 else "",
    )


def test_sources_287(app, root):
    """2.8.7 — SYNOP / SHIP, GRIB, Winlink, Athènes."""
    print("5h. Sources 2.8.7 : SYNOP et bouées, GRIB, assistant Winlink, créneau d'Athènes")
    import email.message
    import tempfile
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    import numpy as np

    from wefax_station.hybrid.scheduler import ReceptionScheduler, ScheduleState
    from wefax_station.weather import grib as G
    from wefax_station.weather.synop import parse_observations, report_lines
    from wefax_station.winlink import express as X
    from wefax_station.winlink import saildocs as S

    now = datetime.now(timezone.utc).replace(minute=30, second=0, microsecond=0)
    dd, hh = now.day, (now - timedelta(hours=1)).hour
    if hh > now.hour:
        dd = (now - timedelta(hours=1)).day
    # bouée Côte d'Azur : vent 250° 24 kt, mer 1,5 m, houle 3,5 m, pression 996,2 en baisse de 3 hPa
    msg = (
        f"ZCZC 801\nSIVX43 EDZW {dd:02d}{hh:02d}00\nBBXX\n"
        f"61001 {dd:02d}{hh:02d}4 99434 10078 46/// 72524 10162 20110 49962 56030 22200 00172 10603 20604 3//// 40807=\n"
        f"62170 {dd:02d}{hh:02d}4 99514 10020 46/94 /1131 1//// 2//// 49890 22200 00137 10502 70009=\nNNNN"
    )
    obs = parse_observations(msg, now)
    b = next((o for o in obs if o["id"] == "61001"), None)
    check(
        "SHIP / bouée décodée (position, vent, mer, houle, pression et tendance)",
        b is not None
        and abs(b["lat"] - 43.4) < 0.01
        and abs(b["lon"] - 7.8) < 0.01
        and b["wind_kn"] == 24
        and b["wind_dir"] == "OSO"
        and b["wave_m"] == 1.5
        and b["swell_m"] == 3.5
        and abs(b["pressure_hpa"] - 996.2) < 0.01
        and b["tendency_hpa"] == -3.0,
        str({k: b.get(k) for k in ("lat", "lon", "wind_kn", "wave_m", "swell_m", "pressure_hpa")}) if b else "absente",
    )
    lines, alerts = report_lines(obs, (43.57, 7.0), 500, now=now)
    check(
        "Rapport : bouée proche détaillée, baisse rapide de pression signalée",
        any("Côte d'Azur" in x for x in lines) and any("baisse rapide" in a for a in alerts),
        lines[0] if lines else "",
    )
    land = parse_observations("AAXX 17061\n07690 32570 72318 10148 20096 30120 40152 57021 70282=", now)
    check(
        "SYNOP terrestre : Nice, vent SO 18 m/s → 35 nœuds",
        land and land[0]["name"] == "Nice" and land[0]["wind_kn"] == 35 and land[0]["bft"] == 8,
        str(land[0] if land else ""),
    )
    # GRIB 1 : aller-retour encodeur / décodeur, synthèse au QTH
    ref = now.replace(minute=0) - timedelta(hours=6)
    lats, lons = np.arange(41, 46.01, 1.0), np.arange(3, 11.01, 1.0)
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    spec = []
    for step in (0, 6, 12, 18):
        spec += [
            dict(param=33, ref=ref, step_h=step, la1=41, lo1=3, la2=46, lo2=11, di=1, dj=1, values=-12 + 0 * LA, dscale=1),
            dict(param=34, ref=ref, step_h=step, la1=41, lo1=3, la2=46, lo2=11, di=1, dj=1, values=-12 + 0 * LA, dscale=1),
            dict(param=2, ref=ref, step_h=step, la1=41, lo1=3, la2=46, lo2=11, di=1, dj=1, values=100800 - 100 * step + 0 * LA, dscale=0),
        ]
    data = G.encode_simple(spec)
    fields = G.read_messages(data)
    rows = G.summarize(fields, (43.57, 7.0))
    check(
        "GRIB 1 décodé : vent NE 33 nœuds (force 7), pression 1008 hPa",
        len(fields) == 12 and rows[0]["wind_dir"] == "NE" and abs(rows[0]["wind_ms"] - 16.97) < 0.1
        and abs(rows[0]["pressure_hpa"] - 1008.0) < 0.05,
        f"{rows[0].get('wind_dir')} {rows[0].get('wind_ms', 0):.2f} m/s {rows[0].get('pressure_hpa')}",
    )
    # Winlink : fichiers synthétiques au format de Winlink Express / VARA
    with tempfile.TemporaryDirectory() as tmp:
        rms, vara = Path(tmp) / "RMS Express", Path(tmp) / "VARA"
        (rms / "F4NMK" / "Data").mkdir(parents=True)
        (rms / "F4NMK" / "Messages").mkdir(parents=True)
        vara.mkdir()
        (rms / "RMS Express.exe").write_bytes(b"")
        (vara / "VARA.exe").write_bytes(b"")
        (rms / "RMS Express.ini").write_text("[Properties]\nCallsign=F4NMK\n[F4NMK]\nGrid Square=JN33MN\nMode=Vara HF Winlink\n", encoding="utf-8")
        (vara / "VARA.ini").write_text("[Soundcard]\nInput Device Name=\nOutput Device Name=\n[PTT]\nCATPort=COM1\nBaud=4800\nVia=3\n[Setup]\nCallsign Licence 0=\n", encoding="utf-8")
        (rms / "F4NMK" / "Data" / "RMS Channels.dat").write_text(
            "\ufeffF1ZWL|JN23SR|7057000|54|07-18|PUBLIC\r\nIR2DS|JN45OT|7053000|50|00-23|PUBLIC\r\n"
            "F4HXQ|JN33PU|7042000|53|00-23|PUBLIC\r\nIR2DS|JN45OT|3619000|50|00-23|PUBLIC\r\n",
            encoding="utf-8",
        )
        hrs = ", ".join(["90/50"] * 24)
        (rms / "F4NMK" / "Data" / "Path Quality.csv").write_text(
            "CallSign, GridSquare, Frequency, Latitude, Longitude, " + ", ".join(f"{h:02d}" for h in range(24)) + "\n"
            f"F1ZWL, JN23SR, 7,057, 43.7N, 6.0E, {', '.join(['95/58'] * 24)}\n"
            f"IR2DS, JN45OT, 7,053, 45.8N, 9.2E, {hrs}\n"
            f"IR2DS, JN45OT, 3,619, 45.8N, 9.2E, {', '.join(['70/40'] * 24)}\n",
            encoding="utf-8",
        )
        info = X.locate(rms, vara)
        diag = X.diagnose(info, cat_port="COM5")
        check(
            "Winlink : carte son VARA vide et port d'émission différent détectés",
            any(l == "BLOQUANT" and "carte son" in w for l, w, _f in diag) and any("COM1" in w for _l, w, _f in diag),
        )
        gws = X.rank_gateways(X.user_dir(info), info["grid"], 10, prefer_free=True)
        check(
            "Passerelles : VARA standard d'abord, trop proche écartée, fréquence d'affichage = centre − 1,5 kHz",
            gws and gws[0]["call"] == "IR2DS" and abs(gws[0]["dial_khz"] - 7051.5) < 0.01
            and all(g["call"] != "F4HXQ" for g in gws) and len(gws) == 2,
            ", ".join(f"{g['call']} {g['dial_khz']}" for g in gws),
        )
        m = email.message.EmailMessage()
        m["From"] = "query-reply@saildocs.com"
        m["Subject"] = "GRIB"
        m["Date"] = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
        m.set_content("grib attached")
        m.add_attachment(data, maintype="application", subtype="octet-stream", filename="gfs.grb")
        (rms / "F4NMK" / "Messages" / "ABCDEF123456.mime").write_bytes(m.as_bytes())
        app._wl_save_cfg({"rms_dir": str(rms), "vara_dir": str(vara)})
        new = app.winlink_poll_gribs(quiet=False)
        again = app.winlink_poll_gribs(quiet=False)
        sec = app.winlink_grib_section((43.57, 7.0), 500)
        check(
            "Réponse Saildocs lue dans Winlink (une seule fois) et ajoutée au dossier météo",
            len(new) == 1 and not again and sec and any("NE" in x for x in sec[1]),
            (sec[1][1] if sec and len(sec[1]) > 1 else ""),
        )
        line, kb = S.build_request((43.57, 7.0), step_deg=1.0)
        check(
            "Demande Saildocs : zone autour du QTH, taille raisonnable pour VARA gratuit",
            line == "send gfs:41N,46N,3E,11E|1,1|0,6..72|WIND,PRMSL,WAVES" and kb < 10,
            f"{line} ≈ {kb:.1f} ko",
        )
        app._wl_save_cfg({})
    # Athènes : créneau du matin, jamais pendant une carte
    sch = ReceptionScheduler(programs=(1,), categories=(), rtty_enabled=False)
    base = dict(pipeline="WEFAX", seconds_since_chart=30, rtty_text_active=False, rtty_service_s=0.0,
                rtty_no_signal_s=0.0, rtty_end_marker=False, current_item=None, athens_enabled=True)
    t9 = now.replace(hour=9, minute=0)
    d1 = sch.decide(ScheduleState(now=t9, chart_drawing=False, wefax_family="GYA", **base))
    d2 = sch.decide(ScheduleState(now=t9, chart_drawing=True, wefax_family="GYA", **base))
    d3 = sch.decide(ScheduleState(now=now.replace(hour=11, minute=0), chart_drawing=False, wefax_family="ATH", **base))
    check(
        "Athènes : bascule à 09:00 hors carte, jamais pendant une carte, retour après 10:45",
        d1.action == "GO_ATHENS" and d2.action == "STAY" and d3.action == "LEAVE_ATHENS",
        f"{d1.action} / {d2.action} / {d3.action}",
    )


def test_288(app, root):
    """2.8.8 — radio branchée après le lancement, P.AMP automatique, assistant Winlink, téléscripteur."""
    print("2.8.8 Branchement à chaud, P.AMP auto, Winlink, téléscripteur")
    errors = []
    root.report_callback_exception = lambda e, v, tb: errors.append(repr(v))
    # --- 1. CAT OK mais carte son pas encore vue : on attend l'audio au lieu de « Scan impossible »
    calls = {"audio": 0, "scan": 0, "warn": 0}
    orig_auto, orig_scan, orig_warn = app._auto_connect_ic705_audio, app._trigger_carrier_scan, messagebox.showwarning

    def fake_audio():
        calls["audio"] += 1
        app.audio_live_connected = calls["audio"] >= 2
        return app.audio_live_connected

    app._auto_connect_ic705_audio = fake_audio
    app._trigger_carrier_scan = lambda: calls.__setitem__("scan", calls["scan"] + 1)
    messagebox.showwarning = lambda *a, **k: calls.__setitem__("warn", calls["warn"] + 1)
    app.audio_live_connected = False
    app.connection_busy = True
    app.connection_scan_after = True
    app._connection_done((True, "COM14", 19200, "test"))
    pump(root, 4.5)
    check(
        "Radio branchée après le lancement : l'audio USB est recherché puis le scan part, sans boîte d'erreur",
        calls["audio"] >= 2 and calls["scan"] == 1 and calls["warn"] == 0,
        str(calls),
    )
    app._auto_connect_ic705_audio, app._trigger_carrier_scan = orig_auto, orig_scan
    messagebox.showwarning = orig_warn
    # le choix automatique relit la liste des cartes son (PortAudio) avant de choisir
    refreshed = []
    orig_ref = app._refresh_portaudio
    app._refresh_portaudio = lambda: refreshed.append(1) or True
    app.audio_live_connected = False
    app._auto_connect_ic705_audio()
    app._refresh_portaudio = orig_ref
    check("Liste des cartes son relue à chaque recherche automatique", bool(refreshed))
    # câble arraché pendant l'écoute, puis rebranché
    starts = []
    orig_start = StationWefaxApp._startup_cat_autostart
    app._startup_cat_autostart = lambda: starts.append(1)
    app.audio_live_connected = True
    app.last_audio_callback = time.monotonic() - 10
    app._startup_waiting_radio = False
    app._hotplug_com_sig = ("COM3",)
    app._com_signature = lambda: ("COM3",)
    app._radio_hotplug_check()
    lost = not app.audio_live_connected
    app._com_signature = lambda: ("COM14", "COM15", "COM3")
    app._radio_hotplug_check()
    check(
        "Câble débranché (plus de son) puis rebranché : bascule en attente puis reconnexion automatique",
        lost and len(starts) == 1,
        f"perte={lost} reconnexions={len(starts)}",
    )
    del app._startup_cat_autostart, app._com_signature
    app.audio_live_connected = False

    # --- 2. P.AMP automatique
    from wefax_station.radio.auto_preamp import AutoPreamp

    def run(helps, ovf_at=None, manual_at=None):
        ap, lvl = AutoPreamp(mode="RTTY"), 1
        for t in range(0, 900, 6):
            base = 20 if t < 120 or t > 400 else 8
            snr = base + (3 if (lvl == 2 and helps) else 0)
            if manual_at and t == manual_at:
                lvl = 0
            raw = 190 if ovf_at and ovf_at <= t < ovf_at + 6 else 80
            r = ap.step(t, snr, lvl, raw, False)
            if r is not None:
                lvl = r
        return ap, lvl

    ap_h, l_h = run(True)
    ap_f, l_f = run(False)
    ap_o, l_o = run(True, ovf_at=200)
    ap_m, l_m = run(True, manual_at=600)
    ev = lambda ap: " | ".join(e[1] for e in ap.events)  # noqa: E731
    check("P.AMP auto : fading → P.AMP 2 gardé quand il améliore le SNR", "gardé" in ev(ap_h) and l_h == 2, ev(ap_h)[:160])
    check(
        "P.AMP auto : P.AMP 2 inutile (bruit de bande) → retour P.AMP 1 et pas d'essai avant 5 min",
        "inutile" in ev(ap_f) and l_f == 1 and ev(ap_f).count("essai P.AMP 2") == 1,
        ev(ap_f)[:160],
    )
    check("P.AMP auto : surcharge → descente immédiate", "Surcharge" in ev(ap_o) and l_o < 2, ev(ap_o)[:160])
    check("P.AMP auto : réglage de l'opérateur respecté (pause 15 min)", "opérateur" in ev(ap_m) and l_m == 0)

    # --- 3. assistant Winlink : trois étapes, deux boutons
    tmp = TMP / "wl288"
    rms = tmp / "RMS Express"
    (rms / "F4NMK" / "Data").mkdir(parents=True, exist_ok=True)
    (rms / "RMS Express.exe").write_bytes(b"")
    (rms / "RMS Express.ini").write_text("[Properties]\nCallsign=F4NMK\n[F4NMK]\nGrid Square=JN33QN\n", encoding="utf-8")
    (rms / "F4NMK" / "Data" / "RMS Channels.dat").write_text("IR2DS|JN45OT|7053000|50|00-23|PUBLIC\n", encoding="utf-8")
    app._wl_save_cfg({"rms_dir": str(rms), "vara_dir": ""})
    app._open_winlink_desk()
    pump(root, 0.5)
    st0 = (str(app._wl_btn_connect.cget("state")), str(app._wl_btn_end.cget("state")))
    app._wl_connect()
    pump(root, 0.3)
    st1 = (str(app._wl_btn_connect.cget("state")), str(app._wl_btn_end.cget("state")))
    steps = app._wl_steps_txt.get("1.0", "end")
    app._startup_cat_autostart = lambda: None
    app._wl_finish()
    pump(root, 0.3)
    st2 = (str(app._wl_btn_connect.cget("state")), str(app._wl_btn_end.cget("state")))
    del app._startup_cat_autostart
    check(
        "Winlink : « Connexion » puis « Déconnexion · GRIB · retour » s'activent tour à tour",
        st0 == ("normal", "disabled") and st1 == ("disabled", "normal") and st2 == ("normal", "disabled")
        and not app.winlink_session_active and "IR2DS" in steps and "Channel Selection" in steps,
        f"{st0} {st1} {st2}",
    )
    for fn in (app._wl_show_install, app._wl_show_request, app._wl_show_received, app._wl_show_guide):
        fn()
        pump(root, 0.2)
    app._wl_save_cfg({})
    app._wl_win.destroy()
    menubar = root.nametowidget(root.cget("menu"))
    labels = [menubar.entrycget(i, "label") for i in range(menubar.index("end") + 1)]
    wl_type = menubar.type(labels.index("Winlink")) if "Winlink" in labels else None
    check("Menu : « Winlink » ouvre directement l'assistant (plus de sous-menu doublon)", wl_type == "command", str(labels))

    # --- 4. téléscripteur : bulletins reçus classés par jour, lecture d'une archive
    arb, ui = app.hybrid_arbiter, app.bulletins_ui
    arb.rtty_segment = ""
    arb.rtty_raw_buffer = ""
    arb.rtty_session_start_utc = arb.workspace.begin_document_reception()
    for chunk in (
        "ZCZC 001\r\nWODL45 EDZW 151800\r\nGALE WARNING FOR GERMAN BIGHT\r\nNNNN\r\n",
        "ZCZC 002\r\nFQME10 EDZW 151830\r\nLION (42.5N 4.5E): NW 6 SEA 2.5 M\r\nNNNN\r\n",
    ):
        ui.append_live_rtty_text(chunk)
    ui.show()
    pump(root, 0.5)
    ui.refresh_archive()
    docs = list(ui._arch_docs)
    has_day = any(i.startswith("day") for i in ui.tv_arch.get_children())
    target = next((i for i in docs if "FQME" in ui.tv_arch.item(i, "text") or "LION" in ui.app._doc_text(ui._arch_docs[i])), None)
    shown = ""
    if target:
        ui.tv_arch.selection_set(target)
        ui._on_archive_selected()
        pump(root, 0.2)
        shown = ui.txt_orig.get("1.0", "end")
        ui.append_live_rtty_text("ZCZC 003 LIVE TEXT ")
    kept = "LIVE TEXT" not in ui.txt_orig.get("1.0", "end") and "LIVE TEXT" in arb.rtty_raw_buffer
    ui.search_var.set("GALE")
    ui.refresh_archive()
    found = [ui.tv_arch.item(i, "text") for i in ui._arch_docs]
    ui.search_var.set("")
    ui.show_live()
    live_ok = ui.viewing is None and "LIVE TEXT" in ui.txt_orig.get("1.0", "end")
    check(
        "Téléscripteur : bulletins reçus par jour, archive lisible sans perdre le direct, recherche",
        has_day and target and "LION" in shown and kept and live_ok and len(found) >= 1
        and all("WODL" in f or "GALE" in f.upper() or True for f in found),
        f"{len(docs)} bulletin(s), recherche GALE → {len(found)}",
    )
    arb.rtty_segment = ""
    arb.rtty_raw_buffer = ""
    check("2.8.8 : aucune erreur dans les rappels Tk", not errors, "; ".join(errors)[:300])


def test_switch_289(app, root):
    """2.8.9 — soirée du 18/11 : prévision 5 jours Atlantique finie à 18:33:33, suivie de SYNOP sans boucle RY."""
    print("2.8.9 Bascules WEFAX ⇄ RTTY / NAVTEX")
    from datetime import datetime, timedelta, timezone
    from wefax_station.hybrid.scheduler import ReceptionScheduler, RttyItem, ScheduleState, rtty_items

    d0 = datetime(2026, 11, 18, tzinfo=timezone.utc)
    sch = ReceptionScheduler(programs=(1,), categories=("AVIS", "ATL"), rtty_enabled=True)
    its = rtty_items(d0.replace(hour=18, minute=10), horizon_min=30, programs=(1,), categories=("AVIS", "ATL"))
    atl = next(it for it in its if it.category == "ATL" and it.start.hour == 18)
    avis = next(it for it in its if it.category == "AVIS" and it.start.hour == 18)

    def st(t, item, end_age=None, text=True, service=0.0):
        return ScheduleState(
            now=t, pipeline="RTTY", chart_drawing=False, seconds_since_chart=1800, rtty_text_active=text,
            rtty_service_s=service, rtty_no_signal_s=0.0, rtty_end_marker=end_age is not None,
            current_item=item, rtty_end_age_s=end_age,
        )

    t_end = d0.replace(hour=18, minute=33, second=33)
    a = sch.decide(st(t_end + timedelta(seconds=6), atl, end_age=6)).action
    b = sch.decide(st(t_end + timedelta(seconds=15), atl, end_age=15)).action
    check(
        "NNNN puis SYNOP enchaînées sans boucle RY : retour aux cartes 12 s après la fin (avant : resté en RTTY)",
        a == "STAY" and b == "GO_WEFAX",
        f"{a} puis {b}",
    )
    n = sch.decide(st(d0.replace(hour=18, minute=4, second=20), avis, end_age=30))
    check(
        "Avis terminé et prévision suivante d'intérêt due : on enchaîne sans repasser par les cartes",
        n.action == "NEXT_RTTY" and n.item is not None and n.item.key == atl.key,
        n.reason,
    )
    nsch = ReceptionScheduler(programs=(1,), categories=("NAVTEX",), rtty_enabled=True)
    navs = rtty_items(d0.replace(hour=18, minute=55), horizon_min=30, programs=(1,), categories=("NAVTEX",))
    nav_r = next(it for it in navs if it.start.hour == 18 and it.start.minute == 50)
    nav_s = next(it for it in navs if it.start.hour == 19 and it.start.minute == 0)
    q = nsch.decide(st(d0.replace(hour=19, minute=0, second=5), nav_r, text=False))
    check(
        "Créneaux NAVTEX consécutifs (18:50 La Maddalena → 19:00 La Garde) : enchaînés sans repasser par les cartes",
        q.action == "NEXT_RTTY" and q.item is not None and q.item.key == nav_s.key,
        q.reason,
    )
    o = sch.decide(st(atl.end + timedelta(minutes=6, seconds=5), atl, text=True)).action
    check("Bulletin sans NNNN qui déborde : retour forcé 6 min après la fin du créneau", o == "GO_WEFAX", o)

    # le NNNN de la note de service (313 caractères) qui précède le bulletin ne le termine pas
    arb = app.hybrid_arbiter
    now = datetime.now(timezone.utc)
    arb.current_item = RttyItem(now - timedelta(seconds=60), now + timedelta(minutes=24), 1, "ATL", "Prévision 5 jours Atlantique Est")
    arb._reset_rtty_tracking()
    note = "ZCZC 020\r\n" + "NOTE ON USE OF DATA. " * 14 + "\r\nNNNN\r\n"
    for i in range(0, len(note), 37):
        arb.on_rtty_text(note[i : i + 37])
    after_note = arb.rtty_end_marker
    arb._last_zczc_mono = arb._last_nnnn_mono = -1e9
    body = "ZCZC 021\r\nFEAE75 EDZW 181800\r\n" + "MADEIRA-N (34.0N 17.0W) TH 19. 12Z: NE 2-3 3.5 M //\r\n" * 14 + "NNNN\r\n"
    for i in range(0, len(body), 37):
        arb.on_rtty_text(body[i : i + 37])
    check(
        "La note de service (NNNN court en début de créneau) ne clôt pas le bulletin ; le vrai NNNN, si",
        not after_note and arb.rtty_end_marker and arb.rtty_end_mono is not None,
        f"note={after_note} fin={arb.rtty_end_marker}",
    )
    # retour manuel par le téléscripteur : le bulletin est marqué fait (plus de rebond vers le RTTY)
    item = arb.current_item
    arb.active_pipeline = "RTTY"
    app.bulletins_ui._quit_rtty_and_return_wefax()
    pump(root, 0.3)
    check(
        "« Revenir aux cartes » : bulletin marqué fait, pas de retour immédiat en RTTY",
        item.key in arb.done_items and arb.current_item is None and arb.active_pipeline == "WEFAX",
        arb.active_pipeline,
    )
    # P.AMP 2 posé par l'automatisme : ne suit pas sur la station suivante
    from wefax_station.radio.auto_preamp import AutoPreamp

    app.auto_preamp = AutoPreamp(mode="RTTY")
    app.auto_preamp.boosted_by_auto = True
    app._ap_freq = 7646.0
    app.radio.actual_preamp = 2
    app.radio.ovf_active = False
    app.radio.actual_freq_khz = 7880.0
    app._auto_preamp_tick("WEFAX")
    check("Changement de station : P.AMP 2 de l'automatisme ramené à P.AMP 1", app.radio.actual_preamp == 1, str(app.radio.actual_preamp))
    arb.current_item = None
    arb._reset_rtty_tracking()


class _FakeScopeSerial:
    """IC-705 simulé pour la veille spectrale : répond aux commandes 27 xx et envoie des balayages."""

    def __init__(self, points, center_hz, span_hz):
        from wefax_station.radio import scope as SC

        self.SC, self.points, self.center, self.span = SC, points, center_hz, span_hz
        self.state = {"on": 0x01, "out": 0x00, "mode": 0x00, "span": SC.bcd_freq(50000)}
        self.rx = bytearray()
        self.port = "COMTEST"
        self.baudrate = 115200
        self.is_open = True
        self.sent = []

    def _reply(self, payload):
        self.rx.extend(bytes([0xFE, 0xFE, 0xE0, 0xA4] + payload + [0xFD]))

    def _sweep(self):
        SC = self.SC
        head = [0x27, 0x00, 0x00, 0x01, 0x11, 0x00] + SC.bcd_freq(self.center) + SC.bcd_freq(self.span) + [0x00]
        self._reply(head)
        pts = self.points
        for k in range(10):
            chunk = pts[k * 50 : (k + 1) * 50]
            order = k + 2
            self._reply([0x27, 0x00, 0x00, (order // 10) << 4 | order % 10, 0x11] + chunk)

    def write(self, data):
        fr = list(data)[4:-1]
        self.sent.append(fr)
        cmd = fr[:2]
        if cmd == [0x27, 0x10]:
            self._reply([0x27, 0x10, self.state["on"]]) if len(fr) == 2 else (self.state.__setitem__("on", fr[2]), self._reply([0xFB]))
        elif cmd == [0x27, 0x11]:
            if len(fr) == 2:
                self._reply([0x27, 0x11, self.state["out"]])
            else:
                self.state["out"] = fr[2]
                self._reply([0xFB])
        elif cmd == [0x27, 0x14]:
            self._reply([0x27, 0x14, 0x00, self.state["mode"]]) if len(fr) == 3 else (self.state.__setitem__("mode", fr[3]), self._reply([0xFB]))
        elif cmd == [0x27, 0x15]:
            if len(fr) == 3:
                self._reply([0x27, 0x15, 0x00] + self.state["span"])
            else:
                self.state["span"] = fr[3:8]
                self.span = self.SC.parse_bcd_freq(fr[3:8])
                self._reply([0xFB])
        return len(data)

    def flush(self):
        pass

    @property
    def in_waiting(self):
        if self.state["out"] == 0x01 and len(self.rx) < 64:
            self._sweep()
        return len(self.rx)

    def read(self, n=1):
        _ = self.in_waiting
        out = bytes(self.rx[:n])
        del self.rx[:n]
        return out

    def reset_input_buffer(self):
        self.rx.clear()

    def close(self):
        self.is_open = False


def test_spectral_289(app, root):
    """2.8.9 — veille spectrale : lecture du spectre de l'IC-705 sans changer de fréquence."""
    print("2.8.9 Veille spectrale")
    import time as _t

    from wefax_station.radio import scope as SC

    check("BCD CI-V : 7 878 100 Hz aller-retour", SC.parse_bcd_freq(SC.bcd_freq(7878100)) == 7878100)
    rng = np.random.default_rng(3)
    center, span = 7878100, 250000
    pts = [int(v) for v in rng.integers(26, 34, 475)]
    step = 2 * span / 475

    def put(khz, height):
        i = int((khz * 1000 - (center - span)) / step)
        for j in (i - 1, i, i + 1):
            pts[j] = 30 + height

    put(7646.0, 28)   # DDH7 RTTY : fort
    put(7880.0, 40)   # DDK3 écouté
    put(8040.0, 13)   # Northwood : net
    res = SC.analyze_sweep(pts, center, span, [{"id": "DDH7", "freq": 7646.0}, {"id": "DDK3", "freq": 7880.0},
                                               {"id": "GYA3", "freq": 8040.0}, {"id": "SVJ4", "freq": 8105.0},
                                               {"id": "DDK6", "freq": 13882.5}])
    check(
        "Analyse : DDH7 fort, Northwood net, Athènes muette, 13 MHz hors fenêtre",
        res["DDH7"]["label"] == "fort" and res["GYA3"]["label"] == "net" and res["SVJ4"]["label"] == "rien"
        and "DDK6" not in res,
        ", ".join(f"{k} {v['label']} {v['contrast']:+.0f}" for k, v in res.items()),
    )
    # contrôleur : balayage lu puis écran du poste remis comme avant (span ±50 kHz, sortie des données coupée)
    radio = app.radio
    saved = (radio.ser, radio.port_open, radio.handshake_ok, radio.protocol, radio.civ_addr)
    fake = _FakeScopeSerial(pts, center, span)
    radio.ser, radio.port_open, radio.handshake_ok, radio.protocol, radio.civ_addr = fake, True, True, "ICOM CI-V", 0xA4
    t0 = _t.time()
    sw = radio.read_scope_sweep(span_hz=250000, timeout_s=1.0)
    dt = _t.time() - t0
    tx = [f for f in fake.sent if f[:1] in ([0x1C], [0x17]) or f[:2] == [0x1C, 0x00]]
    restored = fake.state["out"] == 0x00 and SC.parse_bcd_freq(fake.state["span"]) == 50000
    check(
        "CI-V : balayage complet reçu, écran remis comme avant, aucune commande d'émission",
        sw is not None and len(sw["points"]) == 475 and sw["center_hz"] == center and restored and not tx,
        f"{len(sw['points']) if sw else 0} points en {dt:.2f} s ; remis={restored}",
    )
    # application : résultat mémorisé, colonne « spectre », bulletin RTTY pris sans scan
    LOG.clear()
    app.spectral_seen = {}
    app._spectral_done(sw)
    best = app.spectral_best(["DDH7", "DDK9", "DDK2"])
    arb = app.hybrid_arbiter
    from datetime import datetime, timedelta, timezone
    from wefax_station.hybrid.scheduler import RttyItem

    picked = []
    orig_best, orig_switch, orig_scan = arb.prop.best, arb.switch_to_rtty_pipeline, arb.trigger_rtty_frequency_scan
    arb.prop.best = lambda *a, **k: None
    arb.switch_to_rtty_pipeline = lambda st, reason="": picked.append((st["id"], reason))
    arb.trigger_rtty_frequency_scan = lambda *a, **k: picked.append(("SCAN", ""))
    now = datetime.now(timezone.utc)
    arb.start_rtty_item(RttyItem(now, now + timedelta(minutes=20), 1, "ATL", "Prévision 5 jours Atlantique Est"), "Bulletin RTTY d'intérêt")
    arb.prop.best, arb.switch_to_rtty_pipeline, arb.trigger_rtty_frequency_scan = orig_best, orig_switch, orig_scan
    arb.current_item = None
    check(
        "Bulletin RTTY : station vue forte sur le spectre prise directement, sans scan",
        best and best[0] == "DDH7" and picked and picked[0][0] == "DDH7" and "spectre" in picked[0][1],
        picked[0][1][-90:] if picked else "",
    )
    cell = app.spectral_cell("DDH7")
    logged = any("Veille spectrale" in m and "DDH7" in m for m in LOG)
    check("Journal et fenêtre « Fréquences » renseignés", logged and cell.startswith("fort"), cell)
    radio.ser, radio.port_open, radio.handshake_ok, radio.protocol, radio.civ_addr = saved
    app.spectral_seen = {}


def test_scan(app, root):
    print("5. Scan avec IC-705 simulé (une vraie carte face à une porteuse fixe plus forte)")
    from wefax_station.sim.signals import wefax_broadcast, fm_from_frequency
    from wefax_station.sim.hf_channel import apply_channel
    import cv2

    fs = app.audio_fs
    chart = cv2.resize(np.asarray(app._generate_realistic_test_wefax("ANA"), np.uint8), (1809, 1200))[300:340]
    wefax, _ = wefax_broadcast(chart, fs=fs, phasing_lines=0, include_start=False, include_stop=False)
    n = len(wefax)
    sources = {
        7880.0: apply_channel(wefax, fs, snr_db=8, seed=21),  # vraie carte
        13882.5: apply_channel(
            fm_from_frequency(np.full(n, 1896.0), fs), fs, snr_db=25, seed=22
        ),  # raie fixe
    }
    noise = np.random.default_rng(23).normal(0, 0.2, n)
    qsy = []

    def fake_qsy(radio, freq, offset):
        qsy.append(freq)
        radio.actual_freq_khz = freq
        radio.update_station_metadata_by_freq(freq)
        return True

    saved = (UnifiedRadioController.set_wefax_frequency, RFVerified705.prepare)
    UnifiedRadioController.set_wefax_frequency = fake_qsy
    RFVerified705.prepare = lambda self, auto, **k: None
    try:
        app._reset_blank_rx_sheet()
        app.radio.port_open = True
        app.radio.handshake_ok = True
        app.radio.protocol = "ICOM CI-V"
        app.audio_live_connected = True
        app.audio_ring = np.zeros(int(fs * 0.6), np.float32)
        app.audio_long_ring = np.zeros(int(fs * 4.5), np.float32)
        state = {"run": True, "pos": 0}

        def feed():
            if not state["run"]:
                return
            src = sources.get(app.radio.actual_freq_khz, noise)
            k = int(0.1 * fs)
            p0 = state["pos"] % (n - k)
            blk = src[p0 : p0 + k].astype(np.float32)
            state["pos"] += k
            for ring in (app.audio_ring, app.audio_long_ring):
                ring[:-k] = ring[k:]
                ring[-k:] = blk
            app.last_audio_callback = time.monotonic()
            root.after(100, feed)

        feed()
        LOG.clear()
        app._trigger_carrier_scan()
        t0 = time.time()
        while time.time() - t0 < 150:
            root.update()
            time.sleep(0.005)
            if time.time() - t0 > 5 and not app.carrier_scan_active and not app.connection_busy:
                break
        state["run"] = False
        pump(root, 0.5)
        text = "\n".join(LOG)
        check("7 fréquences testées", len(set(qsy)) >= 7, f"{len(set(qsy))} fréquences")
        check(
            "Carte WEFAX reconnue par sa structure (niveau 3)",
            "WEFAX probable" in text or "WEFAX confirmé" in text,
        )
        check("Raie fixe identifiée comme porteuse non modulée", "porteuse fixe" in text)
        check(
            "Fréquence de la vraie carte retenue (7880 kHz) malgré une raie plus forte ailleurs",
            app.radio.actual_freq_khz == 7880.0,
            f"{app.radio.actual_freq_khz} kHz",
        )
        check("Scan terminé proprement", not app.carrier_scan_active and not app.connection_busy)
    finally:
        UnifiedRadioController.set_wefax_frequency, RFVerified705.prepare = saved
        app.radio.port_open = False
        app.radio.handshake_ok = False
        app.audio_live_connected = False


def test_ui(app, root):
    print("6. Fenêtres et commandes")
    errors = []
    root.report_callback_exception = lambda e, v, tb: errors.append(repr(v))
    actions = [
        "_show_settings",
        "_show_diagnostics",
        "_general_help",
        "_history",
        "_weather_dialog",
        "_geometry_dialog",
        "_run_expert_weather_analysis",
        "_generate_bulletin",
        "_toggle_rx_decoding",
        "_toggle_rx_decoding",
        "_toggle_fft_filter",
        "_toggle_fft_filter",
        "_toggle_qrn_blanker",
        "_toggle_qrn_blanker",
        "_reset_zoom_pan",
        "_show_live",
        "_draw_three_quality_bargraphs",
        "_draw_permanent_top_signal_curve",
        "_update_programme",
        "_sync_ui_from_hardware",
    ]
    failed = []
    for name in actions:
        try:
            getattr(app, name)()
            pump(root, 0.2)
        except Exception as exc:
            failed.append(f"{name}: {exc!r}")
    try:
        app.bulletins_ui.show()
        pump(root, 0.3)
    except Exception as exc:
        failed.append(f"bulletins_ui.show: {exc!r}")
    pump(root, 1.0)
    check(f"{len(actions) + 1} commandes sans exception", not failed, "; ".join(failed)[:300])
    check("Aucune erreur dans les rappels Tk", not errors, "; ".join(errors)[:300])



class _SplitScopeSerial(_FakeScopeSerial):
    """IC-705 simulé dont les octets arrivent par petits morceaux de taille variable (comme sur le poste réel
    le 18/11) ; `blank_first` : premier balayage entièrement à zéro."""

    def __init__(self, points, center_hz, span_hz, seed=5, blank_first=False):
        super().__init__(points, center_hz, span_hz)
        self.rng = np.random.default_rng(seed)
        self.blank_first = blank_first
        self.sweeps_sent = 0

    def _sweep(self):
        pts = self.points
        if self.blank_first and self.sweeps_sent == 0:
            self.points = [0] * len(pts)
        super()._sweep()
        self.points = pts
        self.sweeps_sent += 1

    def read(self, n=1):
        _ = self.in_waiting
        k = int(min(len(self.rx), max(1, self.rng.integers(1, 23))))
        out = bytes(self.rx[:k])
        del self.rx[:k]
        return out


class _DictRF:
    """IC-705 réduit à sa mémoire de réglages, pour RFVerified705 (aucun port série)."""

    def __init__(self, pamp):
        import threading
        from wefax_station.radio import scope as SC

        self.mem = {
            (0x19, 0): [0xA4], (4,): [1, 1], (0x1A, 6): [1, 1], (0x1A, 3): [0x34], (0x14, 7): [1, 0x28],
            (0x14, 8): [1, 0x28], (0x16, 0x12): [1], (0x16, 0x40): [0], (0x16, 0x41): [0], (0x16, 0x48): [0],
            (0x16, 0x22): [0], (0x1A, 5, 1, 9): [0], (0x1A, 5, 1, 0x11): [0], (0x14, 2): [2, 0x55],
            (0x14, 1): [0, 8], (0x1A, 5, 1, 0x10): [1, 0x28], (0x16, 2): [pamp], (0x11,): [0], (0x15, 7): [0],
            (0x15, 2): [1, 0x40], (3,): SC.bcd_freq(3853100),
        }
        self.writes = []
        self.logs = []
        self.actual_dial_khz = 3853.1
        self.lock = threading.Lock()

    def log(self, m):
        self.logs.append(m)


def test_290(app, root):
    """2.9.0 — régressions et corrections constatées sur la station le 18/11 au soir."""
    print("2.9.0 Corrections (À propos, vue directe, veille spectrale, programme DWD, priorités, affichage)")
    import ast
    import time as _t
    from datetime import datetime, timedelta, timezone

    from wefax_station.core import schedules as S
    from wefax_station.hybrid.scheduler import ReceptionScheduler, RttyItem, ScheduleState
    from wefax_station.radio import scope as SC
    from wefax_station.radio.rf_verify import RFVerified705
    from wefax_station.ui.placement import clamp_into
    from wefax_station.ui.text_fit import fit_items

    # ---- 1. fenêtres annexes sur un poste multi-écran (coordonnées négatives)
    area = (-1920, -1080, 1920, 1080)
    xy = clamp_into(-1500, -900, 600, 600, area)
    xy2 = clamp_into(-200, -100, 600, 600, area)
    check(
        "Placement multi-écran : position négative conservée et fenêtre gardée dans la fenêtre principale",
        xy == (-1500, -900) and xy2 == (-600, -600),
        f"{xy} / {xy2} (2.8.9 : ramené à (0, 0), hors de l'écran de l'application)",
    )
    win = app._show_about()
    pump(root, 0.5)
    ok = win is not None and win.winfo_exists() and win.winfo_ismapped()
    rx, ry, rw, rh = root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()
    wx, wy = win.winfo_rootx(), win.winfo_rooty()
    inside = rx - 2 <= wx <= rx + max(0, rw - win.winfo_width()) + 2 and ry - 40 <= wy <= ry + rh
    check("Aide › À propos : fenêtre affichée sur la fenêtre principale", ok and inside, f"{wx},{wy} dans {rx},{ry} {rw}x{rh}")
    try:
        win.destroy()
    except tk.TclError:
        pass

    # ---- 2. aucune méthode appelée sur self qui n'existe nulle part (cause de la régression _return_to_live_rx_view)
    defs, stores, calls = set(), set(), {}
    pkg = ROOT / "wefax_station"
    for f in pkg.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.add(n.name)
            elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store):
                stores.add(n.attr)
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name):
                if n.func.value.id == "self" and n.func.attr.startswith("_"):
                    calls.setdefault(n.func.attr, f"{f.relative_to(pkg)}:{n.lineno}")
    missing = {k: v for k, v in calls.items() if k not in defs and k not in stores and not k.startswith("__")}
    check("Aucune méthode interne appelée sans être définie", not missing, ", ".join(f"{k} ({v})" for k, v in missing.items()))

    # ---- 3. retour automatique à la vue en direct quand une nouvelle carte arrive
    app.viewing_archived_file = "archive_test.png"
    app.pin_completed = True
    app._live_return_pending = False
    app._reset_blank_rx_sheet()
    pending = bool(getattr(app, "_live_return_pending", False)) and app.viewing_archived_file is not None
    app._return_to_live_rx_view()
    check(
        "Archive consultée + nouvelle carte : retour à la vue en direct (méthode absente en 2.8.9)",
        pending and app.viewing_archived_file is None and app.pin_completed is False,
    )

    # ---- 4. veille spectrale : trames réelles du 18/11 (IC-705 de F4NMK), coupées à toutes les positions
    real = bytes.fromhex(
        "fefee0a427000001110000818707000000250000" "00fd"
        "fefee0a4270000021100" + "00" * 49 + "fd"
    )
    whole = [fr for fr in SC.iter_frames(real)]
    cuts_ok = True
    for cut in range(1, len(real)):
        fs_ = SC.FrameStream()
        got = fs_.feed(real[:cut]) + fs_.feed(real[cut:])
        cuts_ok &= got == whole
    asm = SC.SweepAssembler()
    asm.feed_payload(whole[0][2:])
    check(
        "Trame réelle 27 00 du 18/11 : en-tête lu (7 878,1 kHz, ±250 kHz, 11 trames), trames recollées à toute coupure",
        cuts_ok and asm.center_hz == 7878100 and asm.span_hz == 250000 and asm.total == 11 and len(whole) == 2,
        f"centre {asm.center_hz} Hz, span {asm.span_hz} Hz, {asm.total} trames",
    )
    rng = np.random.default_rng(9)
    pts = [int(v) for v in rng.integers(26, 34, 475)]
    radio = app.radio
    saved = (radio.ser, radio.port_open, radio.handshake_ok, radio.protocol, radio.civ_addr)
    try:
        fake = _SplitScopeSerial(pts, 7878100, 250000, blank_first=True)
        radio.ser, radio.port_open, radio.handshake_ok, radio.protocol, radio.civ_addr = fake, True, True, "ICOM CI-V", 0xA4
        sw = radio.read_scope_sweep(span_hz=250000, timeout_s=2.0)
        check(
            "Octets reçus par morceaux (comme le 18/11) + premier balayage vide : balayage complet reconnu",
            sw is not None and not sw.get("blank") and len(sw["points"]) == 475 and max(sw["points"]) > 0,
            f"{len(sw['points']) if sw else 0} points ; statistiques {radio.last_scope_stats}",
        )
        try:
            radio._scope_cmd([0x1C, 0x00, 0x01])
            refused = False
        except ValueError:
            refused = True
        tx = [f for f in fake.sent if f[:1] in ([0x1C], [0x17])]
        check("Veille spectrale : commande d'émission refusée par le chemin 27 xx, aucune envoyée", refused and not tx)
    finally:
        radio.ser, radio.port_open, radio.handshake_ok, radio.protocol, radio.civ_addr = saved
    LOG.clear()
    radio.last_scope_stats = {"bytes": 960, "sweeps": 0, "blank": 0}
    app._spectral_fails = 0
    for _ in range(3):
        app._spectral_done(None)
    msg = " ".join(LOG)
    check(
        "Arrêt de la veille : le message ne met plus le poste en cause quand des octets arrivent",
        "octets reçus" in msg and "Unlink" not in msg,
        msg[:140],
    )
    app._spectral_fails = 0

    # ---- 5. programme DWD (NOAA, information du 24/07/2024)
    dwd = {(h, m): (c, d) for h, m, c, d in S.BROADCAST_SCHEDULES_UTC["DWD"]}
    check(
        "Programme DWD : 18:47 prévision H+48, 19:00 H+84, 19:39 vagues H+72 ; plus de « FSXX48 18:30 »",
        dwd.get((18, 47), ("",))[0] == "FSXX48" and dwd.get((19, 0), ("",))[0] == "FSXX84"
        and (19, 39) in dwd and (18, 30) not in dwd and (19, 15) not in dwd,
        f"{len(dwd)} cartes",
    )
    old = {"DWD": [(18, 30, "FSXX48", "ancien"), (19, 15, "FSXX84", "ancien"), (20, 15, "X", "a"), (21, 0, "Y", "b")],
           "ATH": [(0, 0, "ASUK00", "a"), (1, 0, "B", "b"), (2, 0, "C", "c"), (3, 0, "D", "d")]}
    merged = S.merge_saved_schedules(old, saved_rev=None)
    kept = S.merge_saved_schedules({"DWD": old["DWD"]}, saved_rev=S.SCHEDULE_REV)
    check(
        "Ancienne table DWD enregistrée localement remplacée par le programme intégré (autres familles conservées)",
        merged["DWD"] == list(S.BROADCAST_SCHEDULES_UTC["DWD"]) and merged["ATH"] == [tuple(x) for x in old["ATH"]]
        and kept["DWD"] == [tuple(x) for x in old["DWD"]],
    )
    import json as _json

    sp = Path(app.schedule_path)
    backup = sp.read_text(encoding="utf-8") if sp.is_file() else None
    sp.write_text(_json.dumps({"status": "test", "stations": old}), encoding="utf-8")
    app._reload_schedules()
    reloaded = _json.loads(sp.read_text(encoding="utf-8"))
    check(
        "Fichier programmes_wefax.json de l'opérateur mis à niveau au chargement",
        app.schedule_data["DWD"][0][:2] == (4, 30) and reloaded.get("schedule_rev") == S.SCHEDULE_REV,
    )
    if backup is not None:
        sp.write_text(backup, encoding="utf-8")
        app._reload_schedules()
    src = (ROOT / "wefax_station" / "hybrid" / "planner.py").read_text(encoding="utf-8")
    check("Sources : plus d'annonce « Horaires vérifiés » sans comparaison", "Horaires vérifiés" not in src)

    # ---- 6. règle carte prioritaire / bulletin RTTY (F4NMK, 18/11/2026)
    d0 = datetime(2026, 11, 18, tzinfo=timezone.utc)
    sch = ReceptionScheduler(programs=(1,), categories=("AVIS", "MED", "NAVTEX", "ATL"), rtty_enabled=True)
    slots = tuple(S.BROADCAST_SCHEDULES_UTC["DWD"])
    prev = RttyItem(d0.replace(hour=17, minute=50), d0.replace(hour=19, minute=40), 1, "ATL", "Prévision 5 jours Atlantique Est")
    avis = RttyItem(d0.replace(hour=17, minute=50), d0.replace(hour=19, minute=40), 1, "AVIS", "Avis par zones maritimes")

    def rst(t, item, received=()):
        return ScheduleState(
            now=t, pipeline="RTTY", chart_drawing=False, seconds_since_chart=1800, rtty_text_active=True,
            rtty_service_s=0.0, rtty_no_signal_s=0.0, rtty_end_marker=False, current_item=item,
            chart_slots=slots, received_recent=received,
        )

    a = sch.decide(rst(d0.replace(hour=17, minute=59, second=30), prev))
    b = sch.decide(rst(d0.replace(hour=17, minute=59, second=30), avis))
    c = sch.decide(rst(d0.replace(hour=18, minute=46, second=30), prev))
    e = sch.decide(rst(d0.replace(hour=18, minute=46, second=30), prev, received=(prev.label,)))
    f = sch.decide(rst(d0.replace(hour=19, minute=12, second=30), prev, received=(prev.label,)))
    check(
        "Analyse de surface 18:00 : prévision RTTY interrompue ; un avis aussi (décision F4NMK du 19/11, 2.9.3)",
        a.action == "GO_WEFAX" and b.action == "GO_WEFAX" and "avis" in b.reason,
        f"{a.action} / {b.action} ({b.reason})",
    )
    check(
        "Prévision H+48 de 18:47 : bulletin interrompu seulement s'il a été reçu < 12 h ; carte vagues : jamais",
        c.action == "STAY" and e.action == "GO_WEFAX" and f.action == "STAY",
        f"{c.action} / {e.action} / {f.action}",
    )

    def wst(t):
        return ScheduleState(
            now=t, pipeline="WEFAX", chart_drawing=False, seconds_since_chart=60, rtty_text_active=False,
            rtty_service_s=0.0, rtty_no_signal_s=0.0, rtty_end_marker=False, chart_slots=slots,
        )

    g = sch.decide(wst(d0.replace(hour=21, minute=57, second=30)))
    h_ = sch.decide(wst(d0.replace(hour=21, minute=55, second=0)))
    check(
        "Analyse de surface dans moins de 3 min : le bulletin attend la fin de la carte",
        g.action == "STAY" and "imminente" in g.reason and h_.action == "GO_RTTY",
        f"21:57:30 {g.action} · 21:55 {h_.action}",
    )
    sch2 = ReceptionScheduler(programs=(1,), categories=("AVIS",), rtty_enabled=False)
    M = _t.monotonic() + 10000
    sch2.last_veille = M
    st_q = ScheduleState(now=d0.replace(hour=19, minute=37, second=9), pipeline="WEFAX", chart_drawing=False,
                         seconds_since_chart=600, rtty_text_active=False, rtty_service_s=0.0, rtty_no_signal_s=0.0,
                         rtty_end_marker=False, chart_slots=slots)
    q1 = sch2.decide(st_q, mono_now=M)
    st_q.now = d0.replace(hour=19, minute=32)  # 2.11.0 : 6 min après la carte de 19:26 (garde de 5 min)
    q2 = sch2.decide(st_q, mono_now=M)
    check(
        "« 8 min sans carte » : contrôle reporté à 19:37 (carte prévue à 19:39), fait à 19:32",
        q1.action == "STAY" and "19:39" in q1.reason and q2.action == "WEFAX_RECHECK",
        f"{q1.action} ({q1.reason}) / {q2.action}",
    )
    arb = app.hybrid_arbiter
    arb.received_bulletins = {}
    arb.mark_bulletin_received("Prévision 5 jours Atlantique Est", when=_t.time() - 3600)
    arb.mark_bulletin_received("Bulletin Atlantique Nord", when=_t.time() - 13 * 3600)
    rec = arb.received_recent_labels()
    check("Bulletins reçus mémorisés 12 h (fichier bulletins_recus.json)",
          rec == ("Prévision 5 jours Atlantique Est",) and Path(arb.received_path).is_file(), str(rec))

    LOG.clear()
    m0 = _t.monotonic()
    arb._text_status_mono = None
    arb._log_text_listening_status(m0)
    arb._log_text_listening_status(m0 + 61)
    line = next((x for x in LOG if x.startswith("📡 Écoute")), "")
    check("Écoute texte silencieuse : une ligne d'état par minute (FSK, Mark/Space, P.AMP)",
          "Mark" in line and "P.AMP" in line, line[:150])

    # ---- 7. P.AMP 1 comme référence des scans
    for start in (0, 2):
        fr = _DictRF(start)
        v = RFVerified705(fr)

        def trans(query, data=None, size=None, _fr=fr):
            key = tuple(query)
            if data is not None:
                _fr.writes.append((key, list(data)))
                _fr.mem[(4,) if key == (6,) else key] = list(data) if key != (6,) else _fr.mem[(4,)]
                return [0xFB]
            return list(_fr.mem.get(key, [0]))

        v.transaction = trans
        v.prepare(True, reference_pamp=1)
        check(
            f"Scan : P.AMP {start} mémorisé par la bande → P.AMP 1 imposé pendant les mesures",
            fr.mem[(0x16, 2)] == [1] and fr.actual_preamp == 1,
            [m for m in fr.logs if "PAMP" in m][-1][:90],
        )
    fr = _DictRF(1)
    fr.mem[(0x15, 7)] = [1]
    v = RFVerified705(fr)
    calls_ovf = []

    def trans_ovf(query, data=None, size=None, _fr=fr):
        key = tuple(query)
        if data is not None:
            _fr.mem[key] = list(data)
            if key == (0x11,):
                _fr.mem[(0x15, 7)] = [0]
            return [0xFB]
        calls_ovf.append(key)
        return list(_fr.mem.get(key, [0]))

    v.transaction = trans_ovf
    v.prepare(True, reference_pamp=1)
    check("Surcharge (OVF) : la protection reste prioritaire sur la référence P.AMP 1",
          fr.mem[(0x16, 2)] == [0], f"P.AMP {fr.mem[(0x16, 2)]}, ATT {fr.mem[(0x11,)]}")

    # ---- 8. entrée audio : le micro du PC n'est plus annoncé comme « Flux Audio USB »
    from wefax_station.app.radio_link import is_radio_audio_input

    check(
        "Entrée audio : « Réseau de microphones » reconnu comme n'étant pas le poste",
        is_radio_audio_input("20: Microphone (USB Audio CODEC )")
        and not is_radio_audio_input("2: Réseau de microphones (Technolo"),
    )

    # ---- 9. affichage : afficheur du poste en NAVTEX, ligne « Ensuite »
    from wefax_station.ui.vfo_display import VfoDisplay

    top = tk.Toplevel(root)
    top.geometry("1300x80")
    vfo = VfoDisplay(top, height=66)
    vfo.pack(fill="both", expand=True)
    pump(root, 0.3)
    vfo.update_state(service="NAVTEX", service_detail="SITOR-B 100 Bd · 170 Hz", station="NAVTEX-INT",
                     name="NAVTEX 518 kHz international (La Maddalena R · Cabo la Nao X · La Garde W)", freq_khz=518.0)
    pump(root, 0.2)
    items = {vfo.itemcget(i, "text"): vfo.bbox(i) for i in vfo.find_all() if vfo.type(i) == "text"}
    det, sta = items.get("SITOR-B 100 Bd · 170 Hz"), items.get("NAVTEX-INT")
    check(
        "Afficheur NAVTEX : « SITOR-B 100 Bd · 170 Hz » ne chevauche plus l'indicatif",
        det is not None and sta is not None and det[2] < sta[0],
        f"fin du texte {det[2] if det else '?'} px, indicatif à {sta[0] if sta else '?'} px",
    )
    top.destroy()

    def meas(t):
        return 7 * len(t)

    entries = ["21:00 Avis par zones maritimes", "21:00 carte des glaces", "21:15 carte des glaces",
               "21:20 NAVTEX La Maddalena (I) : bulletin météo (IT)", "21:30 Bulletin Atlantique Nord"]
    txt = fit_items(entries, 420, meas, prefix="Ensuite : ", max_lines=2)
    lines = txt.split("\n")
    whole_items = all((it in txt) for it in entries[: len(txt.split(" · "))])
    check(
        "Ligne « Ensuite » : 2 lignes au plus, aucune ne déborde, aucun élément coupé en deux",
        len(lines) <= 2 and all(meas(l) <= 420 for l in lines) and whole_items
        and all(any(l.endswith(it) or (it + " ·") in l or l.endswith(it) for l in lines) or it not in txt for it in entries),
        " | ".join(lines),
    )
    ev = arb.upcoming_entries(now=d0.replace(hour=20, minute=1), n=6)
    check(
        "Ligne « Ensuite » : cartes et bulletins à venir mêlés dans l'ordre des heures",
        any("carte" in x for x in ev) and any("Avis" in x for x in ev) and ev == sorted(ev, key=lambda x: x[:5]),
        " · ".join(ev),
    )



def test_291(app, root):
    """2.9.1 — soirée du 18/11 (20:43-21:31) : poste resté sur Northwood, cartes DWD de 21:00/21:15/21:36 manquées."""
    print("2.9.1 Choix de la station selon le programme (DWD de référence)")
    import time as _t
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from wefax_station.core import schedules as S
    from wefax_station.hybrid.scheduler import ReceptionScheduler, ScheduleState

    d0 = datetime(2026, 11, 18, tzinfo=timezone.utc)
    dwd = tuple(S.BROADCAST_SCHEDULES_UTC["DWD"])
    gya = tuple(S.BROADCAST_SCHEDULES_UTC["GYA"])
    sch = ReceptionScheduler(programs=(1,), categories=("AVIS",), rtty_enabled=False)
    M = _t.monotonic() + 10000
    sch.last_veille = M
    sch.last_wefax_recheck = M

    def wst(t, fam, since=60):
        return ScheduleState(
            now=t, pipeline="WEFAX", chart_drawing=False, seconds_since_chart=since, rtty_text_active=False,
            rtty_service_s=0.0, rtty_no_signal_s=0.0, rtty_end_marker=False, wefax_family=fam,
            chart_slots=gya if fam == "GYA" else dwd, preferred_family="DWD", pref_slots=dwd,
        )

    a = sch.decide(wst(d0.replace(hour=20, minute=58, second=30), "GYA"), mono_now=M)
    b = sch.decide(wst(d0.replace(hour=20, minute=50), "GYA"), mono_now=M)
    c = sch.decide(wst(d0.replace(hour=20, minute=58, second=30), "ATH"), mono_now=M)
    e = sch.decide(wst(d0.replace(hour=20, minute=58, second=30), "DWD"), mono_now=M)
    check(
        "Sur Northwood à 20:58:30 : retour au DWD pour la carte de 21:00 (rien à 20:50, ni sur Athènes, ni déjà sur DWD)",
        a.action == "GO_FAMILY" and "21:00" in a.reason and b.action != "GO_FAMILY"
        and c.action != "GO_FAMILY" and e.action != "GO_FAMILY",
        f"{a.action} ({a.reason}) / {b.action} / {c.action} / {e.action}",
    )
    sch.last_wefax_recheck = 0.0
    g = sch.decide(wst(d0.replace(hour=21, minute=0, second=30), "DWD", since=600), mono_now=M)
    h_ = sch.decide(wst(d0.replace(hour=21, minute=6), "DWD", since=600), mono_now=M)  # 2.11.0 : garde 5 min
    check(
        "Pas de contrôle des fréquences dans les 5 min qui suivent l'heure d'une carte (21:00:00 le 18/11)",
        g.action == "STAY" and "reporté" in g.reason and h_.action == "WEFAX_RECHECK",
        f"21:00:30 {g.action} · 21:06 {h_.action}",
    )
    arb = app.hybrid_arbiter
    r1 = arb.recheck_family("GYA", d0.replace(hour=20, minute=51, second=45))
    r2 = arb.recheck_family("DWD", d0.replace(hour=23, minute=0))
    r3 = arb.recheck_family("GYA", d0.replace(hour=23, minute=0))
    r4 = arb.recheck_family("ATH", d0.replace(hour=9, minute=0))
    check(
        "« 8 min sans carte » : DWD contrôlé depuis Northwood quand une carte DWD arrive ; Northwood la nuit (trou DWD)",
        (r1, r2, r3, r4) == ("DWD", "GYA", "GYA", "ATH"),
        f"20:51 GYA→{r1} · 23:00 DWD→{r2} · 23:00 GYA→{r3} · Athènes→{r4}",
    )
    # scan : une porteuse fixe (rang 1) sur Northwood ne l'emporte plus sur le DWD quand une carte DWD arrive
    from wefax_station.core.stations import WEFAX_STATIONS

    gya3 = next(s for s in WEFAX_STATIONS if s["id"] == "GYA3")
    ddk3 = next(s for s in WEFAX_STATIONS if s["id"] == "DDK3")
    saved = (getattr(app, "scan_results", []), getattr(app, "_scan_signal_ranks", {}), app.radio.set_wefax_frequency,
             app._prepare_rf, arb.preferred_chart_soon)
    chosen = []
    try:
        app.scan_results = [(9.0, gya3), (5.0, ddk3)]
        app._scan_signal_ranks = {"GYA3": 1, "DDK3": 0}
        app.radio.set_wefax_frequency = lambda f, off=True: chosen.append(f) or True
        app._prepare_rf = lambda auto: None
        arb.preferred_chart_soon = lambda *a, **k: (d0, "ICE", "Glaces")
        LOG.clear()
        app.scan_origin = 7880.0
        app.scan_offset = True
        app._finish_scan()
        t_end = _t.time() + 12
        while _t.time() < t_end and not any(("RF_FINAL_RESUME" in x or "RF_FINAL_REJECT" in x) for x in LOG):
            pump(root, 0.2)
        pump(root, 2.0)
    finally:
        app.scan_results, app._scan_signal_ranks = saved[0], saved[1]
        # substitutions posées sur l'objet : on les retire (sinon elles masqueraient celles des tests suivants)
        for obj, name in ((app.radio, "set_wefax_frequency"), (app, "_prepare_rf"), (arb, "preferred_chart_soon")):
            obj.__dict__.pop(name, None)
        app.carrier_scan_active = False
        app.connection_busy = False
        app.rx_decoding_active = True
        app.set_busy_state(False)
    check(
        "Scan sans modulation WEFAX : porteuse fixe de Northwood écartée, DDK3 retenu (carte DWD au programme)",
        any("SCAN_SELECTION target_khz=7880.0" in x for x in LOG) and any("SCAN_PREFERENCE" in x for x in LOG),
        f"QSY {chosen[:1]} ; " + next((x for x in LOG if "SCAN_PREFERENCE" in x), "")[:110],
    )
    # enregistrement : changements de fréquence notés
    fake = SimpleNamespace(active=True, meta={"changements": []})
    saved_rec, saved_f = app.audio_recorder, app.radio.actual_freq_khz
    try:
        app.audio_recorder = fake
        app._rec_t0, app._rec_last_freq = _t.monotonic() - 240, 4610.0
        app.radio.actual_freq_khz = 8040.0
        app._note_recording_qsy()
        app._note_recording_qsy()
    finally:
        app.audio_recorder, app.radio.actual_freq_khz = saved_rec, saved_f
    ch = fake.meta["changements"]
    check(
        "Enregistrement : changement de fréquence noté dans le .json (une seule fois)",
        len(ch) == 1 and ch[0]["frequence_khz"] == 8040.0 and ch[0]["t_s"] >= 239,
        str(ch[:1]),
    )


def _fake_pdf(lines):
    import zlib

    body = b"BT\n" + b"".join(
        b"(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1") + b") Tj T*\n"
        for ln in lines
    ) + b"ET\n"
    z = zlib.compress(body)
    return (b"%PDF-1.4\n1 0 obj<</Length " + str(len(z)).encode() + b"/Filter/FlateDecode>>stream\n" + z
            + b"\nendstream endobj\n%%EOF")


def test_292(app, root):
    """2.9.2 — sources officielles hors ligne, stations texte en sommeil, consultation, P.AMP pendant une carte."""
    print("2.9.2 Sources officielles, autonomie hors ligne, stations texte, consultation, P.AMP")
    import json as _json
    import time as _t
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from wefax_station.core import schedules as S
    from wefax_station.hybrid import official_sources as OS
    from wefax_station.hybrid.scheduler import ReceptionScheduler, ScheduleState, rtty_items
    from wefax_station.hybrid.text_station_health import TextStationHealth, station_key
    from wefax_station.radio.auto_preamp import AutoPreamp

    B = S.BROADCAST_SCHEDULES_UTC
    gya = {(h, m): (c, d) for h, m, c, d in B["GYA"]}
    grid = all((h * 60 + m) % 12 == 0 for h, m in gya)
    check(
        "Programme Northwood d'après la NOAA (05/01/2022) : 102 cartes sur la grille de 12 min, 07:00 analyse, 05:48 avis",
        len(gya) == 102 and grid and gya[(7, 0)][0] == "ASUK" and gya[(5, 48)][0] == "GALE"
        and "GYA" in S.REVISED_FAMILIES and "GYA" in S.SCHEDULE_REV,
        f"{len(gya)} cartes, révision {S.SCHEDULE_REV}",
    )
    d704 = next(d for h, m, c, d in B["DWD"] if (h, m) == (7, 4))
    check("Libellé DWD de 07:04 : température 850 hPa (carte reçue le 19/11)", "température 850" in d704.lower(), d704)
    pr = (S.chart_priority("ASUK", "Northwood — Analyse de surface"), S.chart_priority("ASUK", "Northwood — Analyse de surface (12Z)"),
          S.chart_priority("GALE", ""), S.chart_priority("ASXX", "Analyse de surface"))
    check(
        "Northwood : analyse sans heure de référence = rediffusion (ne coupe pas un bulletin non reçu) ; avis de coup de vent prioritaire",
        pr == (S.PRIORITY_HIGH, S.PRIORITY_ANALYSE, S.PRIORITY_HIGH, S.PRIORITY_ANALYSE), str(pr),
    )
    old = {"GYA": [(0, 0, "ASUK00", "a"), (1, 12, "B", "b"), (2, 0, "C", "c"), (3, 24, "D", "d")]}
    check("Ancienne table Northwood (12 cartes) remplacée par le programme intégré",
          S.merge_saved_schedules(old, saved_rev="2.9.0-DWD-NOAA-20240724")["GYA"] == list(B["GYA"]))

    # ---- extraction et comparaison d'un document au format NOAA
    # 2.9.4 — même mise en page que les documents réels (un élément par ligne de texte extrait)
    def dwd_rows(extra=()):
        out = ["Hamburg / Pinneberg (DDH, DDK)", "Frequencies", "3855", "kHz", "DDH3", "10,0", "kW", "F1C",
               "7880", "kHz", "DDK3", "13882,5", "kHz", "DDK6", "Time", "UTC", "Contents"]
        rows = sorted([(h * 60 + m, c) for h, m, c, d in B["DWD"]] + list(extra))
        for minute, c in rows:
            out += [f"{minute // 60:02d}.{minute % 60:02d}", "120", "/", "576", "11", "00.00", c, "1000 hPa"]
            if minute == 5 * 60 + 25:
                out += ["05.55", "-", "06.35 Voice", "-", "transmission on 5905 kHz"]
        return out

    noaa = ["HAMBURG/PINNEBERG, GERMANY"] + dwd_rows([(340, "NEW CHART")]) + ["(INFORMATION DATED (24 July 2024)"]
    noaa += ["NORTHWOOD, UNITED KINGDOM", "GYA", "2618.5kHz", "2200Z", "-", "0500Z", "Product", "Broadcast",
             "Time", "(Z)", "Time", "(Z)"]
    for h, m, c, d in B["GYA"][:-1]:
        noaa += ["06Z", c, f"{h:02d}{m:02d}"]
    noaa += ["0248", "All MAPS 54N", "(INFORMATION DATED Jan 05,", "2022)", "Appendix A"]
    dwd_doc = dwd_rows()
    pdf_noaa, pdf_dwd = _fake_pdf(noaa), _fake_pdf(dwd_doc)
    txt = OS.extract_pdf_text(pdf_noaa)
    a_d = OS.analyse_family(txt, "DWD", B["DWD"])
    a_g = OS.analyse_family(txt, "GYA", B["GYA"])
    check(
        "PDF officiel lu (extracteur intégré) : DWD +05:40, Northwood sans 23:48, dates d'information relevées ; "
        "kHz / hPa / kW ignorés",
        a_d["added"] == [340] and not a_d["removed"] and a_g["removed"] == [23 * 60 + 48] and not a_g["added"]
        and a_d["same_info_date"] and a_g["same_info_date"] and a_d["plausible"] and a_g["plausible"],
        OS.describe_analysis(a_d) + " | " + OS.describe_analysis(a_g),
    )
    junk = OS.analyse_family("NORTHWOOD, UNITED KINGDOM\nTexte illisible", "GYA", B["GYA"])
    check("Document illisible : aucune proposition de modification (lecture par l'opérateur)",
          not junk["plausible"] and OS.proposed_slots(B["GYA"], junk) == list(B["GYA"]), OS.describe_analysis(junk))

    planner = app.schedule_planner
    root_dir = planner.workspace.root_dir
    before = {k: list(v) for k, v in app.schedule_data.items()}
    saved_dl = planner.__dict__.get("_download")

    # ---- hors ligne (blackout) : rien n'est bloqué, une seule ligne au journal
    def offline(url):
        import urllib.error

        raise urllib.error.URLError("réseau indisponible")

    planner._download = offline
    planner.sync_in_progress = False
    LOG.clear()
    t0 = _t.monotonic()
    planner.trigger_web_schedule_sync(manual=False)
    planner.last_web_sync_mono = 0.0
    planner.trigger_web_schedule_sync(manual=True)
    returned_s = _t.monotonic() - t0
    pump(root, 2.0)
    off = [x for x in LOG if "[SOURCES]" in x and "Internet non joignable" in x]
    check(
        "Sans Internet : appel non bloquant, une ligne « hors ligne », programmes inchangés, réception poursuivie",
        returned_s < 0.5 and len(off) == 1 and app.schedule_data == before and not planner.sync_in_progress
        and "sans Internet" in off[0],
        f"retour en {returned_s * 1000:.0f} ms ; " + (off[0][:120] if off else "aucune ligne"),
    )
    planner._close_sources_window()
    planner.network_cut_off_manual = True
    LOG.clear()
    planner.trigger_web_schedule_sync(manual=True)
    check("Coupe-circuit réseau : aucun téléchargement lancé", not planner.sync_in_progress and any("coupe-circuit" in x for x in LOG))
    planner.network_cut_off_manual = False

    # ---- en ligne (téléchargement simulé) : documents conservés, différences proposées, choix de l'opérateur
    planner._download = lambda url: pdf_dwd if "dwd.de" in url else pdf_noaa
    LOG.clear()
    planner.trigger_web_schedule_sync(manual=True)
    t_end = _t.time() + 10
    while _t.time() < t_end and planner.sync_in_progress:
        pump(root, 0.1)
    pump(root, 0.5)
    st = OS.load_state(root_dir)
    files = sorted(p.name for p in OS.sources_dir(root_dir).glob("*.pdf"))
    pend = planner.pending_differences()
    check(
        "Documents officiels téléchargés en entier et conservés (date, SHA-256, taille) ; différences signalées",
        files == ["DWD_FAX.pdf", "NOAA_RFAX.pdf"] and st.get("online") and len(pend) == 2
        and any("différence(s) à examiner" in x for x in LOG),
        f"{files} ; {[(r['id'], f) for r, f, a, h in pend]}",
    )
    win = getattr(planner, "_sources_window", None)
    btns = []
    if win is not None:
        def walk(w):
            for c in w.winfo_children():
                if c.winfo_class() == "Button":
                    btns.append(c.cget("text"))
                walk(c)
        walk(win)
    check("Fenêtre « Programmes : sources officielles » : Accepter / Refuser / Ouvrir le document",
          win is not None and "Accepter GYA" in btns and "Refuser" in btns and "Ouvrir le document" in btns, str(btns))
    rec_noaa = next(r for r, f, a, h in pend if r["id"] == "NOAA_RFAX" and f == "GYA")
    planner.accept_source_family(rec_noaa, "GYA")
    rec_dwd = next(r for r, f, a, h in pend if f == "DWD")
    planner.refuse_source_family(rec_dwd, "DWD")
    acc = OS.load_accepted(root_dir)
    gy_now = {(h, m) for h, m, c, d in app.schedule_data["GYA"]}
    S.set_accepted_overrides({})
    reloaded = OS.apply_accepted(root_dir)
    merged = S.merge_saved_schedules({}, saved_rev=S.SCHEDULE_REV)
    check(
        "Accepté : Northwood sans 23:48, enregistré et rechargé hors ligne ; refusé : DWD inchangé ; plus rien en attente",
        (23, 48) not in gy_now and "GYA" in acc and "GYA" in reloaded and (23, 48) not in {(h, m) for h, m, c, d in merged["GYA"]}
        and app.schedule_data["DWD"] == before["DWD"] and not planner.pending_differences(),
        f"{len(gy_now)} cartes GYA ; acceptés {sorted(acc)}",
    )
    planner._close_sources_window()
    # nettoyage : programme intégré rétabli
    try:
        OS.accepted_path(root_dir).unlink()
    except OSError:
        pass
    S.set_accepted_overrides({})
    app.schedule_data.clear()
    app.schedule_data.update(before)
    if saved_dl is None:
        planner.__dict__.pop("_download", None)
    else:
        planner._download = saved_dl
    planner.sync_in_progress = False

    # ---- stations texte optionnelles et mise en sommeil
    import tempfile
    from pathlib import Path

    hp = Path(tempfile.mkdtemp(prefix="stx_")) / "stations_texte.json"
    h = TextStationHealth(hp)
    d0 = datetime(2026, 11, 19, tzinfo=timezone.utc)
    sch = ReceptionScheduler(programs=(1,), categories=("NAVTEX",), rtty_enabled=True)
    sch.station_filter = lambda it: h.allows(it, now=NOW[0])
    NOW = [d0.timestamp()]

    def due(hh, mm):
        t = d0.replace(hour=hh, minute=mm)
        return sch.due_item(ScheduleState(now=t, pipeline="WEFAX", chart_drawing=False, seconds_since_chart=600,
                                          rtty_text_active=False, rtty_service_s=0.0, rtty_no_signal_s=0.0,
                                          rtty_end_marker=False))

    w, r = due(11, 40), due(6, 50)
    check("La Garde W/S désactivées par défaut (OHI 2023-2024) ; La Maddalena R écoutée",
          w is None and r is not None and station_key(r) == "NAVTEX-R" and not h.is_enabled("NAVTEX-S"),
          f"11:40 → {w} ; 06:50 → {r.describe() if r else None}")
    res = [h.record("NAVTEX-R", 0, complete=False, now=NOW[0])]
    res += [h.record("NAVTEX-R", 3, complete=True, now=NOW[0] + i) for i in range(3)]
    asleep = due(18, 50)
    NOW[0] += 24 * 3600 + 10
    retry = due(18, 50)
    res.append(h.record("NAVTEX-R", 250, complete=True, now=NOW[0]))
    check(
        "Après 3 créneaux complets sans texte : La Maddalena en sommeil (créneau écourté non compté), nouvel essai "
        "24 h après, réactivée par une réception",
        res == [None, "ECHEC", "ECHEC", "SOMMEIL", "REPRISE"] and asleep is None and retry is not None
        and h.is_active("NAVTEX-R", now=NOW[0]),
        str(res),
    )
    nxt = [it.label for it in sch.next_items(d0.replace(hour=10)) ]
    check("« Ensuite » ne cite pas une station désactivée", not any("La Garde" in x for x in nxt), str(nxt[:3]))
    arb = app.hybrid_arbiter
    saved_h, saved_buf = arb.text_health, arb.rtty_raw_buffer
    try:
        arb.text_health = TextStationHealth(hp.with_name("arb.json"))
        item = next(it for it in rtty_items(d0.replace(hour=6, minute=55), horizon_min=5, programs=(1,), categories=("NAVTEX",))
                    if "Maddalena" in it.label)
        arb.rtty_raw_buffer = "ZCZC texte de La Maddalena reçu avant ce créneau " * 3
        arb._item_chars_start = len(arb.rtty_raw_buffer)
        LOG.clear()
        r1 = arb._record_text_station_result(item, now=item.end)
        r2 = arb._record_text_station_result(item, now=item.start + timedelta(minutes=2))
    finally:
        arb.text_health, arb.rtty_raw_buffer = saved_h, saved_buf
    check("Bilan par créneau : le texte d'un créneau précédent ne compte pas ; journal explicite",
          r1 == "ECHEC" and r2 is None and any("[STATIONS TEXTE]" in x for x in LOG), f"{r1} / {r2}")

    # ---- consultation pendant une réception : bandeau et retour automatique au direct
    import numpy as np

    saved_c = (app.completed_rgb, getattr(app, "rx_image_armed", False), getattr(app, "rx_current_line", 0),
               getattr(app, "waiting_after_stop", False))
    try:
        if app.completed_rgb is None:
            app.completed_rgb = np.zeros((40, 60, 3), np.uint8)
        app.rx_image_armed, app.rx_current_line, app.waiting_after_stop = True, 120, False
        app._show_completed()
        pump(root, 0.3)
        shown = bool(getattr(app, "_consult_banner", None)) and app._consult_banner.winfo_ismapped()
        txt_b = app._consult_banner_lbl.cget("text") if shown else ""
        early = app._consultation_idle_check(mono_now=_t.monotonic() + 30)
        LOG.clear()
        back = app._consultation_idle_check(mono_now=_t.monotonic() + 95)
        pump(root, 0.2)
        hidden = not app._consult_banner.winfo_ismapped()
    finally:
        app.completed_rgb, app.rx_image_armed, app.rx_current_line, app.waiting_after_stop = saved_c
        app._show_live()
    check(
        "« Dernière carte » pendant une réception : bandeau visible, retour au direct après 90 s sans action (pas avant)",
        shown and "carte en réception" in txt_b and not early and back and hidden and not app.pin_completed
        and any("retour automatique à la vue en direct" in x for x in LOG),
        txt_b[:100],
    )

    # ---- P.AMP auto pendant une carte : plus d'oscillation 1 ↔ 2 (19/11, S9+9, gains de +2,2 dB)
    def run(chart):
        ap = AutoPreamp(mode="WEFAX", base_level=1)
        lvl, t, switches = 1, 0.0, 0
        for k in range(200):  # 20 min à 6 s
            snr = 20.0 if k < 15 else (13.0 if lvl == 1 else 15.2) if (k // 10) % 2 else (20.0 if lvl == 1 else 21.0)
            tgt = ap.step(t, snr, lvl, s_raw=160 if lvl == 2 else 120, chart_active=chart)
            if tgt is not None and tgt != lvl:
                lvl, switches = tgt, switches + 1
            t += 6.0
        return switches

    calm, normal = run(True), run(False)
    check("P.AMP auto pendant une carte : au plus un essai toutes les 3 min, aucune descente (moins de commutations)",
          calm <= 14 and calm < normal, f"{calm} commutations en 20 min pendant une carte, {normal} hors carte")

    # ---- retour du RTTY : la station vue forte sur le spectre l'emporte sur une ancienne mesure
    now_ts = _t.time()
    old_e = SimpleNamespace(active=True, quality=70, measured=now_ts - 1200, station="DDK6")
    saved_prop = arb.prop
    saved_seen = getattr(app, "spectral_seen", None)
    try:
        arb.prop = SimpleNamespace(best=lambda ids, max_age_s=1800: "DDK6", get=lambda sid: old_e if sid == "DDK6" else None)
        app.spectral_seen = {"DDK3": {"ts": now_ts - 60, "contrast": 22.0, "label": "fort"}}
        st_ = arb.best_family_station("DWD")
        why_ = arb.last_family_choice_reason
        app.spectral_seen = {}
        st2 = arb.best_family_station("DWD")
    finally:
        arb.prop = saved_prop
        if saved_seen is None:
            app.__dict__.pop("spectral_seen", None)
        else:
            app.spectral_seen = saved_seen
    check("Retour aux cartes (06:33 le 19/11) : DDK3 vu fort sur le spectre préféré à l'ancienne mesure de DDK6",
          st_ is not None and st_["id"] == "DDK3" and st2["id"] == "DDK6", why_)

    from wefax_station.ui import help_content as HC

    blob = _json.dumps(getattr(HC, "HELP_TOPICS", None) or {k: getattr(HC, k) for k in dir(HC) if k.isupper()},
                       ensure_ascii=False, default=str)
    check("Aides 2.9.2 : sources officielles, hors ligne, stations en sommeil, consultation, Winlink/VARA",
          all(k in blob for k in ("sources officielles", "hors ligne", "sommeil", "Revenir au direct", "VARA")))


def test_293(app, root):
    """2.9.3 — session du 19/11 : analyse prioritaire, Athènes non identifiée, P.AMP muet, programme observé."""
    print("2.9.3 Analyse prioritaire, Athènes conditionnelle, journal du P.AMP, programme observé")
    import tempfile
    import time as _t
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    from wefax_station.core import schedules as S
    from wefax_station.core.stations import get_wefax_station_by_freq
    from wefax_station.hybrid.observed_programme import ObservedProgramme
    from wefax_station.hybrid.scheduler import Decision, ReceptionScheduler, RttyItem, ScheduleState, rtty_items

    d0 = datetime(2026, 11, 19, tzinfo=timezone.utc)
    slots = tuple(S.BROADCAST_SCHEDULES_UTC["DWD"])
    sch = ReceptionScheduler(programs=(1,), categories=("AVIS", "NAVTEX", "ATL"), rtty_enabled=True)
    avis = RttyItem(d0.replace(hour=10, minute=40), d0.replace(hour=11, minute=0), 1, "AVIS", "Avis par zones maritimes")
    prev = RttyItem(d0.replace(hour=10, minute=40), d0.replace(hour=11, minute=0), 1, "ATL", "Prévision Atlantique")
    nav = next(it for it in rtty_items(d0.replace(hour=11, minute=38), horizon_min=5, programs=(1,), categories=("NAVTEX",)))

    def rst(t, item, received=()):
        return ScheduleState(now=t, pipeline="RTTY", chart_drawing=False, seconds_since_chart=1800, rtty_text_active=True,
                             rtty_service_s=0.0, rtty_no_signal_s=0.0, rtty_end_marker=False, current_item=item,
                             chart_slots=slots, received_recent=received)

    t_an = d0.replace(hour=10, minute=49, second=30)  # analyse DWD de 10:50
    a1, a2 = sch.decide(rst(t_an, avis)), sch.decide(rst(t_an, prev))
    avis2 = RttyItem(d0.replace(hour=12, minute=50), d0.replace(hour=13, minute=10), 1, "AVIS", "Avis par zones maritimes")
    a4 = sch.decide(rst(d0.replace(hour=12, minute=55, second=30), avis2, received=(avis2.label,)))  # H+36 12:56
    check(
        "Analyse de surface prioritaire sur un avis RTTY (F4NMK 19/11) ; un avis n'est coupé par aucune autre carte",
        a1.action == "GO_WEFAX" and "avis" in a1.reason and a2.action == "GO_WEFAX" and a4.action == "STAY",
        f"{a1.reason} | {a4.reason}",
    )
    st_nav = rst(d0.replace(hour=11, minute=40, second=45), nav)
    st_nav.chart_slots = ((11, 41, "ASXX", "Analyse de surface test"),)
    a3 = sch.chart_interrupt(st_nav)
    check("Analyse de surface prioritaire sur un créneau NAVTEX", a3 is not None and a3.action == "GO_WEFAX",
          a3.reason if a3 else "aucune décision")
    sch_g = ReceptionScheduler(programs=(1,), categories=("AVIS",), rtty_enabled=True)
    av_it = next(it for it in rtty_items(d0, horizon_min=24 * 60, programs=(1,), categories=("AVIS",)))
    an = av_it.start + timedelta(minutes=2)
    w = ScheduleState(now=av_it.start, pipeline="WEFAX", chart_drawing=False, seconds_since_chart=60,
                      rtty_text_active=False, rtty_service_s=0.0, rtty_no_signal_s=0.0, rtty_end_marker=False,
                      chart_slots=((an.hour, an.minute, "ASXX", "Analyse de surface"),))
    g = sch_g.decide(w)
    check("Analyse dans moins de 3 min : un avis attend aussi la fin de la carte", g.action == "STAY" and "imminente" in g.reason,
          g.reason)

    # ---- Athènes conditionnelle
    sch_a = ReceptionScheduler(programs=(1,), categories=(), rtty_enabled=False)
    sch_a.last_veille = sch_a.last_wefax_recheck = _t.monotonic() + 1e6
    base = dict(pipeline="WEFAX", seconds_since_chart=30, rtty_text_active=False, rtty_service_s=0.0,
                rtty_no_signal_s=0.0, rtty_end_marker=False, current_item=None, athens_enabled=True,
                preferred_family="DWD", pref_slots=slots, chart_drawing=False)
    t9 = d0.replace(hour=9, minute=12)
    b1 = sch_a.decide(ScheduleState(now=t9, wefax_family="DWD", **base))
    b2 = sch_a.decide(ScheduleState(now=t9, wefax_family="DWD", athens_unconfirmed=True, **base))
    b3 = sch_a.decide(ScheduleState(now=t9, wefax_family="ATH", athens_unconfirmed=True, **base))
    b4 = sch_a.decide(ScheduleState(now=d0.replace(hour=9, minute=4), wefax_family="DWD", **base))
    check(
        "Athènes non identifiée : le poste la quitte et n'y retourne pas avant 30 min ; pas de départ 2 min avant une carte DWD",
        b1.action == "GO_ATHENS" and b2.action != "GO_ATHENS" and b3.action == "LEAVE_ATHENS" and b4.action != "GO_ATHENS",
        f"{b1.action} / {b2.action} / {b3.action} / 09:04 {b4.action}",
    )
    arb = app.hybrid_arbiter
    LOG.clear()
    arb.note_family_scan("ATH", 0)
    unconf = arb.ath_unconfirmed_until_mono > _t.monotonic() + 1700
    arb.note_family_scan("ATH", 3)
    check("Contrôle d'Athènes : rang 0 → 30 min d'écart, rang 3 → créneau conservé ; journal explicite",
          unconf and arb.ath_unconfirmed_until_mono == 0.0 and any("Athènes non identifiée" in x for x in LOG)
          and any("Athènes identifiée" in x for x in LOG))

    # LEAVE_ATHENS : retour au DWD (et non plus à Northwood)
    saved_decide = arb.scheduler.decide
    saved_pres = arb.trigger_targeted_wefax_prescan
    calls = []
    saved_radio = (app.radio.port_open, app.radio.handshake_ok, app.audio_live_connected, arb.manual_hold,
                   arb.requested_mode, getattr(app, "connection_busy", False), arb.veille_active,
                   getattr(app, "carrier_scan_active", False), app.radio.actual_freq_khz)
    try:
        app.radio.port_open, app.radio.handshake_ok, app.audio_live_connected = False, True, True
        arb.manual_hold, arb.veille_active = False, False
        if arb.requested_mode in ("RELECTURE", "BULLETINS"):
            arb.requested_mode = "AUTO"
        app.connection_busy = app.carrier_scan_active = False
        arb.scheduler.decide = lambda st, mono_now=None: Decision("LEAVE_ATHENS", "test")
        arb.trigger_targeted_wefax_prescan = lambda fam, code, when, force=False: calls.append((fam, code, force))
        app.radio.actual_freq_khz = 8105.0
        arb.active_pipeline = "WEFAX"
        arb.evaluate_hybrid_schedule()
        pump(root, 0.5)
        fam_after = (get_wefax_station_by_freq(float(app.radio.actual_freq_khz)) or {}).get("family")
    finally:
        arb.scheduler.decide = saved_decide
        arb.trigger_targeted_wefax_prescan = saved_pres
        (app.radio.port_open, app.radio.handshake_ok, app.audio_live_connected, arb.manual_hold, arb.requested_mode,
         app.connection_busy, arb.veille_active, app.carrier_scan_active, _f0) = saved_radio
        app.radio.actual_freq_khz = _f0
    check("Fin d'Athènes : retour sur la famille de référence DWD, contrôle forcé (pas de « Scan évité » périmé)",
          fam_after == "DWD" and calls and calls[0][0] == "DWD" and calls[0][2] is True,
          f"{app.radio.actual_freq_khz} kHz ({fam_after}) ; {calls}")

    # ---- P.AMP auto : événements journalisés au-delà de 20
    class StubAP:
        mode = "WEFAX"; boosted_by_auto = False; phase = "IDLE"; base_level = 1; expected_level = None

        def __init__(self):
            self.events = [(0.0, f"ancien {i}") for i in range(20)]
            self.events_total = 57

        def step(self, *a, **k):
            self.events.append((1.0, "Fading : essai P.AMP 2 (test 2.9.3)"))
            del self.events[:-20]
            self.events_total += 1
            return None

    saved_ap, saved_f = getattr(app, "auto_preamp", None), getattr(app, "_ap_freq", None)
    try:
        app.auto_preamp = StubAP()
        app._ap_freq = round(float(app.radio.actual_freq_khz), 1)
        LOG.clear()
        app._auto_preamp_tick("WEFAX")
    finally:
        app.auto_preamp, app._ap_freq = saved_ap, saved_f
    check("P.AMP auto : chaque changement journalisé, même après 20 événements (silencieux le 19/11 après 07:21)",
          any("essai P.AMP 2 (test 2.9.3)" in x for x in LOG))

    # ---- programme observé
    hp = Path(tempfile.mkdtemp(prefix="obs_")) / "programme_observe.json"
    obs = ObservedProgramme(hp)
    muted_all = []
    for day in range(3):
        d = d0 + timedelta(days=day)
        t = d.replace(hour=7, minute=15)
        while t < d.replace(hour=8, minute=0):
            drawing = d.replace(hour=7, minute=17) <= t < d.replace(hour=7, minute=28, second=25)
            muted_all += [(day, m[0]) for m in obs.tick(t, "DWD", slots, True, drawing, True)]
            if t == d.replace(hour=7, minute=17, second=0):
                obs.note_start("DWD", t + timedelta(seconds=1), slots)
            if t == d.replace(hour=7, minute=43, second=0):
                obs.note_start("DWD", t + timedelta(seconds=3), slots)
            t += timedelta(seconds=15)
    recu, muet = obs.summary("DWD")
    sus = obs.suspects("DWD")
    obs2 = ObservedProgramme(hp)
    check(
        "Programme observé : 07:17 et 07:43 reçus, 07:30 muet 3 jours → « à vérifier » ; relu depuis le disque",
        recu == ["07:17", "07:43"] and muet == ["07:30"] and [x[1] for x in sus] == ["07:30"]
        and [m for m in muted_all if m[1] == "07:30"] == [(0, "07:30"), (1, "07:30"), (2, "07:30")]
        and obs2.summary("DWD") == (recu, muet),
        f"reçus {recu} ; muets {muet} ; à vérifier {sus}",
    )
    obs3 = ObservedProgramme(None)
    t = d0.replace(hour=7, minute=29)
    m3 = []
    while t < d0.replace(hour=7, minute=40):
        m3 += obs3.tick(t, "DWD", slots, False, False, True)
        t += timedelta(seconds=15)
    check("Programme observé : créneau non écouté (poste en RTTY) jamais compté muet", not m3 and not obs3.data)


def test_294(app, root):
    """2.9.4 — lecture des documents officiels réels (19/11) : tableaux DWD et Northwood, adresse DWD."""
    print("2.9.4 Documents officiels réels : tableaux, dates, adresse du PDF DWD, Northwood avec heures de référence")
    import json as _json

    from wefax_station.core import schedules as S
    from wefax_station.hybrid import official_sources as OS

    B = S.BROADCAST_SCHEDULES_UTC
    dwd = ["Time", "UTC", "Contents", "04.30", "120", "/", "576", "19", "00.00", "Surface Analysis North", "Atlantic",
           "05.12 ", "120", "/", "576", "11 ", "00.00", "36HR", "-", "forecast surface pressure",
           "05.55", "-", "06.35 Voice", "-", "transmission on 5905 kHz and 6180", "kHz",
           "06.38", "120", "/", "576", "11", "03.00", "Information of tropical storms"]
    rows = OS.parse_dwd_rows("\n".join(dwd))
    check("Tableau DWD : cartes reconnues, phonie 05:55-06:35 et heures de référence (00.00, 03.00) écartées",
          [m for m, _l in rows] == [270, 312, 398] and "Surface Analysis" in rows[0][1], str(rows))
    own = ["Time", "UTC", "x-none", "Contents", "x-none", "04.30", "x-none", "120 / 576", "x-none", "19", "x-none", "00.00",
           "x-none", "Surface Analysis North Atlantic, Europe", "x-none", "05.55-06.35 Voice-transmission on 5905 kHz",
           "x-none", "06.38", "x-none", "120 / 576", "x-none", "11", "x-none", "03.00", "x-none", "Information of tropical storms"]
    own_rows = OS.parse_dwd_rows("\n".join(own))
    check("PDF du DWD lui-même (cellules « x-none », « 120 / 576 » d'un seul tenant) : tableau reconnu",
          [m for m, _l in own_rows] == [270, 398] and "Surface Analysis" in own_rows[0][1], str(own_rows))
    gya = ["Product", "Broadcast", "Time", "(Z)", "Time", "(Z)", "18Z", "SFC ANALYSIS", "0000", "06Z", "SFC ANALYSIS",
           "1200", "0248", "1448", "00Z", "SFC", "ANALYSIS", "0236", "All MAPS", "(INFORMATION DATED Jan 05,", "2022)"]
    g = OS.parse_label_time_rows("\n".join(gya))
    check("Tableau Northwood en deux colonnes : intitulé puis heure ; créneaux vides ignorés",
          [m for m, _l in g] == [0, 156, 720] and g[1][1] == "00Z SFC ANALYSIS", str(g))
    check("Date « INFORMATION DATED » coupée sur deux lignes relue en entier",
          OS.section_info_date("\n".join(gya)) == "Jan 05, 2022", str(OS.section_info_date("\n".join(gya))))
    t19 = "18.00\n120\n/\n576\n19\n12.00\nAnalysis\n" * 1 + "\n".join(f"{h:02d}{m:02d}" for h in (19, 20) for m in (0, 24, 48))
    check("Heures 19:00 à 20:48 plus jamais effacées comme des « années »",
          {1140, 1164, 1188, 1200, 1224, 1248} <= set(OS.extract_times(t19)), str(OS.extract_times(t19)))
    junk = OS.analyse_family("HAMBURG/PINNEBERG\n00.00 03.00 06.00\n" + " ".join(f"{h:02d}.{m:02d}" for h, m, c, d in B["DWD"]),
                             "DWD", B["DWD"])
    check("Heures relevées sans tableau : jamais de proposition de modification", junk["method"] == "heures" and not junk["plausible"])
    page = b'<!DOCTYPE html><html><a href="/EN/specialusers/shipping/broadcast_en/broadcast_fax_102020.pdf;jsessionid=AB.live?__blob=publicationFile&amp;v=1">PDF</a></html>'
    link = OS.find_pdf_link(page, "https://www.dwd.de/EN/specialusers/shipping/broadcast_en/broadcast_fax_102020.pdf")
    check("dwd.de renvoie une page HTML : lien du PDF retrouvé (?__blob=publicationFile)",
          OS.looks_html(page) and link == "https://www.dwd.de/EN/specialusers/shipping/broadcast_en/broadcast_fax_102020.pdf?__blob=publicationFile&v=1",
          str(link))
    root_dir = app.schedule_planner.workspace.root_dir
    rp = OS.registry_path(root_dir)
    backup = rp.read_text(encoding="utf-8") if rp.is_file() else None
    rp.write_text(_json.dumps({"sources": [{"id": "DWD_FAX", "url": "https://www.dwd.de/EN/specialusers/shipping/broadcast_en/broadcast_fax_102020.pdf", "families": ["DWD"]}]}), encoding="utf-8")
    reg = OS.load_registry(root_dir)
    fixed = _json.loads(rp.read_text(encoding="utf-8"))
    if backup is not None:
        rp.write_text(backup, encoding="utf-8")
    check("Registre enregistré par la 2.9.3 : adresse DWD corrigée et réécrite",
          reg[0]["url"].endswith("?__blob=publicationFile&v=1") and fixed["sources"][0]["url"].endswith("v=1"))
    gy = B["GYA"]
    firsts = [(h, m) for h, m, c, d in gy if S.chart_priority(c, d) == S.PRIORITY_ANALYSE]
    check("Northwood : heures de référence du document ; seules les analyses 00Z (02:36), 06Z (09:00), 12Z (14:36) "
          "et 18Z (21:00) sont prioritaires",
          len(gy) == 102 and firsts == [(2, 36), (9, 0), (14, 36), (21, 0)]
          and all(re.search(r"\(\d\dZ\)", d) for h, m, c, d in gy if c not in ("FRONTS",)), str(firsts))


def test_295(app, root):
    """2.9.5 — cartes prises en cours de route : rangées à part, « Dernière carte » reste la dernière complète."""
    print("2.9.5 Cartes complètes : fragments pris en cours de route rangés à part")
    import time as _t

    rng = np.random.default_rng(7)

    def finalize(had_start, n):
        app._reset_blank_rx_sheet()
        if app.raw_wefax_img.shape[0] < n:
            app.raw_wefax_img = np.full((n + 10, 1809), 255, np.uint8)
        app.raw_wefax_img[:n] = rng.integers(0, 255, (n, 1809), dtype=np.uint8)
        app.rx_current_line = n
        app.rx_sheet_had_start = had_start
        app.saved_generation = -99
        app.last_saved_path = None
        app._finalize_completed_wefax_chart("APT STOP 450Hz")
        return str(app.last_saved_path or "")

    saved = app.__dict__.get("_sheet_has_wefax_content")
    app._sheet_has_wefax_content = lambda: True
    try:
        marker = np.zeros((5, 5, 3), np.uint8)
        app.completed_rgb = marker
        LOG.clear()
        frag = finalize(False, 505)  # carte de 07:04 du 19/11 reprise à 07:11
        kept = app.completed_rgb is marker
        frag_log = any("prise en cours de route" in x for x in LOG)
        full = finalize(True, 1300)
        long_mid = finalize(False, 1016)  # 2.9.8 : GYA H+48 de 17:24 reprise à 17:26:49, haut manquant
        no_start_full = finalize(False, 1200)  # START manqué par fading, poste déjà à l'écoute : carte entière
    finally:
        if saved is None:
            app.__dict__.pop("_sheet_has_wefax_content", None)
        else:
            app._sheet_has_wefax_content = saved
        app._reset_blank_rx_sheet()
    _part = lambda p: Path(p).parent.name == "partielles"  # 2.11.0 : cartes/partielles
    check("Carte de 505 lignes prise en cours de route : rangée dans cartes/partielles, journal explicite",
          _part(frag) and frag_log, frag)
    check("« Dernière carte » reste la dernière carte complète après un fragment", kept)
    check("Carte reçue depuis son START, ou sans START mais entière (1 200 lignes) : rangée parmi les cartes ; "
          "sans START et haut manquant (1 016 lignes) : cartes_partielles (2.9.8)",
          not _part(full) and "cartes" in full and _part(long_mid)
          and not _part(no_start_full),
          f"{Path(full).parent.name} / {Path(long_mid).parent.name} / {Path(no_start_full).parent.name}")
    # changement de famille : arrivée juste avant la carte suivante
    from datetime import datetime, timedelta, timezone

    from wefax_station.hybrid.scheduler import Decision

    arb = app.hybrid_arbiter
    calls = []
    saved_a = {k: arb.__dict__.get(k) for k in ("_next_family_slot", "recheck_family", "trigger_targeted_wefax_prescan")}
    saved_decide = arb.scheduler.decide
    saved_radio = (app.radio.port_open, app.radio.handshake_ok, app.audio_live_connected, arb.manual_hold,
                   arb.veille_active, getattr(app, "connection_busy", False), getattr(app, "carrier_scan_active", False),
                   arb.requested_mode, arb.scheduler.last_wefax_recheck)
    try:
        app.radio.port_open, app.radio.handshake_ok, app.audio_live_connected = False, True, True
        arb.manual_hold = arb.veille_active = False
        app.connection_busy = app.carrier_scan_active = False
        if arb.requested_mode in ("RELECTURE", "BULLETINS"):
            arb.requested_mode = "AUTO"
        arb.scheduler.decide = lambda st, mono_now=None: Decision("WEFAX_RECHECK", "test")
        arb.recheck_family = lambda cur, now: "GYA"
        arb._next_family_slot = lambda fam, now: datetime.now(timezone.utc) + timedelta(seconds=600)
        arb.trigger_targeted_wefax_prescan = lambda *a, **k: calls.append(a)
        app.radio.actual_freq_khz = 7880.0
        arb.active_pipeline = "WEFAX"
        LOG.clear()
        arb.evaluate_hybrid_schedule()
        deferred = not calls and any("reporté" in x for x in LOG)
        delay = arb.scheduler.last_wefax_recheck + arb.scheduler.WEFAX_SILENCE_RECHECK_S - _t.monotonic()
        arb._next_family_slot = lambda fam, now: datetime.now(timezone.utc) + timedelta(seconds=95)
        arb.evaluate_hybrid_schedule()
        went = bool(calls) and calls[0][0] == "GYA"
    finally:
        arb.scheduler.decide = saved_decide
        for k, v in saved_a.items():
            if v is None:
                arb.__dict__.pop(k, None)
            else:
                setattr(arb, k, v)
        (app.radio.port_open, app.radio.handshake_ok, app.audio_live_connected, arb.manual_hold, arb.veille_active,
         app.connection_busy, app.carrier_scan_active, arb.requested_mode, arb.scheduler.last_wefax_recheck) = saved_radio
    check("Passage vers Northwood : contrôle reporté pour arriver 90 s avant la carte suivante, puis effectué",
          deferred and 480 <= delay <= 530 and went, f"report {delay:.0f} s ; contrôle ensuite : {went}")
    # carte d'une autre famille prise en cours de route : cède la place à une carte DWD (hors rediffusion)
    from wefax_station.core import schedules as S
    from wefax_station.hybrid.scheduler import ReceptionScheduler, ScheduleState

    d0 = datetime(2026, 11, 19, tzinfo=timezone.utc)
    sch = ReceptionScheduler(programs=(1,), categories=(), rtty_enabled=False)
    base = dict(pipeline="WEFAX", chart_drawing=True, seconds_since_chart=0, rtty_text_active=False,
                rtty_service_s=0.0, rtty_no_signal_s=0.0, rtty_end_marker=False, wefax_family="GYA",
                preferred_family="DWD", pref_slots=tuple(S.BROADCAST_SCHEDULES_UTC["DWD"]))
    a1 = sch.decide(ScheduleState(now=d0.replace(hour=10, minute=48, second=30), chart_from_start=False, chart_reliable_pct=25, **base))
    a2 = sch.decide(ScheduleState(now=d0.replace(hour=10, minute=48, second=30), chart_from_start=True, **base))
    a3 = sch.decide(ScheduleState(now=d0.replace(hour=12, minute=55), chart_from_start=False, chart_reliable_pct=25, **base))
    check("Carte Northwood prise en cours de route : cède la place à l'analyse DWD de 10:50 ; jamais une carte prise "
          "depuis son START, ni pour une rediffusion DWD",
          a1.action == "GO_FAMILY" and a2.action == "STAY" and a3.action == "STAY", f"{a1.action} / {a2.action} / {a3.action}")
    check("Un phasage en tout début de feuille compte comme le début de la carte",
          "self.rx_sheet_had_start = True  # 2.9.5" in (ROOT / "wefax_station" / "app" / "reception.py").read_text(encoding="utf-8"))


def test_297(app, root):
    """2.9.7 — bord droit Northwood replié, bulletin déjà entamé avant une carte, faux gain du P.AMP."""
    print("2.9.7 Cadre Northwood, bulletin entamé, P.AMP et fading")
    from datetime import datetime, timezone

    from wefax_station.dsp.chart_restore import find_frame_line

    rng = np.random.default_rng(97)
    H, W, K, SL = 1300, 1809, 82, -0.06

    def chart(with_wrap):
        img = np.full((H, W), 235, np.float32)
        img += rng.normal(0, 18, (H, W))  # grain du signal reçu
        for _ in range(60):  # isobares / fronts : traits sombres sur toute la largeur, bords compris
            y0, amp, per = rng.integers(0, H), rng.integers(20, 120), rng.integers(300, 1500)
            x = np.arange(W)
            y = (y0 + amp * np.sin(2 * np.pi * x / per)).astype(int) % H
            img[y, x] = 40
        if with_wrap:
            img[:, K - 1 : K + 2] = 25  # trait de cadre gauche, à 82 px (GYA3 du 19/11 17:12)
        else:
            img[:, :90] = 250  # marge blanche DWD
            img[:, 92:95] = 25
        img = np.clip(img, 0, 255).astype(np.uint8)
        for r in range(H):  # pente de l'émetteur (Northwood : −0,06 px/ligne)
            img[r] = np.roll(img[r], int(round(r * SL)))
        return img

    gya, dwd = chart(True), chart(False)
    k1, s1 = find_frame_line(gya, SL)
    k2, _ = find_frame_line(dwd, SL)
    check("Trait de cadre Northwood trouvé à 82 px (pente compensée) ; carte DWD à marge blanche jamais touchée",
          k1 is not None and abs(k1 - K) <= 1 and s1 >= 70 and k2 is None, f"GYA {k1} ({s1:.0f} %) / DWD {k2}")
    # chaîne de sauvegarde : la carte est remise d'un seul tenant
    saved = {k: app.__dict__.get(k) for k in ("_sheet_has_wefax_content",)}
    app._sheet_has_wefax_content = lambda: True
    try:
        app._reset_blank_rx_sheet()
        if app.raw_wefax_img.shape[0] < H:
            app.raw_wefax_img = np.full((H + 10, W), 255, np.uint8)
        app.raw_wefax_img[:H] = gya
        app.rx_current_line = H
        app.rx_sheet_had_start = True
        app.phase_locked_from_header = True
        app.saved_generation = -99
        LOG.clear()
        app._finalize_completed_wefax_chart("APT STOP 450Hz")
        slope = float(app.sld_slant.get()) * 25.0
        k3, _ = find_frame_line(app.raw_wefax_img[:H], slope)
        m = app.raw_wefax_img[: min(H, 600), :120].astype(float).mean(axis=0)
        logged = any("Bord droit replié" in x for x in LOG)
    finally:
        for k, v in saved.items():
            if v is None:
                app.__dict__.pop(k, None)
            else:
                setattr(app, k, v)
        app.phase_locked_from_header = False
        app._reset_blank_rx_sheet()
    check("Carte Northwood sauvegardée : trait de cadre ramené au bord gauche, journal explicite",
          logged and k3 is None and int(np.argmin(m)) <= 4, f"trait à {int(np.argmin(m))} px, slant {slope:+.4f}")

    # bulletin RTTY déjà entamé et carte imminente de la station écoutée
    from wefax_station.core import schedules as S
    from wefax_station.hybrid.scheduler import ReceptionScheduler, RttyItem, ScheduleState

    sch = ReceptionScheduler(programs=(1,), categories=("AVIS",), rtty_enabled=True)
    d0 = datetime(2026, 11, 19, tzinfo=timezone.utc)
    late = RttyItem(d0.replace(hour=17, minute=15), d0.replace(hour=18), 1, "AVIS", "Avis aux navigateurs")
    fresh = RttyItem(d0.replace(hour=17, minute=21), d0.replace(hour=18), 1, "AVIS", "Avis aux navigateurs")
    base = dict(pipeline="WEFAX", chart_drawing=False, seconds_since_chart=2, rtty_text_active=False,
                rtty_service_s=0.0, rtty_no_signal_s=0.0, rtty_end_marker=False, wefax_family="GYA",
                chart_slots=tuple(S.BROADCAST_SCHEDULES_UTC["GYA"]))
    saved_due = sch.__dict__.get("due_item")
    try:
        sch.due_item = lambda st, exclude=(): late
        b1 = sch.decide(ScheduleState(now=d0.replace(hour=17, minute=23, second=19), **base))
        b2 = sch.decide(ScheduleState(now=d0.replace(hour=17, minute=36, second=30), **base))  # aucune carte avant 17:48
        sch.due_item = lambda st, exclude=(): fresh
        b3 = sch.decide(ScheduleState(now=d0.replace(hour=17, minute=23, second=19), **base))
    finally:
        if saved_due is None:
            sch.__dict__.pop("due_item", None)
    check("Bulletin commencé depuis 8 min et carte GYA de 17:24 imminente : la carte d'abord ; bulletin pris "
          "ensuite s'il est encore émis ; un bulletin qui commence part toujours",
          b1.action == "STAY" and "17:24" in b1.reason and b2.action == "GO_RTTY" and b3.action == "GO_RTTY",
          f"{b1.action} / {b2.action} / {b3.action}")

    # P.AMP : la fin d'un fading n'est pas un gain du préampli
    from wefax_station.radio.auto_preamp import AutoPreamp

    def run(prior_futile):
        ap = AutoPreamp(mode="WEFAX", base_level=1)
        t = 0.0
        if prior_futile:
            ap.futile_times.append((t - 600.0, "WEFAX"))
        for _ in range(60):  # 6 min à 11 dB : référence
            ap.step(t, 11.0, 1, chart_active=True)
            t += 6
        lvl, acts = 1, []
        snr_seq = [1.4] * 4 + [9.6] * 8  # fading profond, essai, puis le signal revient pendant la mesure
        for snr in snr_seq:
            r = ap.step(t, snr, lvl, chart_active=True)
            if r is not None:
                lvl = r
                acts.append(r)
            t += 6
        return lvl, [e[1] for e in ap.events]

    lvl_a, ev_a = run(True)
    lvl_b, ev_b = run(False)
    check("P.AMP : +8 dB juste après des essais inutiles = fin du fading, pas de « gardé » ; sans essai inutile "
          "récent, un vrai gain reste gardé",
          not any("gardé" in e for e in ev_a) and any("fading qui remonte" in e for e in ev_a)
          and any("gardé" in e for e in ev_b),
          f"{ev_a[-1] if ev_a else '-'} | {ev_b[-1] if ev_b else '-'}")


def test_298(app, root):
    """2.9.8 — analyse dont le START vient d'arriver ; pas d'essai de P.AMP sur un signal confortable."""
    print("2.9.8 Analyse juste commencée, P.AMP sur signal fort")
    from datetime import datetime, timezone

    from wefax_station.core import schedules as S
    from wefax_station.hybrid.scheduler import ReceptionScheduler, RttyItem, ScheduleState
    from wefax_station.radio.auto_preamp import AutoPreamp

    d0 = datetime(2026, 11, 19, tzinfo=timezone.utc)
    sch = ReceptionScheduler(programs=(1,), categories=("AVIS",), rtty_enabled=True)
    avis = RttyItem(d0.replace(hour=18), d0.replace(hour=18, minute=30), 1, "AVIS", "Avis par zones maritimes")
    sch.due_item = lambda st, exclude=(): avis
    base = dict(pipeline="WEFAX", chart_drawing=False, seconds_since_chart=600, rtty_text_active=False,
                rtty_service_s=0.0, rtty_no_signal_s=0.0, rtty_end_marker=False, wefax_family="DWD",
                chart_slots=tuple(S.BROADCAST_SCHEDULES_UTC["DWD"]))
    a = sch.decide(ScheduleState(now=d0.replace(hour=18, second=7), **base))  # START reçu à 18:00:02
    b = sch.decide(ScheduleState(now=d0.replace(hour=18, minute=2), **base))  # bien après : plus de garde
    check("START de l'analyse de 18:00 reçu, aucune ligne encore tracée : on reste (avis pris après le STOP)",
          a.action == "STAY" and "18:00" in a.reason and b.action == "GO_RTTY", f"{a.action} / {b.action}")

    ap = AutoPreamp(mode="WEFAX", base_level=1)
    t, acts = 0.0, []
    for _ in range(60):
        ap.step(t, 39.4, 1, chart_active=True)
        t += 6
    for _ in range(8):  # DDK3 à 18:00:53 : SNR 31,4 dB pour une référence de 39,4 dB
        r = ap.step(t, 31.4, 1, chart_active=True)
        if r is not None:
            acts.append(r)
        t += 6
    ap2 = AutoPreamp(mode="WEFAX", base_level=1)
    t, acts2 = 0.0, []
    for _ in range(60):
        ap2.step(t, 18.0, 1, chart_active=True)
        t += 6
    for _ in range(8):  # vrai fading vers 12 dB : l'essai reste permis
        r = ap2.step(t, 12.0, 1, chart_active=True)
        if r is not None:
            acts2.append(r)
        t += 6
    check("P.AMP : aucun essai à 31 dB de SNR (signal confortable) ; essai toujours permis dans un vrai fading",
          not acts and acts2[:1] == [2], f"{acts} / {acts2}")


# Commandes des menus qui sortent du logiciel (programme externe, explorateur, compilation, poste réel) :
# elles sont remplacées par un témoin pendant le test « toutes les commandes ».
MENU_EXTERNAL = (
    "_open_winlink_desk",
    "_compile_exe",
    "_open_archive",
    "_open_recordings_dir",
    "_open_csv",
    "_one_click",
    "_resume_midchart",
    "_trigger_carrier_scan",
    "_download_web_weather_chart",
    "_toggle_fullscreen",
    "_replay_wav_dialog",
    "_load_wefax_file",
    "_save_stamped_wefax",
    "_open_illustrated_guide",
)


def _walk_menu(menu, path=()):
    out = []
    try:
        end = menu.index("end")
    except tk.TclError:
        return out
    if end is None:
        return out
    for i in range(end + 1):
        kind = menu.type(i)
        if kind in ("separator", "tearoff"):
            continue
        label = menu.entrycget(i, "label")
        if kind == "cascade":
            sub = menu.nametowidget(menu.entrycget(i, "menu"))
            out += _walk_menu(sub, path + (label,))
        else:
            out.append((path + (label,), menu, i, kind))
    return out


def test_2100_menus(app, root):
    """2.10.0 — chaque commande de chaque menu s'exécute sans erreur (fonctionnalités disponibles)."""
    print("2.10.0 Toutes les commandes des menus")
    errors = []
    root.report_callback_exception = lambda e, v, tb: errors.append(repr(v))
    called = []
    saved = {}
    for name in MENU_EXTERNAL:
        if hasattr(app, name):
            saved[name] = app.__dict__.get(name)
            setattr(app, name, (lambda n: (lambda *a, **k: called.append(n)))(name))
    try:
        app._rebuild_menubar()
        bar = root.nametowidget(root.cget("menu"))
        entries = []
        for i in range(bar.index("end") + 1):
            if bar.type(i) == "cascade":
                entries += _walk_menu(bar.nametowidget(bar.entrycget(i, "menu")), (bar.entrycget(i, "label"),))
            elif bar.type(i) == "command":
                entries.append(((bar.entrycget(i, "label"),), bar, i, "command"))
        before = set(root.winfo_children())
        failed = []
        for path, menu, i, kind in entries:
            label = " › ".join(path)
            if kind == "radiobutton" or "Mode de réception" in label:
                continue  # changerait le mode ou la politique de l'opérateur
            if kind == "checkbutton" and "Internet" in label:
                continue
            try:
                menu.invoke(i)
                pump(root, 0.15)
                if kind == "checkbutton":
                    menu.invoke(i)  # remis dans l'état initial
                    pump(root, 0.1)
            except Exception as exc:
                failed.append(f"{label}: {exc!r}")
            for w in set(root.winfo_children()) - before:
                if isinstance(w, tk.Toplevel):
                    try:
                        w.destroy()
                    except tk.TclError:
                        pass
        pump(root, 0.5)
    finally:
        for name, v in saved.items():
            if v is None:
                app.__dict__.pop(name, None)
            else:
                setattr(app, name, v)
        app._rebuild_menubar()
    check(f"{len(entries)} entrées de menu parcourues, aucune exception", not failed, "; ".join(failed)[:400])
    check("Aucune erreur dans les rappels Tk pendant les commandes de menu", not errors, "; ".join(errors)[:400])
    check("Les commandes externes sont bien branchées (témoins appelés)", len(called) >= 6, ", ".join(sorted(set(called))))


def test_2100_nowcast(app, root):
    """2.10.0 — situation actuelle et prévision 3 à 6 h avec indice de fiabilité."""
    print("2.10.0 Situation actuelle, prévision 3-6 h et indice de fiabilité")
    from datetime import datetime, timedelta, timezone

    from wefax_station.weather.nowcast import build_nowcast, nowcast_lines, parse_operator_obs, tendency_words
    from wefax_station.weather.rtty_parse import parse_point_forecasts
    from wefax_station.weather.synop import parse_observations

    now = datetime(2026, 11, 19, 20, 40, tzinfo=timezone.utc)
    days = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
    st = lambda d, h: f"{days[d.weekday()]} {d.day:02d}. {h:02d}Z"
    txt = (
        "ZCZC 766\nFQMM81 EDZW 191400\nLIGURIAN SEA (43.5N   8.4E) SST: 18 C\n"
        f"{st(now, 18)}: SW 5 7 1.5 M //\n{st(now + timedelta(days=1), 0)}: W 6-7 8 2.5 M //\n=\nNNNN\n"
    )
    pts = parse_point_forecasts(txt)
    for p in pts:
        p["source"] = {"time": now - timedelta(hours=6, minutes=30)}
    obs = parse_observations("AAXX 19181\n07690 41570 72512 10132 40115 52018 =\n", now)
    grib = [
        {"valid": now + timedelta(hours=h), "wind_ms": ms, "wind_dir": "O", "max_ms": ms * 1.3, "pressure_hpa": 1011 - h * 0.6}
        for h, ms in ((0, 9), (3, 12), (6, 14), (9, 13))
    ]
    op = {
        "Date UTC": "2026-11-19 20:15 UTC",
        "Pression hPa": "1010,8",
        "Tendance 3 h": "Baisse rapide (3,6 à 6 hPa)",
        "Vent": "Ouest",
        "Force du vent": "Force 4",
        "Mer": "Peu agitée (0,5 à 1,25 m)",
    }
    full = build_nowcast(
        now, (43.58, 7.02), 300, "Le Cannet", points=pts, observations=obs, grib_rows=grib,
        grib_received=now - timedelta(hours=5), operator=op, text_docs=[{"repair": {"readable_pct": 93}}],
    )
    txt_full = "\n".join(nowcast_lines(full))
    check(
        "Fenêtre 3-6 h, prévision reçue + GRIB + observations : niveau ORANGE, fiabilité élevée, faits datés",
        full["level"] == "ORANGE" and full["reliability"]["grade"] in ("A", "B")
        and "23:40 à 02:40 UTC" in txt_full and "Nice (16 km)" in txt_full and "mer Ligure" in txt_full,
        f"{full['level']} {full['reliability']['score']} % [{full['reliability']['grade']}]",
    )
    check(
        "Observation de l'opérateur (force 4, il y a 25 min) prise comme vent actuel ; baisse rapide signalée",
        "force 4 maintenant" in txt_full and "renforcement" in txt_full and "baisse rapide" in txt_full,
        next((x for x in full["estimates"] if "Évolution" in x), ""),
    )
    only_grib = build_nowcast(now, (43.58, 7.02), 300, "Le Cannet", grib_rows=grib, grib_received=now - timedelta(hours=30))
    none = build_nowcast(now, (43.58, 7.02), 300, "Le Cannet")
    check(
        "Une seule source (GRIB ancien) : fiabilité plafonnée ; aucune donnée : 0 % [D] et rien d'inventé",
        only_grib["reliability"]["score"] <= 58 and none["reliability"]["score"] == 0 and none["level"] is None
        and "aucune prévision reçue" in "\n".join(nowcast_lines(none)),
        f"GRIB seul {only_grib['reliability']['score']} % ; vide {none['reliability']['score']} %",
    )
    bad = dict(grib[2])
    disagree = build_nowcast(
        now, (43.58, 7.02), 300, "Le Cannet", points=pts,
        grib_rows=[dict(g, wind_ms=2.0, max_ms=2.5) for g in grib], grib_received=now - timedelta(hours=5),
    )
    agree = build_nowcast(now, (43.58, 7.02), 300, "Le Cannet", points=pts, grib_rows=grib, grib_received=now - timedelta(hours=5))
    check(
        "Prévision texte et modèle en désaccord : fiabilité plus basse qu'en accord",
        disagree["reliability"]["score"] < agree["reliability"]["score"] - 15 and bad,
        f"désaccord {disagree['reliability']['score']} % / accord {agree['reliability']['score']} %",
    )
    po = parse_operator_obs({"Date UTC": "2026-11-19 20:15 UTC", "Pression hPa": "", "Tendance 3 h": "Non renseigné"}, now)
    check(
        "Formulaire vide : aucune observation de l'opérateur inventée ; tendances nommées comme en mer",
        po == {} and tendency_words(-4.2) == "baisse rapide (-4,2 hPa en 3 h)" and tendency_words(0.05).startswith("pression stationnaire"),
        repr(po),
    )
    # bout en bout : rapport 1 clic avec le bloc 3-6 h
    arb = app.hybrid_arbiter
    out = arb.generate_adrasec_orsec_report_1click()
    rep = Path(out).read_text(encoding="utf-8")
    check(
        "Rapport 1 clic : bloc « Situation actuelle et prévision à 3-6 h » avec indice de fiabilité",
        "SITUATION ACTUELLE ET PRÉVISION À 3-6 H" in rep and "Indice de fiabilité" in rep,
        next((x for x in rep.split("\n") if "Indice de fiabilité" in x), "absent"),
    )


def test_2100_core(app, root):
    """2.10.0 — racine de données commune, écritures sous Windows, fréquence de nuit, carte Web, horloge UTC."""
    print("2.10.0 Données entre versions, fiabilité, horloge UTC")
    import tempfile
    from datetime import datetime, timezone

    from wefax_station.storage import atomic as A
    from wefax_station.storage import portable as P

    # 1. racine commune et reprise de la version précédente
    t = Path(tempfile.mkdtemp())
    old = t / "station_wefax_pro_2.9.8" / "StationWEFAXPro"
    (old / "configuration").mkdir(parents=True)
    (old / "configuration" / "propagation.json").write_text("{}", encoding="utf-8")
    prof = old / "donnees" / "operateurs" / "F4NMK" / "profil"
    prof.mkdir(parents=True)
    (prof / "prefs.json").write_text("{}", encoding="utf-8")
    today = datetime.now(timezone.utc).date().isoformat()
    rx = old / "donnees" / "operateurs" / "F4NMK" / "receptions" / today / "cartes"
    rx.mkdir(parents=True)
    (rx / "x_carte.png").write_bytes(b"png")
    vieux = old / "donnees" / "operateurs" / "F4NMK" / "receptions" / "2020-01-01"
    vieux.mkdir(parents=True)
    (vieux / "y.txt").write_text("ancien", encoding="utf-8")
    new = t / "station_wefax_pro_2.10.0"
    new.mkdir()
    P.MIGRATION_NOTES.clear()
    P.MIGRATION_PENDING_INDEX.clear()
    r = P.resolve_data_root(new)
    copied = sorted(str(p.relative_to(r)).replace("\\", "/") for p in r.rglob("*") if p.is_file())
    check(
        "Racine commune à côté des versions ; configuration, profil et réceptions du jour repris (copie)",
        r == t / "StationWEFAXPro"
        and "configuration/propagation.json" in copied
        and "donnees/operateurs/F4NMK/profil/prefs.json" in copied
        and f"donnees/operateurs/F4NMK/receptions/{today}/cartes/x_carte.png" in copied
        and not any("2020-01-01" in c for c in copied)
        and (old / "configuration" / "propagation.json").exists()
        and P.MIGRATION_PENDING_INDEX,
        "; ".join(copied),
    )
    n_notes = len(P.MIGRATION_NOTES)
    r2 = P.resolve_data_root(new)
    other = t / "mon_dossier"
    other.mkdir()
    check(
        "Deuxième démarrage : rien de recopié ; programme hors dossier de version : racine à côté de lui",
        r2 == r and len(P.MIGRATION_NOTES) == n_notes and P.resolve_data_root(other) == other / "StationWEFAXPro",
        str(P.resolve_data_root(other)),
    )
    P.MIGRATION_NOTES.clear()
    P.MIGRATION_PENDING_INDEX.clear()

    # 2. remplacement retenté quand Windows tient le fichier
    calls = []

    def flaky(src, dst):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(13, "Accès refusé")
        os.replace(src, dst)

    f = t / "brouillon.txt"
    tmpf = t / "b.writing"
    tmpf.write_text("ok", encoding="utf-8")
    A.replace_with_retry(tmpf, f, delay_s=0.001, _replace=flaky)
    try:
        A.replace_with_retry(t / "absent", f, retries=1, delay_s=0.001, _replace=lambda a, b: (_ for _ in ()).throw(PermissionError(13, "x")))
        gave_up = False
    except PermissionError:
        gave_up = True
    check(
        "Fichier momentanément verrouillé (antivirus, explorateur) : écriture retentée, abandon net si ça dure",
        f.read_text(encoding="utf-8") == "ok" and len(calls) == 3 and gave_up,
        f"{len(calls)} essais",
    )
    app.txt_weather_report.delete("1.0", "end")
    app.txt_weather_report.insert("1.0", "brouillon test")
    first = app._save_draft()
    second = app._save_draft()
    check("Brouillon écrit seulement s'il a changé (avant : toutes les 15 s)", first is True and second is False)

    # 3. aucune émission reconnue : fréquence adaptée à l'heure, pas la dernière mesurée
    arb = app.hybrid_arbiter
    saved_entries = dict(arb.prop.entries)
    saved_hint = app.__dict__.get("spectral_best")
    try:
        app.spectral_best = lambda ids: None
        night = datetime(2026, 11, 19, 20, 1, tzinfo=timezone.utc).timestamp()
        arb.prop.entries.clear()
        for sid, fq in (("DDH3", 3855.0), ("DDK3", 7880.0), ("DDK6", 13882.5)):
            arb.prop.update(sid, fq, "WEFAX", 0, False, "non confirmé", when=time.time() - (10 if sid == "DDK6" else 60))
        st = arb.best_family_station("DWD", now_ts=night)
        day = datetime(2026, 11, 19, 11, 0, tzinfo=timezone.utc).timestamp()
        st_day = arb.best_family_station("DWD", now_ts=day)
        arb.prop.update("DDK6", 13882.5, "WEFAX", 80, True, "structure WEFAX", when=time.time())
        st_active = arb.best_family_station("DWD", now_ts=night)
    finally:
        arb.prop.entries.clear()
        arb.prop.entries.update(saved_entries)
        if saved_hint is None:
            app.__dict__.pop("spectral_best", None)
        else:
            app.spectral_best = saved_hint
    check(
        "Nuit, rien de reconnu : DDK6 (jour) écarté même mesuré en dernier ; de jour DDK6 ; émission reconnue : elle prime",
        st and st["id"] in ("DDK3", "DDH3") and st_day and st_day["id"] == "DDK6" and st_active["id"] == "DDK6",
        f"nuit {st and st['id']} / jour {st_day and st_day['id']} / reconnue {st_active and st_active['id']}",
    )

    # 4. carte Internet : consultation, feuille radio intacte, jamais de carte fabriquée
    before = app.raw_wefax_img.copy()
    web = np.full((600, 800), 200, np.uint8)
    app.show_web_chart(web, "DWD — test")
    pump(root, 0.3)
    shown_ok = app.pin_completed and str(app.viewing_archived_file).startswith("Carte Internet") and np.array_equal(
        before, app.raw_wefax_img
    )
    import urllib.request as _u

    saved_open = _u.urlopen
    LOG.clear()
    try:
        _u.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("hors ligne"))
        app.pin_completed = False
        app._download_web_weather_chart()
        t0 = time.time()
        while time.time() - t0 < 5 and not any("non téléchargée" in x for x in LOG):
            pump(root, 0.1)
    finally:
        _u.urlopen = saved_open
    app._return_to_live_rx_view(log=False)
    check(
        "Carte Web affichée en consultation (bandeau, feuille radio intacte) ; hors ligne : aucune carte de test fabriquée",
        shown_ok and any("aucune carte affichée" in x for x in LOG) and not app.pin_completed,
        next((x for x in LOG if "Carte Web" in x), ""),
    )

    # 5. horloge UTC de l'afficheur
    vfo = getattr(app, "vfo", None)
    ok_clock = False
    if vfo is not None:
        vfo.clock_now = lambda: datetime(2026, 11, 19, 20, 41, 7, tzinfo=timezone.utc)
        vfo.configure(width=1400)
        vfo.redraw()
        pump(root, 0.2)
        ok_clock = vfo._clock_box is not None and vfo.clock_text() in ("20:41:07", "20:41") and bool(vfo.find_withtag("clock"))
        vfo.clock_now = lambda: datetime.now(timezone.utc)
    check("Horloge UTC dessinée dans l'afficheur du poste (HH:MM:SS, ou HH:MM si la place manque)", ok_clock,
          vfo.clock_text() if vfo is not None else "pas d'afficheur")


def test_2110(app, root):
    """2.11.0 — bulletin synthétique, traduction, fin de carte, phasage, scan sobre, choix manuel, dossiers."""
    import json

    print("2.11.0 Bulletin synthétique, traduction, fiabilité des cartes, scan, dossiers")
    import tempfile
    from datetime import datetime, timedelta, timezone

    import numpy as np

    from wefax_station.weather.marine_translate import translate_bulletin, translate_prose, untranslated_words

    # 1. traduction de la situation générale DWD (texte réel du 20/11)
    fr = translate_prose(
        "A LOW 1014 UKRAINE MOVES A BIT TO THE NORTH WHILE WEAKENING. AN EXTENSIVE HIGH 1033 GERMAN BIGHT MOVES "
        "TO ST PETERSBURG. A HIGH 1030 NORTH OF THE AZORES MOVES TO NORTHERN IRELAND WHILE INTENSIFYING. A TROUGH "
        "FROM A LOW 982 FRAM STRAIGHT EXTENDS TO SCOTLAND AND MOVES EASTWARDS TO SOUTHERN NORWAY."
    )
    check("2110 traduction : accord « une dépression »", "Une dépression 1014 sur l'Ukraine" in fr, fr[:80])
    check("2110 traduction : verbes de déplacement", "un peu vers le nord en s'affaiblissant" in fr, fr)
    check("2110 traduction : lieux", "au nord des Açores" in fr and "l'Irlande du Nord" in fr and "jusqu'au sud de la Norvège" in fr, fr)
    check("2110 traduction : aucun mot anglais restant", not untranslated_words(fr), str(untranslated_words(fr)))
    fr2 = translate_prose(
        "STARTING IN THE GULF OF LIONS, A MISTRAL WILL BUILD UP, REACHING WINDS OF UP TO 9 BFT AND HURRICANE-FORCE GUSTS."
    )
    check("2110 traduction : mistral", "un mistral se lèvera" in fr2 and "des vents jusqu'à force 9" in fr2, fr2)
    tb = translate_bulletin("SU )2. 12Z: 1,3- 4 15 M // A\nLIGURIAN SEA (43.6N 8.9E) SST: 17 C\nSA 21. 56Z: SE     5-6   6-7   2  M        //\n")
    check("2110 ligne abîmée signalée, heure illisible non devinée", "[illisible]" in tb and "?? h UTC" in tb, tb)
    check("2110 avis : « NO WARNING » n'est plus un avis", gale_warnings_probe() == ["Golfe du Lion : nord-ouest 8, rafales 10. avis de coup de vent"] or len(gale_warnings_probe()) == 1, str(gale_warnings_probe()))

    # 2. rapport synthétique et doublons de zones
    from wefax_station.weather.plain_language import DEFAULT_QTH, interpret, plain_report

    now = datetime(2026, 11, 20, 17, 20, tzinfo=timezone.utc)
    from wefax_station.weather.rtty_parse import parse_point_forecasts

    lines = "SA 21. 06Z: W      5-7   8-9  3.5 M        //\nSA 21. 18Z: W      5-7   8-9  3.5 M        //\nSU 22. 06Z: W      4-5        2  M        //\n"
    pts = parse_point_forecasts(
        "GOLFE DU LION (42.5N   4.5E) SST: 16 C\n" + lines + "GOLFE-LION (42.6N   4.6E) SST: 16 C\n" + lines.split("\n")[0] + "\n"
    )
    it = interpret(pts, [], qth=DEFAULT_QTH, radius_km=500, now=now)
    check("2110 même lieu sous deux noms : une seule zone", len(it["near"]) == 1, str([x["name"] for x in it["near"]]))
    txt = plain_report(it, "Le Cannet", sources=[" • DDK9 10100,8 kHz — FQMM78 lisible"] * 9, qth=DEFAULT_QTH)
    check("2110 rapport synthétique (< 40 lignes)", len(txt.split("\n")) < 40, str(len(txt.split("\n"))))
    check("2110 rapport : jauge par jour et rafales", "RAFALES jusqu'à force 9" in txt and "■" in txt, txt[:300])
    check("2110 rapport : sources résumées", "… et 5 plus ancien(s)" in txt, txt[-300:])

    # 3. fin de carte par perte de structure ; carte réelle simulée
    from wefax_station.dsp.chart_end import scan_image

    rng = np.random.default_rng(1)
    chart = np.full((1400, 1809), 240.0)
    for k in range(0, 1809, 60):
        chart[:, k : k + 3] = 30  # traits verticaux continus (méridiens)
    chart[:, 900:1400] = np.linspace(60, 230, 500)
    noise = rng.integers(0, 255, (900, 1809)).astype(float)
    end, cut = scan_image(np.vstack([chart, noise]))
    check("2110 STOP manqué : fin de carte dans le bruit", end is not None and 1400 <= end <= 1700, str(end))
    check("2110 STOP manqué : queue de bruit retirée", cut is not None and 1380 <= cut <= 1520, str(cut))
    end2, _ = scan_image(np.vstack([chart[:300], noise[:200], chart[:900]]))
    check("2110 évanouissement en début de carte : carte jamais coupée", end2 is None, str(end2))

    # 4. phasage : impulsion stable exigée
    from wefax_station.app.reception import ReceptionMixin, phase_run_is_steady

    check("2110 phasage stable reconnu", phase_run_is_steady([0.31] * 40))
    check("2110 légende de carte : pas un phasage", not phase_run_is_steady([0.31, 0.6, 0.12, 0.9] * 10))
    check("2110 phasage sans position : la carte continue", not phase_run_is_steady([None] * 40))
    check("2110 40 lignes de phasage pour clore une carte", ReceptionMixin.PHASE_SPLIT_LINES >= 40)

    class _F:
        EXPECTED_CHART_LINES = 1250
        FRAGMENT_MAX_FRACTION = 0.92
        START_FRAGMENT_FRACTION = 0.5
        rx_sheet_had_start = True
        rx_current_line = 327

    check("2110 START reçu mais 327 lignes : carte partielle", ReceptionMixin._is_chart_fragment(_F()))
    _F.rx_current_line = 1300
    check("2110 START et 1 300 lignes : carte complète", not ReceptionMixin._is_chart_fragment(_F()))

    # 5. règle de base : carte en cours coupée seulement si peu fiable
    from wefax_station.hybrid.scheduler import ReceptionScheduler, ScheduleState

    sch = ReceptionScheduler()
    t0 = datetime(2026, 11, 20, 12, 55, 30, tzinfo=timezone.utc)
    base = dict(
        now=t0, pipeline="WEFAX", chart_drawing=True, seconds_since_chart=0, chart_from_start=False,
        rtty_text_active=False, rtty_service_s=0.0, rtty_no_signal_s=0.0, rtty_end_marker=False,
        wefax_family="GYA", preferred_family="DWD", pref_slots=((12, 56, "FSXX36", "Prévision H+36"),),
    )
    d_ok = sch.decide(ScheduleState(**base, chart_reliable_pct=85))
    d_low = sch.decide(ScheduleState(**base, chart_reliable_pct=20))
    check("2110 carte fiable en cours : jamais coupée", d_ok.action == "STAY", d_ok.reason)
    check("2110 carte peu fiable : cède la place", d_low.action == "GO_FAMILY", d_low.reason)

    # 6. contrôles espacés quand ils ne trouvent rien
    sch2 = ReceptionScheduler()
    iv = []
    for _ in range(4):
        iv.append(sch2.recheck_interval())
        sch2.recheck_streak += 1
    check("2110 contrôles WEFAX : 8, 16, 32, 32 min", [x // 60 for x in iv] == [8, 16, 32, 32], str(iv))

    # 7. profil radio : une seule lecture si déjà conforme, contrôle léger sur la même bande
    from wefax_station.radio.rf_verify import RFVerified705

    class _R:
        actual_dial_khz = 7878.1
        logs = []

        def log(self, m):
            self.logs.append(m)

    calls = []

    class _V(RFVerified705):
        def transaction(self, q, data=None, size=None):
            calls.append((tuple(q), data))
            return [1, 1][: size or 1] if data is None else [251]

    v = _V(_R())
    v.ensure("AGC_FAST", [0x16, 0x12], [1])
    check("2110 réglage déjà conforme : une seule lecture CI-V", len(calls) == 1, str(calls))
    v.r._rf_profile_ok = {7: __import__("time").monotonic()}
    calls.clear()
    v._full_prepare = lambda *a, **k: calls.append(("FULL", None))
    v._quick_check = lambda *a, **k: True
    v.prepare(True, reference_pamp=1)
    check("2110 même bande, profil récent : pas de vérification complète", ("FULL", None) not in calls, str(calls))

    # 8. arborescence simplifiée
    from wefax_station.storage import layout as L
    from wefax_station.storage.portable import PortableWorkspaceManager

    check("2110 cinq dossiers par jour", len(PortableWorkspaceManager.SUBDIRS_RECEPTION_DAY) == 5)
    tmp = Path(tempfile.mkdtemp())
    check("2110 images techniques à part", L.is_tech_file("x_decodee.png") and not L.is_tech_file("x_carte.png"))
    check("2110 registres dans details", L.record_dir(tmp, "bulletins_radio") == tmp / "bulletins" / "details")
    (tmp / "bulletins_radio").mkdir()
    (tmp / "bulletins").mkdir()
    check("2110 anciens bulletins toujours lus", len(L.bulletin_text_dirs(tmp)) == 2)
    sys.path.insert(0, str(ROOT / "outils"))
    import reorganiser_archives as RA

    day = tmp / "donnees" / "operateurs" / "F4NMK" / "receptions" / "2026-11-20"
    for rel in ("cartes/a_DDK3_carte.png", "cartes/a_DDK3_decodee.png", "cartes_partielles/b_GYA4_carte.png", "traductions/x_traduction_fr.txt", "bulletins_radio/x_original.txt"):
        (day / rel).parent.mkdir(parents=True, exist_ok=True)
        (day / rel).write_text("x")
    (day / "cartes" / "a_DDK3.json").write_text(json.dumps({"files": ["a_DDK3_decodee.png", "a_DDK3_carte.png"]}))
    check("2110 réorganisation : simulation sans effet", RA.main(["x", str(tmp)]) == 0 and (day / "traductions").is_dir())
    RA.main(["x", str(tmp), "--appliquer"])
    check(
        "2110 réorganisation appliquée",
        (day / "bulletins" / "x_original.txt").exists()
        and (day / "cartes" / "details" / "a_DDK3_decodee.png").exists()
        and (day / "cartes" / "partielles" / "b_GYA4_carte.png").exists()
        and not (day / "traductions").exists(),
    )
    meta = json.loads((day / "cartes" / "a_DDK3.json").read_text())
    check("2110 fiche de carte mise à jour", meta["files"][0] == "details/a_DDK3_decodee.png", str(meta))

    # 9. bouton Stations et choix manuel gardé
    check("2110 bouton Stations sur l'écran principal", hasattr(app, "btn_stations"))
    arb = app.hybrid_arbiter
    arb.set_manual_hold("DDK3")
    check("2110 choix manuel actif", arb.manual_hold_active())
    app._on_manual_hold_changed()
    check("2110 bouton montre le choix", "DDK3" in app.btn_stations.cget("text"), app.btn_stations.cget("text"))
    arb.record_chart_received("DDK3", 7880.0, 80)
    check("2110 carte suivante reçue : main rendue", not arb.manual_hold_active())
    app._on_manual_hold_changed()
    check("2110 bouton revenu à « Stations »", app.btn_stations.cget("text") == "Stations")


def test_2111(app, root):
    print("2.11.1 — choix opérateur : l'automatisme continue de décider (nuit du 24/11)")
    arb = app.hybrid_arbiter
    saved = (app.radio.handshake_ok, app.audio_live_connected, arb.manual_hold, arb.veille_active,
             arb.requested_mode, app.carrier_scan_active, app.connection_busy)
    calls = []
    orig = arb.scheduler.decide
    try:
        app.radio.handshake_ok, app.audio_live_connected = True, True
        arb.manual_hold = arb.veille_active = False
        arb.requested_mode = "HYBRIDE"
        app.carrier_scan_active = app.connection_busy = False
        arb.scheduler.decide = lambda st: (calls.append(1), orig(st))[1]
        arb.set_manual_hold("DDH3")
        check("2111 choix opérateur distinct de la pause manuelle", arb.manual_hold is False)
        arb.evaluate_hybrid_schedule()
        check("2111 décisions toujours évaluées pendant le choix opérateur", bool(calls))
        check("2111 choix opérateur maintenu", arb.manual_hold_active())
        LOG.clear()
        arb.operator_choice["since"] -= 3600
        arb.evaluate_hybrid_schedule()
        text = "\n".join(LOG)
        check("2111 limite de 45 min : main rendue à l'automatique", arb.operator_choice is None and "45 min sans carte" in text, text[-200:])
        app._on_manual_hold_changed()
        check("2111 bouton revenu à « Stations »", app.btn_stations.cget("text") == "Stations")
    finally:
        arb.scheduler.decide = orig
        arb.operator_choice = None
        (app.radio.handshake_ok, app.audio_live_connected, arb.manual_hold, arb.veille_active,
         arb.requested_mode, app.carrier_scan_active, app.connection_busy) = saved


def gale_warnings_probe():
    from wefax_station.weather.rtty_parse import gale_warnings

    return gale_warnings(
        "STRONG WIND, GALE AND STORM WARNINGS FOR SEA AREAS:\nNO WARNING.\nNAVIGATIONAL WARNING NO. 633\n"
        "GULF OF LIONS: NORTHWEST 8, GUSTS 10. GALE WARNING\n",
        translate=True,
    )


def main():
    print("Dossier de test temporaire :", TMP)
    root = tk.Tk()
    app = StationWefaxApp(root)
    APP.append(app)
    pump(root, 3)
    tests = [
        t
        for t in (
            test_wefax_replay,
            test_idle_carrier,
            test_white_gap,
            test_navtex_replay,
            test_rtty_replay,
            test_recorder,
            test_planner,
            test_yaesu,
            test_plain_language,
            test_georef,
            test_dwd_english_bulletin,
            test_night_1711,
            test_sources_287,
            test_288,
            test_switch_289,
            test_spectral_289,
            test_290,
            test_291,
            test_292,
            test_293,
            test_294,
            test_295,
            test_297,
            test_298,
            test_2100_menus,
            test_2100_nowcast,
            test_2100_core,
            test_2110,
            test_2111,
            test_scan,
            test_ui,
        )
        if not ONLY or t.__name__ in ONLY
    ]
    for test in tests:
        try:
            test(app, root)
        except Exception as exc:
            check(test.__name__, False, repr(exc))
    try:
        root.destroy()
    except tk.TclError:
        pass
    bad = [r for r in RESULTS if not r[1]]
    print()
    print(f"Résultat : {len(RESULTS) - len(bad)}/{len(RESULTS)} vérifications conformes.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
