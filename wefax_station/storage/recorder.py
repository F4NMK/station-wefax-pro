"""Enregistrement audio brut (WAV 16 bits mono) et relecture dans la chaîne de décodage.

L'enregistrement capture exactement ce que reçoit le décodeur (sortie audio USB de l'IC-705), avec un
fichier de métadonnées JSON (fréquence, station, mode, filtre, fréquence d'échantillonnage, erreur
d'horloge mesurée). Il sert à rejouer une réception difficile pour régler et valider la chaîne.

L'écriture se fait dans un thread dédié : le rappel audio (temps réel) ne fait que déposer les blocs
dans une file. Limites de durée et de taille issues de la politique de rétention de l'espace portable.
"""

import json
import queue
import threading
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


class AudioRecorder:
    def __init__(self, log=print):
        self.log = log
        self.active = False
        self.q = queue.Queue(maxsize=600)
        self.thread = None
        self.path = None
        self.meta = {}
        self.samples = 0
        self.fs = 44100
        self.max_samples = None
        self.max_bytes = None
        self.dropped = 0
        self.limit_reached = False

    def start(self, folder, fs, meta, max_minutes=15, max_mb=80):
        if self.active:
            return self.path
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
        tag = str(meta.get("station", "audio")).replace("/", "-").replace(" ", "_")
        self.path = folder / f"{stamp}_{tag}_{meta.get('mode', 'RX')}.wav"
        self.fs = int(fs)
        self.meta = dict(meta)
        self.meta.update(
            {
                "fs_hz": self.fs,
                "format": "WAV PCM 16 bits mono",
                "debut_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.max_samples = int(max_minutes * 60 * self.fs)
        self.max_bytes = int(max_mb * 1024 * 1024)
        self.samples = 0
        self.dropped = 0
        self.limit_reached = False
        self.q = queue.Queue(maxsize=600)
        self.active = True
        self.thread = threading.Thread(target=self._writer, daemon=True)
        self.thread.start()
        self.log(f"⏺️ Enregistrement audio démarré : {self.path.name} ({self.fs} Hz)")
        return self.path

    def push(self, block):
        """Appelé depuis le rappel audio : ne bloque jamais."""
        if not self.active:
            return
        try:
            self.q.put_nowait(np.asarray(block, dtype=np.float32).copy())
        except queue.Full:
            self.dropped += 1

    def stop(self, reason="Arrêt opérateur"):
        if not self.active:
            return None
        self.active = False
        self.q.put(None)
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.meta.update(
            {
                "fin_utc": datetime.now(timezone.utc).isoformat(),
                "duree_s": round(self.samples / self.fs, 1),
                "blocs_perdus": self.dropped,
                "motif_fin": reason,
            }
        )
        try:
            self.path.with_suffix(".json").write_text(
                json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            self.log("Métadonnées d'enregistrement non écrites : " + repr(exc))
        self.log(f"⏹️ Enregistrement terminé : {self.path.name} — {self.samples / self.fs:.0f} s ({reason})")
        return self.path

    def finish_if_limit(self):
        """À appeler régulièrement : clôt proprement (fiche JSON, journal) un enregistrement arrivé à sa limite."""
        if not getattr(self, "limit_reached", False):
            return False
        self.limit_reached = False
        self.active = True  # stop() ne traite qu'un enregistrement actif
        minutes = self.max_samples / self.fs / 60.0
        self.stop(f"Limite de durée ou de taille atteinte ({minutes:.0f} min)")
        return True

    def _writer(self):
        try:
            with wave.open(str(self.path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.fs)
                while True:
                    blk = self.q.get()
                    if blk is None:
                        break
                    pcm = np.clip(blk * 32767.0, -32768, 32767).astype("<i2")
                    w.writeframes(pcm.tobytes())
                    self.samples += len(pcm)
                    if self.samples >= self.max_samples or self.samples * 2 >= self.max_bytes:
                        # 2.8.5 : la limite est signalée (voir finish_if_limit) ; auparavant l'enregistrement
                        # s'arrêtait en silence, sans fiche JSON, le bouton restant sur « REC ON ».
                        self.limit_reached = True
                        self.active = False
                        break
        except Exception as exc:
            self.active = False
            self.log("ERREUR enregistrement audio : " + repr(exc))


def read_wav(path):
    """Lit un WAV PCM 8/16/32 bits ou flottant ; renvoie (signal float32 mono, fs, métadonnées)."""
    from scipy.io import wavfile

    fs, data = wavfile.read(str(path))
    data = np.asarray(data)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if data.dtype == np.int16:
        x = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        x = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        x = (data.astype(np.float32) - 128.0) / 128.0
    else:
        x = data.astype(np.float32)
    meta = {}
    side = Path(path).with_suffix(".json")
    if side.is_file():
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
    return x, int(fs), meta
