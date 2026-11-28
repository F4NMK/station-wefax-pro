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


def compact_chart_image(
    signed_rgb, map_height, max_width=None, gray_levels=COMPACT_GRAY_LEVELS, footer_colors=COMPACT_FOOTER_COLORS
):
    """Copie compacte d'une carte signée, pour l'envoi par Winlink / VARA HF.

    Une carte WEFAX est un dessin au trait : 4 niveaux de gris suffisent à la carte (traits, chiffres,
    fronts), sans les halos qu'un JPEG crée autour des isobares. Mesuré (2.14.1) sur une carte DWD
    passée par le banc HF (12 dB, fading moyen), 1809×1200 + bandeau : carte signée PNG RGB ≈ 2,3 Mo ;
    copie compacte ≈ 175 ko en pleine largeur, ≈ 100 ko réduite à 1200 px (un JPEG q75 de la carte
    seule pèse ≈ 650 ko). Le bandeau de signature (logo, indicatif, heure) garde ses couleurs.
    Renvoie une image PIL en mode palette (gray_levels + footer_colors couleurs).
    2.14.1 — même codage pour la carte enregistrée par défaut (ARCHIVE_GRAY_LEVELS, voir atomic_card).
    """
    src = Image.fromarray(np.asarray(signed_rgb, dtype=np.uint8)).convert("RGB")
    map_height = max(1, min(int(map_height), src.height))
    if max_width and src.width > int(max_width):
        k = int(max_width) / src.width
        src = src.resize((int(max_width), max(1, round(src.height * k))), Image.LANCZOS)
        map_height = max(1, min(src.height, round(map_height * k)))
    arr = np.asarray(src)
    step = 255.0 / (gray_levels - 1)
    gray = np.asarray(src.crop((0, 0, src.width, map_height)).convert("L"), dtype=np.float64)
    idx = np.empty((src.height, src.width), dtype=np.uint8)
    idx[:map_height] = np.clip(np.round(gray / step), 0, gray_levels - 1).astype(np.uint8)
    palette = []
    for i in range(gray_levels):
        v = int(round(i * step))
        palette += [v, v, v]
    if map_height < src.height:
        footer = Image.fromarray(arr[map_height:]).quantize(
            colors=footer_colors, dither=Image.Dither.NONE
        )
        idx[map_height:] = np.asarray(footer, dtype=np.uint8) + gray_levels
        fp = list(footer.getpalette()[: 3 * footer_colors])
        palette += fp + [0] * (3 * footer_colors - len(fp))
    palette += [0, 0, 0] * (256 - len(palette) // 3)
    out = Image.fromarray(idx, mode="P")
    out.putpalette(palette)
    return out


def atomic_compact_chart(
    path, signed_rgb, map_height, max_width=None, gray_levels=COMPACT_GRAY_LEVELS,
    footer_colors=COMPACT_FOOTER_COLORS, bits=4,
):
    """Écrit atomiquement la carte codée en palette (voir compact_chart_image) ; renvoie le chemin."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.stem + ".writing.png")
    try:
        compact_chart_image(signed_rgb, map_height, max_width, gray_levels, footer_colors).save(
            temp, format="PNG", optimize=True, bits=bits
        )
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


# 2.14.1 — carte enregistrée par défaut (F4NMK, 28/11 : « la taille des fichiers images n'a pas été réduite ») :
# la carte signée était un PNG RGB alors que la carte est en gris. Codée en palette, 32 niveaux de gris pour la
# carte (écart ≤ 4 niveaux sur 255, invisible) et 224 couleurs pour le bandeau. Mesuré sur une carte décodée :
# 435 → ≈ 130 ko. La source de retraitement (…_decodee.png) reste sans perte.
ARCHIVE_GRAY_LEVELS = 32
ARCHIVE_FOOTER_COLORS = 256 - ARCHIVE_GRAY_LEVELS
CONFIDENCE_LEVELS = 4  # carte de confiance : 0 / 85 / 170 / 255 ; la limite « fiable » (≥ 128) est conservée


def atomic_card(path, signed_rgb, map_height):
    """Carte signée enregistrée par défaut (voir ARCHIVE_GRAY_LEVELS)."""
    return atomic_compact_chart(
        path, signed_rgb, map_height, gray_levels=ARCHIVE_GRAY_LEVELS, footer_colors=ARCHIVE_FOOTER_COLORS, bits=8
    )


def atomic_png_levels(path, array, levels):
    """Image en niveaux de gris ramenée à `levels` niveaux, PNG palette (carte de confiance)."""
    step = 255.0 / (levels - 1)
    q = np.clip(np.round(np.asarray(array, dtype=np.float64) / step), 0, levels - 1).astype(np.uint8)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.stem + ".writing.png")
    try:
        im = Image.fromarray(q, mode="P")
        pal = []
        for i in range(levels):
            v = int(round(i * step))
            pal += [v, v, v]
        im.putpalette(pal + [0] * (768 - len(pal)))
        im.save(temp, format="PNG", optimize=True, bits=max(1, int(np.ceil(np.log2(levels)))))
        with Image.open(temp) as image:
            image.verify()
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
