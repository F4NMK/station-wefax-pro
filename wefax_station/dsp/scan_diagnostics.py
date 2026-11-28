"""Évaluation spectrale d'un tampon audio pendant le scan (heuristiques expérimentales)."""

import numpy as np
from scipy import signal as sp_signal


def assess_scan_audio(audio, fs):
    r = dict(
        proxy_db=None,
        occupancy=None,
        span_hz=None,
        clip_ratio=None,
        rms_dbfs=None,
        candidate=False,
        reasons=[],
        verdict="invalid",
    )
    x = np.asarray(audio, dtype=float)
    if x.ndim != 1 or fs < 8000 or len(x) < int(0.45 * fs):
        r["reasons"] = ["invalid_buffer_or_sample_rate"]
        return r
    if not np.isfinite(x).all():
        r["reasons"] = ["nonfinite_samples"]
        return r
    r["clip_ratio"] = float(np.mean(np.abs(x) >= 0.995))
    x = x - np.mean(x)
    rms = float(np.sqrt(np.mean(x * x)))
    r["rms_dbfs"] = float(20 * np.log10(max(rms, 1e-12)))
    if rms < 1e-6:
        r.update(verdict="silence", reasons=["silence"])
        return r
    f, p = sp_signal.welch(x, fs, nperseg=min(len(x), int(fs * 0.25)))
    band = (f >= 1400) & (f <= 2400)
    ref = ((f >= 700) & (f <= 1200)) | ((f >= 2600) & (f <= 2900))
    floor = max(float(np.median(p[ref])), 1e-30)
    r["proxy_db"] = float(10 * np.log10(max(np.mean(p[band]) / floor, 1e-12)))
    j = np.flatnonzero(band)[int(np.argmax(p[band]))]
    r["peak_hz"] = float(f[j])
    r["peak_contrast_db"] = float(10 * np.log10(max(float(p[j]) / floor, 1e-12)))
    near = (f >= 1850) & (f <= 1950)
    jc = np.flatnonzero(near)[int(np.argmax(p[near]))]
    local = ((f >= 1650) & (f <= 2150)) & (np.abs(f - f[jc]) > 65)
    local_floor = max(float(np.median(p[local])), 1e-30)
    r["center_hz"] = float(f[jc])
    r["center_prominence_db"] = float(10 * np.log10(max(float(p[jc]) / local_floor, 1e-12)))
    narrow = np.abs(f - f[jc]) <= 25
    r["center_fraction"] = float(np.sum(p[narrow]) / max(float(np.sum(p[band])), 1e-30))
    r["center_candidate"] = bool(
        r["clip_ratio"] <= 0.01
        and r["rms_dbfs"] > -100
        and r["center_prominence_db"] >= 10
        and r["center_fraction"] >= 0.20
    )

    sos = sp_signal.butter(4, [1250, 2550], fs=fs, btype="bandpass", output="sos")
    z = sp_signal.hilbert(sp_signal.sosfilt(sos, x))
    env = np.abs(z)[1:]
    freq = np.angle(z[1:] * z[:-1].conj()) * fs / (2 * np.pi)
    edge = max(1, int(0.025 * fs))
    env, freq = env[edge:-edge], freq[edge:-edge]
    good = env > max(0.25 * np.median(env), 1e-12)
    if not good.any():
        r["reasons"] = ["no_valid_envelope"]
        return r
    r["occupancy"] = float(np.mean(good & (freq >= 1400) & (freq <= 2400)))
    q05, q95 = np.percentile(freq[good], [5, 95])
    r["span_hz"] = float(q95 - q05)
    reasons = []
    if r["clip_ratio"] > 0.01:
        reasons.append("clipped_above_1pct")
    if r["proxy_db"] < 6:
        reasons.append("proxy_below_6dB")
    if r["occupancy"] < 0.70:
        reasons.append("occupancy_below_70pct")
    if r["span_hz"] < 100:
        reasons.append("steady_tone_unidentified")
    elif not 150 <= r["span_hz"] <= 1100:
        reasons.append("span_outside_150_1100Hz")
    r.update(
        candidate=not reasons,
        reasons=reasons,
        verdict="modulation_compatible_unconfirmed" if not reasons else "criteria_not_met",
    )
    return r
