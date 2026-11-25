"""Conversions d'unités météorologiques partagées entre les modules weather.

Regroupé ici (v2.14.0) pour éliminer les doublons entre grib.py et nowcast.py.
"""


def ms_to_beaufort(ms: float) -> int:
    """Convertit une vitesse en m/s en échelle de Beaufort (0-12)."""
    kn = ms * 1.94384
    for f, lim in enumerate((1, 4, 7, 11, 17, 22, 28, 34, 41, 48, 56, 64)):
        if kn < lim:
            return f
    return 12
