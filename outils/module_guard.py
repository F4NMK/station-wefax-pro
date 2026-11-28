#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gestion des modules « validés terrain ».

Un module validé est figé : son empreinte SHA-256 est enregistrée dans
validation/module_status.json. Toute modification ultérieure est détectée
(au démarrage de l'application, dans le journal, et par la commande « check »).

Commandes :
  python outils/module_guard.py status                 état de tous les modules
  python outils/module_guard.py validate MODULE [note] marque un module validé (fige son empreinte)
  python outils/module_guard.py unvalidate MODULE      repasse un module « à valider »
  python outils/module_guard.py check                  vérifie qu'aucun module validé n'a changé
                                                       (code retour 1 sinon)
MODULE est le chemin relatif au paquet, ex. : dsp/engine.py  ou  app/scanner.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wefax_station.validation import (  # noqa: E402
    STATUS_FILE,
    list_modules,
    load_status,
    save_status,
    sha256_of,
    check_validated,
    PACKAGE_DIR,
)
from datetime import datetime, timezone  # noqa: E402


def cmd_status():
    status = load_status()
    mods = status.get("modules", {})
    print(f"{'Module':42s} {'Statut':10s} {'Intègre':8s} Note")
    for rel in list_modules():
        info = mods.get(rel, {})
        st = info.get("status", "a_valider")
        ok = ""
        if st == "valide":
            ok = "oui" if sha256_of(PACKAGE_DIR / rel) == info.get("sha256") else "MODIFIÉ"
        print(f"{rel:42s} {st:10s} {ok:8s} {info.get('note', '')}")


def cmd_validate(rel, note=""):
    path = PACKAGE_DIR / rel
    if not path.is_file():
        raise SystemExit("Module introuvable : " + rel)
    status = load_status()
    status.setdefault("modules", {})[rel] = {
        "status": "valide",
        "sha256": sha256_of(path),
        "validated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "note": note,
    }
    save_status(status)
    print("Validé et figé :", rel)


def cmd_unvalidate(rel):
    status = load_status()
    info = status.setdefault("modules", {}).get(rel)
    if not info:
        print("Module déjà « à valider » :", rel)
        return
    info["status"] = "a_valider"
    info.pop("sha256", None)
    save_status(status)
    print("Repassé à valider :", rel)


def cmd_check():
    problems = check_validated()
    if not problems:
        print("OK : aucun module validé n'a été modifié.")
        return 0
    for p in problems:
        print("ATTENTION :", p)
    return 1


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[1]
    if cmd == "status":
        cmd_status()
    elif cmd == "validate" and len(argv) >= 3:
        cmd_validate(argv[2].replace("\\", "/"), " ".join(argv[3:]))
    elif cmd == "unvalidate" and len(argv) >= 3:
        cmd_unvalidate(argv[2].replace("\\", "/"))
    elif cmd == "check":
        return cmd_check()
    else:
        print(__doc__)
        return 2
    print("Fichier d'état :", STATUS_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
