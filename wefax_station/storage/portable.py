"""Espace de travail portable : dossiers par opérateur / jour UTC, index, rétention, journaux tournants."""

import hashlib
import json
import logging
import re
import shutil
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from logging.handlers import RotatingFileHandler
from tkinter import filedialog, messagebox  # TODO PyQt6 : QFileDialog / QMessageBox
from wefax_station.storage.atomic import atomic_json
from wefax_station.version import PROJECT_ROOT, SOFTWARE_BRAND, SOFTWARE_VERSION
from wefax_station.weather.reliability import WeatherReliabilityEstimator


_VERSION_DIR = re.compile(r"^station_wefax_pro[_-]?(\d+(?:\.\d+)*)$", re.IGNORECASE)
SHARED_ROOT_NAME = "StationWEFAXPro"
# 2.10.0 — ce qui suit l'opérateur d'une version à l'autre (petit) ; les archives restent où elles sont
MIGRATED_ITEMS = ("configuration", "modeles")
MIGRATION_NOTES = []  # lignes à journaliser au démarrage (l'application n'existe pas encore ici)
MIGRATION_PENDING_INDEX = []  # racines dont l'index des réceptions doit être reconstruit (réceptions copiées)


def _version_key(name):
    m = _VERSION_DIR.match(name)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write_test.tmp"
        probe.write_text("OK", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def _copy_missing(src: Path, dst: Path):
    """Copie src dans dst sans jamais écraser un fichier existant ; retourne le nombre de fichiers copiés."""
    n = 0
    for f in src.rglob("*"):
        if not f.is_file() or f.name.endswith((".writing", ".tmp")):
            continue
        target = dst / f.relative_to(src)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        n += 1
    return n


def migrate_previous_data(shared: Path, anchor: Path):
    """Première ouverture de la racine commune : reprend la configuration et les profils opérateur.

    Source : la racine de cette version si elle a déjà servi, sinon celle de la version la plus récente
    rangée à côté (station_wefax_pro_X.Y.Z/StationWEFAXPro). Rien n'est déplacé ni effacé.
    """
    sources = []
    own = anchor / SHARED_ROOT_NAME
    if own.is_dir():
        sources.append(own)
    siblings = []
    for d in anchor.parent.iterdir() if anchor.parent.is_dir() else []:
        k = _version_key(d.name)
        if k is not None and d.resolve() != anchor.resolve() and (d / SHARED_ROOT_NAME).is_dir():
            siblings.append((k, d / SHARED_ROOT_NAME))
    sources += [p for _, p in sorted(siblings, reverse=True)]
    for src in sources:
        n = 0
        for item in MIGRATED_ITEMS:
            if (src / item).is_dir():
                n += _copy_missing(src / item, shared / item)
        ops = src / "donnees" / "operateurs"
        n_rx = 0
        if ops.is_dir():
            today = datetime.now(timezone.utc).date()
            recent = {(today - timedelta(days=d)).isoformat() for d in range(2)}
            for op in ops.iterdir():
                dst_op = shared / "donnees" / "operateurs" / op.name
                if (op / "profil").is_dir():
                    n += _copy_missing(op / "profil", dst_op / "profil")
                # les réceptions d'hier et d'aujourd'hui suivent (dossier Météo & bulletin sur 24 h)
                for day in (op / "receptions").glob("*") if (op / "receptions").is_dir() else []:
                    if day.is_dir() and day.name in recent:
                        n_rx += _copy_missing(day, dst_op / "receptions" / day.name)
        if n_rx:
            MIGRATION_PENDING_INDEX.append(shared)
        if n or n_rx:
            MIGRATION_NOTES.append(
                f"📦 Données reprises de {src} vers {shared} : {n} fichier(s) de configuration et de profil, "
                f"{n_rx} fichier(s) de réception d'hier et d'aujourd'hui (copiés, rien n'est effacé). "
                f"Les réceptions plus anciennes restent dans {src / 'donnees'}."
            )
            return src
    return None


def resolve_data_root(anchor: Path, unsafe=lambda p: False):
    """Racine des données (2.10.0).

    1. portable_root_path.txt à côté du programme, s'il désigne un dossier accessible ;
    2. si le programme est dans un dossier de version (station_wefax_pro_X.Y.Z), une racine COMMUNE à
       côté des versions : <dossier parent>/StationWEFAXPro. Avant, chaque version avait la sienne
       (station_wefax_pro_X.Y.Z/StationWEFAXPro) : configuration et profils étaient à refaire à chaque mise
       à jour, et supprimer une ancienne version supprimait ses archives ;
    3. sinon <dossier du programme>/StationWEFAXPro (comportement d'avant).
    """
    anchor = Path(anchor)
    pointer = anchor / "portable_root_path.txt"
    if pointer.is_file():
        try:
            custom = Path(pointer.read_text(encoding="utf-8").strip())
            if str(custom) and not unsafe(custom) and _writable(custom):
                return custom
        except Exception:
            pass
    if _version_key(anchor.name) is not None:
        shared = anchor.parent / SHARED_ROOT_NAME
        if not unsafe(shared):
            existed = shared.is_dir()
            if _writable(shared):
                if not existed or not (shared / "configuration").is_dir():
                    try:
                        migrate_previous_data(shared, anchor)
                    except Exception as exc:  # la reprise ne doit jamais empêcher le démarrage
                        MIGRATION_NOTES.append(f"⚠️ Reprise des données précédentes impossible : {exc!r}")
                return shared
    return anchor / SHARED_ROOT_NAME


def program_anchor() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PROJECT_ROOT


def default_portable_root() -> Path:
    """Racine des données (voir resolve_data_root) ; jamais dans le profil Windows de l'utilisateur."""
    return resolve_data_root(program_anchor())


from wefax_station.storage import layout as _layout  # noqa: E402


class PortableWorkspaceManager:
    SUBDIRS_ROOT = ("programme", "ressources", "aide", "modeles", "configuration", "donnees")
    # 2.11.0 — cinq dossiers par jour au lieu de sept (voir storage/layout.py)
    SUBDIRS_RECEPTION_DAY = _layout.DAY_SUBDIRS

    def __init__(self, app):
        self.app = app
        self.RetentionDays = 7
        self.quota_mb = 1500
        self.raw_audio_enabled = False
        self.raw_audio_max_minutes = 15
        self.raw_audio_max_mb = 80
        self.active_document_ids = set()
        self.session_id = (
            f"SES_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6].upper()}"
        )
        self.session_start_mono = time.monotonic()
        self.session_start_utc = datetime.now(timezone.utc)
        self.active_rx_start_utc = None
        self.rotating_logger = None
        self.root_dir = self._resolve_explicit_portable_root()
        self._init_root_structure()
        self._init_rotating_file_logger()

    def _init_rotating_file_logger(self):
        try:
            log_dir = self.reception_day_dir() / "journaux"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "station_wefax_pro_rotating.log"
            logger = logging.getLogger("StationWEFAXProRotating")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            for h in list(logger.handlers):
                logger.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass
            handler = RotatingFileHandler(
                str(log_file), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            self.rotating_logger = logger
        except Exception:
            self.rotating_logger = None

    def _is_temp_or_unsafe_path(self, candidate: Path) -> bool:
        s = str(candidate).lower()
        unsafe_tokens = ("\\appdata\\local\\temp", "/tmp/", "_meipass", "\\temp\\")
        return any(tok in s for tok in unsafe_tokens)

    def _test_writable(self, folder: Path) -> tuple:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / f".write_probe_{uuid.uuid4().hex[:8]}.tmp"
            probe.write_text("OK", encoding="utf-8")
            probe.unlink()
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _resolve_explicit_portable_root(self) -> Path:
        app_anchor = program_anchor()  # dossier de l'exécutable figé, sinon du lanceur station_wefax_pro.py
        pointer_file = app_anchor / "portable_root_path.txt"
        default_portable = resolve_data_root(app_anchor, unsafe=self._is_temp_or_unsafe_path)
        if not self._is_temp_or_unsafe_path(default_portable):
            ok, err = self._test_writable(default_portable)
            if ok:
                return default_portable
        else:
            err = "Chemin d'extraction temporaire détecté."

        messagebox.showwarning(
            "Dossier portable inaccessible",
            f"Le dossier portable par défaut n'est pas accessible en écriture :\n"
            f"{default_portable}\nMotif : {err}\n\n"
            "Veuillez choisir un dossier pour la racine portable StationWEFAXPro.",
        )
        chosen = filedialog.askdirectory(title="Choisir le dossier racine portable StationWEFAXPro")
        if chosen:
            chosen_path = Path(chosen) / "StationWEFAXPro"
            ok, err2 = self._test_writable(chosen_path)
            if ok:
                try:
                    pointer_file.write_text(str(chosen_path), encoding="utf-8")
                except Exception:
                    pass
                return chosen_path
            raise RuntimeError(f"Dossier choisi inaccessible en écriture ({chosen_path}) : {err2}")
        raise RuntimeError("Aucune racine portable valide sélectionnée.")

    def _init_root_structure(self):
        for name in self.SUBDIRS_ROOT:
            (self.root_dir / name).mkdir(parents=True, exist_ok=True)

        self.retention_cfg_path = self.root_dir / "configuration" / "politique_retention.json"
        if not self.retention_cfg_path.exists():
            self.save_retention_config()
        else:
            self.load_retention_config()

        help_file = self.root_dir / "aide" / "guide_indices_fiabilite_et_selection_hf.txt"
        try:
            help_file.write_text(WeatherReliabilityEstimator.HELP_TEXT_FR, encoding="utf-8")
        except Exception:
            pass

        tpl_path = self.root_dir / "modeles" / "modele_bulletin_adrasec.txt"
        if not tpl_path.exists():
            atomic_json(
                self.root_dir / "modeles" / "metadonnees_modele.json",
                {
                    "schema": "StationWEFAXPro-Template-1.0",
                    "version": SOFTWARE_VERSION,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                },
            )
            tpl_path.write_text(
                f"=== BULLETIN DE SITUATION MÉTÉOROLOGIQUE HF ({SOFTWARE_BRAND}) ===\n"
                "Opérateur : {OPERATEUR} | Secteur : {SECTEUR}\n"
                "Référence UTC : {DATE_UTC} | Indice de Fiabilité : {FIABILITE}\n\n"
                "1. BULLETINS RADIO DÉCODÉS (RTTY / WEFAX) :\n{SOURCES_RADIO}\n\n"
                "2. OBSERVATIONS LOCALES DATÉES :\n{OBSERVATIONS}\n\n"
                "3. SYNTHÈSE OPÉRATEUR :\n{SYNTHESE}\n",
                encoding="utf-8",
            )

    def save_retention_config(self):
        payload = {
            "version": SOFTWARE_VERSION,
            "retention_days_utc": int(self.RetentionDays),
            "quota_mb": int(self.quota_mb),
            "raw_audio_enabled": bool(self.raw_audio_enabled),
            "raw_audio_max_minutes": int(self.raw_audio_max_minutes),
            "raw_audio_max_mb": int(self.raw_audio_max_mb),
            "updated_utc": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json(self.retention_cfg_path, payload)

    def load_retention_config(self):
        try:
            data = json.loads(self.retention_cfg_path.read_text(encoding="utf-8"))
            self.RetentionDays = max(1, min(7, int(data.get("retention_days_utc", 7))))
            self.quota_mb = max(100, int(data.get("quota_mb", 1500)))
            self.raw_audio_enabled = bool(data.get("raw_audio_enabled", False))
            self.raw_audio_max_minutes = max(1, min(60, int(data.get("raw_audio_max_minutes", 15))))
            self.raw_audio_max_mb = max(10, min(500, int(data.get("raw_audio_max_mb", 80))))
        except Exception:
            pass

    def operator_tag(self, callsign: str = None) -> str:
        raw = callsign if callsign is not None else self.app.operator_callsign_var.get()
        clean = re.sub(r"[^A-Za-z0-9_-]+", "_", (raw or "").strip().upper()).strip("_")
        return clean if clean else "F4NMK"

    def operator_dir(self, callsign: str = None) -> Path:
        tag = self.operator_tag(callsign)
        op_path = self.root_dir / "donnees" / "operateurs" / tag
        (op_path / "profil").mkdir(parents=True, exist_ok=True)
        (op_path / "receptions").mkdir(parents=True, exist_ok=True)
        return op_path

    def profile_dir(self, callsign: str = None) -> Path:
        return self.operator_dir(callsign) / "profil"

    def begin_document_reception(self, start_utc: datetime = None) -> datetime:
        self.active_rx_start_utc = start_utc or datetime.now(timezone.utc)
        return self.active_rx_start_utc

    def reception_day_dir(self, ref_start_utc: datetime = None, callsign: str = None) -> Path:
        dt = ref_start_utc or self.active_rx_start_utc or datetime.now(timezone.utc)
        day_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
        day_dir = self.operator_dir(callsign) / "receptions" / day_str
        for sub in self.SUBDIRS_RECEPTION_DAY:
            (day_dir / sub).mkdir(parents=True, exist_ok=True)
        return day_dir

    @staticmethod
    def sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def relpath(self, target: Path) -> str:
        try:
            return str(Path(target).resolve().relative_to(self.root_dir.resolve())).replace("\\", "/")
        except Exception:
            return str(target)

    def register_document_record(
        self,
        category: str,
        doc_id: str,
        start_utc: datetime,
        end_utc: datetime,
        station: str,
        freq_khz: float,
        params: dict,
        quality: dict,
        source_files: list,
        derived_files: list,
        status: str = "COMPLET",
        errors: list = None,
    ) -> Path:
        day_dir = self.reception_day_dir(start_utc)
        # 2.11.0 — registres dans le sous-dossier « details » (cartes/details, bulletins/details)
        cat_dir = _layout.record_dir(day_dir, category)
        cat_dir.mkdir(parents=True, exist_ok=True)

        sources_meta = []
        for sp in source_files:
            p = Path(sp)
            if p.is_file():
                sources_meta.append(
                    {
                        "rel_path": self.relpath(p),
                        "name": p.name,
                        "size_bytes": p.stat().st_size,
                        "sha256": self.sha256_file(p),
                        "immutable_source": True,
                    }
                )

        derived_meta = []
        for dp in derived_files:
            p = Path(dp)
            if p.is_file():
                derived_meta.append(
                    {
                        "rel_path": self.relpath(p),
                        "name": p.name,
                        "size_bytes": p.stat().st_size,
                        "sha256": self.sha256_file(p),
                        "reproducible_derived": True,
                    }
                )

        record = {
            "schema": "StationWEFAXPro-Document-1.0",
            "version": SOFTWARE_VERSION,
            "session_id": self.session_id,
            "document_id": doc_id,
            "category": category,
            "start_utc": start_utc.astimezone(timezone.utc).isoformat(),
            "end_utc": end_utc.astimezone(timezone.utc).isoformat(),
            "station": station,
            "freq_khz": float(freq_khz),
            "parameters": params,
            "quality": quality,
            "status": status,
            "errors": errors or [],
            "sources": sources_meta,
            "derived": derived_meta,
        }
        rec_path = cat_dir / f"{doc_id}_record.json"
        atomic_json(rec_path, record)
        self._append_to_operator_index(record, rec_path)
        return rec_path

    def _append_to_operator_index(self, record: dict, rec_path: Path):
        idx_path = self.operator_dir() / "index_receptions.json"
        entries = []
        if idx_path.is_file():
            try:
                data = json.loads(idx_path.read_text(encoding="utf-8"))
                entries = data.get("documents", [])
            except Exception:
                entries = []
        entries = [e for e in entries if e.get("document_id") != record["document_id"]]
        entries.append(
            {
                "document_id": record["document_id"],
                "category": record["category"],
                "start_utc": record["start_utc"],
                "end_utc": record["end_utc"],
                "station": record["station"],
                "freq_khz": record["freq_khz"],
                "status": record["status"],
                "record_rel_path": self.relpath(rec_path),
            }
        )
        entries.sort(key=lambda x: x.get("start_utc", ""), reverse=True)
        atomic_json(
            idx_path,
            {
                "schema": "StationWEFAXPro-Index-1.0",
                "version": SOFTWARE_VERSION,
                "updated_utc": datetime.now(timezone.utc).isoformat(),
                "documents": entries,
            },
        )

    def rebuild_operator_index(self) -> int:
        op_dir = self.operator_dir()
        rx_root = op_dir / "receptions"
        entries = []
        for rec_path in rx_root.rglob("*_record.json"):
            try:
                rec = json.loads(rec_path.read_text(encoding="utf-8"))
                entries.append(
                    {
                        "document_id": rec["document_id"],
                        "category": rec.get("category", "cartes"),
                        "start_utc": rec.get("start_utc", ""),
                        "end_utc": rec.get("end_utc", ""),
                        "station": rec.get("station", ""),
                        "freq_khz": rec.get("freq_khz", 0.0),
                        "status": rec.get("status", ""),
                        "record_rel_path": self.relpath(rec_path),
                    }
                )
            except Exception:
                continue
        entries.sort(key=lambda x: x.get("start_utc", ""), reverse=True)
        atomic_json(
            op_dir / "index_receptions.json",
            {
                "schema": "StationWEFAXPro-Index-1.0",
                "version": SOFTWARE_VERSION,
                "rebuilt_utc": datetime.now(timezone.utc).isoformat(),
                "documents": entries,
            },
        )
        return len(entries)

    def enforce_retention_and_quota(self) -> dict:
        now_utc = datetime.now(timezone.utc)
        cutoff_utc = now_utc - timedelta(days=self.RetentionDays)
        rx_root = self.operator_dir() / "receptions"
        purged_files = 0
        purged_bytes = 0

        if rx_root.is_dir():
            for path in list(rx_root.rglob("*")):
                if not path.is_file():
                    continue
                if any(doc_id in path.name for doc_id in self.active_document_ids):
                    continue
                ref_dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                web_meta = path.with_suffix(".web.json")
                if web_meta.is_file():
                    try:
                        wm = json.loads(web_meta.read_text(encoding="utf-8"))
                        ref_dt = datetime.fromisoformat(wm["first_download_utc"].replace("Z", "+00:00"))
                    except Exception:
                        pass
                if ref_dt < cutoff_utc:
                    try:
                        sz = path.stat().st_size
                        path.unlink()
                        purged_files += 1
                        purged_bytes += sz
                    except OSError:
                        pass

            for day_folder in sorted(rx_root.iterdir()):
                if day_folder.is_dir():
                    for sub in day_folder.iterdir():
                        if sub.is_dir() and not any(sub.iterdir()):
                            try:
                                sub.rmdir()
                            except OSError:
                                pass
                    if not any(day_folder.iterdir()):
                        try:
                            day_folder.rmdir()
                        except OSError:
                            pass

        quota_bytes = int(self.quota_mb * 1024 * 1024)
        all_files = [p for p in rx_root.rglob("*") if p.is_file()] if rx_root.is_dir() else []
        total_bytes = sum(p.stat().st_size for p in all_files)

        if total_bytes > quota_bytes:
            derived_candidates = [
                p
                for p in all_files
                if (
                    p.name.endswith("_traitee.png")
                    or p.name.endswith("_carte.png")
                    or p.name.endswith(".tmp.png")
                )
                and not any(doc_id in p.name for doc_id in self.active_document_ids)
            ]
            derived_candidates.sort(key=lambda p: p.stat().st_mtime)
            for p in derived_candidates:
                if total_bytes <= quota_bytes:
                    break
                try:
                    sz = p.stat().st_size
                    p.unlink()
                    total_bytes -= sz
                    purged_files += 1
                    purged_bytes += sz
                except OSError:
                    pass

        if purged_files > 0:
            self.rebuild_operator_index()
            self.app.log_event(
                f"🧹 [Rétention 7j & Quota] {purged_files} fichier(s) purgé(s) "
                f"({purged_bytes / 1024.0:.1f} Ko libérés)."
            )
        return {
            "purged_files": purged_files,
            "purged_bytes": purged_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
        }

    def export_beyond_7days_bundle(self, target_zip_or_dir: Path) -> Path:
        export_dir = Path(target_zip_or_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        rx_root = self.operator_dir() / "receptions"
        copied = 0
        if rx_root.is_dir():
            for f in rx_root.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(rx_root)
                    dest = export_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)
                    copied += 1
        manifest = {
            "schema": "StationWEFAXPro-AutonomousExport-1.0",
            "version": SOFTWARE_VERSION,
            "operator": self.operator_tag(),
            "exported_utc": datetime.now(timezone.utc).isoformat(),
            "files_count": copied,
            "note": "Archive autonome exportée hors rétention 7 jours.",
        }
        atomic_json(export_dir / "manifest_export_autonome.json", manifest)
        return export_dir
