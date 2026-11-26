"""
launcher_qt.py — Point d'entrée de l'interface Qt de Station WEFAX PRO

Lance QApplication + QQmlApplicationEngine, enregistre les ponts Python
comme context properties QML, puis démarre la boucle d'événements Qt.

Usage :
    python -m wefax_station.qt.launcher_qt
    # ou
    python launcher_qt.py

Contrainte : ne modifie RIEN dans app/, ui/, hybrid/ — les moteurs
Tkinter restent intacts et peuvent être lancés indépendamment via main.py.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# ── Localisation du répertoire QML ──────────────────────────────────────────
_QML_DIR = Path(__file__).parent / "qml"


def _setup_qt_env() -> None:
    """Variables d'environnement nécessaires avant import PyQt6."""
    # Évite les avertissements MESA / libGL sur Linux sans GPU
    os.environ.setdefault("QT_XCB_NO_MITSHM", "1")
    # Rendu logiciel de secours si pas de GPU
    # os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")


def main() -> int:
    _setup_qt_env()

    # ── Imports PyQt6 (après env) ────────────────────────────────────────
    from PyQt6.QtGui     import QGuiApplication
    from PyQt6.QtQml     import QQmlApplicationEngine
    from PyQt6.QtCore    import QUrl, Qt
    from PyQt6.QtWidgets import QApplication

    # QApplication plutôt que QGuiApplication pour les widgets Qt éventuels
    app_qt = QApplication.instance() or QApplication(sys.argv)
    app_qt.setApplicationName("Station WEFAX PRO")
    app_qt.setApplicationVersion("2.0-qt")
    app_qt.setOrganizationName("F4NMK")
    app_qt.setOrganizationDomain("f4nmk.radio")

    # ── Instanciation des ponts ──────────────────────────────────────────
    # AppBridge crée RadioBridge et DspBridge en interne ;
    # on récupère les instances pour les exposer séparément au QML.
    from wefax_station.qt.bridge.app_bridge import AppBridge

    app_bridge   = AppBridge()
    radio_bridge = app_bridge.radio
    dsp_bridge   = app_bridge.dsp

    # ── Moteur QML ───────────────────────────────────────────────────────
    engine = QQmlApplicationEngine()

    # Chemin vers le module QML (pour le singleton Theme + qmldir)
    engine.addImportPath(str(_QML_DIR.parent))   # wefax_station/qt/ → "WefaxStation"

    # Context properties accessibles depuis tout le QML
    ctx = engine.rootContext()
    ctx.setContextProperty("radio", radio_bridge)
    ctx.setContextProperty("dsp",   dsp_bridge)
    ctx.setContextProperty("app",   app_bridge)

    # Chargement de main.qml
    main_qml = _QML_DIR / "main.qml"
    engine.load(QUrl.fromLocalFile(str(main_qml)))

    if not engine.rootObjects():
        print("[Qt] ERREUR : impossible de charger main.qml", file=sys.stderr)
        return 1

    # ── Boucle d'événements ──────────────────────────────────────────────
    return app_qt.exec()


if __name__ == "__main__":
    sys.exit(main())
