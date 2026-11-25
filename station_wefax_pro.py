#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Station WEFAX Pro — F4NMK / ADRASEC : lanceur.

Exécution :  python station_wefax_pro.py
Dépendances : pip install -r requirements.txt
"""

import sys
from pathlib import Path

# Rend le paquet wefax_station importable quel que soit le dossier courant.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wefax_station.launcher import main  # noqa: E402

if __name__ == "__main__":
    main()
