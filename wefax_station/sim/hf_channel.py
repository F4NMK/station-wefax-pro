"""Modèle de canal HF pour les essais (signal audio réel en sortie de récepteur BLU).

Dégradations combinables :
* bruit blanc gaussien, SNR mesuré dans 3 kHz ;
* fading Watterson à deux trajets (Rayleigh, spectre Doppler gaussien) — profils proches de
  ITU-R F.1487 / CCIR 520 : « moderate » (retard 1 ms, étalement 0,5 Hz), « poor » (2 ms, 1 Hz),
  « flutter » (0,5 ms, 10 Hz) ;
* parasites impulsifs (QRN : orages, allumages) : impulsions amorties tirées selon un processus de Poisson ;
* décalage de fréquence (accord / dérive du poste) ;
* erreur d'horloge de la carte son (ppm) ;
* brouilleur (porteuse pure).
"""

import numpy as np
from scipy import signal as sp_signal

PROFILES = {
    "none": None,
    "moderate": (1.0e-3, 0.5),
    "poor": (2.0e-3, 1.0),
    "flutter": (0.5e-3, 10.0),
}


def _rayleigh_process(n, fs, spread_hz, rng):
    """Gain complexe de puissance moyenne 1, spectre Doppler gaussien d'étalement total spread_hz."""
    if spread_hz <= 0:
        return np.ones(n, dtype=np.complex128)
    fs_low = max(20.0 * spread_hz, 50.0)
    n_low = int(np.ceil(n / fs * fs_low)) + 8
    w = (rng.standard_normal(n_low) + 1j * rng.standard_normal(n_low)) / np.sqrt(2)
    sigma_hz = spread_hz / 2.0
    sigma_samples = fs_low / (2 * np.pi * sigma_hz)
    half = int(np.ceil(4 * sigma_samples))
    k = np.exp(-0.5 * (np.arange(-half, half + 1) / sigma_samples) ** 2)
    k /= np.sqrt(np.sum(k**2))
    g = np.convolve(w, k, mode="same")
    t_low = np.arange(n_low) / fs_low
    t = np.arange(n) / fs
    g_full = np.interp(t, t_low, g.real) + 1j * np.interp(t, t_low, g.imag)
    return g_full / np.sqrt(np.mean(np.abs(g_full) ** 2))


def apply_channel(
    x,
    fs,
    snr_db=None,
    fading="none",
    freq_offset_hz=0.0,
    ppm=0.0,
    impulses_per_s=0.0,
    impulse_amp=8.0,
    qrm_hz=None,
    qrm_db=-6.0,
    seed=1,
):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    p_sig = float(np.mean(x**2)) + 1e-20
    za = sp_signal.hilbert(x)
    t = np.arange(n) / fs
    prof = PROFILES.get(fading)
    if prof is not None:
        delay_s, spread = prof
        d = int(round(delay_s * fs))
        g1 = _rayleigh_process(n, fs, spread, rng)
        g2 = _rayleigh_process(n, fs, spread, rng)
        delayed = np.concatenate([np.zeros(d, dtype=np.complex128), za[: n - d]])
        za = (g1 * za + g2 * delayed) / np.sqrt(2.0)
    if freq_offset_hz:
        za = za * np.exp(2j * np.pi * freq_offset_hz * t)
    y = za.real
    if ppm:
        # le récepteur échantillonne à fs·(1+ppm·1e-6) : chaque seconde réelle contient plus d'échantillons
        eps = ppm * 1e-6
        n_out = int(n * (1 + eps))
        src = np.arange(n_out) / (1 + eps)
        y = np.interp(src, np.arange(n), y)
        n = len(y)
    if snr_db is not None:
        noise_var = p_sig / (10 ** (snr_db / 10.0)) * (fs / 2.0) / 3000.0
        y = y + rng.standard_normal(n) * np.sqrt(noise_var)
    if impulses_per_s > 0:
        k = rng.poisson(impulses_per_s * n / fs)
        pos = rng.integers(0, n, size=k)
        dur = int(0.002 * fs)
        tt = np.arange(dur) / fs
        peak = np.sqrt(2 * p_sig)
        for p in pos:
            burst = (
                impulse_amp
                * peak
                * np.exp(-tt / 0.0003)
                * np.cos(2 * np.pi * rng.uniform(300, 3000) * tt + rng.uniform(0, 6.28))
            )
            e = min(n, p + dur)
            y[p:e] += burst[: e - p] * rng.choice([-1, 1])
    if qrm_hz:
        y = y + np.sqrt(2 * p_sig * 10 ** (qrm_db / 10.0)) * np.cos(2 * np.pi * qrm_hz * np.arange(n) / fs)
    return y
