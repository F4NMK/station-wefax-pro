"""Restauration d'une carte WEFAX guidée par la carte de confiance du démodulateur.

Le démodulateur fournit pour chaque pixel une confiance 0..1 (amplitude de porteuse, rafales QRN,
fréquence hors bande). Les défauts d'une réception HF sont surtout HORIZONTAUX (un évanouissement ou
une rafale abîme une ou plusieurs lignes entières), alors que le dessin de la carte est continu d'une
ligne à la suivante. La réparation se fait donc d'abord verticalement, à partir des lignes voisines
fiables, et seulement là où la confiance est basse : un pixel bien reçu n'est jamais modifié par cette
étape (le pointillé des terres et les petits caractères restent intacts).

Chaîne : 1. réparation des pixels peu fiables par interpolation verticale pondérée ;
2. suppression des stries de ligne (biais de niveau d'une ligne entière) ;
3. fond « papier » uniformisé (division par l'estimation du fond) ;
4. accentuation anisotrope : plus forte en horizontal, direction où le filtre vidéo du récepteur
   étale les traits verticaux ;
5. courbe de tons : papier blanc franc, traits fins noircis.
"""

import cv2
import numpy as np


def repair_low_confidence(img, conf, threshold=0.35, sigma_rows=1.6):
    """Remplace les pixels peu fiables par la moyenne verticale pondérée par la confiance des voisins."""
    f = np.asarray(img, dtype=np.float32)
    c = np.clip(np.asarray(conf, dtype=np.float32), 0.0, 1.0)
    if c.shape != f.shape:
        return f
    w = c * c
    k = max(3, int(round(sigma_rows * 3)) * 2 + 1)
    num = cv2.GaussianBlur(f * w, (1, k), sigmaX=0, sigmaY=sigma_rows, borderType=cv2.BORDER_REFLECT)
    den = cv2.GaussianBlur(w, (1, k), sigmaX=0, sigmaY=sigma_rows, borderType=cv2.BORDER_REFLECT)
    # trous plus longs : second passage plus large
    k2 = 13
    num2 = cv2.GaussianBlur(f * w, (3, k2), sigmaX=0.8, sigmaY=4.0, borderType=cv2.BORDER_REFLECT)
    den2 = cv2.GaussianBlur(w, (3, k2), sigmaX=0.8, sigmaY=4.0, borderType=cv2.BORDER_REFLECT)
    est = np.where(den > 0.08, num / np.maximum(den, 1e-6), num2 / np.maximum(den2, 1e-6))
    est = np.where((den <= 0.08) & (den2 <= 0.02), 250.0, est)  # aucune information : papier
    # seuil bas (0,35) : au-dessus, le pixel est gardé tel quel. Un seuil plus haut effaçait des traits
    # horizontaux fins réels reçus faiblement (isobares GYA4 du 15/11 coupées en tirets).
    mix = np.clip((threshold - c) / threshold, 0.0, 1.0)  # 0 si fiable, 1 si confiance nulle
    return f * (1.0 - mix) + est * mix


def destripe_rows(f, strength=0.85):
    row_med = np.median(f, axis=1, keepdims=True)
    row_smooth = cv2.GaussianBlur(row_med, (1, 35), 0)
    bias = np.clip(row_med - row_smooth, -24.0, 24.0)
    return np.clip(f - strength * bias, 0.0, 255.0)


def flatten_paper(f):
    u8 = np.clip(f, 0, 255).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
    bg = cv2.morphologyEx(u8, cv2.MORPH_CLOSE, kernel).astype(np.float32)
    bg = cv2.GaussianBlur(bg, (0, 0), 11.0)
    return np.clip(f / np.maximum(bg, 75.0) * 252.0, 0.0, 255.0)


def sharpen_anisotropic(f, amount_x=0.9, amount_y=0.35):
    bx = cv2.GaussianBlur(f, (0, 0), sigmaX=1.3, sigmaY=0.01)
    f = f + amount_x * (f - bx)
    by = cv2.GaussianBlur(f, (0, 0), sigmaX=0.01, sigmaY=0.9)
    return f + amount_y * (f - by)


def tone_curve(f, paper=205.0, ink=150.0):
    out = f.copy()
    p = out > paper
    out[p] = np.clip(paper + 5.0 + (out[p] - paper) * 1.3, 0.0, 255.0)
    i = out < ink
    out[i] = np.clip((out[i] - ink) * 1.3 + ink - 10.0, 0.0, 255.0)
    return np.clip(out, 0.0, 255.0)


