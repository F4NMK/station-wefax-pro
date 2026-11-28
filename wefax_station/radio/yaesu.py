"""Commandes CAT Yaesu (réception uniquement).

Deux familles :
* CAT « ASCII » (commandes texte terminées par « ; ») : FT-991/991A, FT-891, FT-710, FTDX10, FTDX101D/MP,
  FT-450D, FT-950, FT-2000, FTDX3000/5000. Fréquence VFO-A « FA » sur 9 chiffres en Hz, mode « MD0 »
  (C = DATA-USB), AGC « GT0 » (1 = FAST), réducteur de bruit « NR0 », notch automatique « BC0 »,
  préampli « PA0 » (0 = IPO, 1 = AMP1, 2 = AMP2), atténuateur « RA0 », S-mètre « SM0 » (0..255),
  identification « ID ».
* CAT « historique » à trames binaires de 5 octets : FT-817/818, FT-857, FT-897. Fréquence en BCD au pas
  de 10 Hz + code 0x01 ; mode + code 0x07 (0x01 = USB, 0x0A = DIG) ; lecture fréquence/mode : code 0x03 ;
  état réception (S-mètre 0..15) : code 0xE7.

Aucune commande d'émission n'est jamais envoyée (pas de TX, pas de PTT, pas de tuner).

Réglages à faire une fois dans le menu du poste (non accessibles en CAT sur tous les modèles) :
* FT-991A / FT-891 / FT-710 / FTDX10 / FTDX101 : « DATA MODE » = OTHERS (ou PSK selon le modèle) avec
  sortie audio vers USB ; niveau de sortie USB AF vers le PC ≈ 50 % ;
* FT-817 / 818 / 857 / 897 : « DIG MODE » = USER-U, interface audio externe (le poste n'a pas de carte son).
"""

YAESU_MODELS = {
    "0241": "FT-450D",
    "0251": "FT-2000",
    "0310": "FT-950",
    "0362": "FTDX5000",
    "0460": "FTDX3000",
    "0570": "FT-991",
    "0650": "FT-891",
    "0670": "FT-991A",
    "0681": "FTDX101D",
    "0682": "FTDX101MP",
    "0761": "FTDX10",
    "0800": "FT-710",
}

ASCII_RX_PROFILE = (
    ("DATA-USB", "MD0C;"),
    ("AGC FAST", "GT01;"),
    ("NR OFF", "NR00;"),
    ("Notch auto OFF", "BC00;"),
)

LEGACY_MODES = {"USB": 0x01, "DIG": 0x0A}
TX_FORBIDDEN_ASCII = ("TX", "MX", "AC", "KY", "KS", "PS0")  # émission, VOX, tuner, manipulateur, arrêt


def ascii_freq_cmd(freq_hz):
    return f"FA{int(freq_hz):09d};"


def ascii_is_safe(cmd):
    c = cmd.strip().upper()
    return not any(c.startswith(p) for p in TX_FORBIDDEN_ASCII)


def parse_ascii_freq(resp):
    """« FA014070000; » -> 14070000 (Hz) ou None."""
    r = (resp or "").strip()
    i = r.find("FA")
    if i < 0:
        return None
    digits = "".join(ch for ch in r[i + 2 :].split(";")[0] if ch.isdigit())
    return int(digits) if len(digits) >= 8 else None


def parse_ascii_id(resp):
    r = (resp or "").strip()
    i = r.find("ID")
    if i < 0:
        return None
    code = r[i + 2 : i + 6]
    return YAESU_MODELS.get(code, f"Yaesu ID {code}" if code.isdigit() else None)


def legacy_freq_frame(freq_hz):
    s = f"{int(round(freq_hz / 10.0)):08d}"
    return bytes([int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16), 0x01])


def legacy_mode_frame(mode="DIG"):
    return bytes([LEGACY_MODES[mode], 0x00, 0x00, 0x00, 0x07])


LEGACY_READ_FREQ = bytes([0x00, 0x00, 0x00, 0x00, 0x03])
LEGACY_READ_RX = bytes([0x00, 0x00, 0x00, 0x00, 0xE7])


def parse_legacy_freq(reply):
    """5 octets (4 BCD + mode) -> fréquence en Hz, ou None si la réponse n'est pas du BCD valide."""
    if not reply or len(reply) < 5:
        return None
    b = reply[:4]
    if any((x & 15) > 9 or (x >> 4) > 9 for x in b):
        return None
    hz = int("".join(f"{x:02x}" for x in b)) * 10
    return hz if 100_000 <= hz <= 470_000_000 else None


def legacy_smeter_label(byte):
    """Octet d'état réception FT-817/857/897 : bits 0-3 = S-mètre (0..15, 9 = S9)."""
    v = int(byte) & 0x0F
    return v, (f"S{v}" if v <= 9 else f"S9+{(v - 9) * 10}dB")
