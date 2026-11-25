"""Décodeur NAVTEX / SITOR-B (CCIR 476, ITU-R M.476 et M.625, mode FEC collectif).

Chaîne :
1. Récupération d'horloge bit synchrone (100 Bd) par boucle avance/retard sur les décisions souples :
   la dérive de la carte son et le jitter de propagation sont suivis en continu.
2. Alignement des mots de 7 bits et polarité : on retient l'alignement qui maximise la proportion de
   mots conformes au contrôle 4B/3Y (exactement quatre « B »).
3. Diversité temporelle : chaque caractère est émis en position DX puis répété en position RX quatre
   signaux plus tard (+5 mots). La parité DX/RX est déterminée par la concordance des deux copies et
   par les signaux de phasage (β en DX, α en RX).
4. Combinaison des deux copies : copie conforme à 4B/3Y préférée ; si les deux sont conformes mais
   différentes, la plus sûre (marges souples) ; si aucune ne l'est, correction souple d'un bit
   (le moins fiable) quand les deux copies corrigées concordent ; sinon caractère d'erreur « * ».
5. Analyse des messages : ZCZC B1B2B3B4 … NNNN (B1 émetteur, B2 objet, B3B4 numéro), taux d'erreur
   et élimination des doublons déjà reçus correctement (taux d'erreur ≤ 4 %, règle des récepteurs NAVTEX).
"""

import re
from datetime import datetime, timezone

import numpy as np

from wefax_station.rtty.codes import (
    CCIR476_FIGS,
    CCIR476_LTRS,
    CCIR476_VALID,
    CCIR_ALPHA,
    CCIR_BETA,
    CCIR_FIGS,
    CCIR_LTRS,
    CCIR_RQ,
)
from wefax_station.rtty.fsk import SPS
from wefax_station.rtty.segmenter import find_marker

ERROR_CHAR = "*"
NAVTEX_SUBJECTS = {
    "A": "Avis aux navigateurs",
    "B": "Avis de coup de vent / météo",
    "C": "Glaces",
    "D": "SAR / piraterie",
    "E": "Prévisions météo",
    "F": "Pilotage",
    "G": "AIS",
    "H": "LORAN",
    "J": "GNSS",
    "K": "Autres aides",
    "L": "Avis aux navigateurs (suite)",
    "V": "Service spécial",
    "W": "Service spécial",
    "X": "Service spécial",
    "Y": "Service spécial",
    "Z": "Aucun message",
}


