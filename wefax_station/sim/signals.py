"""Générateurs de signaux audio (bande latérale supérieure, porteuse audio 1900 Hz).

Références :
* WEFAX — caractéristiques OMM / BoM « Technical characteristics of Voice and Fax HF transmissions » :
  porteuse 1900 Hz, blanc +400 Hz, noir −400 Hz, 120 lignes/min, IOC 576 ;
  START 5 s alternance noir/blanc à 300 Hz (675 Hz en IOC 288) ;
  phasage 60 lignes de 25 ms blanc + 475 ms noir ;
  chaque ligne d'image commence par 25 ms de blanc ;
  STOP 5 s alternance à 450 Hz puis 10 s de noir.
* RTTY — ITA2, 50 Bd, 1 bit de start, 5 bits (LSB d'abord), 1,5 bit de stop (DWD : shift 450 Hz, 85 Hz sur DDH47).
* NAVTEX — SITOR-B / CCIR 476 (ITU-R M.476/M.625), 100 Bd, shift 170 Hz, mots de 7 bits à 4 « B »,
  mode FEC : chaque caractère émis deux fois (DX puis RX quatre signaux plus tard).
"""

import numpy as np

from wefax_station.rtty.codes import (
    ITA2_ENCODE_LTRS,
    ITA2_ENCODE_FIGS,
    CCIR476_ENCODE_LTRS,
    CCIR476_ENCODE_FIGS,
)
from wefax_station.rtty.codes import (
    ITA2_LTRS_CODE,
    ITA2_FIGS_CODE,
    CCIR_LTRS,
    CCIR_FIGS,
    CCIR_ALPHA,
    CCIR_BETA,
)


def fm_from_frequency(freq_hz, fs, amplitude=0.6):
    """Signal à phase continue à partir d'une trajectoire de fréquence instantanée (Hz par échantillon)."""
    phase = 2.0 * np.pi * np.cumsum(np.asarray(freq_hz, dtype=np.float64)) / float(fs)
    return (amplitude * np.cos(phase)).astype(np.float64)


# ----------------------------------------------------------------------------- WEFAX
def wefax_broadcast(
    chart,
    fs=44100,
    shift_hz=800.0,
    center_hz=1900.0,
    ioc=576,
    phasing_lines=60,
    start_s=5.0,
    stop_s=5.0,
    black_tail_s=10.0,
    tune_white_s=0.0,
    lpm=120.0,
    include_start=True,
    include_stop=True,
):
    """Émission WEFAX complète. Renvoie (audio, infos)."""
    chart = np.asarray(chart, dtype=np.float64)
    black = center_hz - shift_hz / 2.0
    white = center_hz + shift_hz / 2.0
    line_s = 60.0 / lpm
    spl = line_s * fs  # échantillons par ligne (réel)
    parts = []
    t_acc = [0.0]

    def seg(duration_s, fn):
        n0 = int(round(t_acc[0] * fs))
        t_acc[0] += duration_s
        n1 = int(round(t_acc[0] * fs))
        t = np.arange(n0, n1) / fs
        parts.append(fn(t))

    def level(v):  # v : 0 (noir) .. 1 (blanc)
        return black + (white - black) * np.clip(v, 0.0, 1.0)

    if tune_white_s > 0:
        seg(tune_white_s, lambda t: np.full(len(t), white))
    start_hz = 300.0 if ioc == 576 else 675.0
    if include_start:
        seg(start_s, lambda t: level((np.sin(2 * np.pi * start_hz * t) >= 0).astype(float)))
    # phasage : 25 ms blanc puis 475 ms noir
    for _ in range(phasing_lines):
        seg(line_s, lambda t: level(((t * lpm / 60.0) % 1.0) < 0.05).astype(float))
    width = chart.shape[1]
    for row in chart:

        def line_fn(t, row=row):
            frac = (t * lpm / 60.0) % 1.0
            v = np.ones(len(t))
            body = frac >= 0.05
            pos = (frac[body] - 0.05) / 0.95 * (width - 1)
            v[body] = np.interp(pos, np.arange(width), row / 255.0)
            return level(v)

        seg(line_s, line_fn)
    if include_stop:
        seg(stop_s, lambda t: level((np.sin(2 * np.pi * 450.0 * t) >= 0).astype(float)))
        seg(black_tail_s, lambda t: np.full(len(t), black))
    freq = np.concatenate(parts)
    audio = fm_from_frequency(freq, fs)
    n_start = int(round((tune_white_s + (start_s if include_start else 0)) * fs))
    info = {
        "fs": fs,
        "samples_per_line": spl,
        "image_start_sample": int(round(n_start + phasing_lines * spl)),
        "phasing_start_sample": n_start,
        "lines": chart.shape[0],
        "ioc": ioc,
    }
    return audio, info


