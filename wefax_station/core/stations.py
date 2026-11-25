"""Fréquences des émetteurs WEFAX et RTTY/NAVTEX + fonctions d'identification."""

WEFAX_STATIONS = [
    {"id": "DDH3", "station": "DWD Pinneberg (All.)", "freq": 3855.0, "period": "NUIT", "family": "DWD"},
    {"id": "DDK3", "station": "DWD Pinneberg (All.)", "freq": 7880.0, "period": "JOUR/NUIT", "family": "DWD"},
    {"id": "DDK6", "station": "DWD Pinneberg (All.)", "freq": 13882.5, "period": "JOUR", "family": "DWD"},
    {"id": "GYA1", "station": "Northwood (UK)", "freq": 2618.5, "period": "NUIT", "family": "GYA"},
    {"id": "GYA2", "station": "Northwood (UK)", "freq": 4610.0, "period": "NUIT", "family": "GYA"},
    {"id": "GYA3", "station": "Northwood (UK)", "freq": 8040.0, "period": "JOUR/NUIT", "family": "GYA"},
    {"id": "GYA4", "station": "Northwood (UK)", "freq": 11086.5, "period": "JOUR", "family": "GYA"},
    # 2.8.7 — service météo grec (HNMS) via Olympia Radio : seules cartes centrées sur la Méditerranée.
    # Un créneau par jour (≈ 08:45-10:45 UTC), fréquences prévues pour la Grèce : réception à confirmer.
    {"id": "SVJ4", "station": "Athènes (Grèce)", "freq": 8105.0, "period": "JOUR", "family": "ATH"},
    {"id": "SVJ4B", "station": "Athènes (Grèce)", "freq": 4481.0, "period": "JOUR", "family": "ATH"},
]

# ==============================================================================
# ÉMETTEURS MÉTÉO TEXTE (RTTY DWD HF/LF + NAVTEX SITOR-B CROSS LA GARDE)
# ==============================================================================
RTTY_WEATHER_STATIONS = [
    {
        "id": "DDH47",
        "station": "DWD Pinneberg (LF 147.3 kHz · Continu 24h/24)",
        "freq": 147.3,
        "baud": 50.0,
        "shift_hz": 85.0,
        "center_hz": 1900.0,
        "period": "JOUR/NUIT",
        "protocol": "RTTY_ITA2",
        "lang": "EN/DE",
        "family": "DWD_RTTY",
    },
    {
        "id": "DDH7",
        "station": "DWD Pinneberg (HF 7 MHz · Mer du Nord/Méd.)",
        "freq": 7646.0,
        "baud": 50.0,
        "shift_hz": 450.0,
        "center_hz": 1900.0,
        "period": "JOUR/NUIT",
        "protocol": "RTTY_ITA2",
        "lang": "EN/DE",
        "family": "DWD_RTTY",
    },
    {
        "id": "DDK9",
        "station": "DWD Pinneberg (HF 10 MHz · Europe/Atlantique)",
        "freq": 10100.8,
        "baud": 50.0,
        "shift_hz": 450.0,
        "center_hz": 1900.0,
        "period": "JOUR/NUIT",
        "protocol": "RTTY_ITA2",
        "lang": "EN/DE",
        "family": "DWD_RTTY",
    },
    {
        "id": "DDK2",
        "station": "DWD Pinneberg (HF 4.5 MHz · Soir/Nuit Europe)",
        "freq": 4583.0,
        "baud": 50.0,
        "shift_hz": 450.0,
        "center_hz": 1900.0,
        "period": "NUIT",
        "protocol": "RTTY_ITA2",
        "lang": "EN/DE",
        "family": "DWD_RTTY",
    },
    {
        "id": "DDH9",
        "station": "DWD Pinneberg (HF 11 MHz · Jour/Méditerranée)",
        "freq": 11039.0,
        "baud": 50.0,
        "shift_hz": 450.0,
        "center_hz": 1900.0,
        "period": "JOUR",
        "protocol": "RTTY_ITA2",
        "lang": "EN/DE",
        "family": "DWD_RTTY",
    },
    {
        "id": "DDH8",
        "station": "DWD Pinneberg (HF 14 MHz · Grand Jour)",
        "freq": 14467.3,
        "baud": 50.0,
        "shift_hz": 450.0,
        "center_hz": 1900.0,
        "period": "JOUR",
        "protocol": "RTTY_ITA2",
        "lang": "EN/DE",
        "family": "DWD_RTTY",
    },
    {
        "id": "NAVTEX-FR",
        "station": "NAVTEX 490 kHz national (La Garde S · La Maddalena I)",
        "freq": 490.0,
        "baud": 100.0,
        "shift_hz": 170.0,
        "center_hz": 1900.0,  # fréquence publiée = centre ; accord USB -1,9 kHz -> 1900 Hz audio
        "period": "créneaux météo (FR/IT)",
        "protocol": "NAVTEX_SITORB",
        "lang": "FR",
        "family": "NAVTEX_FR",
    },
    {
        "id": "NAVTEX-INT",
        "station": "NAVTEX 518 kHz international (La Maddalena R · Cabo la Nao X · La Garde W)",
        "freq": 518.0,
        "baud": 100.0,
        "shift_hz": 170.0,
        "center_hz": 1900.0,  # fréquence publiée = centre ; accord USB -1,9 kHz -> 1900 Hz audio
        "period": "créneaux météo (EN)",
        "protocol": "NAVTEX_SITORB",
        "lang": "EN",
        "family": "NAVTEX_INT",
    },
]


def is_rtty_frequency(freq_khz: float) -> bool:
    return any(abs(float(freq_khz) - s["freq"]) < 0.8 for s in RTTY_WEATHER_STATIONS)


def is_wefax_frequency(freq_khz: float) -> bool:
    return any(abs(float(freq_khz) - s["freq"]) < 0.8 for s in WEFAX_STATIONS)


def get_wefax_station_by_freq(freq_khz: float) -> dict:
    for s in WEFAX_STATIONS:
        if abs(float(freq_khz) - s["freq"]) < 0.8:
            return s
    return None
