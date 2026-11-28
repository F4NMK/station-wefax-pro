"""Identification d'une émission WEFAX par sa signature normalisée (utilisé par le scan).

Un pic spectral (porteuse blanche 2300 Hz, raie fixe vers 1900 Hz…) ne prouve pas qu'une carte est
en cours : une porteuse pure, un brouilleur ou un signal numérique peuvent le produire. La signature
s'appuie sur la structure imposée par la spécification OMM (IOC 576, 120 lignes/min) :

* continuité verticale : deux lignes successives d'une carte se ressemblent (isobares, côtes, texte) ;
* signaux de service : START 300 Hz / 675 Hz, STOP 450 Hz, phasage (impulsion de 5 %) ;
* occupation : la fréquence instantanée reste dans 1500–2300 Hz (± marge) la majeure partie du temps.

Une porteuse fixe donne des lignes uniformes (aucune marge, aucune structure) ; du bruit donne des
lignes non corrélées ; un RTTY occupe deux raies sans structure de ligne.
"""

import numpy as np

from wefax_station.dsp.wefax_demod import WefaxStreamDemodulator

IMAGE_MIN_CORR = 0.5
IMAGE_MIN_STD = 12.0


def line_structure(rows, confs):
    """(corrélation médiane entre lignes successives, écart-type vidéo) sur des lignes démodulées."""
    rows = np.asarray(rows, dtype=np.float64)
    confs = np.asarray(confs, dtype=np.float64)
    corrs = []
    for a, b, ca, cb in zip(rows[:-1], rows[1:], confs[:-1], confs[1:]):
        m = (ca > 0.5) & (cb > 0.5)
        if np.sum(m) > 300 and np.std(a[m]) > 4 and np.std(b[m]) > 4:
            corrs.append(float(np.corrcoef(a[m], b[m])[0, 1]))
    # au moins 70 % des paires exploitables : quelques lignes structurées au milieu de lignes plates
    # (fin d'un signal STOP suivi du noir de fin) ne suffisent pas
    corr = round(float(np.median(corrs)), 3) if len(corrs) >= max(1, int(0.7 * (len(rows) - 1))) else 0.0
    sel = confs > 0.5
    std = round(float(np.std(rows[sel])) if np.any(sel) else 0.0, 1)
    return corr, std


def is_chart_structure(corr, std):
    """Vrai si des lignes ressemblent à une carte en cours (et non à une porteuse, du bruit ou du RTTY)."""
    return corr >= IMAGE_MIN_CORR and std >= IMAGE_MIN_STD


def wefax_signature(audio, fs, shift_hz=800.0):
    x = np.asarray(audio, dtype=np.float64)
    spl = int(0.5 * fs)
    n_lines = len(x) // spl
    res = {
        "lines": n_lines,
        "occupancy": 0.0,
        "line_corr": 0.0,
        "margin_contrast": 0.0,
        "video_std": 0.0,
        "apt": None,
        "verdict": "insuffisant",
        "confirmed": False,
    }
    if n_lines < 4:
        return res
    d = WefaxStreamDemodulator(fs)
    rows, confs, flags = [], [], []
    for k in range(n_lines):
        r, f, c, _ = d.process_line(x[k * spl : (k + 1) * spl], shift=shift_hz)
        rows.append(r.astype(np.float64))
        confs.append(c)
        flags.append(f)
    rows = np.array(rows[1:])  # la première ligne sert à amorcer les filtres
    confs = np.array(confs[1:])
    flags = flags[1:]
    occ = float(np.mean(confs))
    res["occupancy"] = round(occ, 3)
    for f in ("START_576", "STOP", "PHASE"):
        if flags.count(f) >= 2:
            res["apt"] = f
    # continuité verticale
    res["line_corr"], res["video_std"] = line_structure(rows, confs)
    # marge blanche commune (fenêtre circulaire de 5 %) : information seulement — sur une carte réelle le
    # papier est aussi blanc que la marge, ce critère n'est donc pas discriminant
    w = np.sum(confs, axis=0) + 1e-9
    col = np.sum(rows * confs, axis=0) / w
    width = int(0.05 * rows.shape[1])
    ext = np.concatenate([col, col[:width]])
    run = np.convolve(ext, np.ones(width) / width, mode="valid")[: rows.shape[1]]
    i = int(np.argmax(run))
    res["margin_contrast"] = round(float((run[i] - np.median(col)) / 255.0), 3)
    res["margin_position"] = round(i / rows.shape[1], 4)
    confirmed = False
    if res["apt"] is not None and occ >= 0.4:
        confirmed, verdict = True, "WEFAX confirmé (signal de service " + res["apt"] + ")"
    elif is_chart_structure(res["line_corr"], res["video_std"]) and occ >= 0.5:
        confirmed, verdict = True, "WEFAX probable (continuité de ligne à 120 lignes/min)"
    elif res["video_std"] < 8 and occ >= 0.6:
        verdict = "porteuse fixe / signal non modulé"
    else:
        verdict = "pas de structure WEFAX"
    res["confirmed"] = confirmed
    res["verdict"] = verdict
    return res
