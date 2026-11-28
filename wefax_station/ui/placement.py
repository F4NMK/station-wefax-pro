"""Placement des fenêtres annexes et des bulles d'aide (2.9.0).

Sous Windows avec plusieurs écrans, les coordonnées peuvent être négatives (écran placé à gauche ou
au-dessus de l'écran principal), et `winfo_screenwidth()` ne donne que la taille de l'écran PRINCIPAL.
Jusqu'en 2.8.9, les positions étaient ramenées dans [0, taille de l'écran principal] : la fenêtre
« À propos » ou une bulle d'aide partait alors sur un autre écran, voire hors de tout écran (constaté le
18/11 sur le poste de F4NMK : application sur l'écran PL2480H, bulle d'aide affichée sur l'écran du
portable, « À propos » invisible).

Règle : on place par rapport à la fenêtre principale, qui est forcément sur un écran visible, et on
reste à l'intérieur de son rectangle. Aucune borne à 0.
"""


def clamp_into(x, y, w, h, area):
    """Ramène le rectangle (x, y, w, h) à l'intérieur de area = (ax, ay, aw, ah) ; coordonnées négatives
    acceptées. Si la fenêtre est plus grande que la zone, on aligne sur le coin haut-gauche de la zone."""
    ax, ay, aw, ah = area
    x = min(x, ax + aw - w)
    y = min(y, ay + ah - h)
    return max(x, ax), max(y, ay)


def root_area(root):
    """Rectangle (x, y, largeur, hauteur) de la fenêtre principale, en coordonnées écran."""
    root.update_idletasks()
    return root.winfo_rootx(), root.winfo_rooty(), max(1, root.winfo_width()), max(1, root.winfo_height())


def centered_over(root, w, h, vertical=1 / 3):
    """Position (x, y) d'une fenêtre w × h centrée horizontalement sur root, au tiers supérieur."""
    ax, ay, aw, ah = root_area(root)
    x = ax + (aw - w) // 2
    y = ay + int(max(0, ah - h) * vertical)
    return clamp_into(x, y, w, h, (ax, ay, aw, ah))


def show_over_root(win, root, vertical=1 / 3):
    """Place `win` sur la fenêtre principale, l'affiche et la passe au premier plan."""
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x, y = centered_over(root, w, h, vertical)
    win.geometry(f"+{x}+{y}")
    try:
        win.deiconify()
        win.lift()
        win.focus_force()
    except Exception:
        pass
    return x, y
