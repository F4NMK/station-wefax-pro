"""2.9.2 — Stations NAVTEX / RTTY optionnelles et mise en sommeil automatique.

Demande F4NMK (19/11/2026) : une station texte qui n'est pas reçue après plusieurs essais (propagation,
installation inadaptée, émetteur arrêté) ne doit plus coûter des cartes. Chaque station a donc :
* une case « activée » (choix de l'opérateur, onglet Plan de réception) ;
* un compteur d'échecs : un créneau écouté JUSQU'À SON TERME sans au moins 40 caractères décodés est un
  échec ; un créneau interrompu (carte prioritaire, opérateur) ne compte pas ;
* après N échecs de suite, la station est mise en sommeil, puis réessayée une fois par période (24 h pour
  le NAVTEX, 6 h pour les programmes RTTY du DWD) ; une réception réussie la réactive aussitôt ;
* « Réactiver » remet le compteur à zéro.
Les données sont dans configuration/stations_texte.json : rien ne dépend d'Internet.
"""

import json
import re
import time

NAVTEX_FAILS = 3
NAVTEX_RETRY_S = 24 * 3600
DWD_FAILS = 5
DWD_RETRY_S = 6 * 3600
MIN_CHARS_OK = 40

# Stations désactivées par défaut (l'opérateur peut les réactiver) et raison affichée.
DEFAULT_DISABLED = {
    "NAVTEX-W": "La Garde 518 kHz : « temporairement suspendue » (OHI 2023) puis « No operational » (rapport "
    "MBSHC24 de l'OHI, 2024). À réactiver si l'émission reprend.",
    "NAVTEX-S": "La Garde 490 kHz : même situation que La Garde 518 kHz (OHI 2023-2024).",
}

STATION_NAMES = {
    "NAVTEX-R": "NAVTEX La Maddalena R (518 kHz, anglais)",
    "NAVTEX-I": "NAVTEX La Maddalena I (490 kHz, italien)",
    "NAVTEX-X": "NAVTEX Cabo la Nao X (518 kHz, anglais)",
    "NAVTEX-W": "NAVTEX La Garde W (518 kHz, anglais)",
    "NAVTEX-S": "NAVTEX La Garde S (490 kHz, français)",
    "DWD-P1": "RTTY DWD programme 1 (anglais)",
    "DWD-P2": "RTTY DWD programme 2 (allemand)",
}


def station_key(item):
    """Clé de station d'un créneau (RttyItem)."""
    if getattr(item, "is_navtex", False):
        m = re.search(r"\(([A-Z])\)", str(getattr(item, "label", "")))
        return f"NAVTEX-{m.group(1)}" if m else f"NAVTEX-{item.program}"
    prog = getattr(item, "program", "")
    if prog in (1, 2):
        return f"DWD-P{prog}"
    return None  # écoute choisie par l'opérateur : jamais filtrée


class TextStationHealth:
    def __init__(self, path=None):
        self.path = path
        self.data = {}
        self.load()

    # ------------------------------------------------------------------ fichier
    def load(self):
        try:
            if self.path and self.path.is_file():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(d.get("stations"), dict):
                    self.data = {str(k): dict(v) for k, v in d["stations"].items() if isinstance(v, dict)}
        except Exception:
            self.data = {}
        return self

    def save(self):
        if not self.path:
            return
        try:
            from wefax_station.storage.atomic import atomic_json

            atomic_json(self.path, {"schema": "stations-texte-1", "stations": self.data})
        except Exception:
            pass

    # ------------------------------------------------------------------ état
    def _rec(self, key):
        rec = self.data.get(key)
        if rec is None:
            rec = {"fails": 0, "ok": 0, "last_ok": 0.0, "last_try": 0.0, "suspended_until": 0.0}
            if key in DEFAULT_DISABLED:
                rec["enabled"] = False
                rec["reason"] = DEFAULT_DISABLED[key]
            else:
                rec["enabled"] = True
            self.data[key] = rec
        return rec

    @staticmethod
    def _limits(key):
        return (NAVTEX_FAILS, NAVTEX_RETRY_S) if str(key).startswith("NAVTEX") else (DWD_FAILS, DWD_RETRY_S)

    def is_enabled(self, key):
        return bool(self._rec(key).get("enabled", True))

    def is_active(self, key, now=None):
        """Station à écouter maintenant : activée et pas en sommeil (ou période de nouvel essai atteinte)."""
        if key is None:
            return True
        rec = self._rec(key)
        if not rec.get("enabled", True):
            return False
        now = time.time() if now is None else now
        return now >= float(rec.get("suspended_until") or 0.0)

    def allows(self, item, now=None):
        return self.is_active(station_key(item), now)

    def record(self, key, chars, complete=True, now=None):
        """Résultat d'un créneau. Renvoie 'OK', 'ECHEC', 'SOMMEIL' ou None (créneau non concluant)."""
        if key is None:
            return None
        now = time.time() if now is None else now
        rec = self._rec(key)
        rec["last_try"] = now
        if chars >= MIN_CHARS_OK:
            was = rec.get("fails", 0) or float(rec.get("suspended_until") or 0) > 0
            rec.update(fails=0, ok=int(rec.get("ok", 0)) + 1, last_ok=now, suspended_until=0.0)
            self.save()
            return "REPRISE" if was else "OK"
        if not complete:
            self.save()
            return None
        rec["fails"] = int(rec.get("fails", 0)) + 1
        n_max, retry = self._limits(key)
        result = "ECHEC"
        if rec["fails"] >= n_max:
            rec["suspended_until"] = now + retry
            result = "SOMMEIL"
        self.save()
        return result

    def set_enabled(self, key, enabled):
        rec = self._rec(key)
        rec["enabled"] = bool(enabled)
        if enabled:
            rec.update(fails=0, suspended_until=0.0)
        self.save()

    def reset(self, key):
        rec = self._rec(key)
        rec.update(fails=0, suspended_until=0.0, enabled=True)
        self.save()

    def status_text(self, key, now=None):
        now = time.time() if now is None else now
        rec = self._rec(key)
        if not rec.get("enabled", True):
            return "désactivée" + (f" — {rec['reason']}" if rec.get("reason") else "")
        until = float(rec.get("suspended_until") or 0.0)
        if until > now:
            h = max(1, int((until - now) // 3600))
            return f"en sommeil ({rec.get('fails', 0)} créneaux sans réception) — nouvel essai dans ~{h} h"
        last = rec.get("last_ok") or 0
        last_txt = time.strftime("%d/%m %H:%M UTC", time.gmtime(last)) if last else "jamais"
        return f"active — {rec.get('fails', 0)} échec(s) de suite — dernière réception : {last_txt}"

    def keys(self):
        return list(STATION_NAMES)
