#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyse hors ligne d'un enregistrement WAV (sans interface graphique, sans poste).

Usage :
  python outils/analyse_wav.py ENREGISTREMENT.wav            mode lu dans le .json associé
  python outils/analyse_wav.py ENREGISTREMENT.wav --mode WEFAX|RTTY|NAVTEX [--shift 800|850]
          [--baud 50] [--fsk-shift 450] [--centre 1900]

WEFAX  : produit ENREGISTREMENT_analyse.png (toutes les lignes), ENREGISTREMENT_confiance.png et un
         compte rendu : signaux START / phasage / STOP avec leur instant, erreur d'horloge mesurée,
         correction d'accord (AFC), proportion de pixels fiables.
RTTY / NAVTEX : produit ENREGISTREMENT_texte.txt et, en NAVTEX, la liste des messages ZCZC … NNNN
         avec leur taux d'erreur.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from wefax_station.storage.recorder import read_wav  # noqa: E402


def analyse_wefax(x, fs, shift, out_stem, ppm0=0.0):
    from wefax_station.dsp.wefax_demod import WefaxStreamDemodulator

    d = WefaxStreamDemodulator(fs)
    d.clock_ppm = ppm0
    rows, confs, events = [], [], []
    pos, rem, k = 0, 0.0, 0
    last = None
    while True:
        spl = d.samples_per_line()
        n = int(spl + rem)
        rem = spl + rem - n
        if pos + n > len(x):
            break
        r, flag, c, obs = d.process_line(x[pos : pos + n], shift=shift)
        if flag != last and flag is not None:
            events.append((pos / fs, flag, obs.get("ioc")))
        last = flag
        pos += n
        k += 1
        rows.append(r)
        confs.append((np.clip(c, 0, 1) * 255).astype(np.uint8))
    img = np.array(rows, dtype=np.uint8)
    conf = np.array(confs, dtype=np.uint8)
    Image.fromarray(img).save(str(out_stem) + "_analyse.png")
    Image.fromarray(conf).save(str(out_stem) + "_confiance.png")
    print(f"Lignes démodulées : {k} ({k / 120:.1f} min)")
    for t, f, ioc in events:
        lab = {"START_576": "START", "PHASE": "PHASAGE", "STOP": "STOP"}.get(f, f)
        print(f"  {int(t // 60):02d}:{t % 60:05.2f}  {lab}" + (f" (IOC {ioc})" if ioc else ""))
    print(f"Erreur d'horloge de la carte son mesurée : {d.clock_ppm:+.1f} ppm")
    print(f"Correction d'accord (AFC) : {d.afc_hz:+.1f} Hz")
    print(f"Pixels fiables : {np.mean(conf >= 128) * 100:.1f} %")
    print("Images :", str(out_stem) + "_analyse.png", "/", str(out_stem) + "_confiance.png")


def analyse_text(x, fs, protocol, baud, shift, centre, out_stem):
    from wefax_station.rtty.decoder import RTTYITA2Decoder

    dec = RTTYITA2Decoder(sample_rate=fs, baud=baud, shift_hz=shift, center_hz=centre, protocol=protocol)
    ring = np.zeros(int(0.6 * fs))
    text = ""
    blk = int(0.2 * fs)
    for i in range(0, len(x), blk):
        b = x[i : i + blk]
        ring = np.concatenate([ring, b])[-len(ring) :]
        t, _m = dec.feed_audio(b, ring_buffer_2s=ring)
        text += t
    Path(str(out_stem) + "_texte.txt").write_text(text, encoding="utf-8")
    m = dec.last_metrics
    print(
        f"Caractères restitués : {len(text)} | polarité {m['polarity_used']} | trames valides {m['frame_sync_ratio']}"
        f" | contraste M/S {m['mark_snr_db']}/{m['space_snr_db']} dB"
    )
    for msg in getattr(dec, "navtex_messages", []):
        print(
            f"  NAVTEX {msg['b1']}{msg['b2']}{msg['serial']} ({msg['subject']}) erreurs {msg['error_rate'] * 100:.1f} %"
            + (" [doublon]" if msg.get("duplicate") else "")
        )
    print("Texte :", str(out_stem) + "_texte.txt")
    print("-" * 60)
    print(text[:2000])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav")
    ap.add_argument("--mode", choices=["WEFAX", "RTTY", "NAVTEX"])
    ap.add_argument("--shift", type=float, help="WEFAX : excursion totale (800 ; DWD 850)")
    ap.add_argument("--baud", type=float)
    ap.add_argument("--fsk-shift", type=float)
    ap.add_argument("--centre", type=float, default=1900.0)
    a = ap.parse_args()
    x, fs, meta = read_wav(a.wav)
    mode = a.mode or str(meta.get("mode", "WEFAX"))
    stem = Path(a.wav).with_suffix("")
    print(
        f"{Path(a.wav).name} : {len(x) / fs:.1f} s à {fs} Hz, mode {mode}"
        + (f", station {meta.get('station')}" if meta.get("station") else "")
    )
    if mode == "WEFAX":
        dwd = str(meta.get("station", "")).startswith("DD")
        analyse_wefax(
            x, fs, a.shift or (850.0 if dwd else 800.0), stem, float(meta.get("horloge_audio_ppm", 0.0))
        )
    else:
        navtex = mode == "NAVTEX"
        baud = a.baud or (100.0 if navtex else 50.0)
        shift = a.fsk_shift or (170.0 if navtex else 450.0)
        analyse_text(x, fs, "NAVTEX_SITORB" if navtex else "RTTY_ITA2", baud, shift, a.centre, stem)


if __name__ == "__main__":
    main()
