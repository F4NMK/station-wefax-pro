"""Gain RF automatique (2.14.1) — désactivé par défaut, activé par l'opérateur (Réglages › Radio).

Principe, en clair
------------------
Sur l'IC-705 (échantillonnage direct sous 25 MHz), baisser le gain RF recule le point d'écrêtage du
convertisseur : le manuel demande de réduire le gain RF (ou d'enclencher l'ATT) quand « OVF » s'affiche.
Tant que le bruit de bande reste au-dessus du bruit propre du récepteur, baisser le gain RF ne fait rien
perdre (les signaux plus faibles que le bruit de bande sont de toute façon inaudibles) et réduit
l'intermodulation. Mais personne ne sait d'avance où est ce point : on ESSAIE et on MESURE, comme le
P.AMP automatique (auto_preamp.py).

1. Surcharge (OVF) en P.AMP 0 sans ATT → descente du gain RF par paliers de 20 % (au plus toutes les
   6 s), avant de recourir à l'ATT −20 dB ; au plancher (50 %), l'ATT prend le relais.
2. Hors surcharge, hors tracé de carte, émission présente : toutes les 2 min, essai d'un palier de 10 %
   plus bas. Après stabilisation, SNR mesuré sur 3 relevés : gardé s'il ne perd pas plus de 0,5 dB,
   sinon retour au palier précédent et plus d'essai pendant 15 min.
3. Fading (SNR lissé à 4 dB sous sa référence) → remontée d'un palier, même pendant une carte.
4. Jamais au-dessus du gain choisi par l'opérateur, jamais sous 50 %.
5. L'opérateur touche au gain RF → ce réglage devient la référence, automatisme en pause 15 min.
6. Désactivation ou changement de station → retour au gain de l'opérateur.

Pourquoi pas l'ancien « AGC-RF » (version Qt, 27/11) : il visait un niveau audio de −18 dBFS. L'application
impose l'AGC FAST, qui maintient ce niveau quel que soit le gain RF : la boucle aurait descendu le gain
jusqu'à son plancher sans effet sur le niveau, au détriment des signaux faibles.

Module purement logique (aucune E/S) : `step()` renvoie le gain CI-V (0–255) à appliquer, ou None.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

MAX_GAIN = 255
MIN_GAIN = 128  # ≈ 50 % : plancher absolu de l'automatisme
OVF_STEP = 51  # ≈ 20 % par palier en surcharge
TRIAL_STEP = 26  # ≈ 10 % par essai d'optimisation
OVF_MIN_GAP_S = 6.0
SETTLE_S = 6.0  # AGC du poste + premier bloc audio après le changement
MEASURE_SAMPLES = 3
KEEP_TOLERANCE_DB = 0.5
TRIAL_GAP_S = 120.0
FUTILE_COOLDOWN_S = 900.0
FADE_DROP_DB = 4.0
MANUAL_PAUSE_S = 900.0
OVERLOAD_RAW = 185  # même seuil S-mètre que le P.AMP automatique (≈ S9+40)
EMA_ALPHA = 0.35


def pct(gain: int) -> int:
    return round(int(gain) * 100 / MAX_GAIN)


@dataclass
class AutoRfGain:
    enabled: bool = False
    base_gain: int = MAX_GAIN  # gain choisi par l'opérateur : plafond de l'automatisme
    expected_gain: int | None = None
    phase: str = "IDLE"  # IDLE | SETTLE | MEASURE
    phase_t: float = 0.0
    before_gain: int = MAX_GAIN
    before_snr: float = 0.0
    samples: list = field(default_factory=list)
    ema: float | None = None
    history: deque = field(default_factory=lambda: deque(maxlen=50))
    last_action_t: float = -1e9
    next_trial_t: float = -1e9
    paused_until: float = -1e9
    lowered_by_auto: bool = False
    trial_qsy: int = 0
    events: list = field(default_factory=list)
    events_total: int = 0

    # ------------------------------------------------------------ utilitaires
    def _log(self, now, text):
        self.events.append((now, text))
        del self.events[:-20]
        self.events_total += 1

    def _act(self, now, gain, text):
        gain = int(max(MIN_GAIN, min(self.base_gain, gain)))
        self.last_action_t = now
        self.expected_gain = gain
        self.lowered_by_auto = gain < self.base_gain
        self._log(now, text)
        return gain

    def reference(self):
        if len(self.history) < 4:
            return None
        vals = sorted(self.history)
        return vals[int(len(vals) * 0.7)]

    def set_enabled(self, enabled: bool, actual_gain, now: float):
        """Activation : le gain actuel du poste devient la référence de l'opérateur. actual_gain None (poste
        pas encore connecté, option rechargée au démarrage) : le premier gain lu sera adopté."""
        enabled = bool(enabled)
        if enabled and not self.enabled:
            self.expected_gain = None if actual_gain is None else int(actual_gain)
            if actual_gain is not None:
                self.base_gain = int(actual_gain)
            self.next_trial_t = now + TRIAL_GAP_S
        self.enabled = enabled

    def reset(self):
        """Changement de station ou de mode : nouvelles mesures."""
        self.phase = "IDLE"
        self.samples = []
        self.ema = None
        self.history.clear()

    # ------------------------------------------------------------------ cœur
    def step(
        self,
        now: float,
        snr_db: float | None,
        gain: int,
        ovf: bool = False,
        s_raw: int = 0,
        preamp: int = 0,
        att: bool = False,
        chart_active: bool = False,
        other_trial: bool = False,
        signal_present: bool = True,
        qsy_id: int = 0,
    ):
        """Un appel par tick (≈ 6 s). Renvoie le gain CI-V à appliquer, ou None.

        other_trial    : le P.AMP automatique a un essai en cours (on n'en lance pas un second en même temps).
        signal_present : l'émission est entendue en ce moment (porteuse WEFAX accrochée, FSK RTTY valide).
                         Hors émission, le SNR mesure du silence : aucun essai, aucune référence.
        qsy_id         : compteur des QSY de l'application ; un QSY pendant l'essai (veille de propagation,
                         changement de station) l'annule.
        """
        gain = int(gain)
        if not self.enabled:
            if self.lowered_by_auto and gain != self.base_gain and gain == self.expected_gain:
                self.phase = "IDLE"
                return self._act(now, self.base_gain, f"désactivé → retour au gain de l'opérateur {pct(self.base_gain)} %")
            self.lowered_by_auto = False
            return None

        if self.expected_gain is None:  # premier gain lu après activation : c'est celui de l'opérateur
            self.base_gain = self.expected_gain = gain
            self._log(now, f"référence : gain RF de l'opérateur {pct(gain)} % (plafond), plancher {pct(MIN_GAIN)} %")
        # l'opérateur a touché au gain RF lui-même
        if gain != self.expected_gain:
            self.base_gain = gain
            self.expected_gain = gain
            self.lowered_by_auto = False
            self.phase = "IDLE"
            self.paused_until = now + MANUAL_PAUSE_S
            self._log(now, f"gain RF {pct(gain)} % réglé par l'opérateur : nouvelle référence, pause 15 min")
            return None
        self.expected_gain = gain

        # 1. surcharge : priorité, pas d'essai, même pendant une carte
        if ovf or s_raw > OVERLOAD_RAW:
            self.phase = "IDLE"
            if preamp == 0 and not att and gain > MIN_GAIN and now - self.last_action_t >= OVF_MIN_GAP_S:
                self.next_trial_t = now + FUTILE_COOLDOWN_S
                return self._act(now, gain - OVF_STEP, f"surcharge OVF → gain RF {pct(max(MIN_GAIN, gain - OVF_STEP))} %")
            return None

        # 2. essai en cours : une carte qui commence l'interrompt sans retour en arrière (chaque changement de
        # gain marque l'image) ; la règle de fading (3) remonte le gain si ce palier fait perdre du signal.
        if self.phase in ("SETTLE", "MEASURE") and chart_active:
            self.phase = "IDLE"
            self.next_trial_t = now + TRIAL_GAP_S
            self._log(now, f"essai interrompu par le début d'une carte : gain RF {pct(gain)} % conservé")
            return None
        # 2.14.1 (journal du 28/11, 12:11) — essai lancé juste après un STOP, poste déplacé par la veille de
        # propagation, puis jugé sur le silence entre deux cartes (SNR 12,1 → 0,0 dB) : mesure sans valeur.
        # Signal perdu ou QSY pendant l'essai → essai annulé, retour au palier précédent.
        if self.phase in ("SETTLE", "MEASURE") and (
            not signal_present or snr_db is None or qsy_id != self.trial_qsy
        ):
            self.phase = "IDLE"
            self.next_trial_t = now + TRIAL_GAP_S
            why = "changement de fréquence" if qsy_id != self.trial_qsy else "émission interrompue"
            return self._act(now, self.before_gain, f"essai annulé ({why}) : retour à {pct(self.before_gain)} %")

        if now < self.paused_until or snr_db is None or not signal_present:
            return None

        self.ema = snr_db if self.ema is None else EMA_ALPHA * snr_db + (1 - EMA_ALPHA) * self.ema
        if self.phase == "SETTLE":
            if now - self.phase_t >= SETTLE_S:
                self.phase, self.samples = "MEASURE", []
            return None
        if self.phase == "MEASURE":
            self.samples.append(snr_db)
            if len(self.samples) < MEASURE_SAMPLES:
                return None
            measured = sorted(self.samples)[len(self.samples) // 2]
            self.phase = "IDLE"
            if measured >= self.before_snr - KEEP_TOLERANCE_DB:
                self.next_trial_t = now + TRIAL_GAP_S
                self._log(now, f"gain RF {pct(gain)} % gardé : SNR {self.before_snr:.1f} → {measured:.1f} dB")
                return None
            self.next_trial_t = now + FUTILE_COOLDOWN_S
            return self._act(
                now,
                self.before_gain,
                f"gain RF {pct(gain)} % rejeté (SNR {self.before_snr:.1f} → {measured:.1f} dB) : retour à "
                f"{pct(self.before_gain)} %, pas d'essai pendant 15 min",
            )

        self.history.append(self.ema)
        ref = self.reference()

        # 3. fading : remontée d'un palier
        if ref is not None and self.ema < ref - FADE_DROP_DB and gain < self.base_gain:
            if now - self.last_action_t >= OVF_MIN_GAP_S:
                self.next_trial_t = now + FUTILE_COOLDOWN_S
                return self._act(now, gain + TRIAL_STEP, f"fading (SNR {self.ema:.1f} dB, réf. {ref:.1f}) → gain RF "
                                 f"{pct(min(self.base_gain, gain + TRIAL_STEP))} %")
            return None

        # 2. lancement d'un essai
        if (
            not chart_active
            and not other_trial
            and not att
            and ref is not None
            and now >= self.next_trial_t
            and gain - TRIAL_STEP >= MIN_GAIN
        ):
            self.phase, self.phase_t = "SETTLE", now
            self.before_gain, self.before_snr = gain, self.ema
            self.trial_qsy = qsy_id
            return self._act(now, gain - TRIAL_STEP, f"essai gain RF {pct(gain - TRIAL_STEP)} % (SNR {self.ema:.1f} dB)")
        return None
