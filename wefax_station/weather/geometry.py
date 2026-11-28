"""Géométrie de carte (marge, slant) et calcul géostrophique."""

import math
import numpy as np
from scipy.ndimage import sobel, uniform_filter1d
from scipy.signal import find_peaks


def estimate_geometry(image):
    """Détection robuste de la bande verticale de synchronisation WEFAX (blanche ou noire)
    et de sa pente (slant) sur les 1809 colonnes circulaires.
    Retourne (decalage px, pente px/ligne, score de confiance 0..99).
    """
    a = np.asarray(image, dtype=np.uint8)
    if a.ndim != 2 or min(a.shape) < 60:
        return 0, 0.0, 0.0
    h, w = a.shape
    white_bands = []
    black_bands = []
    centres = []
    for inds in np.array_split(np.arange(h), min(28, max(8, h // 25))):
        patch = a[inds]
        dark_frac = float(np.mean(patch < 185))
        if not 0.008 < dark_frac < 0.80:
            continue
        w_prof = uniform_filter1d(
            np.mean(patch > 215, axis=0).astype(float), size=max(5, w // 180), mode="wrap"
        )
        b_prof = uniform_filter1d(
            np.mean(patch < 135, axis=0).astype(float), size=max(3, w // 260), mode="wrap"
        )
        if np.ptp(w_prof) < 0.03 and np.ptp(b_prof) < 0.03:
            continue
        white_bands.append(w_prof)
        black_bands.append(b_prof)
        centres.append(float(np.mean(inds)))
    if len(white_bands) < 5:
        return 0, 0.0, 0.0
    pw = np.asarray(white_bands)
    pb = np.asarray(black_bands)
    y = np.asarray(centres)
    best = None
    candidates = []
    for slope in np.linspace(-0.08, 0.08, 81):
        shifts = np.round(slope * y).astype(int)
        aw = np.array([np.roll(v, -s) for v, s in zip(pw, shifts)])
        ab = np.array([np.roll(v, -s) for v, s in zip(pb, shifts)])
        edge_grad = np.abs(np.roll(np.mean(aw, axis=0), -6) - np.roll(np.mean(aw, axis=0), 6))
        comb_w = np.quantile(aw, 0.35, axis=0) + 0.45 * edge_grad
        comb_b = np.quantile(ab, 0.65, axis=0) + 0.45 * edge_grad
        for mode_sign, combined, arr in ((1, comb_w, aw), (-1, comb_b, ab)):
            triple = np.tile(combined, 3)
            peaks, props = find_peaks(triple, prominence=0.018, width=(max(2, w // 600), w * 0.14))
            for i, pos in enumerate(peaks):
                if not w <= pos < 2 * w:
                    continue
                x = int(pos - w)
                prominence = float(props["prominences"][i])
                spread = float(np.std(arr[:, x]))
                support = float(np.mean(arr[:, x] > np.median(combined) + 0.02))
                merit = prominence * (0.4 + support) / (1.0 + 3.5 * spread)
                cand = (merit, x, slope, prominence, support, spread, mode_sign)
                candidates.append(cand)
                if best is None or merit > best[0]:
                    best = cand
    if best is None:
        return 0, 0.0, 0.0
    merit, x, slope, prom, support, spread, mode_sign = best
    arr_ref = pw if mode_sign == 1 else pb
    positions = []
    radius = max(36, w // 35)
    for profile, yy in zip(arr_ref, y):
        guess = x + slope * yy
        offsets = np.arange(-radius, radius + 1)
        vals = profile[(np.round(guess).astype(int) + offsets) % w]
        good = offsets[vals >= float(np.max(vals)) - 0.008]
        positions.append(guess + float(np.median(good)))
    fit = np.polyfit(y, np.asarray(positions), 1)
    residual = float(np.median(np.abs(np.asarray(positions) - np.polyval(fit, y))))
    score = 100.0 * min(1.0, max(0.45, support)) * min(1.0, prom / 0.045) * max(0.0, 1.0 - residual / 18.0)
    if abs(fit[0]) > 0.09:
        score = min(score, 45.0)
    return int(round(fit[1])) % w, float(fit[0]), float(np.clip(score, 0.0, 99.0))


def geostrophic_estimate(delta_hpa, spacing_km, latitude, low_bearing=None):
    values = [float(delta_hpa), float(spacing_km), float(latitude)]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Valeurs non finies")
    dp, distance, lat = values
    if dp <= 0 or distance <= 0:
        raise ValueError("Ecart de pression et distance doivent etre positifs")
    if not 5 <= abs(lat) <= 85:
        raise ValueError("Approximation non proposee hors des latitudes 5 a 85 degres")
    f = 2 * 7.292115e-5 * math.sin(math.radians(lat))
    gradient = dp * 100 / (distance * 1000)
    speed = gradient / (1.225 * abs(f))
    result = {
        "gradient_hpa_100km": dp / distance * 100,
        "geostrophic_ms": speed,
        "geostrophic_kmh": speed * 3.6,
        "geostrophic_kt": speed * 1.943844,
        "wind_from_deg": None,
        "surface_wind": None,
    }
    if low_bearing is not None:
        bearing = float(low_bearing)
        if not math.isfinite(bearing):
            raise ValueError("Azimut invalide")
        result["wind_from_deg"] = (bearing + (270 if lat > 0 else 90)) % 360
    return result


def local_line_axis(image):
    patch = np.asarray(image, dtype=float)
    if patch.ndim != 2 or min(patch.shape) < 25:
        return None
    gx = sobel(patch, axis=1)
    gy = sobel(patch, axis=0)
    a = float(np.mean(gx * gx))
    b = float(np.mean(gx * gy))
    c = float(np.mean(gy * gy))
    coherence = math.sqrt((a - c) ** 2 + 4 * b * b) / (a + c + 1e-12)
    angle = (math.degrees(0.5 * math.atan2(2 * b, a - c)) + 90) % 180
    return {"axis_image_deg": angle, "coherence": coherence, "isobar_confirmed": False}
