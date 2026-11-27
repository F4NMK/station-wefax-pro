"""Écritures atomiques (fichier temporaire vérifié puis remplacement).

2.10.0 — sous Windows, le remplacement échoue (« Accès refusé », WinError 5 / errno 13) quand un autre
programme tient le fichier ouvert un instant : antivirus, indexation, explorateur, synchronisation. Le
19/11 à 19:38 UTC : « Brouillon non sauvé : PermissionError(13, 'Accès refusé') ». Le remplacement est
retenté quelques fois (≈ 1 s au total) avant d'abandonner.
"""

import json
import os
import time
from pathlib import Path
import numpy as np
from PIL import Image


REPLACE_RETRIES = 6
REPLACE_DELAY_S = 0.05


def replace_with_retry(src, dst, retries=REPLACE_RETRIES, delay_s=REPLACE_DELAY_S, _replace=os.replace):
    """os.replace, retenté si le fichier cible est momentanément verrouillé par un autre programme."""
    for attempt in range(retries + 1):
        try:
            _replace(src, dst)
            return
        except PermissionError:
            if attempt >= retries:
                raise
            time.sleep(delay_s * (2**attempt))


def atomic_text(path, text, encoding="utf-8"):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".writing")
    try:
        temp.write_text(text, encoding=encoding)
        replace_with_retry(temp, target)
        return target
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass


def atomic_png(path, array):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.stem + ".writing.png")
    try:
        # optimize=True + compress_level=9 : PNG lossless ≈ 25-35 % plus petit
        Image.fromarray(np.asarray(array, dtype=np.uint8)).save(
            temp, format="PNG", optimize=True, compress_level=9
        )
        with Image.open(temp) as image:
            image.verify()
        if not temp.stat().st_size:
            raise OSError("Image vide")
        replace_with_retry(temp, target)
        return target
    finally:
        if temp.exists():
            temp.unlink()


def atomic_image(path, array, format: str = "PNG", jpeg_quality: int = 90) -> Path:
    """Sauvegarde atomique dans le format choisi : PNG (lossless) ou JPEG (Winlink).

    Args:
        path       : chemin cible (l'extension doit correspondre au format)
        array      : np.ndarray uint8 (H×W niveaux de gris, ou H×W×3 RGB)
        format     : "PNG" (défaut, lossless) ou "JPEG" (lossy, 5–8× plus petit)
        jpeg_quality: qualité JPEG 1–95 (défaut 90 — bon compromis finesse/taille)

    Notes pour les cartes météo WEFAX :
        PNG  → archive de référence — fidèle au pixel, ~200–600 kB
        JPEG → envoi Winlink/VARA — ≈ 40–80 kB, légère perte sur les isobares fins
               Utilisez jpeg_quality ≥ 85 pour préserver les traits météo.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ext = ".writing" + target.suffix
    temp = target.with_name(target.stem + ext)
    try:
        img = Image.fromarray(np.asarray(array, dtype=np.uint8))
        fmt = format.upper()
        if fmt == "JPEG":
            # WEFAX est en niveaux de gris (mode L) — JPEG supporte nativement L
            if img.mode not in ("L", "RGB", "CMYK"):
                img = img.convert("L")
            img.save(temp, format="JPEG", quality=jpeg_quality, optimize=True, progressive=True)
        elif fmt == "PNG":
            img.save(temp, format="PNG", optimize=True, compress_level=9)
        else:
            img.save(temp, format=fmt)
        if not temp.stat().st_size:
            raise OSError("Image vide")
        replace_with_retry(temp, target)
        return target
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass


def atomic_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".writing")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        replace_with_retry(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
