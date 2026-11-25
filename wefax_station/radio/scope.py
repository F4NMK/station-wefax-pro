"""Veille spectrale (2.8.9) : lecture du spectre de l'IC-705 par CI-V, SANS changer de fréquence.

L'IC-705 n'a qu'un récepteur, mais son écran de spectre couvre jusqu'à ±500 kHz autour de la fréquence
écoutée, et il peut en envoyer le contenu au PC (commande CI-V 27 00, 475 points de 0 à 160, découpés en
11 trames sur l'USB). On y lit le niveau des autres stations de la même bande pendant que la carte ou le
bulletin continue : par exemple, réglé sur DDK3 (7880 kHz) avec ±250 kHz, on voit aussi DDH7 (7646 kHz,
RTTY), Northwood (8040 kHz) et Athènes (8105 kHz).

Ce que cela mesure : l'écart entre la station et le bruit, en points de l'échelle du spectre (0 à 160).
Ce n'est PAS la qualité de décodage (le scan reste juge), mais cela suffit pour savoir qu'une station
émet, si elle est forte, ou muette.

Ce module ne fait aucune entrée / sortie : assemblage des trames et analyse.
"""

from __future__ import annotations

import statistics

SCOPE_POINTS = 475
SPANS_HZ = (2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000)

LEVELS = ((20, "fort"), (10, "net"), (5, "faible"))


def bcd_freq(hz: int) -> list:
    """Fréquence en Hz → 5 octets BCD (ordre CI-V : chiffres de poids faible d'abord)."""
    digits = f"{int(hz):010d}"[::-1]
    return [int(digits[i + 1]) << 4 | int(digits[i]) for i in range(0, 10, 2)]


def parse_bcd_freq(b) -> int:
    v, mul = 0, 1
    for byte in list(b)[:5]:
        v += (byte & 0x0F) * mul + (byte >> 4) * mul * 10
        mul *= 100
    return v


def _bcd(byte) -> int:
    return (byte >> 4) * 10 + (byte & 0x0F)


def iter_frames(raw: bytes):
    """Trames CI-V complètes (FE FE dst src … FD) contenues dans un flux brut → [dst, src, charge…].

    2.9.0 — seules les trames TERMINÉES par FD sont rendues : le morceau qui suit le dernier FD est une
    trame incomplète (la suite arrive à la lecture suivante) et n'est plus pris pour une trame entière."""
    pieces = bytes(raw).split(b"\xfd")
    for chunk in pieces[:-1]:  # le dernier morceau n'a pas (encore) son FD
        pos = chunk.rfind(b"\xfe\xfe")
        if pos == -1 or len(chunk) < pos + 5:
            continue
        yield list(chunk[pos + 2 :])


class FrameStream:
    """Recolle les trames CI-V coupées entre deux lectures du port série (2.9.0).

    Le 18/11 sur l'IC-705 réel, les trames 27 00 arrivaient coupées en plusieurs lectures : chaque morceau
    était analysé seul, les trames à cheval étaient perdues et aucun balayage n'était jamais complet
    (« aucun balayage reconnu »), alors que le poste envoyait bien son spectre au bon format."""

    MAX_PENDING = 4096

    def __init__(self):
        self.pending = bytearray()

    def feed(self, chunk: bytes):
        """Ajoute les octets reçus ; rend la liste des trames complètes [dst, src, charge…]."""
        if not chunk:
            return []
        self.pending.extend(chunk)
        end = self.pending.rfind(b"\xfd")
        if end == -1:
            if len(self.pending) > self.MAX_PENDING:  # flux sans FD : on ne garde que la fin
                del self.pending[: -512]
            return []
        done, self.pending = bytes(self.pending[: end + 1]), bytearray(self.pending[end + 1 :])
        return list(iter_frames(done))


