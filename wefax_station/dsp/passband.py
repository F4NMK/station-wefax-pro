"""Mesure de la bande passante audio réelle du récepteur à partir du bruit.

Le bruit de bande (sans signal fort) prend la forme du filtre FI : on en déduit les bords à −6 dB.
Cela permet de vérifier, à chaque changement de fréquence, que la bande utile du mode (par exemple
1500–2300 Hz en WEFAX) est bien dans la bande passante, sans pente excessive.
"""

import numpy as np
from scipy import signal as sp_signal


def measure_passband(audio, fs, required=(1450.0, 2350.0)):
    x = np.asarray(audio, dtype=np.float64)
    if len(x) < int(0.5 * fs):
        return None
    x = x - np.mean(x)
    f, p = sp_signal.welch(x, fs=fs, nperseg=4096)
    keep = (f >= 50) & (f <= 4500)
    f, p = f[keep], p[keep]
    # lissage sur ~100 Hz puis référence = médiane des 30 % de bins les plus forts (robuste aux raies)
    k = max(1, int(round(100.0 / (f[1] - f[0]))))
    ps = np.convolve(p, np.ones(k) / k, mode="same")
    db = 10 * np.log10(ps + 1e-20)
    ref = float(np.median(np.sort(db)[-max(3, len(db) * 3 // 10) :]))
    inside = db >= ref - 6.0
    if not np.any(inside):
        return None
    idx = np.flatnonzero(inside)
    lo, hi = float(f[idx[0]]), float(f[idx[-1]])
    band = (f >= required[0]) & (f <= required[1])
    tilt = float(np.max(db[band]) - np.min(db[band])) if np.any(band) else 99.0
    # Tolérance de 100 Hz : en présence d'un signal fort, les bords mesurés suivent le signal lui-même.
    # Seul un filtre nettement trop étroit ou mal centré est signalé. La pente est informative.
    ok = lo <= required[0] + 100.0 and hi >= required[1] - 100.0
    return {
        "low_hz": round(lo),
        "high_hz": round(hi),
        "tilt_db": round(tilt, 1),
        "ok": bool(ok),
        "required": tuple(required),
    }
