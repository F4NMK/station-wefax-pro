"""Traduction hors ligne des bulletins (glossaire local)."""

import json
import re
from pathlib import Path
from wefax_station.rtty.segmenter import BulletinSegmenter
from wefax_station.storage.atomic import atomic_json


class OfflineWeatherTranslator:
    DEFAULT_LEXICON = {
        "installed_languages": ["EN->FR (Météo maritime hors-ligne)", "DE->FR (Météo maritime hors-ligne)"],
        "phrases": {
            "STORM WARNING": "[AVERTISSEMENT DE TEMPÊTE / STORM WARNING]",
            "GALE WARNING": "[AVIS DE COUP DE VENT / GALE WARNING]",
            "STRONG WIND WARNING": "[AVIS DE GRAND FRAIS / STRONG WIND WARNING]",
            "NO GALE WARNING": "[AUCUN AVIS DE COUP DE VENT / NO GALE WARNING]",
            "NO WARNING": "[AUCUN AVERTISSEMENT EN VIGUEUR / NO WARNING]",
            "SHIPPING FORECAST": "PRÉVISION MARITIME",
            "GENERAL SYNOPSIS": "SITUATION GÉNÉRALE SYNOPTIQUE",
            "FORECAST FOR": "PRÉVISION POUR",
            "OUTLOOK": "TENDANCE ULTÉRIEURE",
            "ISSUED AT": "ÉMIS À",
            "IN EFFECT FOR": "EN VIGUEUR POUR",
            "LOW PRESSURE": "DÉPRESSION",
            "HIGH PRESSURE": "ANTICYCLONE",
            "COLD FRONT": "FRONT FROID",
            "WARM FRONT": "FRONT CHAUD",
            "OCCLUDED FRONT": "FRONT OCCLUS",
            "TROUGH": "TALWEG",
            "RIDGE": "DORSALE",
            "MOVING": "SE DÉPLAÇANT VERS",
            "DEEPENING": "SE CREUSANT",
            "FILLING": "SE COMBLANT",
            "SLOWLY": "LENTEMENT",
            "RAPIDLY": "RAPIDEMENT",
            "STATIONARY": "STATIONNAIRE",
            "BACKING": "RECULANT (BACKING)",
            "VEERING": "ADONNANT (VEERING)",
            "INCREASING": "FRAÎCHISSANT",
            "DECREASING": "MOLLISSANT",
            "BECOMING": "DEVENANT",
            "LATER": "PLUS TARD",
            "AT FIRST": "D'ABORD",
            "GUSTS": "RAFALES",
            "SQUALLS": "GRAINS",
            "THUNDERSTORMS": "ORAGES",
            "SHOWERS": "AVERSES",
            "RAIN": "PLUIE",
            "DRIZZLE": "BRUINE",
            "FOG": "BROUILLARD",
            "MIST": "BRUME",
            "GOOD": "BONNE",
            "MODERATE": "MODÉRÉE",
            "POOR": "MAUVAISE",
            "VERY POOR": "TRÈS MAUVAISE",
            "VISIBILITY": "VISIBILITÉ",
            "SEA STATE": "ÉTAT DE LA MER",
            "SLIGHT": "PEU AGITÉE",
            "ROUGH": "FORTE",
            "VERY ROUGH": "TRÈS FORTE",
            "HIGH": "GROSSE",
            "SWELL": "HOULE",
            "WIND": "VENT",
            "VORHERSAGE": "PRÉVISION",
            "WETTERLAGE": "SITUATION MÉTÉOROLOGIQUE",
            "TIEF": "DÉPRESSION",
            "HOCH": "ANTICYCLONE",
            "ZUNEHMEND": "FRAÎCHISSANT",
            "ABNEHMEND": "MOLLISSANT",
            "RECHTDREHEND": "ADONNANT",
            "RUECKDREHEND": "RECULANT",
            "SCHAUER": "AVERSES",
            "GEWITTER": "ORAGES",
            "NEBEL": "BROUILLARD",
            "SICHT": "VISIBILITÉ",
            "SEEGANG": "ÉTAT DE LA MER",
        },
    }

    def __init__(self, resources_dir: Path):
        self.resources_dir = Path(resources_dir)
        self.lexicon_path = self.resources_dir / "lexique_meteo_offline.json"
        self.lexicon = dict(self.DEFAULT_LEXICON)
        self.status = "Hors-ligne prêt (EN/DE -> FR)"
        self._load_or_init_lexicon()

    def _load_or_init_lexicon(self):
        try:
            self.resources_dir.mkdir(parents=True, exist_ok=True)
            if not self.lexicon_path.is_file():
                atomic_json(self.lexicon_path, self.DEFAULT_LEXICON)
            else:
                self.lexicon = json.loads(self.lexicon_path.read_text(encoding="utf-8"))
            self.status = "Actif · EN/DE -> FR hors-ligne"
        except Exception as exc:
            self.status = f"Repli mémoire ({exc})"

    def translate_preserve_critical(self, original_text: str) -> dict:
        if not original_text or not original_text.strip():
            return {"ok": True, "translated": "", "status": self.status, "preserved_tokens": 0}

        try:
            # 2.8.5 — traduction par expressions (weather/marine_translate.py) au lieu du glossaire mot à mot,
            # qui ne remplaçait que quelques mots isolés. Le lexique personnel de l'opérateur
            # (ressources/lexique_meteo_offline.json) complète : il ne s'applique qu'aux mots restés en
            # majuscules, c'est-à-dire non traduits.
            from wefax_station.weather.marine_translate import translate_bulletin, untranslated_words

            work = translate_bulletin(original_text)
            default = self.DEFAULT_LEXICON["phrases"]
            for src, dst in sorted(self.lexicon.get("phrases", {}).items(), key=lambda kv: -len(kv[0])):
                if default.get(src) == dst:
                    continue  # entrée d'origine, déjà couverte par le traducteur
                work = re.sub(rf"(?<![\w-]){re.escape(src.upper())}(?![\w-])", str(dst).lower(), work)
            left = untranslated_words(work)
            header_note = (
                "[TRADUCTION HORS LIGNE — nombres, heures et positions conservés à l'identique. "
                "Un mot resté en MAJUSCULES n'a pas pu être traduit : il est laissé dans sa langue d'origine.]\n\n"
            )
            return {
                "ok": True,
                "translated": header_note + work,
                "status": self.status,
                "preserved_tokens": 0,
                "untranslated": left,
            }
        except Exception as exc:
            return {
                "ok": False,
                "translated": "[Traduction différée : " + str(exc) + "]\n\n" + original_text,
                "status": "Erreur non bloquante : " + str(exc),
                "preserved_tokens": 0,
            }
