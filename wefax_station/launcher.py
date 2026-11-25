"""Démarrage de l'application (création de la fenêtre Tk et boucle principale)."""

import tkinter as tk


def main():
    """Lance l'interface graphique."""
    from wefax_station.app.main_window import StationWefaxApp

    root = tk.Tk()
    app = StationWefaxApp(root)
    root.mainloop()
    return app
