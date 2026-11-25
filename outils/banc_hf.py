#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Banc d'essai HF simulé : mesure la chaîne de décodage sur des conditions de propagation types.

Usage : python outils/banc_hf.py [wefax] [rtty] [navtex]      (par défaut : les trois, ≈ 5 à 10 min)

Conditions : bruit (SNR dans 3 kHz), fading Watterson « moderate » / « poor » / « flutter »,
parasites impulsifs (QRN), erreur d'accord, erreur d'horloge de la carte son, brouilleur.
WEFAX : corrélation carte décodée / carte émise (1 = parfait), détection START / STOP (sur 10 lignes).
RTTY / NAVTEX : taux d'erreur caractère (CER), moyenne sur trois tirages.
À relancer après toute modification d'un module de traitement du signal.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from wefax_station.sim.hf_channel import apply_channel  # noqa: E402
from wefax_station.sim.metrics import cer, image_score  # noqa: E402
from wefax_station.sim.signals import rtty_signal, sitorb_signal, wefax_broadcast  # noqa: E402

FS = 44100
SEEDS = (3, 4, 5)


def test_chart(lines=120):
    rng = np.random.default_rng(0)
    img = np.full((lines, 1809), 245.0)
    yy, xx = np.mgrid[0:lines, 0:1809]
    for k in range(6):  # isobares
        cx, cy, r = rng.uniform(200, 1600), rng.uniform(-200, lines + 200), rng.uniform(150, 600)
        d = np.abs(np.hypot(xx - cx, (yy - cy) * 3) - r)
        img[d < 3] = 20
    for k in range(40):  # texte / chiffres
        x0, y0 = int(rng.uniform(0, 1780)), int(rng.uniform(0, lines - 8))
        img[y0 : y0 + 7, x0 : x0 + 4] = rng.choice([20, 245], size=(7, 4))
    return img.astype(np.uint8)


def expected(chart):
    w = chart.shape[1]
    out = np.full(chart.shape, 255.0)
    frac = np.arange(w) / w
    body = frac >= 0.05
    pos = (frac[body] - 0.05) / 0.95 * (w - 1)
    for i, r in enumerate(chart):
        out[i, body] = np.interp(pos, np.arange(w), r)
    return out


WEFAX_CASES = [
    ("propre", dict(snr_db=30)),
    ("SNR 10 dB", dict(snr_db=10)),
    ("SNR 3 dB", dict(snr_db=3)),
    ("fading moyen 12 dB", dict(snr_db=12, fading="moderate")),
    ("fading fort 10 dB", dict(snr_db=10, fading="poor")),
    ("flutter 15 dB", dict(snr_db=15, fading="flutter")),
    ("QRN 15 dB", dict(snr_db=15, impulses_per_s=20, impulse_amp=15)),
    ("accord +40 Hz", dict(snr_db=15, freq_offset_hz=40)),
    ("horloge +120 ppm", dict(snr_db=20, ppm=120)),
    ("brouilleur 2 kHz", dict(snr_db=15, qrm_hz=2000, qrm_db=-6)),
]
TEXT_CASES = [
    ("propre", dict(snr_db=30)),
    ("SNR 5 dB", dict(snr_db=5)),
    ("SNR 2 dB", dict(snr_db=2)),
    ("fading moyen 15 dB", dict(snr_db=15, fading="moderate")),
    ("fading fort 12 dB", dict(snr_db=12, fading="poor")),
    ("QRN 12 dB", dict(snr_db=12, impulses_per_s=20, impulse_amp=15)),
    ("accord +30 Hz", dict(snr_db=12, freq_offset_hz=30)),
    ("horloge +200 ppm", dict(snr_db=12, ppm=200)),
]


