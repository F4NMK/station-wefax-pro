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