def despeckle_unreliable(f, conf, threshold=0.3):
    """Médiane 3×3 uniquement sur les pixels peu fiables (le pointillé volontaire des cartes reste)."""
    if conf is None:
        return f
    c = np.asarray(conf, dtype=np.float32)
    if c.shape != f.shape:
        return f
    med = cv2.medianBlur(np.clip(f, 0, 255).astype(np.uint8), 3).astype(np.float32)
    return np.where(c < threshold, med, f)


def restore_chart(img, conf=None, repair=True, flatten=True, binarize=False):
    """Restauration complète. img uint8 (H×W), conf uint8 0..255 ou float 0..1 (même taille) ou None."""
    a = np.asarray(img, dtype=np.uint8)
    if a.size == 0:
        return a.copy()
    f = a.astype(np.float32)
    c = None
    if conf is not None:
        c = np.asarray(conf, dtype=np.float32)
        if c.shape != a.shape:
            c = None
        elif c.max() > 1.5:
            c = c / 255.0
    if repair:
        if c is not None:
            f = repair_low_confidence(f, c)
            f = despeckle_unreliable(f, c)
        f = destripe_rows(f)
        med = cv2.medianBlur(np.clip(f, 0, 255).astype(np.uint8), 3).astype(np.float32)
        impulse = np.abs(f - med) > 60.0
        if c is not None:
            impulse &= c < 0.8  # un point isolé bien reçu (pointillé, ponctuation) est conservé
        f[impulse] = med[impulse]
    if flatten:
        f = flatten_paper(f)
        f = sharpen_anisotropic(f)
        f = tone_curve(f)
    out = np.clip(f, 0, 255).astype(np.uint8)
    if binarize:
        out = cv2.adaptiveThreshold(out, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, 10)
    return out


