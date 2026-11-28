"""Tables de codage : ITA2 (télégraphe international n° 2) et CCIR 476 / ITU-R M.476 (SITOR).

ITA2 : codes 5 bits, bit 1 émis en premier (poids faible), 1 = mark.
CCIR 476 : mots de 7 bits, bit de poids fort émis en premier, exactement 4 bits à 1 (« B »)
et 3 à 0 (« Y ») — c'est le contrôle d'erreur 4B/3Y. Source de la table : CCIR 476
(reproduite sur https://en.wikipedia.org/wiki/CCIR_476). Signaux de service :
α (signal de phasage 1) = 0x0F, β (signal de phasage 2) = 0x33, RQ (répétition) = 0x66.
"""

# --------------------------------------------------------------------------- ITA2
ITA2_LTRS = {
    0x00: "",
    0x01: "E",
    0x02: "\n",
    0x03: "A",
    0x04: " ",
    0x05: "S",
    0x06: "I",
    0x07: "U",
    0x08: "\r",
    0x09: "D",
    0x0A: "R",
    0x0B: "J",
    0x0C: "N",
    0x0D: "F",
    0x0E: "C",
    0x0F: "K",
    0x10: "T",
    0x11: "Z",
    0x12: "L",
    0x13: "W",
    0x14: "H",
    0x15: "Y",
    0x16: "P",
    0x17: "Q",
    0x18: "O",
    0x19: "B",
    0x1A: "G",
    0x1B: "<FIGS>",
    0x1C: "M",
    0x1D: "X",
    0x1E: "V",
    0x1F: "<LTRS>",
}
ITA2_FIGS = {
    0x00: "",
    0x01: "3",
    0x02: "\n",
    0x03: "-",
    0x04: " ",
    0x05: "'",
    0x06: "8",
    0x07: "7",
    0x08: "\r",
    0x09: "$",
    0x0A: "4",
    0x0B: "\a",
    0x0C: ",",
    0x0D: "!",
    0x0E: ":",
    0x0F: "(",
    0x10: "5",
    0x11: "+",
    0x12: ")",
    0x13: "2",
    0x14: "#",
    0x15: "6",
    0x16: "0",
    0x17: "1",
    0x18: "9",
    0x19: "?",
    0x1A: "&",
    0x1B: "<FIGS>",
    0x1C: ".",
    0x1D: "/",
    0x1E: "=",
    0x1F: "<LTRS>",
}
ITA2_LTRS_CODE = 0x1F
ITA2_FIGS_CODE = 0x1B
ITA2_ENCODE_LTRS = {v: k for k, v in ITA2_LTRS.items() if v and not v.startswith("<")}
ITA2_ENCODE_FIGS = {v: k for k, v in ITA2_FIGS.items() if v and not v.startswith("<") and v != "\a"}

# --------------------------------------------------------------------------- CCIR 476
CCIR476_LTRS = {
    0x17: "J",
    0x1B: "F",
    0x1D: "C",
    0x1E: "K",
    0x27: "W",
    0x2B: "Y",
    0x2D: "P",
    0x2E: "Q",
    0x35: "G",
    0x39: "M",
    0x3A: "X",
    0x3C: "V",
    0x47: "A",
    0x4B: "S",
    0x4D: "I",
    0x4E: "U",
    0x53: "D",
    0x55: "R",
    0x56: "E",
    0x59: "N",
    0x63: "Z",
    0x65: "L",
    0x69: "H",
    0x71: "O",
    0x72: "B",
    0x74: "T",
    0x5C: " ",
    0x6C: "\n",
    0x78: "\r",
    0x6A: "",
    0x36: "<FIGS>",
    0x5A: "<LTRS>",
    0x0F: "<ALPHA>",
    0x33: "<BETA>",
    0x66: "<RQ>",
}
CCIR476_FIGS = dict(CCIR476_LTRS)
CCIR476_FIGS.update(
    {
        0x17: "\a",
        0x1B: "!",
        0x1D: ":",
        0x1E: "(",
        0x27: "2",
        0x2B: "6",
        0x2D: "0",
        0x2E: "1",
        0x35: "&",
        0x39: ".",
        0x3A: "/",
        0x3C: "=",
        0x47: "-",
        0x4B: "'",
        0x4D: "8",
        0x4E: "7",
        0x53: "$",
        0x55: "4",
        0x56: "3",
        0x59: ",",
        0x63: "+",
        0x65: ")",
        0x69: "#",
        0x71: "9",
        0x72: "?",
        0x74: "5",
    }
)
CCIR_LTRS = 0x5A
CCIR_FIGS = 0x36
CCIR_ALPHA = 0x0F
CCIR_BETA = 0x33
CCIR_RQ = 0x66
CCIR476_VALID = frozenset(CCIR476_LTRS)
CCIR476_ENCODE_LTRS = {v: k for k, v in CCIR476_LTRS.items() if v and not v.startswith("<")}
CCIR476_ENCODE_FIGS = {
    v: k for k, v in CCIR476_FIGS.items() if v and not v.startswith("<") and v not in (" ", "\r", "\n", "\a")
}

assert len(CCIR476_LTRS) == 35 and all(bin(c).count("1") == 4 for c in CCIR476_LTRS)
assert len(set(range(128)) & {c for c in range(128) if bin(c).count("1") == 4}) == 35
