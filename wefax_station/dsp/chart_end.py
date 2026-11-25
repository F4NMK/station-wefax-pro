"""Fin de carte par perte de structure (signal STOP manqué).

2.11.0 — Le 20/11, les cartes DDK3 de 10:50 et de 11:12 ont été enregistrées avec 2 400 lignes : la carte
utile (≈ 1 300 et ≈ 1 200 lignes) suivie de 17 à 20 minutes de bruit. Le STOP n'avait pas été entendu et le
bruit restait « au-dessus du squelch » : la fin de carte n'arrivait qu'à la hauteur maximale.

Une carte se reconnaît à la ressemblance entre deux lignes successives (les traits continuent d'une ligne à
la suivante) ; le bruit n'en a aucune. Mesuré sur les cartes réelles du 20/11, la corrélation entre lignes
lissées (15 pixels), en médiane glissante sur 100 lignes, vaut 0,14 à 0,88 dans une carte, même faible, et
0,02 à 0,07 dans le bruit. Le détecteur :
* ne conclut qu'après END_RUN lignes (1 min) de médiane sous NOISE_MEDIAN ;
* ne s'arme qu'au-delà de ARM_FRACTION de la durée normale d'une carte : un évanouissement en début ou en
  milieu de carte ne la coupe jamais (règle de base : ne jamais couper une carte en cours sauf fiabilité
  faible) ;
* donne la dernière ligne structurée, pour retirer la queue de bruit avant l'archivage.
"""

from collections import deque

import numpy as np

SMOOTH_PX = 15
NOISE_MEDIAN = 0.09
STRUCT_MEDIAN = 0.12
WINDOW = 100
END_RUN = 120
ARM_FRACTION = 0.6

_KERNEL = np.ones(SMOOTH_PX) / SMOOTH_PX


def _smooth(row):
    return np.convolve(np.asarray(row, dtype=np.float64), _KERNEL, "same")


class ChartEndDetector:
    def __init__(self):
        self.reset()

    def reset(self):
        self._prev = None
        self._corrs = deque(maxlen=WINDOW)
        self.noise_run = 0
        self.last_structured = 0
        self.median = None

    def update(self, line_index, row):
        """À appeler pour chaque ligne tracée (pixels 0-255)."""
        cur = _smooth(row)
        if self._prev is not None:
            a, b = self._prev, cur
            if a.std() > 2 and b.std() > 2:
                self._corrs.append(float(np.corrcoef(a, b)[0, 1]))
        self._prev = cur
        if len(self._corrs) < 40:
            return
        self.median = float(np.median(self._corrs))
        if self.median >= STRUCT_MEDIAN:
            self.last_structured = int(line_index)
            self.noise_run = 0
        elif self.median < NOISE_MEDIAN:
            self.noise_run += 1

    def should_end(self, line_index, expected_lines):
        return line_index >= int(ARM_FRACTION * expected_lines) and self.noise_run >= END_RUN

    def crop_line(self, line_index):
        """Ligne où couper : fin de la dernière zone structurée (la médiane glissante retarde d'une demi-fenêtre)."""
        if self.last_structured <= 0:
            return int(line_index)
        return int(min(line_index, self.last_structured + WINDOW // 2))


