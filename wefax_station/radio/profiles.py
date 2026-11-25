"""Profil de réception unique pour les modes WEFAX, RTTY et NAVTEX (IC-705 en CI-V).

Les trois modes sont des signaux à enveloppe constante (FM sur sous-porteuse audio / FSK), écoutés
en BLU supérieure avec un décalage de cadran de −1,9 kHz : la fréquence publiée tombe à 1900 Hz audio.

| Réglage          | Valeur            | Raison                                                                 |
|------------------|-------------------|------------------------------------------------------------------------|
| Mode             | USB-D (DATA)      | Audio USB direct, micro coupé, pas de traitement BF de modulation      |
| Filtre FI        | FIL, 3,0 kHz      | Contient 1500–2300 Hz (WEFAX) et les tonalités FSK avec leurs flancs ; |
|                  |                   | la sélectivité fine est faite par les filtres adaptés logiciels        |
| PBT              | centré            | Bande passante reproductible                                           |
| AGC              | FAST              | Après un craquement (QRN), le gain revient en quelques ms              |
| NR               | OFF               | Le réducteur de bruit altère phase et fréquence instantanée            |
| Notch auto       | OFF               | Le notch automatique supprimerait la porteuse blanche 2300 Hz ou une   |
|                  |                   | tonalité FSK qu'il prend pour un sifflement                            |
| Notch manuel     | OFF               | idem                                                                   |
| NB               | conservé          | Choix de l'opérateur selon le QRN local ; le logiciel a son propre     |
|                  |                   | suppresseur d'impulsions (WEFAX) et des filtres adaptés (RTTY/NAVTEX)  |
| Préampli / ATT   | protection        | Seule la surcharge (OVF) est corrigée automatiquement                  |

Filtre plus étroit pour RTTY/NAVTEX : non appliqué automatiquement. Sur l'IC-705, en USB-D, la position
du centre d'un filtre étroit dans la bande audio n'est pas garantie à 1900 Hz ; un filtre mal centré
supprimerait une tonalité. La bande passante réellement obtenue est mesurée sur le bruit à chaque
changement de fréquence (dsp/passband.py) et journalisée.
"""

USB_DIAL_OFFSET_KHZ = -1.90
AUDIO_CENTER_HZ = 1900.0

RX_PROFILE = {
    "mode": "USB-D",
    "if_width_hz": 3000,
    "agc": "FAST",
    "nr": False,
    "auto_notch": False,
    "manual_notch": False,
    "nb": "conservé",
}

# Bande audio utile par mode (Hz) : sert au contrôle de la bande passante mesurée.
REQUIRED_AUDIO_BAND = {
    "WEFAX": (1450.0, 2350.0),
    "RTTY": (1900.0 - 225.0 - 60.0, 1900.0 + 225.0 + 60.0),
    "RTTY_LF": (1900.0 - 42.5 - 60.0, 1900.0 + 42.5 + 60.0),
    "NAVTEX": (1900.0 - 85.0 - 120.0, 1900.0 + 85.0 + 120.0),
}

# Commandes CI-V (IC-705) du profil, toutes en lecture/écriture de réglages de RÉCEPTION uniquement.
CIV_RX_PROFILE = [
    ("AGC FAST", [0x16, 0x12, 0x01]),
    ("NR OFF", [0x16, 0x40, 0x00]),
    ("Notch auto OFF", [0x16, 0x41, 0x00]),
    ("Notch manuel OFF", [0x16, 0x48, 0x00]),
]
