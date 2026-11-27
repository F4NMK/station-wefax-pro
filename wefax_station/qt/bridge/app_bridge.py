"""Pont principal PyQt6 ↔ moteurs métier (arbitre, cycle de vie, audio).

Orchestre RadioBridge et DspBridge, expose le statut global de l'application
au QML, et gère le thread audio (sounddevice).

Règle : ce fichier n'importe jamais tkinter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import (
    QObject, pyqtSignal, pyqtSlot, pyqtProperty, QTimer
)

from wefax_station.qt.bridge.radio_bridge import RadioBridge
from wefax_station.qt.bridge.dsp_bridge import DspBridge

try:
    from wefax_station.version import SOFTWARE_VERSION
except ImportError:
    SOFTWARE_VERSION = "2.0-qt"

log = logging.getLogger("wefax.qt")

# Chemin par défaut des préférences
_PREFS_PATH = Path.home() / ".station_wefax_pro" / "preferences.json"


class AppBridge(QObject):
    """Pont principal : cycle de vie de l'application exposé au QML.

    Signaux → QML :
      statusChanged(str)         Message de statut (barre du bas)
      versionReady(str)          Numéro de version logicielle
      journalLine(str)           Ligne de journal
      modeChanged(str)           Mode courant : WEFAX | RTTY | NAVTEX | IDLE
      scheduleChanged(list)      Plan de réception mis à jour
      workspaceReady(str)        Chemin du dossier de travail ouvert
      audioConnected(bool)       Flux audio USB actif
      closingApp()               Fermeture confirmée
      weatherUpdated(dict)       Nouvelles données météo synoptique
      bulletinsUpdated(list)     Liste des bulletins RTTY/NAVTEX reçus
      rttyLine(str, str)         Ligne RTTY reçue (texte, station)
      navtexLine(str, str)       Ligne NAVTEX reçue (texte, station)
      prefsLoaded(dict)          Préférences chargées
      diagnosticLine(str)        Ligne de sortie diagnostic
    """

    # ── Signaux généraux ─────────────────────────────────────────────────────
    statusChanged    = pyqtSignal(str,            arguments=["msg"])
    versionReady     = pyqtSignal(str,            arguments=["version"])
    journalLine      = pyqtSignal(str,            arguments=["line"])
    modeChanged      = pyqtSignal(str,            arguments=["mode"])
    scheduleChanged  = pyqtSignal("QVariantList", arguments=["schedule"])
    workspaceReady   = pyqtSignal(str,            arguments=["path"])
    audioConnected   = pyqtSignal(bool,           arguments=["ok"])
    closingApp       = pyqtSignal()

    # ── Signaux météo / bulletins ────────────────────────────────────────────
    weatherUpdated   = pyqtSignal("QVariantMap",  arguments=["data"])
    bulletinsUpdated = pyqtSignal("QVariantList", arguments=["list"])

    # ── Signaux RTTY / NAVTEX ────────────────────────────────────────────────
    rttyLine         = pyqtSignal(str, str,       arguments=["text", "station"])
    navtexLine       = pyqtSignal(str, str,       arguments=["text", "station"])

    # ── Signaux paramètres / diagnostic ─────────────────────────────────────
    prefsLoaded      = pyqtSignal("QVariantMap",  arguments=["prefs"])
    diagnosticLine   = pyqtSignal(str,            arguments=["text"])

    # ── Signaux DSP toggles ──────────────────────────────────────────────────
    dspToggleChanged = pyqtSignal(str, bool,      arguments=["name", "value"])

    # ── Signaux Winlink ──────────────────────────────────────────────────────
    winlinkStatus    = pyqtSignal(str,            arguments=["msg"])
    winlinkSessionStarted = pyqtSignal()
    winlinkSessionStopped = pyqtSignal()

    # ── Signaux Recording ────────────────────────────────────────────────────
    recordingStarted = pyqtSignal(str,            arguments=["path"])
    recordingStopped = pyqtSignal(str,            arguments=["path"])

    # ── Signaux Archives ─────────────────────────────────────────────────────
    archivesLoaded   = pyqtSignal("QVariantList", arguments=["files"])
    imageCompleted   = pyqtSignal(str,            arguments=["path"])
    exportDone       = pyqtSignal(str,            arguments=["path"])

    # ── Signaux Météo analyse ────────────────────────────────────────────────
    weatherCalcResult = pyqtSignal(str,           arguments=["report"])
    webChartReady     = pyqtSignal(str, str,      arguments=["path", "label"])

    # ── Signaux Bulletin desk ────────────────────────────────────────────────
    bulletinDocsLoaded  = pyqtSignal("QVariantList", arguments=["docs"])
    bulletinTextReady   = pyqtSignal(str,            arguments=["text"])
    bulletinStatsReady  = pyqtSignal(str,            arguments=["text"])
    bulletinSaved       = pyqtSignal(str,            arguments=["path"])

    # ────────────────────────────────────────────────────────────────────────
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._mode       = "IDLE"
        self._audio_ok   = False
        self._closing    = False
        self._prefs: dict[str, Any] = {}
        self._bulletins: list[dict] = []

        # Sous-ponts
        self.radio = RadioBridge(parent=self)
        self.dsp   = DspBridge(parent=self)

        # Moteurs métier (lazy)
        self._workspace = None
        self._arbiter   = None
        self._planner   = None

        # Timers
        self._radio_timer = QTimer(self)
        self._radio_timer.setInterval(500)
        self._radio_timer.timeout.connect(self.radio.pollStatus)

        self._dsp_timer = QTimer(self)
        self._dsp_timer.setInterval(80)
        self._dsp_timer.timeout.connect(self.dsp.pollAudio)

        self._sched_timer = QTimer(self)
        self._sched_timer.setInterval(60_000)
        self._sched_timer.timeout.connect(self._refresh_schedule)

        self._wx_timer = QTimer(self)
        self._wx_timer.setInterval(300_000)   # toutes les 5 min
        self._wx_timer.timeout.connect(self._refresh_weather)

        # Connexions inter-ponts
        self.radio.logMessage.connect(self.journalLine)
        self.dsp.phaseDetected.connect(self._on_phase)
        self.dsp.lineReceived.connect(self._on_dsp_line)
        self.dsp.imageCompleted.connect(self._on_image_completed)
        # Câblage DSP → AGC-RF : DspBridge alimente RadioBridge en métriques RMS/SNR
        self.dsp.set_radio_bridge(self.radio)

    # ── Propriétés ───────────────────────────────────────────────────────────

    @pyqtProperty(str, notify=modeChanged)
    def currentMode(self) -> str:
        return self._mode

    @pyqtProperty(bool, notify=audioConnected)
    def isAudioConnected(self) -> bool:
        return self._audio_ok

    @pyqtProperty(str, constant=True)
    def softwareVersion(self) -> str:
        return SOFTWARE_VERSION

    # ── Slots QML : cycle de vie ─────────────────────────────────────────────

    @pyqtSlot()
    def initialize(self) -> None:
        """Appelé par QML au chargement : démarre les moteurs, les timers."""
        self._load_prefs_internal()
        self.versionReady.emit(SOFTWARE_VERSION)
        self.statusChanged.emit("Station WEFAX PRO — prêt")
        self._start_arbiter()
        self._radio_timer.start()
        self._dsp_timer.start()
        self._sched_timer.start()
        self._wx_timer.start()
        self._refresh_schedule()
        self._refresh_weather()
        self.journalLine.emit(f"Station WEFAX PRO v{SOFTWARE_VERSION} démarrée.")

        # Appliquer les toggles DSP sauvegardés
        self._apply_dsp_prefs()

        # Auto-connexion radio si prefs l'indiquent
        if self._prefs.get("auto_connect_radio"):
            port     = self._prefs.get("serial_port", "COM14")
            baud     = int(self._prefs.get("baud_rate", 19200))
            protocol = self._prefs.get("protocol", "ICOM CI-V")
            civ_hex  = self._prefs.get("civ_address", "A4")
            self.radio.connectFull(port, baud, protocol, civ_hex)

        # Auto-démarrage audio
        if self._prefs.get("start_audio_auto"):
            dev  = self._prefs.get("audio_device", "")
            rate = int(self._prefs.get("sample_rate", 44100))
            self.startAudio(dev, rate)

    @pyqtSlot(str, int)
    def connectRadio(self, port: str, baud: int) -> None:
        ok  = self.radio.connect(port, baud)
        msg = f"CI-V {'établie' if ok else 'échouée'} sur {port} à {baud} bauds."
        self.statusChanged.emit(msg)
        self.journalLine.emit(msg)

    @pyqtSlot()
    def disconnectRadio(self) -> None:
        self.radio.disconnect()
        self.statusChanged.emit("Liaison CI-V fermée.")

    @pyqtSlot(str)
    def setMode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self.modeChanged.emit(mode)
        if self._arbiter:
            try:
                self._arbiter.set_requested_mode(mode, user_initiated=True)
            except Exception:
                pass
        self.journalLine.emit(f"Mode → {mode}")

    @pyqtSlot()
    def requestClose(self) -> None:
        if self._closing:
            return
        self._closing = True
        for t in (self._radio_timer, self._dsp_timer, self._sched_timer, self._wx_timer):
            t.stop()
        self._stop_audio()
        self.radio.disconnect()
        self.closingApp.emit()

    # ── Slots QML : audio ────────────────────────────────────────────────────

    @pyqtSlot(str, int)
    def startAudio(self, device: str, sample_rate: int) -> None:
        self._stop_audio()
        try:
            import sounddevice as sd
            self._sd_stream = sd.InputStream(
                device=device or None,
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=2048,
                callback=self._audio_callback,
            )
            self._sd_stream.start()
            self._audio_ok = True
            self.audioConnected.emit(True)
            self.journalLine.emit(f"Audio démarré : {device or 'défaut'} @ {sample_rate} Hz")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Audio : {exc}")
            self._audio_ok = False
            self.audioConnected.emit(False)

    @pyqtSlot()
    def stopAudio(self) -> None:
        self._stop_audio()

    # ── Slots QML : planning ─────────────────────────────────────────────────

    @pyqtSlot()
    def requestScheduleRefresh(self) -> None:
        self._refresh_schedule()

    @pyqtSlot(str, float)
    def launchScheduledReception(self, station_id: str, freq_khz: float) -> None:
        self.radio.tuneStation(freq_khz)
        self.setMode("WEFAX")
        self.journalLine.emit(f"▶ Lancement réception {station_id} @ {freq_khz} kHz")
        self.statusChanged.emit(f"Réception {station_id}")

    @pyqtSlot()
    def startNextScheduled(self) -> None:
        """Lance la prochaine émission prévue."""
        if self._planner:
            try:
                nxt = self._planner.next_emission()
                if nxt:
                    self.launchScheduledReception(nxt.get("station_id", "?"), nxt.get("freq_khz", 0))
            except Exception as exc:
                self.journalLine.emit(f"⚠️ Planificateur : {exc}")

    # ── Slots QML : météo ────────────────────────────────────────────────────

    @pyqtSlot()
    def refreshWeather(self) -> None:
        self._refresh_weather()

    # ── Slots QML : archives ─────────────────────────────────────────────────

    @pyqtSlot()
    def openArchives(self) -> None:
        path = Path(self._prefs.get("archive_dir", Path.home() / "Documents" / "WEFAX" / "archives"))
        path.mkdir(parents=True, exist_ok=True)
        self._open_folder(path)
        self.workspaceReady.emit(str(path))

    @pyqtSlot(str)
    def saveCurrentImage(self, src_path: str) -> None:
        """Copie l'image courante dans le dossier archives."""
        try:
            import shutil
            src = Path(src_path)
            dst_dir = Path(self._prefs.get("archive_dir", src.parent))
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            shutil.copy2(src, dst)
            self.journalLine.emit(f"Image archivée : {dst}")
            self.statusChanged.emit(f"Sauvegardé dans {dst_dir.name}")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Sauvegarde : {exc}")

    @pyqtSlot()
    def refreshArchives(self) -> None:
        """Scanne le dossier archives et émet archivesLoaded avec la liste triée."""
        archive_dir = Path(self._prefs.get("archive_dir",
                           Path.home() / "Documents" / "WEFAX" / "archives"))
        try:
            base = archive_dir
            partials = base / "partielles"
            files = []
            for p in list(base.glob("*.png")) + list(base.glob("*.jpg")) + \
                     list((partials).glob("*.png") if partials.exists() else []):
                if p.name in ("logo_personnalise.png",) or \
                   p.name.startswith("reception_en_cours") or \
                   "_decodee" in p.name or "_traitee" in p.name or \
                   p.parent.name == "det":
                    continue
                stat = p.stat()
                files.append({
                    "path":    str(p),
                    "name":    p.name + ("  (partielle)" if p.parent.name == "partielles" else ""),
                    "size_kb": round(stat.st_size / 1024),
                    "mtime":   stat.st_mtime,
                    "partial": p.parent.name == "partielles",
                })
            files.sort(key=lambda f: f["mtime"], reverse=True)
            self.archivesLoaded.emit(files)
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Archives : {exc}")
            self.archivesLoaded.emit([])

    @pyqtSlot(str)
    def exportSignedImage(self, src_path: str) -> None:
        """Exporte l'image avec cartouche opérateur (signature) en PNG."""
        import threading
        threading.Thread(target=self._run_export_signed, args=(src_path,), daemon=True).start()

    def _run_export_signed(self, src_path: str) -> None:
        try:
            import numpy as np
            from PIL import Image, ImageDraw, ImageFont
            from wefax_station.storage.atomic import atomic_png
            from wefax_station.ui.logo import default_app_logo
            from wefax_station.version import SOFTWARE_BRAND

            p = Path(src_path)
            if not p.exists():
                self.journalLine.emit(f"⚠️ Export : fichier introuvable {p.name}")
                return
            with Image.open(p) as im:
                image = im.convert("RGB")
            arr = np.asarray(image)
            height, width = arr.shape[:2]
            # Cartouche bas de page
            result = Image.new("RGB", (width, height + 92), (12, 23, 43))
            result.paste(image, (0, 0))
            d = ImageDraw.Draw(result)
            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except OSError:
                font = ImageFont.load_default()
            # Logo
            logo_src = default_app_logo()
            logo = logo_src.copy().convert("RGBA")
            logo.thumbnail((58, 58))
            result.paste(logo, (12, height + 16), logo)
            # Textes
            callsign = self._prefs.get("operator_callsign", "").strip()
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            texts = [
                SOFTWARE_BRAND + (f" · Opérateur : {callsign}" if callsign else ""),
                f"Réception : {stamp}",
                "Export manuel signé",
            ]
            for i, text in enumerate(texts):
                d.text((80, height + 9 + i * 26), text, font=font, fill=(176, 194, 212))
            # Sauvegarde
            out_path = p.parent / (p.stem + "_signe.png")
            atomic_png(str(out_path), np.asarray(result))
            self.exportDone.emit(str(out_path))
            self.journalLine.emit(f"🖊️ Export signé : {out_path.name}")
            self.statusChanged.emit(f"Export signé : {out_path.name}")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Export signé : {exc}")

    @pyqtSlot(str)
    def deleteArchiveFile(self, path: str) -> None:
        """Supprime une archive après confirmation (depuis QML)."""
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
                self.journalLine.emit(f"🗑️ Supprimé : {p.name}")
                self.refreshArchives()
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Suppression : {exc}")

    # ── Slots QML : analyse météo assistée ──────────────────────────────────

    @pyqtSlot(str)
    def computeGeostrophic(self, json_params: str) -> None:
        """Calcule l'estimation géostrophique depuis les paramètres QML (JSON).

        json_params : {"dp": float, "dist": float, "lat": float,
                       "low": float|null, "front": str, "type": str, "valid": str}
        Émet weatherCalcResult(str) avec le texte du rapport.
        """
        import json as _json
        import threading
        def _run():
            try:
                p = _json.loads(json_params)
                from wefax_station.weather.geometry import geostrophic_estimate
                result = geostrophic_estimate(
                    float(p["dp"]), float(p["dist"]), float(p["lat"]),
                    float(p["low"]) if p.get("low") else None,
                )
                kind    = p.get("type", "analyse").strip().lower()
                valid   = p.get("valid", "").strip()
                lines = [
                    "CALCUL PHYSIQUE ASSISTÉ — pas une prévision locale complète",
                    f"Carte : {kind} ; validité {valid}",
                    "Source de position et de mesure : confirmation manuelle opérateur.",
                    f"Gradient : {result['gradient_hpa_100km']:.2f} hPa / 100 km",
                    f"Vent géostrophique théorique : {result['geostrophic_kmh']:.0f} km/h"
                    f" ({result['geostrophic_kt']:.0f} kt).",
                    "Ce n'est ni le vent à 10 m, ni une rafale. Densité supposée : 1,225 kg/m³.",
                ]
                if result.get("wind_from_deg") is None:
                    lines.append("Direction : indéterminée sans sens des basses pressions et nord vrai.")
                else:
                    lines.append(f"Direction géostrophique de provenance : {result['wind_from_deg']:.0f}° vrais.")
                comments = {
                    "froid":  "Front froid confirmé à proximité : risque de bande pluvieuse ou d'averses.",
                    "chaud":  "Front chaud confirmé : nébulosité étendue et précipitations possibles.",
                    "occlus": "Front occlus confirmé : nuages et précipitations possibles.",
                }
                front = p.get("front", "").strip().lower()
                lines.append(comments.get(front,
                    "Pluie / couverture nuageuse : non déterminées par ce calcul de gradient."))
                lines.extend([
                    "Ensoleillement : non déterminable à partir du seul espacement des isobares.",
                    "Évolution : comparer des cartes datées successives. Aucune échéance n'est inventée.",
                    "Relief, friction, courbure et effets côtiers : non modélisés. Confiance non calibrée.",
                ])
                self.weatherCalcResult.emit("\n".join(lines))
            except Exception as exc:
                self.weatherCalcResult.emit(f"⚠️ Calcul impossible : {exc}")
        threading.Thread(target=_run, daemon=True).start()

    @pyqtSlot(str)
    def downloadWebChart(self, chart_key: str) -> None:
        """Télécharge une carte DWD et émet webChartReady(tmp_path)."""
        import threading
        threading.Thread(target=self._run_download_web_chart,
                         args=(chart_key,), daemon=True).start()

    def _run_download_web_chart(self, chart_key: str) -> None:
        import io, urllib.request
        try:
            from wefax_station.core.web_charts import WEB_WEATHER_CHARTS
            from wefax_station.version import SOFTWARE_VERSION
            cfg      = WEB_WEATHER_CHARTS.get(chart_key)
            if cfg is None:
                # Clé numérique (index)
                keys = list(WEB_WEATHER_CHARTS.keys())
                try:
                    cfg = WEB_WEATHER_CHARTS[keys[int(chart_key)]]
                    chart_key = keys[int(chart_key)]
                except (ValueError, IndexError):
                    self.journalLine.emit(f"⚠️ Carte inconnue : {chart_key}")
                    return
            self.statusChanged.emit(f"Téléchargement {chart_key}…")
            last_err = "Serveur injoignable"
            for url in cfg["urls"]:
                try:
                    req = urllib.request.Request(url, headers={
                        "User-Agent": f"Mozilla/5.0 StationWEFAXPro/{SOFTWARE_VERSION}"
                    })
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        raw = resp.read()
                    # Sauvegarde temporaire
                    tmp = Path(self._prefs.get("workspace_dir",
                               Path.home() / "Documents" / "WEFAX")) / "web_chart_tmp.png"
                    from PIL import Image as PILImage
                    img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                    img.save(str(tmp))
                    self.webChartReady.emit(str(tmp), chart_key)
                    self.statusChanged.emit(f"✅ Carte DWD : {chart_key}")
                    self.journalLine.emit(f"🌐 Carte Web DWD téléchargée : {chart_key}")
                    return
                except Exception as exc:
                    last_err = str(exc)
            self.journalLine.emit(f"⚠️ Carte Web : {last_err}")
            self.statusChanged.emit(f"⚠️ Carte Web non disponible")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Carte Web : {exc}")

    @pyqtSlot(result="QVariantList")
    def listWebCharts(self) -> list:
        """Retourne la liste des noms de cartes web disponibles."""
        try:
            from wefax_station.core.web_charts import WEB_WEATHER_CHARTS
            return list(WEB_WEATHER_CHARTS.keys())
        except Exception:
            return []

    # ── Slots QML : aide intégrée ─────────────────────────────────────────────

    @pyqtSlot(result="QVariantList")
    def listHelpTopics(self) -> list:
        """Retourne la liste des rubriques d'aide : [{key, title}]."""
        try:
            from wefax_station.ui.help_content import HELP_TOPICS_25
            return [{"key": k, "title": v[0]} for k, v in HELP_TOPICS_25.items()]
        except Exception:
            return []

    @pyqtSlot(str, result=str)
    def getHelpContent(self, topic_key: str) -> str:
        """Retourne le contenu textuel d'une rubrique d'aide."""
        try:
            from wefax_station.ui.help_content import HELP_TOPICS_25
            title, body = HELP_TOPICS_25.get(topic_key, ("Rubrique inconnue", "Contenu non disponible."))
            return f"## {title}\n\n{body}"
        except Exception as exc:
            return f"⚠️ Erreur aide : {exc}"

    # ── Slots QML : Bulletin desk ─────────────────────────────────────────────

    @pyqtSlot(int, result="QVariantList")
    def getBulletinDocs(self, hours: int = 24) -> list:
        """Retourne la liste des documents reçus dans les N dernières heures.

        Chaque élément : {id, kind, start_utc, station, freq_khz, status,
                          reliability_pct, reliability_grade, product, files}
        """
        try:
            from datetime import timedelta
            import json as _json
            workspace_dir = Path(self._prefs.get("workspace_dir",
                                 Path.home() / "Documents" / "WEFAX"))
            idx_path = workspace_dir / "index_receptions.json"
            if not idx_path.exists():
                return []
            docs_raw = _json.loads(idx_path.read_text(encoding="utf-8")).get("documents", [])
            now = datetime.now(timezone.utc)
            out = []
            for d in docs_raw:
                try:
                    start = datetime.fromisoformat(str(d.get("start_utc", "")).replace("Z", "+00:00"))
                    if not start.tzinfo:
                        start = start.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if now - start > timedelta(hours=hours):
                    continue
                # Cherche le fichier record
                rec_rel = d.get("record_rel_path", "")
                rec = {}
                if rec_rel:
                    rec_p = workspace_dir / rec_rel
                    try:
                        rec = _json.loads(rec_p.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        pass
                q = rec.get("quality", {})
                station = d.get("station", "?")
                kind = ("Carte WEFAX" if d.get("category") == "cartes"
                        else ("NAVTEX" if "NAVTEX" in station else "Bulletin RTTY"))
                # Fichiers sources
                file_paths = []
                for s in rec.get("sources", []):
                    rp = s.get("rel_path", "")
                    if rp:
                        file_paths.append(str(workspace_dir / rp))
                for s in rec.get("derived", []):
                    rp = s.get("rel_path", "")
                    if rp:
                        file_paths.append(str(workspace_dir / rp))
                out.append({
                    "id":               d.get("document_id", ""),
                    "kind":             kind,
                    "start_utc":        start.strftime("%d/%m %H:%M"),
                    "station":          station,
                    "freq_khz":         d.get("freq_khz", 0.0),
                    "status":           d.get("status", ""),
                    "reliability_pct":  q.get("reliability_pct"),
                    "reliability_grade": q.get("reliability_grade", ""),
                    "product":          q.get("product", ""),
                    "files":            file_paths,
                })
            out.sort(key=lambda x: x["start_utc"], reverse=True)
            return out
        except Exception as exc:
            self.journalLine.emit(f"⚠️ BulletinDocs : {exc}")
            return []

    @pyqtSlot("QVariantList", str)
    def compileBulletin(self, included_ids: list, zone: str) -> None:
        """Compile le bulletin météo depuis les documents sélectionnés.

        Émet bulletinTextReady(texte) et bulletinStatsReady(stats).
        """
        import threading
        threading.Thread(
            target=self._run_compile_bulletin,
            args=(list(included_ids), zone),
            daemon=True,
        ).start()

    def _run_compile_bulletin(self, included_ids: list, zone: str) -> None:
        try:
            import json as _json
            workspace_dir = Path(self._prefs.get("workspace_dir",
                                 Path.home() / "Documents" / "WEFAX"))
            # Recharge tous les docs
            all_docs = {d["id"]: d for d in self.getBulletinDocs(72)}
            docs = [all_docs[i] for i in included_ids if i in all_docs]
            charts = [d for d in docs if d["kind"] == "Carte WEFAX"]
            texts  = [d for d in docs if d["kind"] != "Carte WEFAX"]

            now = datetime.now(timezone.utc)
            callsign = self._prefs.get("operator_callsign", "").strip().upper()

            L = [
                f"BULLETIN MÉTÉO MARINE — {now:%d/%m/%Y %H:%M} UTC"
                + (f" — {callsign}" if callsign else ""),
                f"Zone d'analyse : {zone}" if zone else "Zone d'analyse : non spécifiée",
                "=" * 72,
                "",
                "CE QU'IL FAUT RETENIR",
                "",
            ]

            # Textes RTTY / NAVTEX
            def _doc_body(doc):
                txt_files = [f for f in doc["files"] if f.endswith("_original.txt")]
                if not txt_files:
                    return ""
                try:
                    text = Path(txt_files[0]).read_text(encoding="utf-8", errors="ignore")
                    return text.split("=" * 78)[-1] if "=" * 78 in text else text
                except OSError:
                    return ""

            if texts:
                try:
                    from wefax_station.weather.rtty_parse import parse_point_forecasts, gale_warnings
                    from wefax_station.weather.plain_language import clean_raw
                    combined = "\n".join(clean_raw(_doc_body(d)) for d in texts)
                    if combined.strip():
                        L.append("Synthèse des bulletins texte RTTY / NAVTEX :")
                        L.append(combined[:3000])
                except Exception:
                    L.append("(Synthèse non disponible)")
            else:
                L.append("Aucun bulletin texte sélectionné.")

            L += ["", "=" * 72, "A. CARTES WEFAX REÇUES", ""]
            if charts:
                for d in sorted(charts, key=lambda x: x["start_utc"]):
                    rel = d["reliability_pct"]
                    L.append(f"  • {d['start_utc']} UTC — {d['station']} "
                              f"({float(d['freq_khz']):.1f} kHz) — fiabilité "
                              f"{rel if rel is not None else '?'} % — {d['status']}")
            else:
                L.append("  Aucune carte sélectionnée.")

            L += ["", "B. BULLETINS TEXTE REÇUS (RTTY / NAVTEX)", ""]
            if texts:
                for d in sorted(texts, key=lambda x: x["start_utc"]):
                    rel = d["reliability_pct"]
                    body = _doc_body(d)
                    warnings_txt = ""
                    try:
                        from wefax_station.weather.rtty_parse import gale_warnings
                        ws = gale_warnings(body, translate=True)
                        if ws:
                            warnings_txt = " ⚠ " + "; ".join(ws[:3])
                    except Exception:
                        pass
                    L.append(f"  ▸ {d['start_utc']} UTC — {d['station']} "
                              f"— fiabilité {'fiable' if (rel or 0) >= 70 else 'à vérifier'} "
                              f"({rel if rel is not None else '?'} %){warnings_txt}")
            else:
                L.append("  Aucun bulletin texte sélectionné.")

            L += ["", "C. OBSERVATIONS DE L'OPÉRATEUR", "",
                  "  (Saisir ici les observations locales : pression, vent, ciel…)", ""]

            L += [
                "",
                "Faits reçus et hypothèses de l'opérateur sont distingués.",
                "Ce bulletin ne remplace pas les avis officiels (Météo-France, CROSS, NAVTEX).",
            ]
            self.bulletinTextReady.emit("\n".join(L))

            # Statistiques
            per: dict = {}
            for d in self.getBulletinDocs(24):
                s = per.setdefault(d["station"], {"cartes": 0, "textes": 0, "rel": [], "hours": []})
                s["cartes" if d["kind"] == "Carte WEFAX" else "textes"] += 1
                if d["reliability_pct"] is not None:
                    s["rel"].append(d["reliability_pct"])
                try:
                    h = int(d["start_utc"].split(" ")[1].split(":")[0])
                    s["hours"].append(h)
                except Exception:
                    pass
            stat_lines = [
                "RÉCEPTIONS DES DERNIÈRES 24 H PAR STATION",
                "",
                f"{'Station':<12}{'Cartes':>7}{'Textes':>7}{'Fiab. moy.':>12}  Heures UTC",
                "-" * 70,
            ]
            for sid in sorted(per):
                s = per[sid]
                mean = (f"{sum(s['rel']) / len(s['rel']):.0f} %" if s["rel"] else "—")
                hours = ",".join(f"{h:02d}" for h in sorted(set(s["hours"])))
                stat_lines.append(f"{sid:<12}{s['cartes']:>7}{s['textes']:>7}{mean:>12}  {hours}")
            if not per:
                stat_lines.append("Aucune réception archivée sur 24 h.")
            self.bulletinStatsReady.emit("\n".join(stat_lines))

        except Exception as exc:
            self.bulletinTextReady.emit(f"⚠️ Compilation impossible : {exc}")

    @pyqtSlot(str, str)
    def saveBulletinText(self, text: str, zone: str) -> None:
        """Sauvegarde le texte du bulletin dans le dossier de travail.

        Émet bulletinSaved(path) ou journalLine avec l'erreur.
        """
        try:
            callsign = self._prefs.get("operator_callsign", "").strip().upper()
            ts   = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
            name = f"BULLETIN_METEO{'_' + callsign if callsign else ''}_{ts}Z.txt"
            workspace_dir = Path(self._prefs.get("workspace_dir",
                                 Path.home() / "Documents" / "WEFAX"))
            dest_dir = workspace_dir / "mes_bulletins"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            dest.write_text(text + "\n", encoding="utf-8")
            self.bulletinSaved.emit(str(dest))
            self.journalLine.emit(f"📝 Bulletin enregistré : {name}")
            self.statusChanged.emit(f"Bulletin enregistré : {name}")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Sauvegarde bulletin : {exc}")

    # ── Slots QML : RTTY / log ───────────────────────────────────────────────

    @pyqtSlot(int)
    def setRttyBaud(self, baud: int) -> None:
        if self.dsp and hasattr(self.dsp, "set_rtty_baud"):
            self.dsp.set_rtty_baud(baud)
        self.journalLine.emit(f"RTTY vitesse → {baud} Bd")

    @pyqtSlot(int)
    def setRttyShift(self, shift_hz: int) -> None:
        if self.dsp and hasattr(self.dsp, "set_rtty_shift"):
            self.dsp.set_rtty_shift(shift_hz)
        self.journalLine.emit(f"RTTY décalage → {shift_hz} Hz")

    @pyqtSlot()
    def saveRttyLog(self) -> None:
        try:
            from datetime import datetime
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = Path(self._prefs.get("workspace_dir", Path.home() / "Documents" / "WEFAX")) / f"rtty_{ts}.txt"
            dst.parent.mkdir(parents=True, exist_ok=True)
            # DspBridge accumule les lignes dans un buffer
            lines = getattr(self.dsp, "_rtty_lines", [])
            dst.write_text("\n".join(lines), encoding="utf-8")
            self.journalLine.emit(f"Log RTTY sauvegardé : {dst}")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Sauvegarde log RTTY : {exc}")

    @pyqtSlot(str)
    def openBulletin(self, bulletin_id: str) -> None:
        # Cherche dans le buffer et affiche le contenu complet
        for b in self._bulletins:
            if str(b.get("id")) == bulletin_id:
                self.journalLine.emit("─" * 60)
                self.journalLine.emit(b.get("full_text", "(pas de texte)"))
                self.journalLine.emit("─" * 60)
                break

    # ── Slots QML : workspace ────────────────────────────────────────────────

    @pyqtSlot()
    def openWorkspace(self) -> None:
        path = Path(self._prefs.get("workspace_dir", Path.home() / "Documents" / "WEFAX"))
        path.mkdir(parents=True, exist_ok=True)
        self._open_folder(path)
        self.workspaceReady.emit(str(path))

    @pyqtSlot()
    def chooseWorkspaceDir(self) -> None:
        # En Qt pur on passerait par QFileDialog — ici on émet juste un log
        self.journalLine.emit("ℹ️ Modifiez le chemin manuellement dans le champ texte.")

    @pyqtSlot()
    def chooseArchiveDir(self) -> None:
        self.journalLine.emit("ℹ️ Modifiez le chemin manuellement dans le champ texte.")

    # ── Slots QML : préférences ──────────────────────────────────────────────

    @pyqtSlot()
    def loadPrefs(self) -> None:
        self._load_prefs_internal()
        self.prefsLoaded.emit(self._prefs)

    @pyqtSlot("QVariantMap")
    def savePrefs(self, prefs: dict) -> None:
        self._prefs.update(prefs)
        try:
            _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _PREFS_PATH.write_text(json.dumps(self._prefs, indent=2, ensure_ascii=False), encoding="utf-8")
            self.statusChanged.emit("Préférences sauvegardées.")
            self.journalLine.emit("💾 Préférences enregistrées.")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Sauvegarde préfs : {exc}")

    @pyqtSlot(str)
    def switchUiMode(self, mode: str) -> None:
        """Redémarre l'application avec l'interface demandée (qt ou tk)."""
        self._prefs["ui_mode"] = mode
        try:
            _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _PREFS_PATH.write_text(json.dumps(self._prefs, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self.journalLine.emit(f"🔄 Redémarrage en mode {mode.upper()}…")
        self.statusChanged.emit(f"Redémarrage → {mode.upper()}")

        # Relancer le processus avec l'argument --ui approprié
        args = [sys.executable, "-m", "wefax_station", f"--ui={mode}"]
        try:
            subprocess.Popen(args)  # noqa: S603
            QTimer.singleShot(500, self.requestClose)
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Redémarrage impossible : {exc}")

    # ── Slots QML : téléchargement cartes web ────────────────────────────────

    @pyqtSlot()
    def downloadWebCharts(self) -> None:
        self.journalLine.emit("📥 Téléchargement des cartes web DWD…")
        threading.Thread(target=self._run_download_charts, daemon=True).start()

    # ── Slots QML : diagnostic ───────────────────────────────────────────────

    @pyqtSlot(str)
    def runDiagnostic(self, check: str) -> None:
        threading.Thread(target=self._run_diagnostic, args=(check,), daemon=True).start()

    # ── Slots QML : toggles DSP ──────────────────────────────────────────────

    @pyqtSlot(bool)
    def setAptAutoEnabled(self, enabled: bool) -> None:
        """Active/désactive la détection automatique APT (signaux 300 Hz et 450 Hz)."""
        self._prefs["apt_auto_enabled"] = enabled
        if self.dsp and hasattr(self.dsp, "setAptAutoEnabled"):
            self.dsp.setAptAutoEnabled(enabled)
        self.dspToggleChanged.emit("apt_auto", enabled)
        self.journalLine.emit(f"APT auto {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(bool)
    def setQrnBlankerEnabled(self, enabled: bool) -> None:
        """Active/désactive le blanker QRN (impulsions parasites courtes)."""
        self._prefs["qrn_blanker_enabled"] = enabled
        if self.dsp and hasattr(self.dsp, "setQrnBlankerEnabled"):
            self.dsp.setQrnBlankerEnabled(enabled)
        self.dspToggleChanged.emit("qrn_blanker", enabled)
        self.journalLine.emit(f"QRN blanker {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(bool)
    def setHfConditionerEnabled(self, enabled: bool) -> None:
        """Active/désactive le conditionneur HF (égalisation spectrale)."""
        self._prefs["hf_conditioner_enabled"] = enabled
        if self.dsp and hasattr(self.dsp, "setHfConditionerEnabled"):
            self.dsp.setHfConditionerEnabled(enabled)
        self.dspToggleChanged.emit("hf_conditioner", enabled)
        self.journalLine.emit(f"Conditionneur HF {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(bool)
    def setAutoMargeEnabled(self, enabled: bool) -> None:
        """Active/désactive la correction automatique de marge (recadrage)."""
        self._prefs["auto_marge_enabled"] = enabled
        if self.dsp and hasattr(self.dsp, "setAutoMargeEnabled"):
            self.dsp.setAutoMargeEnabled(enabled)
        self.dspToggleChanged.emit("auto_marge", enabled)
        self.journalLine.emit(f"Auto-marge {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(bool)
    def setFftNotchEnabled(self, enabled: bool) -> None:
        """Active/désactive le filtre notch FFT (élimination raies parasites)."""
        self._prefs["fft_notch_enabled"] = enabled
        if self.dsp and hasattr(self.dsp, "setFftNotchEnabled"):
            self.dsp.setFftNotchEnabled(enabled)
        self.dspToggleChanged.emit("fft_notch", enabled)
        self.journalLine.emit(f"FFT notch {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(bool)
    def setTensorFilterEnabled(self, enabled: bool) -> None:
        """Active/désactive le filtre tensor (réduction bruit deep learning)."""
        self._prefs["tensor_filter_enabled"] = enabled
        if self.dsp and hasattr(self.dsp, "setTensorFilterEnabled"):
            self.dsp.setTensorFilterEnabled(enabled)
        self.dspToggleChanged.emit("tensor_filter", enabled)
        self.journalLine.emit(f"Filtre tensor {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(bool)
    def setBinarisationEnabled(self, enabled: bool) -> None:
        """Active/désactive la binarisation post-traitement (noir/blanc pur)."""
        self._prefs["binarisation_enabled"] = enabled
        if self.dsp and hasattr(self.dsp, "setBinarisationEnabled"):
            self.dsp.setBinarisationEnabled(enabled)
        self.dspToggleChanged.emit("binarisation", enabled)
        self.journalLine.emit(f"Binarisation {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(bool)
    def setOverlayDept06Enabled(self, enabled: bool) -> None:
        """Active/désactive l'overlay du département 06 (Alpes-Maritimes)."""
        self._prefs["overlay_dept06_enabled"] = enabled
        self.dspToggleChanged.emit("overlay_dept06", enabled)
        self.journalLine.emit(f"Overlay dept 06 {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(bool)
    def setOverlayDept83Enabled(self, enabled: bool) -> None:
        """Active/désactive l'overlay du département 83 (Var)."""
        self._prefs["overlay_dept83_enabled"] = enabled
        self.dspToggleChanged.emit("overlay_dept83", enabled)
        self.journalLine.emit(f"Overlay dept 83 {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(bool)
    def setAutoSavePngEnabled(self, enabled: bool) -> None:
        """Active/désactive la sauvegarde automatique en fin de carte."""
        self._prefs["auto_save_enabled"] = enabled
        self.dspToggleChanged.emit("auto_save", enabled)
        self.journalLine.emit(f"Auto-save image {'ACTIVÉ' if enabled else 'DÉSACTIVÉ'}.")

    @pyqtSlot(str)
    def setImageFormat(self, fmt: str) -> None:
        """Définit le format de sauvegarde : 'PNG' (lossless) ou 'JPEG' (Winlink)."""
        fmt = fmt.upper()
        if fmt not in ("PNG", "JPEG"):
            fmt = "PNG"
        self._prefs["image_format"] = fmt
        self.journalLine.emit(f"Format image → {fmt}.")

    @pyqtSlot(int)
    def setJpegQuality(self, quality: int) -> None:
        """Définit la qualité JPEG (1-100, défaut 90)."""
        quality = max(1, min(100, quality))
        self._prefs["jpeg_quality"] = quality
        self.journalLine.emit(f"Qualité JPEG → {quality}.")

    # ── Slots QML : Winlink ──────────────────────────────────────────────────

    @pyqtSlot(str, int)
    def openWinlinkSession(self, gateway: str, port: int = 8772) -> None:
        """Ouvre une session Winlink/VARA vers le gateway spécifié."""
        threading.Thread(target=self._run_winlink_session, args=(gateway, port), daemon=True).start()

    @pyqtSlot()
    def closeWinlinkSession(self) -> None:
        """Ferme la session Winlink en cours."""
        wl = getattr(self, "_winlink_session", None)
        if wl is not None:
            try:
                wl.close()
            except Exception:
                pass
            self._winlink_session = None
        self.winlinkSessionStopped.emit()
        self.journalLine.emit("Session Winlink fermée.")

    @pyqtSlot(str)
    def sendWinlinkImage(self, image_path: str) -> None:
        """Prépare et envoie l'image WEFAX via Winlink."""
        threading.Thread(target=self._run_send_winlink_image, args=(image_path,), daemon=True).start()

    @pyqtSlot()
    def requestGrib(self) -> None:
        """Demande un fichier GRIB météo via Winlink/Saildocs."""
        threading.Thread(target=self._run_request_grib, daemon=True).start()

    # ── Slots QML : Recording ────────────────────────────────────────────────

    @pyqtSlot()
    def startRecording(self) -> None:
        """Démarre l'enregistrement audio brut."""
        threading.Thread(target=self._run_start_recording, daemon=True).start()

    @pyqtSlot()
    def stopRecording(self) -> None:
        """Arrête l'enregistrement audio en cours."""
        rec = getattr(self, "_recorder", None)
        if rec is not None:
            try:
                path = rec.stop()
                self.recordingStopped.emit(str(path) if path else "")
                self.journalLine.emit(f"Enregistrement arrêté : {path}")
            except Exception as exc:
                self.journalLine.emit(f"⚠️ Arrêt enregistrement : {exc}")
            self._recorder = None

    @pyqtSlot()
    def openRecordings(self) -> None:
        """Ouvre le dossier des enregistrements."""
        rec_dir = Path(self._prefs.get("workspace_dir", Path.home() / "Documents" / "WEFAX")) / "recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        self._open_folder(rec_dir)

    # ── Méthodes internes ────────────────────────────────────────────────────

    def _apply_dsp_prefs(self) -> None:
        """Applique les prefs DSP sauvegardées au bridge DSP au démarrage."""
        if not self.dsp:
            return
        toggles = {
            "apt_auto_enabled":      "setAptAutoEnabled",
            "qrn_blanker_enabled":   "setQrnBlankerEnabled",
            "hf_conditioner_enabled": "setHfConditionerEnabled",
            "auto_marge_enabled":    "setAutoMargeEnabled",
            "fft_notch_enabled":     "setFftNotchEnabled",
            "tensor_filter_enabled": "setTensorFilterEnabled",
            "binarisation_enabled":  "setBinarisationEnabled",
            "wefax_filter_enabled":  "setWefaxFilterEnabled",
        }
        for pref_key, slot_name in toggles.items():
            if pref_key in self._prefs and hasattr(self.dsp, slot_name):
                try:
                    getattr(self.dsp, slot_name)(bool(self._prefs[pref_key]))
                except Exception:
                    pass

    def _load_prefs_internal(self) -> None:
        try:
            if _PREFS_PATH.exists():
                self._prefs = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Lecture préfs : %s", exc)

    def _start_arbiter(self) -> None:
        try:
            from wefax_station.hybrid.arbiter import HybridModeArbiter
            self._arbiter = HybridModeArbiter(app=self)  # type: ignore[arg-type]
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Arbitre non chargé : {exc}")

    def _on_phase(self, phase: str) -> None:
        status_map = {
            "START":   "Démarrage WEFAX détecté",
            "PHASING": "Alignement en cours…",
            "IMAGE":   "Réception image WEFAX",
            "STOP":    "Fin de carte reçue",
            "IDLE":    "En veille",
        }
        self.statusChanged.emit(status_map.get(phase, phase))

    def _on_dsp_line(self, n: int, frac: float) -> None:
        """Appelé à chaque ligne WEFAX reçue (progression)."""
        pass  # Transmis directement au QML via DspBridge.lineReceived

    def _on_image_completed(self, path: str) -> None:
        """Appelé quand une carte WEFAX est complète. Applique le format image configuré."""
        img_path = Path(path)
        self.statusChanged.emit(f"Image reçue : {img_path.name}")
        self.journalLine.emit(f"🗺️ Carte reçue : {img_path.name}")

        # Si auto-save activé et le format est JPEG, convertir la carte finale
        if self._prefs.get("auto_save_enabled", True) and img_path.exists():
            img_fmt = self._prefs.get("image_format", "PNG").upper()
            if img_fmt == "JPEG" and img_path.suffix.lower() == ".png":
                threading.Thread(
                    target=self._convert_to_jpeg,
                    args=(img_path,),
                    daemon=True,
                ).start()

    def _refresh_schedule(self) -> None:
        """Construit le programme d'émissions depuis schedules.py + planner."""
        try:
            from wefax_station.core.schedules import BROADCAST_SCHEDULES_UTC
            from datetime import datetime, timezone

            now_utc = datetime.now(timezone.utc)
            items: list[dict] = []

            for entry in BROADCAST_SCHEDULES_UTC:
                # Determine status
                try:
                    h, m = map(int, entry["time_utc"].split(":"))
                    emit_dt = now_utc.replace(hour=h, minute=m, second=0, microsecond=0)
                    delta   = (emit_dt - now_utc).total_seconds()
                    if -entry.get("duration_min", 20) * 60 < delta < 0:
                        status = "EN COURS"
                    elif 0 <= delta <= 3600:
                        status = "PROCHAIN"
                    elif delta < 0:
                        status = "PASSÉ"
                    else:
                        status = "PRÉVU"
                except Exception:
                    status = "---"

                items.append({
                    "time_utc":    entry.get("time_utc", "?"),
                    "duration_min": entry.get("duration_min", 20),
                    "station_id":  entry.get("station_id", "?"),
                    "station_name": entry.get("station_name", "?"),
                    "freq_khz":    entry.get("freq_khz", 0.0),
                    "mode":        entry.get("mode", "WEFAX"),
                    "status":      status,
                })

            self.scheduleChanged.emit(items)
        except Exception as exc:
            log.debug("Refresh schedule : %s", exc)

    def _refresh_weather(self) -> None:
        """Tente de charger les données météo depuis SynopticWeatherAnalysisEngine."""
        try:
            from wefax_station.meteo.synoptic import SynopticWeatherAnalysisEngine
            if not hasattr(self, "_wx_engine"):
                self._wx_engine = SynopticWeatherAnalysisEngine()
            data = self._wx_engine.get_latest_obs()
            if data:
                self.weatherUpdated.emit(data)
        except Exception:
            pass

    def _run_download_charts(self) -> None:
        try:
            from wefax_station.web.chart_fetcher import download_dwd_charts
            download_dwd_charts()
            self.journalLine.emit("✅ Cartes DWD téléchargées.")
            self.statusChanged.emit("Cartes web mises à jour.")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Téléchargement : {exc}")

    def _run_diagnostic(self, check: str) -> None:
        self.diagnosticLine.emit(f"▶ Diagnostic : {check}")
        try:
            if check == "civ":
                ok = self.radio._ctrl is not None and self.radio._ctrl.is_connected()
                self.diagnosticLine.emit(f"  CI-V : {'✅ connecté' if ok else '❌ non connecté'}")
            elif check == "audio":
                try:
                    import sounddevice as sd
                    devs = sd.query_devices()
                    self.diagnosticLine.emit(f"  Audio : {len(devs)} périphériques détectés.")
                except Exception as e:
                    self.diagnosticLine.emit(f"  Audio : ⚠️ {e}")
            elif check == "freq":
                if self.radio._ctrl and self.radio._ctrl.is_connected():
                    self.radio._ctrl.poll_hardware_state()
                    self.diagnosticLine.emit(f"  Fréquence : {self.radio._ctrl.actual_dial_khz:.3f} kHz")
                    self.diagnosticLine.emit(f"  Mode : {self.radio._ctrl.actual_mode_str}")
                else:
                    self.diagnosticLine.emit("  ❌ Radio non connectée.")
            self.diagnosticLine.emit(f"✅ Diagnostic {check} terminé.")
        except Exception as exc:
            self.diagnosticLine.emit(f"  ⚠️ Erreur : {exc}")

    def _open_folder(self, path: Path) -> None:
        """Ouvre un dossier dans l'explorateur système."""
        try:
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])  # noqa: S603, S607
            else:
                subprocess.Popen(["xdg-open", str(path)])  # noqa: S603, S607
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Ouverture dossier : {exc}")

    def _stop_audio(self) -> None:
        stream = getattr(self, "_sd_stream", None)
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            self._sd_stream = None
        if self._audio_ok:
            self._audio_ok = False
            self.audioConnected.emit(False)

    def _audio_callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        self.dsp.feed_audio(indata[:, 0])

    def _convert_to_jpeg(self, png_path: Path) -> None:
        """Convertit la carte PNG finale en JPEG (taille réduite pour Winlink) et remplace le fichier."""
        try:
            import cv2
            from wefax_station.storage.atomic import atomic_image
            arr = cv2.imread(str(png_path), cv2.IMREAD_GRAYSCALE)
            if arr is None:
                return
            jpeg_q = int(self._prefs.get("jpeg_quality", 90))
            jpeg_path = png_path.with_suffix(".jpg")
            atomic_image(str(jpeg_path), arr, format="JPEG", jpeg_quality=jpeg_q)
            size_kb = jpeg_path.stat().st_size // 1024
            self.journalLine.emit(f"💾 JPEG sauvegardé : {jpeg_path.name} ({size_kb} kB)")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Conversion JPEG : {exc}")

    def _run_winlink_session(self, gateway: str, port: int) -> None:
        """Lance une session Winlink en arrière-plan."""
        try:
            from wefax_station.app.winlink_desk import WinlinkDeskMixin
            session = WinlinkDeskMixin()
            self._winlink_session = session
            self.winlinkSessionStarted.emit()
            self.winlinkStatus.emit(f"Connexion à {gateway}:{port}…")
            session.open_session(gateway=gateway, port=port)
            self.winlinkStatus.emit(f"Session Winlink {gateway} ouverte.")
            self.journalLine.emit(f"🌐 Winlink connecté à {gateway}:{port}")
        except ImportError:
            self.winlinkStatus.emit("⚠️ Module Winlink non disponible.")
            self.journalLine.emit("⚠️ Module winlink_desk non chargé.")
        except Exception as exc:
            self.winlinkStatus.emit(f"⚠️ Winlink : {exc}")
            self.journalLine.emit(f"⚠️ Winlink session : {exc}")

    def _run_send_winlink_image(self, image_path: str) -> None:
        """Envoie l'image WEFAX via Winlink en arrière-plan."""
        try:
            from wefax_station.app.winlink_desk import WinlinkDeskMixin
            img = Path(image_path)
            if not img.exists():
                self.winlinkStatus.emit(f"⚠️ Image introuvable : {img.name}")
                return
            # Conversion JPEG si l'image est en PNG (taille réduite pour Winlink)
            import numpy as np
            import cv2
            from wefax_station.storage.atomic import atomic_image
            arr = cv2.imread(str(img), cv2.IMREAD_GRAYSCALE)
            if arr is None:
                self.winlinkStatus.emit("⚠️ Lecture image impossible.")
                return
            jpeg_q = int(self._prefs.get("jpeg_quality", 90))
            tmp = img.with_suffix(".winlink.jpg")
            atomic_image(str(tmp), arr, format="JPEG", jpeg_quality=jpeg_q)
            size_kb = tmp.stat().st_size // 1024
            self.winlinkStatus.emit(f"Image JPEG prête : {size_kb} kB — envoi Winlink…")
            self.journalLine.emit(f"📤 Image Winlink : {tmp.name} ({size_kb} kB)")
            # Ouvrir le dossier pour faciliter l'envoi manuel si session non ouverte
            session = getattr(self, "_winlink_session", None)
            if session is None:
                self._open_folder(tmp.parent)
                self.winlinkStatus.emit(f"Image convertie dans {tmp.parent.name}/ (session Winlink non ouverte).")
        except Exception as exc:
            self.winlinkStatus.emit(f"⚠️ Préparation Winlink : {exc}")
            self.journalLine.emit(f"⚠️ Winlink image : {exc}")

    def _run_request_grib(self) -> None:
        """Demande un GRIB météo via Saildocs/Winlink."""
        try:
            from wefax_station.app.winlink_desk import WinlinkDeskMixin
            session = getattr(self, "_winlink_session", None)
            if session is None:
                self.winlinkStatus.emit("⚠️ Ouvrez d'abord une session Winlink.")
                return
            session.request_grib()
            self.winlinkStatus.emit("📥 Demande GRIB envoyée.")
            self.journalLine.emit("📥 GRIB demandé via Saildocs.")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ GRIB : {exc}")

    def _run_start_recording(self) -> None:
        """Démarre l'enregistrement audio brut en arrière-plan."""
        try:
            from wefax_station.app.recording import AudioRecorder
            rec_dir = Path(self._prefs.get("workspace_dir", Path.home() / "Documents" / "WEFAX")) / "recordings"
            rec_dir.mkdir(parents=True, exist_ok=True)
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = rec_dir / f"rx_{ts}.wav"
            self._recorder = AudioRecorder(path=path)
            self._recorder.start()
            self.recordingStarted.emit(str(path))
            self.journalLine.emit(f"⏺ Enregistrement démarré : {path.name}")
        except ImportError:
            self.journalLine.emit("⚠️ Module recording non disponible.")
        except Exception as exc:
            self.journalLine.emit(f"⚠️ Enregistrement : {exc}")
