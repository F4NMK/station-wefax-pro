"""Contrôle automatique du gain RF (AGC-RF) par boucle de contre-réaction.

Principe
--------
Le gain RF de l'IC-705 (commande CI-V 0x14 0x02, plage 0–255) règle l'atténuation
du signal **avant** le mélangeur. Le réduire atténue tout le signal entrant (utile +
bruit de bande HF), ce qui ne dégrade le SNR que si le bruit propre du récepteur
dominait — ce qui est rarement le cas en dessous de 15 MHz. En pratique, réduire
le RF gain quand le signal est fort (S8+) réduit l'intermodulation et les parasites
sans toucher au SNR.

Objectif de la boucle
---------------------
Maintenir le niveau audio RMS dans une fenêtre cible (TARGET_DBFS ± WINDOW_DB) :
  - signal trop fort  → réduire le gain RF (atténuation douce)
  - signal trop faible → remonter vers 255 (gain maximal)
  - SNR sous le seuil  → toujours forcer le gain maximal (ne jamais dégrader)

La boucle est purement logique (aucune E/S) : `step()` retourne la nouvelle valeur
de gain (0–255) ou None si rien ne doit changer. Le contrôleur applique la commande.

Paramètres clés
---------------
  TARGET_DBFS     : niveau RMS audio cible (dBFS) — point d'équilibre
  WINDOW_DB       : demi-fenêtre autour de la cible (pas de correction dans la fenêtre)
  MAX_STEP        : variation maximale par tick (pas brusque → pas d'artefact)
  MIN_SNR_DB      : en dessous de ce SNR, le gain reste au maximum
  SETTLE_TICKS    : ticks d'attente après une correction (AGC radio + DSP se stabilisent)
  MANUAL_PAUSE_S  : pause après intervention manuelle de l'opérateur
  MIN_GAIN        : gain minimum autorisé (ne jamais couper le signal !)

La valeur CI-V 255 correspond à un gain RF maximal (atténuation nulle).
La valeur CI-V 0 correspond à un gain RF nul (atténuation maximale).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

# ── Paramètres de réglage ────────────────────────────────────────────────────

TARGET_DBFS     = -18.0   # niveau RMS audio cible (dBFS) — point d'équilibre
WINDOW_DB       =   3.0   # demi-fenêtre : pas de correction si |rms - target| < window
MAX_STEP        =  12     # variation maximale de la valeur CI-V par tick (1 tick ≈ 2 s)
MIN_SNR_DB      =   6.0   # SNR minimum : en dessous, gain = 255 (ne jamais dégrader)
SETTLE_TICKS    =   3     # ticks de stabilisation après une correction
MANUAL_PAUSE_S  = 900.0   # 15 min de pause si l'opérateur touche lui-même au gain
MIN_GAIN        =  64     # gain CI-V minimum (≈ 25 %) — sécurité absolue
MAX_GAIN        = 255     # gain CI-V maximum (100 %)
EMA_ALPHA       =   0.4   # lissage exponentiel du niveau RMS entrant
STEP_KP         =   0.5   # coefficient proportionnel erreur → pas de correction


@dataclass
class AutoRFGain:
    """Automate de contrôle du gain RF — un appel `step()` par tick DSP.

    Paramètres
    ----------
    enabled     : True si l'AGC-RF est actif (l'opérateur peut le désactiver)
    target_dbfs : niveau RMS audio cible (modifiable depuis l'UI)
    base_gain   : gain de départ / référence (255 = gain maximal, pas d'atténuation)
    """

    enabled:        bool  = False      # désactivé par défaut — activation explicite opérateur
    target_dbfs:    float = TARGET_DBFS
    base_gain:      int   = MAX_GAIN

    # ── état interne ─────────────────────────────────────────────────────────
    _current_gain:   int   = field(default=MAX_GAIN, init=False, repr=False)
    _ema_dbfs:       float = field(default=TARGET_DBFS, init=False, repr=False)
    _settle:         int   = field(default=0, init=False, repr=False)        # ticks restants
    _paused_until:   float = field(default=0.0, init=False, repr=False)
    _expected_gain:  int   = field(default=MAX_GAIN, init=False, repr=False) # dernière commande
    _events:         list  = field(default_factory=list, init=False, repr=False)

    # historique RMS (60 derniers ticks ≈ 2 min) pour la référence de base
    _history: deque = field(default_factory=lambda: deque(maxlen=60), init=False, repr=False)

    # ── API publique ─────────────────────────────────────────────────────────

    @property
    def current_gain(self) -> int:
        """Valeur CI-V du gain RF actuellement commandée."""
        return self._current_gain

    @property
    def current_gain_pct(self) -> int:
        """Gain RF en % (0–100) pour l'affichage."""
        return round(self._current_gain * 100 / MAX_GAIN)

    @property
    def events(self) -> list[tuple[float, str]]:
        """Derniers événements journalisés (max 20)."""
        return list(self._events)

    def reset(self) -> None:
        """Réinitialise l'état interne (changement de fréquence, nouvelle station)."""
        self._ema_dbfs     = self.target_dbfs
        self._settle       = 0
        self._history.clear()
        # on garde le gain courant pour éviter une remontée brutale

    def notify_manual_change(self, now: float, new_gain: int) -> None:
        """L'opérateur a modifié le gain manuellement → pause de 15 min."""
        self._current_gain  = new_gain
        self._expected_gain = new_gain
        self._paused_until  = now + MANUAL_PAUSE_S
        self._log(now, f"Gain RF réglé manuellement à {new_gain} ({new_gain*100//MAX_GAIN} %) "
                       f"→ AGC-RF en pause 15 min")

    def step(
        self,
        now: float,
        rms_dbfs: float | None,
        snr_db: float | None,
        actual_gain: int,
    ) -> int | None:
        """Un appel par tick DSP (toutes les ≈ 2 s).

        Paramètres
        ----------
        now         : temps courant (time.monotonic())
        rms_dbfs    : niveau RMS audio mesuré (dBFS) — None si pas de signal
        snr_db      : SNR estimé (dB) — None si pas de mesure
        actual_gain : valeur CI-V du gain RF lue depuis le matériel (détecte modif manuelle)

        Retourne
        --------
        int  : nouvelle valeur CI-V à appliquer (0–255)
        None : aucun changement nécessaire
        """
        if not self.enabled:
            # AGC-RF désactivé : on reste à gain maximal si le gain avait été réduit par nous
            if self._current_gain < MAX_GAIN and self._expected_gain < MAX_GAIN:
                self._current_gain  = MAX_GAIN
                self._expected_gain = MAX_GAIN
                self._log(now, "AGC-RF désactivé → retour gain RF maximal (255)")
                return MAX_GAIN
            return None

        # ── détection de modification manuelle ───────────────────────────────
        if actual_gain != self._expected_gain and actual_gain != self._current_gain:
            self.notify_manual_change(now, actual_gain)
            return None

        # ── pause opérateur ───────────────────────────────────────────────────
        if now < self._paused_until:
            return None

        # ── pas de signal : gain maximal ──────────────────────────────────────
        if rms_dbfs is None or rms_dbfs < -80.0:
            return self._apply(now, MAX_GAIN, "Pas de signal → gain RF maximal")

        # ── lissage EMA du niveau RMS ─────────────────────────────────────────
        self._ema_dbfs = EMA_ALPHA * rms_dbfs + (1.0 - EMA_ALPHA) * self._ema_dbfs
        self._history.append((now, self._ema_dbfs))

        # ── SNR trop faible : ne jamais réduire ──────────────────────────────
        if snr_db is not None and snr_db < MIN_SNR_DB:
            if self._current_gain < MAX_GAIN:
                return self._apply(now, MAX_GAIN,
                                   f"SNR {snr_db:.1f} dB trop faible → retour gain RF maximal")
            return None

        # ── stabilisation post-correction ─────────────────────────────────────
        if self._settle > 0:
            self._settle -= 1
            return None

        # ── calcul de l'erreur et décision ───────────────────────────────────
        error = self._ema_dbfs - self.target_dbfs          # positif = trop fort
        if abs(error) < WINDOW_DB:
            return None                                     # dans la fenêtre : repos

        # Pas de correction proportionnel à l'erreur, plafonné à MAX_STEP
        raw_step = error * STEP_KP * (MAX_GAIN / 40.0)    # 40 dB de plage utile
        step = int(max(-MAX_STEP, min(MAX_STEP, raw_step)))

        new_gain = self._current_gain - step               # erreur + → réduire gain
        new_gain = max(MIN_GAIN, min(MAX_GAIN, new_gain))

        if new_gain == self._current_gain:
            return None

        direction = "↓ atténuation" if new_gain < self._current_gain else "↑ amplification"
        return self._apply(
            now, new_gain,
            f"RMS {self._ema_dbfs:+.1f} dBFS (cible {self.target_dbfs:+.1f}) "
            f"{direction} → gain RF {new_gain} ({new_gain*100//MAX_GAIN} %)"
        )

    # ── internals ─────────────────────────────────────────────────────────────

    def _apply(self, now: float, gain: int, msg: str) -> int | None:
        """Applique la nouvelle valeur de gain et journalise."""
        gain = max(MIN_GAIN, min(MAX_GAIN, gain))
        if gain == self._current_gain:
            return None
        self._current_gain  = gain
        self._expected_gain = gain
        self._settle        = SETTLE_TICKS
        self._log(now, msg)
        return gain

    def _log(self, now: float, text: str) -> None:
        self._events.append((now, text))
        del self._events[:-20]
