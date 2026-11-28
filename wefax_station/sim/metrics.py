"""Mesures de qualité pour le banc d'essai."""

import numpy as np


def cer(reference, decoded):
    """Taux d'erreur caractère (distance de Levenshtein / longueur de référence)."""
    a, b = reference, decoded
    if not a:
        return 0.0 if not b else 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / len(a)


def image_score(reference, decoded):
    """Compare une carte décodée à la référence : meilleur recalage (décalage circulaire horizontal,
    décalage vertical, inversion vidéo exclue) puis corrélation et PSNR.
    """
    ref = np.asarray(reference, dtype=np.float64)
    dec = np.asarray(decoded, dtype=np.float64)
    if dec.size == 0:
        return {"corr": 0.0, "psnr_db": 0.0, "dx": 0, "dy": 0}
    w = min(ref.shape[1], dec.shape[1])
    ref = ref[:, :w]
    dec = dec[:, :w]
    best = (-2.0, 0, 0)
    for dy in range(-4, 5):
        r0, d0 = max(0, -dy), max(0, dy)
        h = min(len(ref) - r0, len(dec) - d0)
        if h < 20:
            continue
        a = ref[r0 : r0 + h]
        b = dec[d0 : d0 + h]
        pa = a.mean(axis=0) - a.mean()
        pb = b.mean(axis=0) - b.mean()
        xc = np.fft.irfft(np.fft.rfft(pa) * np.conj(np.fft.rfft(pb)), n=w)
        dx = int(np.argmax(xc))
        bb = np.roll(b, dx, axis=1)
        c = float(np.corrcoef(a.ravel(), bb.ravel())[0, 1])
        if c > best[0]:
            best = (c, dx, dy)
    c, dx, dy = best
    r0, d0 = max(0, -dy), max(0, dy)
    h = min(len(ref) - r0, len(dec) - d0)
    a = ref[r0 : r0 + h]
    b = np.roll(dec[d0 : d0 + h], dx, axis=1)
    mse = float(np.mean((a - b) ** 2))
    return {
        "corr": round(c, 4),
        "psnr_db": round(10 * np.log10(255.0**2 / max(mse, 1e-9)), 2),
        "dx": dx,
        "dy": dy,
    }
