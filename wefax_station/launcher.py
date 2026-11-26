"""Démarrage de Station WEFAX PRO.

Choix de l'interface graphique :
  - Tkinter (classique, défaut historique)  :  --ui tk
  - Qt / QML (moderne)                      :  --ui qt

La préférence est aussi lue dans ~/.station_wefax_pro/preferences.json
(clé "ui_mode" : "qt" | "tk"), mais l'argument CLI a la priorité.

Exemple d'utilisation :
    python -m wefax_station           → Tkinter (défaut ou prefs)
    python -m wefax_station --ui qt   → Qt
    python -m wefax_station --ui tk   → Tkinter forcé
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger("wefax.launcher")

# Chemin des préférences
_PREFS_PATH = Path.home() / ".station_wefax_pro" / "preferences.json"
_DEFAULT_UI = "tk"


def _read_ui_pref() -> str:
    """Lit la préférence d'interface depuis le fichier de configuration."""
    try:
        if _PREFS_PATH.exists():
            prefs = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
            mode = prefs.get("ui_mode", _DEFAULT_UI)
            if mode in ("qt", "tk"):
                return mode
    except Exception:
        pass
    return _DEFAULT_UI


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Station WEFAX PRO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--ui",
        choices=["qt", "tk"],
        default=None,
        help="Interface graphique : qt (Qt/QML) ou tk (Tkinter, défaut)",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Active les logs DEBUG",
    )
    # Passe les arguments inconnus au moteur sans planter
    ns, _ = p.parse_known_args()
    return ns


# ── Lanceurs ────────────────────────────────────────────────────────────────

def launch_tkinter() -> None:
    """Lance l'interface Tkinter historique."""
    log.info("Démarrage interface Tkinter…")
    try:
        import tkinter as tk
        from wefax_station.app.main_window import StationWefaxApp
        root = tk.Tk()
        app  = StationWefaxApp(root)
        root.mainloop()
    except ImportError as exc:
        log.error("Impossible de charger l'interface Tkinter : %s", exc)
        sys.exit(1)


def launch_qt() -> None:
    """Lance l'interface Qt/QML."""
    log.info("Démarrage interface Qt…")
    try:
        from wefax_station.qt.launcher_qt import main as qt_main
        qt_main()
    except ImportError as exc:
        log.error("PyQt6 manquant ou interface Qt incomplète : %s", exc)
        log.error("Installez PyQt6 : pip install PyQt6")
        sys.exit(1)


# ── Point d'entrée public ────────────────────────────────────────────────────

def main() -> None:
    """Point d'entrée principal — résout le choix d'interface et lance l'UI."""
    args = _parse_args()

    # Configuration des logs
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(name)-25s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Résolution de l'interface
    ui_mode = args.ui if args.ui is not None else _read_ui_pref()
    log.info("Interface sélectionnée : %s", ui_mode.upper())

    if ui_mode == "qt":
        launch_qt()
    else:
        launch_tkinter()
