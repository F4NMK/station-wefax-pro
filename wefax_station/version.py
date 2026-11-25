"""Référence unique de version logicielle et chemins du projet."""

from pathlib import Path

# ==============================================================================
# RÉFÉRENCE UNIQUE DE VERSION LOGICIELLE (SOURCE DE VÉRITÉ GLOBALE)
# ==============================================================================
SOFTWARE_VERSION = "2.11.2"
SOFTWARE_TITLE = f"Station WEFAX Pro {SOFTWARE_VERSION}"
SOFTWARE_BRAND = f"Station WEFAX PRO {SOFTWARE_VERSION} · F4NMK / Marc"
# Anciennes constantes conservées (même valeur effective que dans la version monolithique).
DEVELOPER = SOFTWARE_BRAND
BRAND = SOFTWARE_BRAND

# Dossier racine du projet (celui qui contient station_wefax_pro.py et le dossier wefax_station/).
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
LAUNCHER_SCRIPT = PROJECT_ROOT / "station_wefax_pro.py"
