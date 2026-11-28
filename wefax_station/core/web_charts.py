"""Sources Internet des cartes météo (bouton « Carte Web »)."""

WEB_WEATHER_CHARTS = {
    "DWD — Analyse Surface Atlantique / Europe (Actuelle)": {
        "urls": [
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/bwk_bodendruck_na_ana.png",
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/bwk_bodendruck_weu_ana.png",
        ],
        "fallback_mode": "ANA",
    },
    "DWD — Analyse Surface Europe de l'Ouest (Zoom)": {
        "urls": [
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/bwk_bodendruck_weu_ana.png",
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/bwk_bodendruck_na_ana.png",
        ],
        "fallback_mode": "ZOOM",
    },
    "DWD — Prévision Surface H+24 / H+36 (Europe)": {
        "urls": [
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/ico_tkboden_na_024.png",
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/ico_tkboden_na_036.png",
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/bwk_bodendruck_na_v24.png",
        ],
        "fallback_mode": "H24",
    },
    "DWD — Prévision Surface H+48 (Europe)": {
        "urls": [
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/ico_tkboden_na_048.png",
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/bwk_bodendruck_na_v48.png",
        ],
        "fallback_mode": "H48",
    },
    "DWD — Prévision Surface H+84 / H+108 (Europe)": {
        "urls": [
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/ico_tkboden_na_084.png",
            "https://www.dwd.de/DWD/wetter/wv_spez/hobbymet/wetterkarten/ico_tkboden_na_108.png",
        ],
        "fallback_mode": "H84",
    },
}
