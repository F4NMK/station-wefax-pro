"""Suivi des modules « validés terrain » (empreintes SHA-256).

L'état est stocké dans validation/module_status.json à la racine du projet.
L'application appelle check_validated() au démarrage et journalise tout écart :
un module validé qui a été modifié doit être re-testé sur le terrain.
"""

import hashlib
import json
from pathlib import Path

from wefax_station.version import PACKAGE_DIR, PROJECT_ROOT

STATUS_FILE = PROJECT_ROOT / "validation" / "module_status.json"


def sha256_of(path):
    """Empreinte du contenu (fins de ligne normalisées : Windows et Linux donnent la même valeur)."""
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def list_modules():
    return sorted(
        p.relative_to(PACKAGE_DIR).as_posix()
        for p in PACKAGE_DIR.rglob("*.py")
        if "__pycache__" not in p.parts
    )


def load_status():
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"modules": {}}


def save_status(status):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_FILE.with_suffix(".writing")
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATUS_FILE)


def check_validated():
    """Renvoie la liste des écarts (module validé modifié ou supprimé)."""
    problems = []
    for rel, info in load_status().get("modules", {}).items():
        if info.get("status") != "valide":
            continue
        path = PACKAGE_DIR / rel
        if not path.is_file():
            problems.append(f"module validé absent : {rel}")
        elif sha256_of(path) != info.get("sha256"):
            problems.append(f"module validé MODIFIÉ depuis sa validation : {rel}")
    return problems