# ---------------------------------------------------------------------------------- recadrage
def find_wrap_cut(img, conf=None, min_width=40, block=50):
    """Colonne où couper la carte pour qu'aucun dessin ne soit replié d'un bord à l'autre.

    Une ligne WEFAX commence par 25 ms de blanc (≈ 90 px sur 1809) et la carte a en général une bordure
    blanche : il existe une bande de colonnes blanche sur toute la hauteur. On la cherche par vote de
    blocs de 50 lignes (une ligne bruitée ne casse pas la bande), puis on coupe en son MILIEU : rien
    n'est coupé dans le dessin, même quand la bande blanche est bien plus large que l'impulsion
    (carte « Sea Surface Temperatures » du 15/11 : bande de 490 px). Sans bande nette et constante
    (carte partielle, dessin jusqu'au bord), rien n'est proposé.

    Retourne (colonne de coupe, largeur de la bande, score 0..100) ou (None, 0, 0).
    """
    a = np.asarray(img, dtype=np.float32)
    if a.ndim != 2 or a.shape[0] < 2 * block:
        return None, 0, 0.0
    h, w = a.shape
    if conf is not None and np.shape(conf) == a.shape:
        c = np.asarray(conf, dtype=np.float32)
        c = c / 255.0 if c.max() > 1.5 else c
        good = c >= 0.5
    else:
        good = np.ones_like(a, dtype=bool)
    votes = np.zeros(w)
    n_blocks = 0
    for r0 in range(0, h - block + 1, block):
        s = a[r0 : r0 + block]
        g = good[r0 : r0 + block]
        # lignes de carte : assez de pixels fiables, un peu d'encre, pas une ligne de bruit (> 45 % sombre)
        dark = (s < 170).mean(axis=1)
        ok = (g.mean(axis=1) > 0.6) & (dark > 0.004) & (dark < 0.45)
        if ok.sum() < block // 3:
            continue
        n_blocks += 1
        col_white = ((s[ok] > 200) | ~g[ok]).mean(axis=0) >= 0.97
        tiled = np.tile(col_white.astype(np.uint8), 3)
        closed = cv2.morphologyEx(tiled[None, :], cv2.MORPH_CLOSE, np.ones((1, 5), np.uint8))[0][w : 2 * w]
        votes += closed
    if n_blocks < 4:
        return None, 0, 0.0
    frac = votes / n_blocks
    band = frac >= 0.75
    if band.all() or not band.any():
        return None, 0, 0.0
    start = int(np.argmin(band))
    runs, run_len, run_start = [], 0, None
    for k in range(1, w + 1):
        x = (start + k) % w
        if band[x]:
            if run_len == 0:
                run_start = x
            run_len += 1
        else:
            if run_len:
                runs.append((run_len, run_start))
            run_len = 0
    if run_len:
        runs.append((run_len, run_start))
    runs.sort(reverse=True)
    if not runs or runs[0][0] < min_width:
        return None, (runs[0][0] if runs else 0), 0.0
    best_len, best_start = runs[0]
    cut = (best_start + best_len // 2) % w
    support = float(np.mean(frac[[(best_start + k) % w for k in range(best_len)]]))
    score = 100.0 * min(1.0, best_len / 80.0) * support * min(1.0, n_blocks / 8.0)
    return int(cut), int(best_len), float(np.clip(score, 0.0, 99.0))


def trim_blank_rows(img, conf=None, keep=12, flat_std=5.0):
    """Retire les lignes uniformes (porteuse de repos) en tête et en queue ; garde `keep` lignes de marge.

    Ne touche jamais une ligne qui contient du dessin : seule une suite de lignes parfaitement uniformes
    aux extrémités est retirée. Retourne (premiere_ligne, derniere_ligne_exclue).
    """
    a = np.asarray(img, dtype=np.float32)
    n = a.shape[0]
    if n < 2 * keep + 10:
        return 0, n
    flat = (a.std(axis=1) < flat_std) | ((a < 170).mean(axis=1) < 0.0015)
    top = 0
    while top < n and flat[top]:
        top += 1
    bottom = n
    while bottom > top and flat[bottom - 1]:
        bottom -= 1
    if bottom - top < 40:
        return 0, n
    return max(0, top - keep), min(n, bottom + keep)


def find_frame_line(img, slope_px_per_line=0.0, search_frac=0.08, block=60):
    """2.9.7 — Trait de cadre gauche d'une carte dont le bord droit a été replié à gauche.

    Northwood (GYA) dessine jusque dans l'impulsion de phasage : la carte de 17:12 UTC du 19/11, calée sur
    le phasage, montrait les 82 derniers px de son bord droit À GAUCHE de son trait de cadre (la colonne 0
    était du dessin, continu avec la dernière colonne). Les cartes DWD, elles, commencent par une marge
    blanche : rien à faire.

    On cherche, dans les `search_frac` premiers pourcents (pente déjà compensée), une colonne nettement plus
    sombre que la médiane, étroite, présente au même endroit dans la plupart des blocs de lignes, avec du
    dessin (pas une marge blanche) à sa gauche. Retourne (colonne, score 0..100) ou (None, 0).
    """
    a = np.asarray(img, dtype=np.float32)
    if a.ndim != 2 or a.shape[0] < 4 * block:
        return None, 0.0
    h, w = a.shape
    if abs(slope_px_per_line) > 1e-6:
        a = a.copy()
        for r in range(h):
            s = int(round(r * slope_px_per_line))
            if s:
                a[r] = np.roll(a[r], -s)
    lim = max(20, int(search_frac * w))
    m = a.mean(axis=0)
    med = float(np.median(m))
    k = int(np.argmin(m[:lim]))
    if k < 12 or m[k] > 0.55 * med:
        return None, 0.0
    # étroit : à ±8 px, on retrouve le fond de la carte
    if min(m[max(0, k - 8)], m[min(w - 1, k + 8)]) < 0.8 * med:
        return None, 0.0
    # dessin à gauche du trait (pas une marge blanche ni une bande uniforme)
    left = a[:, : max(1, k - 3)]
    if left.mean() > 230.0 or left.std() < 35.0:
        return None, 0.0
    # présent au même endroit sur toute la hauteur
    hits = tot = 0
    for r0 in range(0, h - block + 1, block):
        tot += 1
        kk = int(np.argmin(a[r0 : r0 + block, :lim].mean(axis=0)))
        hits += abs(kk - k) <= 2
    support = hits / max(1, tot)
    if support < 0.7:
        return None, 0.0
    contrast = 1.0 - float(m[k]) / med
    score = 100.0 * support * min(1.0, contrast / 0.5)
    return k, float(np.clip(score, 0.0, 99.0))