class SweepAssembler:
    """Recompose un balayage complet à partir des trames 27 00 (ordre 1 = en-tête, 2..11 = points)."""

    def __init__(self):
        self.parts = {}
        self.total = None
        self.center_hz = None
        self.span_hz = None
        self.fixed = False
        self.low_hz = self.high_hz = None
        self.out_of_range = False

    def feed_payload(self, payload) -> bool:
        """payload = [0x27, 0x00, 0x00, ordre, total, …]. True quand le balayage est complet."""
        if len(payload) < 5 or payload[0] != 0x27 or payload[1] != 0x00:
            return False
        order, total = _bcd(payload[3]), _bcd(payload[4])
        data = payload[5:]
        if total <= 0 or order <= 0:
            return False
        if order == 1:
            # nouvel en-tête : on repart de zéro (un balayage commence toujours par l'ordre 1)
            self.parts = {}
            self.total = total
            self.completed = False
            if len(data) >= 12:
                self.fixed = data[0] == 0x01
                a, b = parse_bcd_freq(data[1:6]), parse_bcd_freq(data[6:11])
                if self.fixed:
                    self.low_hz, self.high_hz = a, b
                    self.center_hz, self.span_hz = (a + b) // 2, (b - a) // 2
                else:
                    self.center_hz, self.span_hz = a, b
                self.out_of_range = data[11] == 0x01
                self.parts[1] = data[12:]
            else:
                self.parts[1] = []
            return self.total == 1
        if self.total is None:
            return False  # trames de milieu de balayage avant tout en-tête : ignorées
        self.parts[order] = list(data)
        # 2.9.0 — True une seule fois, au moment où la dernière trame du balayage arrive
        if len(self.parts) >= self.total and not getattr(self, "completed", False):
            self.completed = True
            return True
        return False

    def points(self) -> list:
        pts = []
        for k in sorted(self.parts):
            pts.extend(self.parts[k])
        return pts[:SCOPE_POINTS]

    def feed_raw(self, raw: bytes, radio_addr=None) -> bool:
        """Octets bruts du port série, dans l'ordre d'arrivée (les trames coupées sont recollées)."""
        stream = getattr(self, "_stream", None)
        if stream is None:
            stream = self._stream = FrameStream()
        done = False
        for fr in stream.feed(raw):
            if len(fr) < 4:
                continue
            dst, src, payload = fr[0], fr[1], fr[2:]
            if src == 0xE0 or (radio_addr is not None and src != radio_addr):
                continue
            if self.feed_payload(payload):
                done = True
        return done


def is_blank_sweep(points) -> bool:
    """Balayage entièrement à zéro (écran du poste pas encore rafraîchi après le changement de largeur,
    ou niveau de référence trop bas) : inexploitable, mais ce n'est pas une absence de données."""
    return bool(points) and max(points) == 0


def level_label(contrast) -> str:
    for thr, name in LEVELS:
        if contrast >= thr:
            return name
    return "rien"


def analyze_sweep(points, center_hz, span_hz, stations, guard_khz=1.6, floor_khz=25.0):
    """Niveau de chaque station visible : {id: {freq, contrast, peak, floor, label}}.

    `stations` : dictionnaires {"id", "freq"} (kHz, fréquence assignée). Les stations au bord de la fenêtre
    (moins de 3 kHz du bord) sont ignorées.
    """
    n = len(points)
    if n < 50 or not span_hz or not center_hz:
        return {}
    lo = center_hz - span_hz
    step = 2.0 * span_hz / n
    out = {}
    for st in stations:
        f = float(st["freq"]) * 1000.0
        if not (lo + 3000 <= f <= center_hz + span_hz - 3000):
            continue
        i0 = int((f - lo) / step)
        g = max(1, int(guard_khz * 1000 / step))
        w = max(g + 3, int(floor_khz * 1000 / step))
        near = points[max(0, i0 - g) : min(n, i0 + g + 1)]
        ring = points[max(0, i0 - w) : max(0, i0 - g - 2)] + points[min(n, i0 + g + 3) : min(n, i0 + w + 1)]
        if not near or len(ring) < 6:
            continue
        floor = statistics.median(ring)
        peak = max(near)
        c = round(peak - floor, 1)
        out[st["id"]] = {"freq": float(st["freq"]), "contrast": c, "peak": peak, "floor": floor, "label": level_label(c)}
    return out


def visible_stations(center_khz, span_khz, stations, margin_khz=3.0):
    return [s for s in stations if abs(float(s["freq"]) - center_khz) <= span_khz - margin_khz]