def bench_wefax():
    from wefax_station.dsp.engine import WefaxSignalAndImageEngine

    chart = test_chart()
    exp = expected(chart)
    audio, info = wefax_broadcast(chart, fs=FS, phasing_lines=60, black_tail_s=1.0)
    print("\nWEFAX (IOC 576, 120 l/min)")
    print(f"  {'condition':22s} {'corrélation':>11s} {'START':>7s} {'STOP':>7s} {'ms/ligne':>9s}")
    for name, kw in WEFAX_CASES:
        corr, st, sp, ms = [], [], [], []
        for seed in SEEDS:
            y = apply_channel(audio, FS, seed=seed, **kw)
            e = WefaxSignalAndImageEngine(FS)
            e.fm_center_hz, e.fm_shift_hz = 1900.0, 800.0
            rows, flags, pos, rem, t0 = [], [], 0, 0.0, time.time()
            while True:
                spl = e.samples_per_line()
                n = int(spl + rem)
                rem = spl + rem - n
                if pos + n > len(y):
                    break
                r, f = e.demodulate_line_fm(y[pos : pos + n], 1809, True, True)
                rows.append(r)
                flags.append(f)
                pos += n
            ms.append((time.time() - t0) / max(1, len(rows)) * 1000)
            first = int(np.ceil(info["image_start_sample"] / (0.5 * FS)))
            corr.append(image_score(exp[1:-1], np.array(rows)[first : first + len(chart) - 2])["corr"])
            st.append(flags.count("START_576"))
            sp.append(flags.count("STOP"))
        print(
            f"  {name:22s} {np.mean(corr):11.3f} {np.mean(st):5.1f}/10 {np.mean(sp):5.1f}/10 {np.mean(ms):9.1f}"
        )


def bench_text(kind):
    from wefax_station.rtty.decoder import RTTYITA2Decoder

    if kind == "rtty":
        msg = "ZCZC FQXX60 EDZW 141200\nSEEWETTERBERICHT 33560 41/98 12345 NNNN\n" * 2
        sig = rtty_signal(msg, FS)
        cfg = dict(baud=50, shift_hz=450, center_hz=1900, protocol="RTTY_ITA2")
        print("\nRTTY DWD (ITA2, 50 Bd, shift 450 Hz)")
    else:
        msg = "ZCZC WE12\nMETEO FRANCE BULLETIN COTE MEDITERRANEE VENT OUEST 5 A 6 MER AGITEE\nNNNN\n"
        sig = sitorb_signal(msg, FS)
        cfg = dict(baud=100, shift_hz=170, center_hz=1900, protocol="NAVTEX_SITORB")
        print("\nNAVTEX (SITOR-B, 100 Bd, shift 170 Hz)")
    ref = msg.replace("\n", " ")
    for name, kw in TEXT_CASES:
        rates = []
        for seed in SEEDS:
            y = apply_channel(sig, FS, seed=seed, **kw)
            d = RTTYITA2Decoder(sample_rate=FS, **cfg)
            ring, text, rng, i = np.zeros(int(0.6 * FS)), "", np.random.default_rng(seed), 0
            while i < len(y):
                blk = y[i : i + int(rng.uniform(0.08, 0.35) * FS)]
                i += len(blk)
                ring = np.concatenate([ring, blk])[-len(ring) :]
                t, _ = d.feed_audio(blk, ring_buffer_2s=ring)
                text += t
            rates.append(cer(ref, text.replace("\r", "").replace("\n", " ")))
        print(f"  {name:22s} CER {np.mean(rates) * 100:5.1f} %")
    noise = np.random.default_rng(0).normal(0, 0.3, len(sig))
    d = RTTYITA2Decoder(sample_rate=FS, **cfg)
    junk = "".join(d.feed_audio(noise[i : i + 8000])[0] for i in range(0, len(noise), 8000))
    print(f"  {'bruit seul (squelch)':22s} {len(junk)} caractère(s) parasite(s)")


def main():
    which = sys.argv[1:] or ["wefax", "rtty", "navtex"]
    if "wefax" in which:
        bench_wefax()
    for k in ("rtty", "navtex"):
        if k in which:
            bench_text(k)


if __name__ == "__main__":
    main()
