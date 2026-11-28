"""P.AMP automatique (2.8.8) : suivre le fading sans dégrader la réception.

Principe, en clair
------------------
Monter le préampli ne fait pas « plus de signal » : il amplifie AUSSI le bruit. Il n'améliore
le rapport signal/bruit (SNR) que si le bruit propre du récepteur domine le bruit de bande
(petite antenne, site calme, bande haute). Sur 7 MHz le soir, le bruit de bande domine souvent
et P.AMP 2 n'apporte rien… sauf de l'intermodulation.

Donc on ne suppose rien : on ESSAIE et on MESURE.

1. Le SNR est lissé et comparé à sa valeur de référence des dernières minutes.
2. Fading détecté (SNR en chute de 4 dB ou sous le seuil du mode) → essai du cran supérieur
   (P.AMP 1 → 2, ou 0 → 1). Après stabilisation de l'AGC, on mesure :
   - gain ≥ 1,5 dB → on garde ;
   - sinon → retour au cran précédent et pas de nouvel essai avant 5 min (le préampli
     ne sert à rien à ce moment-là).
3. Signal revenu (SNR proche de la référence pendant 1 min, ou S-mètre fort) → on redescend
   d'un cran, en vérifiant que le SNR ne chute pas ; s'il chute, on remonte et on n'y touche
   plus pendant 10 min.
4. Surcharge (OVF) → descente immédiate, sans essai.
5. Si l'opérateur change lui-même le P.AMP, l'automatisme se met en pause 15 min.
6. 2.9.2 — pendant le tracé d'une carte, chaque commutation marque l'image (saut de niveau) : aucun essai
   de descente, un essai de montée au plus toutes les 3 min, après 3 mesures en fading, et le cran n'est
   gardé que pour un gain d'au moins 3 dB. Le 19/11, le P.AMP oscillait entre 1 et 2 toutes les 30 à 40 s
   pendant les cartes DWD (gains de +2,2 dB seulement, S-mètre S9+9).

Le module est purement logique (aucune E/S) : `step()` renvoie le cran à appliquer ou None.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

THRESHOLD_DB = {"RTTY": 12.0, "WEFAX": 10.0}  # SNR en dessous duquel le décodage devient fragile
FADE_DROP_DB = 4.0
KEEP_GAIN_DB = 1.5
SETTLE_S = 6.0  # AGC + premier bloc audio après commutation
MEASURE_S = 14.0
MIN_DWELL_S = 20.0
FUTILE_COOLDOWN_S = 300.0
STEPDOWN_HOLD_S = 600.0
RECOVER_S = 60.0
MANUAL_PAUSE_S = 900.0
CHART_KEEP_GAIN_DB = 3.0  # 2.9.2 — pendant une carte
CHART_TRIAL_GAP_S = 180.0
CHART_FADED_TICKS = 3
# 2.9.7 — un gain énorme juste après des essais inutiles est la fin du fading, pas le préampli. Le 19/11 à
# 17:30 (GYA3) : essais de 17:12 et 17:19 à +0,2 et +0,3 dB, puis « P.AMP 2 gardé : SNR 0,0 → 9,6 dB »
# alors que la référence était à 11,1 dB : le signal revenait simplement.
PLAUSIBLE_GAIN_DB = 6.0
# 2.9.8 — signal confortable : aucun essai de montée. Le 19/11 à 18:00:53 (DDK3, analyse de 18:00), essai de
# P.AMP 2 à SNR 31,4 dB (référence 39,4) : SNR −23,8 dB pendant l'essai, image marquée pour rien.
COMFORT_MARGIN_DB = 10.0
FUTILE_MEMORY_S = 1800.0
STRONG_RAW = 150  # ≈ S9+20 sur l'IC-705
OVERLOAD_RAW = 185


@dataclass
class AutoPreamp:
    mode: str = "WEFAX"
    base_level: int = 1
    ema: float | None = None
    history: deque = field(default_factory=lambda: deque(maxlen=60))  # (t, snr lissé)
    phase: str = "IDLE"  # IDLE | SETTLE_UP | MEASURE_UP | SETTLE_DOWN | MEASURE_DOWN
    phase_t: float = 0.0
    before_snr: float = 0.0
    before_level: int = 1
    samples: list = field(default_factory=list)
    last_action_t: float = -1e9
    no_up_until: float = -1e9
    no_down_until: float = -1e9
    paused_until: float = -1e9
    recovered_since: float | None = None
    expected_level: int | None = None
    boosted_by_auto: bool = False
    events: list = field(default_factory=list)
    recent: deque = field(default_factory=lambda: deque(maxlen=3))  # SNR bruts récents
    faded_ticks: int = 0
    trial_in_chart: bool = False
    futile_times: deque = field(default_factory=lambda: deque(maxlen=10))  # 2.9.7 : (t, mode) des essais inutiles, gardés au changement de mode

    # ------------------------------------------------------------ utilitaires
    def set_mode(self, mode: str):
        mode = "RTTY" if str(mode).upper().startswith("RTTY") else "WEFAX"
        if mode != self.mode:
            self.mode = mode
            self.reset()

    def reset(self):
        self.ema = None
        self.history.clear()
        self.phase = "IDLE"
        self.samples = []
        self.recent.clear()
        self.faded_ticks = 0
        self.recovered_since = None
        self.expected_level = None
        self.boosted_by_auto = False

    def reference(self) -> float | None:
        """SNR « normal » de la station : médiane haute des 5 dernières minutes."""
        if len(self.history) < 4:
            return None
        vals = sorted(v for _, v in self.history)
        return vals[int(len(vals) * 0.7)]

    def _log(self, now, text):
        self.events.append((now, text))
        del self.events[:-20]
        # 2.9.3 — compteur total : la liste est plafonnée à 20, l'appelant ne doit pas se fier à sa longueur
        self.events_total = getattr(self, "events_total", 0) + 1

    def _act(self, now, level, text):
        self.last_action_t = now
        self.expected_level = level
        self._log(now, text)
        return level

    # ------------------------------------------------------------------ cœur
    def step(self, now: float, snr_db: float | None, level: int, s_raw: int = 0, ovf: bool = False,
             chart_active: bool = False):
        """Un appel par tick (≈ 6 s). Renvoie le cran P.AMP à appliquer, ou None.
        chart_active : une carte WEFAX est en cours de tracé (règles plus calmes, voir point 6)."""
        level = int(level)
        # l'opérateur a touché au P.AMP lui-même → pause
        if self.expected_level is not None and level != self.expected_level and self.phase == "IDLE":
            self.paused_until = now + MANUAL_PAUSE_S
            self.boosted_by_auto = False
            self._log(now, f"P.AMP {level} choisi par l'opérateur : automatisme en pause 15 min")
        self.expected_level = level

        # surcharge : priorité absolue, pas d'essai
        if ovf or s_raw > OVERLOAD_RAW:
            self.phase = "IDLE"
            if level > 0 and now - self.last_action_t > 5:
                self.no_up_until = now + FUTILE_COOLDOWN_S
                self.boosted_by_auto = level - 1 > self.base_level
                return self._act(now, level - 1, f"Surcharge (OVF) → P.AMP {level - 1}")
            return None

        if snr_db is None:
            return None
        self.ema = snr_db if self.ema is None else 0.5 * self.ema + 0.5 * snr_db
        self.recent.append(float(snr_db))
        if now < self.paused_until:
            return None

        # ---- essai en cours ------------------------------------------------
        if self.phase in ("SETTLE_UP", "SETTLE_DOWN"):
            if now - self.phase_t >= SETTLE_S:
                self.phase = "MEASURE_UP" if self.phase == "SETTLE_UP" else "MEASURE_DOWN"
                self.phase_t = now
                self.samples = []
            return None
        if self.phase in ("MEASURE_UP", "MEASURE_DOWN"):
            self.samples.append(snr_db)
            if now - self.phase_t < MEASURE_S or len(self.samples) < 2:
                return None
            after = sorted(self.samples)[len(self.samples) // 2]
            gain = after - self.before_snr
            up = self.phase == "MEASURE_UP"
            self.phase = "IDLE"
            self.ema = after
            if up:
                keep_db = CHART_KEEP_GAIN_DB if self.trial_in_chart else KEEP_GAIN_DB
                recent_futile = any(m == self.mode and now - t <= FUTILE_MEMORY_S for t, m in self.futile_times)
                if gain >= keep_db and gain > PLAUSIBLE_GAIN_DB and recent_futile:
                    # 2.9.7 — mesure faussée par la remontée du signal : rien n'est attribué au préampli
                    self.boosted_by_auto = True
                    if self.trial_in_chart:
                        # pas de commutation de plus pendant la carte (elle marquerait l'image) : le cran reste
                        # jusqu'au STOP, puis la descente normale le ramène au réglage de base
                        self._log(
                            now,
                            f"P.AMP {level} : SNR {self.before_snr:.1f} → {after:.1f} dB, mais les essais précédents "
                            "n'apportaient rien : c'est le fading qui remonte, pas le préampli. Cran laissé jusqu'à "
                            "la fin de la carte, puis retour au réglage de base",
                        )
                        self.last_action_t = now
                        return None
                    self.no_up_until = now + FUTILE_COOLDOWN_S
                    self.boosted_by_auto = self.before_level > self.base_level
                    return self._act(
                        now,
                        self.before_level,
                        f"P.AMP {level} : SNR {self.before_snr:.1f} → {after:.1f} dB, mais les essais précédents "
                        f"n'apportaient rien : c'est le fading qui remonte → retour P.AMP {self.before_level}",
                    )
                if gain >= keep_db:
                    self.boosted_by_auto = True
                    self._log(now, f"P.AMP {level} gardé : SNR {self.before_snr:.1f} → {after:.1f} dB (+{gain:.1f})")
                    self.last_action_t = now
                    return None
                self.no_up_until = now + FUTILE_COOLDOWN_S
                self.futile_times.append((now, self.mode))
                self.boosted_by_auto = self.before_level > self.base_level
                return self._act(
                    now,
                    self.before_level,
                    f"P.AMP {level} inutile (SNR {gain:+.1f} dB, bruit de bande dominant) → retour P.AMP "
                    f"{self.before_level}, nouvel essai dans 5 min",
                )
            # descente
            if gain <= -KEEP_GAIN_DB:
                self.no_down_until = now + STEPDOWN_HOLD_S
                self.boosted_by_auto = True
                return self._act(
                    now,
                    self.before_level,
                    f"Descente refusée (SNR {gain:+.1f} dB) → retour P.AMP {self.before_level} pour 10 min",
                )
            self.boosted_by_auto = level > self.base_level
            self._log(now, f"Signal revenu : P.AMP {level} conservé (SNR {after:.1f} dB)")
            self.last_action_t = now
            return None

        # ---- repos : alimente la référence ----------------------------------
        self.history.append((now, self.ema))
        while self.history and now - self.history[0][0] > 300:
            self.history.popleft()
        ref = self.reference()
        dwell = max(MIN_DWELL_S, CHART_TRIAL_GAP_S) if chart_active else MIN_DWELL_S
        if now - self.last_action_t < dwell:
            return None
        thr = THRESHOLD_DB[self.mode]

        faded = self.ema < thr or (
            ref is not None and self.ema < ref - FADE_DROP_DB and self.ema < thr + COMFORT_MARGIN_DB
        )
        self.faded_ticks = self.faded_ticks + 1 if faded else 0
        need_ticks = CHART_FADED_TICKS if chart_active else 2
        # deux mesures consécutives en fading : le niveau est posé, la comparaison avant/après est juste
        if self.faded_ticks >= need_ticks and level < 2 and now >= self.no_up_until and s_raw < STRONG_RAW:
            self.trial_in_chart = bool(chart_active)
            self.faded_ticks = 0
            self.recovered_since = None
            self.before_snr = sorted(list(self.recent)[-2:])[0] if len(self.recent) >= 2 else snr_db
            self.before_level = level
            self.phase = "SETTLE_UP"
            self.phase_t = now
            ref_txt = f", référence {ref:.1f} dB" if ref is not None else ""
            return self._act(now, level + 1, f"Fading : SNR {self.ema:.1f} dB{ref_txt} → essai P.AMP {level + 1}")

        # ---- signal revenu : redescendre vers le réglage de base -------------
        # 2.9.2 — jamais pendant une carte : on attend sa fin
        if chart_active:
            self.recovered_since = None
            return None
        if self.boosted_by_auto and level > self.base_level and now >= self.no_down_until:
            good = s_raw >= STRONG_RAW or (ref is not None and self.ema >= ref - 1.0 and self.ema >= thr + 3)
            if good:
                self.before_snr = snr_db
                if self.recovered_since is None:
                    self.recovered_since = now
                if now - self.recovered_since >= RECOVER_S or s_raw >= STRONG_RAW:
                    self.recovered_since = None
                    self.before_snr = sorted(list(self.recent)[-2:])[0] if len(self.recent) >= 2 else snr_db
                    self.before_level = level
                    self.phase = "SETTLE_DOWN"
                    self.phase_t = now
                    return self._act(now, level - 1, f"Signal revenu → essai retour P.AMP {level - 1}")
            else:
                self.recovered_since = None
        return None
