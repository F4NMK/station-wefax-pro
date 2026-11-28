"""2.9.3 — Programme observé : créneaux WEFAX réellement émis, d'après les START reçus.

Le 19/11/2026, DDK3 était fort toute la matinée, et les cartes de 07:17, 07:43, 08:04 et 08:17 ont été
reçues ; mais aucun START n'a été entendu à 07:30, 08:30 ni 08:42, alors que le programme intégré
(NOAA, information du 24/07/2024) les annonce. Rien ne permet de dire, sur une seule matinée, si ces cartes
ne sont plus émises ou si leur START a été manqué. Ce relevé tient donc les comptes jour après jour :
* « reçu » : un START entendu à ±4 min de l'heure du programme ;
* « muet » : le poste écoutait la famille à l'heure prévue, sans carte en cours de tracé, avec un signal
  correct, et aucun START n'est venu dans les 4 min.
Un créneau muet au moins 3 jours et jamais reçu est signalé à l'opérateur (« à vérifier »). Rien n'est
retiré du programme automatiquement. Fichier : configuration/programme_observe.json (aucun réseau).
"""

import json
from datetime import timedelta

MATCH_S = 240
LISTEN_BEFORE_S = 30
LISTEN_AFTER_S = 120
SUSPECT_DAYS = 3


class ObservedProgramme:
    def __init__(self, path=None):
        self.path = path
        self.data = {}
        self._listened = {}  # (fam, date, HH:MM) -> bool (écoute conforme à l'heure prévue)
        self._evaluated = set()
        try:
            if path and path.is_file():
                d = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(d.get("familles"), dict):
                    self.data = d["familles"]
        except Exception:
            self.data = {}

    def save(self):
        if not self.path:
            return
        try:
            from wefax_station.storage.atomic import atomic_json

            atomic_json(self.path, {"schema": "programme-observe-1", "familles": self.data})
        except Exception:
            pass

    def _rec(self, fam, hm):
        return self.data.setdefault(fam, {}).setdefault(hm, {"recu": 0, "muet": 0, "jours_recu": [], "jours_muet": []})

    @staticmethod
    def _slot_times(slots, now):
        base = now.replace(hour=0, minute=0, second=0, microsecond=0)
        out = []
        for h, m, code, desc in slots or ():
            for day in (-1, 0):
                out.append((base + timedelta(days=day, hours=int(h), minutes=int(m)), code, desc))
        return out

    def note_start(self, fam, when, slots):
        """START reçu : rattaché au créneau le plus proche (±4 min). Renvoie l'heure HH:MM ou None."""
        best = None
        for t, code, desc in self._slot_times(slots, when):
            dt = abs((when - t).total_seconds())
            if dt <= MATCH_S and (best is None or dt < best[0]):
                best = (dt, t)
        if best is None:
            return None
        t = best[1]
        hm = f"{t:%H:%M}"
        key = (fam, f"{t:%Y-%m-%d}", hm)
        if key in self._evaluated:
            return hm
        self._evaluated.add(key)
        rec = self._rec(fam, hm)
        rec["recu"] += 1
        rec["jours_recu"] = (rec["jours_recu"] + [f"{t:%Y-%m-%d}"])[-10:]
        self.save()
        return hm

    def tick(self, now, fam, slots, on_air, chart_drawing, signal_ok):
        """Appelée par l'arbitre à chaque évaluation, pour une famille. on_air : le poste écoute cette famille
        en WEFAX. Renvoie les créneaux devenus « muets » [(HH:MM, code, libellé)]."""
        muted = []
        for t, code, desc in self._slot_times(slots, now):
            hm = f"{t:%H:%M}"
            key = (fam, f"{t:%Y-%m-%d}", hm)
            dt = (now - t).total_seconds()
            if -LISTEN_BEFORE_S <= dt <= LISTEN_AFTER_S:
                ok = bool(on_air) and (not chart_drawing) and bool(signal_ok)
                prev = self._listened.get(key)
                self._listened[key] = ok if prev is None else (prev and ok)
            if MATCH_S <= dt <= MATCH_S + 600 and key not in self._evaluated and key in self._listened:
                self._evaluated.add(key)
                if self._listened.get(key):
                    rec = self._rec(fam, hm)
                    rec["muet"] += 1
                    rec["jours_muet"] = (rec["jours_muet"] + [key[1]])[-10:]
                    muted.append((hm, code, desc))
        if muted:
            self.save()
        if len(self._listened) > 400:
            for k in sorted(self._listened)[:200]:
                self._listened.pop(k, None)
        return muted

    def suspects(self, fam=None):
        """Créneaux muets au moins 3 jours différents et jamais reçus : [(famille, HH:MM, jours muets)]."""
        out = []
        for f, slots in self.data.items():
            if fam and f != fam:
                continue
            for hm, rec in slots.items():
                days = sorted(set(rec.get("jours_muet") or []))
                if len(days) >= SUSPECT_DAYS and not rec.get("recu"):
                    out.append((f, hm, days))
        return sorted(out)

    def summary(self, fam):
        slots = self.data.get(fam) or {}
        recu = sorted(hm for hm, r in slots.items() if r.get("recu"))
        muet = sorted(hm for hm, r in slots.items() if r.get("muet") and not r.get("recu"))
        return recu, muet
