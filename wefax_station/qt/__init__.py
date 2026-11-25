"""Couche interface PyQt6 / QML de Station WEFAX PRO.

Construction parallèle (v2.14.0+) : le code Tkinter existant dans app/ et ui/
reste intact et fonctionnel. Ce package construit la nouvelle interface de zéro.

Point d'entrée : wefax_station/qt/launcher_qt.py
Architecture :
  qt/
  ├── bridge/          Ponts Python ↔ QML (QObject exposés au moteur QML)
  │   ├── app_bridge.py    Pont principal : cycle de vie, événements, radio
  │   ├── dsp_bridge.py    Pont moteur DSP WEFAX (images, démodulation)
  │   └── radio_bridge.py  Pont CI-V IC-705
  ├── qml/             Fichiers QML (interface déclarative)
  │   ├── main.qml         Fenêtre racine
  │   ├── Theme.qml        Singleton thème (couleurs, typographie)
  │   ├── components/      Composants réutilisables (boutons, bargraphes…)
  │   └── panels/          Panneaux fonctionnels (radio, image, météo, plan)
  └── launcher_qt.py   QApplication + QQmlApplicationEngine

Règle de non-régression : ce package n'importe JAMAIS tkinter.
"""
