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
        Image.fromarray(np.asarray(array, dtype=np.uint8)).save(temp, format="PNG")
        with Image.open(temp) as image:
            image.verify()
        if not temp.stat().st_size:
            raise OSError("Image vide")
        replace_with_retry(temp, target)
        return target
    finally:
        if temp.exists():
            temp.unlink()


COMPACT_GRAY_LEVELS = 4  # niveaux de gris de la carte dans la copie compacte
COMPACT_FOOTER_COLORS = 12  # couleurs réservées au bandeau de signature (logo + texte)


def compact_chart_image(signed_rgb, map_height, max_width=None):
    """Copie compacte d'une carte signée, pour l'envoi par Winlink / VARA HF.

    Une carte WEFAX est un dessin au trait : 4 niveaux de gris suffisent à la carte (traits, chiffres,
    fronts), sans les halos qu'un JPEG crée autour des isobares. Mesuré (2.14.1) sur une carte DWD
    passée par le banc HF (12 dB, fading moyen), 1809×1200 + bandeau : carte signée PNG RGB ≈ 2,3 Mo ;
    copie compacte ≈ 175 ko en pleine largeur, ≈ 100 ko réduite à 1200 px (un JPEG q75 de la carte
    seule pèse ≈ 650 ko). Le bandeau de signature (logo, indicatif, heure) garde ses couleurs.
    Renvoie une image PIL en mode palette (16 couleurs, PNG 4 bits).
    """
    src = Image.fromarray(np.asarray(signed_rgb, dtype=np.uint8)).convert("RGB")
    map_height = max(1, min(int(map_height), src.height))
    if max_width and src.width > int(max_width):
        k = int(max_width) / src.width
        src = src.resize((int(max_width), max(1, round(src.height * k))), Image.LANCZOS)
        map_height = max(1, min(src.height, round(map_height * k)))
    arr = np.asarray(src)
    step = 255.0 / (COMPACT_GRAY_LEVELS - 1)
    gray = np.asarray(src.crop((0, 0, src.width, map_height)).convert("L"), dtype=np.float64)
    idx = np.empty((src.height, src.width), dtype=np.uint8)
    idx[:map_height] = np.clip(np.round(gray / step), 0, COMPACT_GRAY_LEVELS - 1).astype(np.uint8)
    palette = []
    for i in range(COMPACT_GRAY_LEVELS):
        v = int(round(i * step))
        palette += [v, v, v]
    if map_height < src.height:
        footer = Image.fromarray(arr[map_height:]).quantize(
            colors=COMPACT_FOOTER_COLORS, dither=Image.Dither.NONE
        )
        idx[map_height:] = np.asarray(footer, dtype=np.uint8) + COMPACT_GRAY_LEVELS
        palette += list(footer.getpalette()[: 3 * COMPACT_FOOTER_COLORS])
    palette += [0, 0, 0] * (256 - len(palette) // 3)
    out = Image.fromarray(idx, mode="P")
    out.putpalette(palette)
    return out


def atomic_compact_chart(path, signed_rgb, map_height, max_width=None):
    """Écrit atomiquement la copie compacte (voir compact_chart_image) ; renvoie le chemin."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.stem + ".writing.png")
    try:
        compact_chart_image(signed_rgb, map_height, max_width).save(temp, format="PNG", optimize=True, bits=4)
        with Image.open(temp) as image:
            image.verify()
        if not temp.stat().st_size:
            raise OSError("Image compacte vide")
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