class SitorBDecoder:
    def __init__(self):
        self.reset()

    def reset(self):
        self.buf = np.zeros(0)
        self.p = None  # position (fraction d'échantillon décimé) du début du prochain bit
        self.bits = []  # décisions souples par bit (+ = B)
        self.align = None  # (polarité ±1,) ; les bits sont recadrés sur la frontière de mot
        self.recent_bits = []
        self._words_since_check = 0
        self.words = []  # (code, marges) — mots alignés
        self.dx_parity = None
        self.next_dx = None  # index du prochain mot DX à combiner
        self.shift = "LTRS"
        self.valid_ema = 0.0
        self.total_chars = 0
        self.error_chars = 0
        self.text_log = ""
        self.messages = []
        self._msg = None
        self.seen = {}

    # ---------------------------------------------------------- 1. horloge bit
    def _bit(self, p):
        a = int(round(p))
        return float(np.mean(self.buf[a : a + SPS])) if a >= 0 and a + SPS <= len(self.buf) else 0.0

    def _acquire(self):
        n_bits = (len(self.buf) // SPS) - 2
        if n_bits < 48:
            return
        scores = []
        for off in range(SPS):
            vals = [abs(self._bit(off + k * SPS)) for k in range(n_bits)]
            scores.append(np.mean(vals))
        self.p = float(int(np.argmax(scores)))

    def _clock(self):
        if self.p is None:
            self._acquire()
            if self.p is None:
                return
        while self.p + SPS + 3 < len(self.buf):
            b = self._bit(self.p)
            e = self._bit(self.p - 2)
            late = self._bit(self.p + 2)
            err = (abs(late) - abs(e)) / (abs(b) + 0.2)
            self.bits.append(b)
            self.p += SPS + float(np.clip(0.6 * err, -0.75, 0.75))
        keep = max(0, int(self.p) - 4 * SPS)
        self.buf = self.buf[keep:]
        self.p -= keep

    # -------------------------------------------------------- 2. alignement
    @staticmethod
    def _word(bits):
        code = 0
        for b in bits:
            code = (code << 1) | (1 if b > 0 else 0)
        return code

    def _score_align(self, bits, off, pol):
        """Proportion de mots 4B/3Y ; bonus pour les signaux de phasage α/β (seuls signaux d'attente du
        mode FEC), pénalité pour RQ (jamais émis en FEC) : lève l'ambiguïté d'alignement pendant le phasage.
        """
        n = (len(bits) - off) // 7
        ok = ab = rq = 0
        for w in range(n):
            c = self._word([pol * b for b in bits[off + 7 * w : off + 7 * w + 7]])
            if c in CCIR476_VALID:
                ok += 1
                ab += c in (CCIR_ALPHA, CCIR_BETA)
                rq += c == CCIR_RQ
        n = max(1, n)
        return ok / n, (ok + 0.5 * ab - 1.0 * rq) / n

    def _best_alignment(self, bits):
        best = None
        for o in range(7):
            for p in (1.0, -1.0):
                valid, score = self._score_align(bits, o, p)
                if best is None or score > best[0]:
                    best = (score, valid, o, p)
        return best

    def _align(self):
        W = 7 * 14
        if self.align is None:
            if len(self.bits) < W:
                return
            window = self.bits[-W:]
            score, valid, off, pol = self._best_alignment(window)
            if valid >= 0.6:
                self.align = (pol,)
                self.bits = self.bits[len(self.bits) - W + off :]
                self.recent_bits = []
            else:
                self.bits = self.bits[-W:]
                return
        pol = self.align[0]
        while len(self.bits) >= 7:
            seg = self.bits[:7]
            del self.bits[:7]
            self.recent_bits = (self.recent_bits + seg)[-W:]
            segp = [pol * b for b in seg]
            self.words.append((self._word(segp), np.abs(segp)))
            self._words_since_check += 1
        if self._words_since_check >= 14 and len(self.recent_bits) == W:
            self._words_since_check = 0
            self._check_lock()

    def _check_lock(self):
        """Contrôle continu : si un autre alignement est nettement meilleur, on se recale."""
        pol = self.align[0]
        cur_valid, cur_score = self._score_align(self.recent_bits, 0, pol)
        self.valid_ema = cur_valid
        score, valid, off, p = self._best_alignment(self.recent_bits)
        if (off != 0 or p != pol) and valid >= 0.7 and score > cur_score + 0.3:
            self.align = None
            self.words = []
            self.dx_parity = None
            self.next_dx = None
            self.bits = list(self.recent_bits) + self.bits
        elif cur_valid < 0.3:
            self.align = None
            self.words = []
            self.dx_parity = None
            self.next_dx = None

    # ------------------------------------------------------------ 3. DX / RX
    def _parity(self):
        w = self.words
        if len(w) < 30:
            return None
        score = [0.0, 0.0]
        for i in range(max(0, len(w) - 120), len(w) - 5):
            c1, c2 = w[i][0], w[i + 5][0]
            if c1 in CCIR476_VALID and c1 == c2 and c1 not in (CCIR_ALPHA, CCIR_BETA):
                score[i % 2] += 1.0
            if c1 == CCIR_BETA:
                score[i % 2] += 0.5
            if c1 == CCIR_ALPHA:
                score[(i + 1) % 2] += 0.5
        if max(score) < 3:
            return self.dx_parity
        best = int(np.argmax(score))
        if self.dx_parity is None or score[best] > 1.5 * score[self.dx_parity]:
            return best
        return self.dx_parity

    @staticmethod
    def _correct(code, margins):
        """Correction souple d'un bit : rend un mot conforme 4B/3Y en inversant le bit le moins sûr."""
        ones = bin(code).count("1")
        if ones not in (3, 5):
            return None, 0.0
        cand = []
        for k in range(7):
            bit = (code >> (6 - k)) & 1
            if (ones == 5 and bit == 1) or (ones == 3 and bit == 0):
                cand.append((margins[k], k))
        m, k = min(cand)
        others = sorted(margins)[1] if len(margins) > 1 else 1.0
        return code ^ (1 << (6 - k)), float(others - m)

    def _combine(self):
        par = self._parity()
        if par is None:
            return []
        if par != self.dx_parity:
            self.dx_parity = par
            self.next_dx = None
        if self.next_dx is None:
            start = max(0, len(self.words) - 60)
            self.next_dx = start + ((par - start) % 2)
        out = []
        while self.next_dx + 5 < len(self.words):
            dx, mdx = self.words[self.next_dx]
            rx, mrx = self.words[self.next_dx + 5]
            self.next_dx += 2
            vdx, vrx = dx in CCIR476_VALID, rx in CCIR476_VALID
            if vdx and vrx:
                code = dx if dx == rx or float(np.min(mdx)) >= float(np.min(mrx)) else rx
                conf = 1.0 if dx == rx else 0.5
            elif vdx:
                code, conf = dx, 0.8
            elif vrx:
                code, conf = rx, 0.8
            else:
                c1, q1 = self._correct(dx, mdx)
                c2, q2 = self._correct(rx, mrx)
                if c1 is not None and c1 == c2:
                    code, conf = c1, 0.4
                else:
                    code, conf = None, 0.0
            tok = self._token(code)
            if tok:
                out.append((tok, conf))
        if len(self.words) > 400:
            cut = len(self.words) - 200
            cut -= cut % 2
            self.words = self.words[cut:]
            self.next_dx -= cut
        return out

    def _token(self, code):
        if code is None:
            self.total_chars += 1
            self.error_chars += 1
            return ERROR_CHAR
        if code in (CCIR_ALPHA, CCIR_BETA, CCIR_RQ):
            return ""
        if code == CCIR_LTRS:
            self.shift = "LTRS"
            return ""
        if code == CCIR_FIGS:
            self.shift = "FIGS"
            return ""
        self.total_chars += 1
        table = CCIR476_LTRS if self.shift == "LTRS" else CCIR476_FIGS
        return table.get(code, "")

    # -------------------------------------------------------- 5. messages
    def _parse_messages(self, text):
        self.text_log = (self.text_log + text)[-6000:]
        if self._msg is None:
            m = re.search(r"ZCZC ?([A-Z])([A-Z])(\d\d)", self.text_log)
            if m:
                self._msg = {
                    "b1": m.group(1),
                    "b2": m.group(2),
                    "serial": m.group(3),
                    "start_utc": datetime.now(timezone.utc).isoformat(),
                    "start": m.start(),
                }
                self._msg_errors0 = self.error_chars
                self._msg_total0 = self.total_chars
        if self._msg is not None:
            body = self.text_log[self._msg["start"] :]
            mark = find_marker(body[4:], "NNNN")  # 2.8.4 : fin tolérante à une erreur (hors « ZCZC » initial)
            end = (mark[0] + 4) if mark is not None else -1
            if end >= 0:
                msg = dict(self._msg)
                msg["text"] = body[: end + 4]
                n = max(1, self.total_chars - self._msg_total0)
                msg["error_rate"] = round((self.error_chars - self._msg_errors0) / n, 4)
                msg["subject"] = NAVTEX_SUBJECTS.get(msg["b2"], "?")
                msg["end_utc"] = datetime.now(timezone.utc).isoformat()
                key = (msg["b1"], msg["b2"], msg["serial"])
                prev = self.seen.get(key)
                msg["duplicate"] = bool(prev is not None and prev <= 0.04 and msg["serial"] != "00")
                if prev is None or msg["error_rate"] < prev:
                    self.seen[key] = msg["error_rate"]
                self.messages.append(msg)
                self.messages = self.messages[-50:]
                self.text_log = body[end + 4 :]
                self._msg = None
            elif len(body) > 5000:
                self._msg = None

    # ------------------------------------------------------------- entrée
    def feed(self, d):
        """d : décisions souples (+ = mark) à SPS échantillons par bit. Renvoie [(caractère, confiance)]."""
        self.buf = np.concatenate([self.buf, np.asarray(d, dtype=np.float64)])
        self._clock()
        self._align()
        out = self._combine() if self.align is not None else []
        if out:
            self._parse_messages("".join(c for c, _ in out))
        return out
