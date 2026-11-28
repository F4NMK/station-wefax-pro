"""Découpage du flux texte en bulletins."""

import re


def find_marker(text, marker, last=False):
    """Position (début, fin) d'un marqueur de message (« ZCZC », « NNNN ») dans un texte reçu, sinon None.

    2.8.4 (audit D9) — forme exacte acceptée partout ; sinon mot isolé de même longueur à UN caractère
    près (« NNNM », « ZCZG ») : une seule erreur de réception ne fait plus manquer le début ou la fin
    d'un bulletin. `last=True` renvoie la dernière occurrence.
    """
    up = (text or "").upper()
    marker = marker.upper()
    hits = [(m.start(), m.end()) for m in re.finditer(re.escape(marker), up)]
    for m in re.finditer(r"(?<![A-Z0-9])[A-Z0-9]{%d}(?![A-Z0-9])" % len(marker), up):
        if sum(a != b for a, b in zip(m.group(0), marker)) == 1:
            hits.append((m.start(), m.end()))
    if not hits:
        return None
    return max(hits) if last else min(hits)


def marker_received(tail, marker):
    """Vrai si le marqueur vient d'être reçu dans la fin du flux en direct.

    La forme exacte suffit ; la forme à un caractère près doit être un mot TERMINÉ (suivi d'un autre
    caractère), pour ne pas se déclencher sur un mot encore en cours de réception.
    """
    if marker.upper() in (tail or "").upper():
        return True
    mark = find_marker(tail, marker, last=True)
    return mark is not None and mark[1] < len(tail)


class BulletinSegmenter:
    KNOWN_ZONES = (
        "GERMAN BIGHT",
        "DOGGER",
        "FISHER",
        "FORTIES",
        "VIKING",
        "UTSIRA",
        "BISCAY",
        "FINISTERRE",
        "SOLE",
        "LUNDY",
        "FASTNET",
        "SHANNON",
        "ENGLISH CHANNEL",
        "DOVER",
        "THAMES",
        "BALTIC",
        "SKAGERRAK",
        "KATTEGAT",
        "MEDITERRANEAN",
        "LION",
        "GENOA",
        "CORSICA",
        "SARDINIA",
        "BALEARES",
        "ALBORAN",
    )

    @classmethod
    def analyze_and_segment(
        cls,
        raw_stream_text: str,
        station_id: str = "DDH47",
        freq_khz: float = 147.3,
        decoder_metrics: dict = None,
    ) -> dict:
        text = (raw_stream_text or "").replace("\r\n", "\n").replace("\r", "\n")
        clean_len = len(text.strip())
        if clean_len == 0:
            return {
                "stream_state": "ATTENTE",
                "station": station_id,
                "freq_khz": freq_khz,
                "product": "Aucun",
                "language": "indéterminée",
                "zones": [],
                "utc_stamp": None,
                "completeness": "VIDE",
                "exploitable": False,
                "uncertainty_count": 0,
                "original_preserved": "",
            }

        upper = text.upper()
        uncertainty_count = text.count("¤")

        is_service = bool(
            ("RYRYRY" in upper or "QUICK BROWN FOX" in upper or "DE DDK" in upper or "DE DDH" in upper)
            and not any(
                w in upper
                for w in ("WARNING", "GALE", "FORECAST", "SYNOP", "PRESSURE", "WIND", "HPA", "STURM")
            )
        )

        has_zczc = (find_marker(upper, "ZCZC") is not None) or bool(re.search(r"\bW[A-Z]{3}\d{2}\s+EDZW\b", upper))
        has_nnnn = find_marker(upper, "NNNN") is not None

        wmo_match = re.search(r"\b([A-Z]{4}\d{2}\s+[A-Z]{4}\s+\d{6})\b", upper)
        if wmo_match:
            product = f"Bulletin OMM {wmo_match.group(1)}"
        elif "GALE WARNING" in upper or "STURMWARNUNG" in upper:
            product = "Avis de Coup de Vent (Gale Warning)"
        elif "FORECAST" in upper or "VORHERSAGE" in upper:
            product = "Prévision Maritime (Shipping Forecast)"
        elif "SYNOP" in upper or "ANALYSIS" in upper:
            product = "Analyse / Relevés Synoptiques"
        elif is_service:
            product = "Séquence de service / calage RTTY"
        else:
            product = "Flux RTTY en cours de réception"

        de_words = sum(
            1 for w in ("VORHERSAGE", "STURM", "WINDSTAERKE", "LUFTDRUCK", "BOEEN", " WARNUNG") if w in upper
        )
        en_words = sum(
            1
            for w in ("FORECAST", "GALE", "WARNING", "WIND", "PRESSURE", "VISIBILITY", "OUTLOOK")
            if w in upper
        )
        lang = "DE" if de_words > en_words else ("EN" if en_words > 0 else "EN/DE")

        zones = [z for z in cls.KNOWN_ZONES if z in upper]
        dt_match = re.search(r"\b(\d{6})\s*(?:UTC|Z)\b", upper)
        utc_stamp = dt_match.group(1) + " UTC" if dt_match else None

        completeness = (
            "COMPLET" if (has_zczc and has_nnnn) else ("PARTIEL" if clean_len >= 45 else "FRAGMENT")
        )
        dm = decoder_metrics or {}
        lex_q = float(dm.get("lexical_quality", 0.0))
        exploitable = bool(not is_service and clean_len >= 45 and lex_q >= 0.4)

        return {
            "stream_state": "SERVICE" if is_service else "BULLETIN",
            "station": station_id,
            "freq_khz": freq_khz,
            "product": product,
            "product_identified": product
            not in ("Flux RTTY en cours de réception", "Séquence de service / calage RTTY"),
            "language": lang,
            "zones": zones,
            "utc_stamp": utc_stamp,
            "completeness": completeness,
            "exploitable": exploitable,
            "uncertainty_count": uncertainty_count,
            "original_preserved": text,
        }