# ----------------------------------------------------------------------------- RTTY ITA2
def ita2_encode(text):
    """Texte -> liste de codes ITA2 (5 bits) avec inversions LTRS/FIGS (sans « unshift on space »)."""
    codes = []
    mode = None
    for ch in text.upper():
        if ch in ITA2_ENCODE_LTRS and ch not in (" ", "\r", "\n"):
            if mode != "L":
                codes.append(ITA2_LTRS_CODE)
                mode = "L"
            codes.append(ITA2_ENCODE_LTRS[ch])
        elif ch in ITA2_ENCODE_FIGS and ch not in (" ", "\r", "\n"):
            if mode != "F":
                codes.append(ITA2_FIGS_CODE)
                mode = "F"
            codes.append(ITA2_ENCODE_FIGS[ch])
        elif ch in (" ", "\r", "\n"):
            codes.append(ITA2_ENCODE_LTRS[ch])
    return codes


def rtty_signal(
    text,
    fs=44100,
    baud=50.0,
    shift_hz=450.0,
    center_hz=1900.0,
    stop_bits=1.5,
    idle_s=1.0,
    mark_high=True,
    amplitude=0.6,
):
    codes = [ITA2_LTRS_CODE] * 4 + ita2_encode(text) + [ITA2_LTRS_CODE] * 4
    halves = [1] * int(round(idle_s * baud * 2))  # repos sur mark, en demi-bits
    for c in codes:
        halves += [0, 0]
        for i in range(5):
            b = (c >> i) & 1
            halves += [b, b]
        halves += [1] * int(round(stop_bits * 2))
    halves += [1] * int(round(idle_s * baud * 2))
    spb_half = fs / baud / 2.0
    n = int(round(len(halves) * spb_half))
    idx = np.minimum((np.arange(n) / spb_half).astype(int), len(halves) - 1)
    lvl = np.asarray(halves)[idx]
    if not mark_high:
        lvl = 1 - lvl
    freq = center_hz + (lvl - 0.5) * shift_hz
    return fm_from_frequency(freq, fs, amplitude)


# ----------------------------------------------------------------------------- NAVTEX SITOR-B
def ccir476_encode(text):
    words = []
    mode = None
    for ch in text.upper():
        if ch in (" ", "\r", "\n"):
            words.append(CCIR476_ENCODE_LTRS[ch])
        elif ch in CCIR476_ENCODE_LTRS:
            if mode != "L":
                words.append(CCIR_LTRS)
                mode = "L"
            words.append(CCIR476_ENCODE_LTRS[ch])
        elif ch in CCIR476_ENCODE_FIGS:
            if mode != "F":
                words.append(CCIR_FIGS)
                mode = "F"
            words.append(CCIR476_ENCODE_FIGS[ch])
    return words


def sitorb_words(text, phasing_s=10.0, tail_s=2.0, baud=100.0):
    """Suite des mots émis (DX/RX entrelacés) en mode FEC collectif."""
    chars = ccir476_encode(text)
    slot_s = 7.0 / baud
    n_phase = max(4, int(round(phasing_s / slot_s / 2)))
    n_tail = max(4, int(round(tail_s / slot_s / 2)))
    # DX pairs : phasage (β en DX, α en RX), puis caractères ; RX = caractère k-2
    dx = [CCIR_BETA] * n_phase + chars + [CCIR_BETA] * n_tail
    stream = []
    for j, d in enumerate(dx):
        stream.append(d)
        k = j - n_phase - 2
        stream.append(chars[k] if 0 <= k < len(chars) else CCIR_ALPHA)
    return stream


def sitorb_signal(
    text, fs=44100, baud=100.0, shift_hz=170.0, center_hz=1700.0, b_high=True, phasing_s=10.0, amplitude=0.6
):
    stream = sitorb_words(text, phasing_s=phasing_s, baud=baud)
    bits = []
    for w in stream:
        for i in range(6, -1, -1):  # bit de poids fort en premier
            bits.append((w >> i) & 1)
    spb = fs / baud
    n = int(round(len(bits) * spb))
    lvl = np.asarray(bits)[np.minimum((np.arange(n) / spb).astype(int), len(bits) - 1)]
    if not b_high:
        lvl = 1 - lvl
    freq = center_hz + (lvl - 0.5) * shift_hz
    return fm_from_frequency(freq, fs, amplitude)
