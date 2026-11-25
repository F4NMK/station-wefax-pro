"""Ajustement de textes à une largeur en pixels, sans couper un élément au milieu (2.9.0).

Utilisé par l'afficheur du poste (nom de station trop long) et par la ligne « Ensuite : » du bandeau,
qui revenait à la ligne au milieu d'un bulletin (« … · 21:30 Bulletin / Atlantique Nord »).
"""


def fit_text(text, width, measure, ellipsis="…"):
    """`text` raccourci (avec « … ») pour tenir dans `width` pixels ; "" si rien ne tient."""
    text = str(text or "")
    if width <= 0:
        return ""
    if measure(text) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid].rstrip() + ellipsis) <= width:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo].rstrip() + ellipsis) if lo > 0 else ""


def fit_items(items, width, measure, prefix="", sep=" · ", max_lines=2):
    """Répartit des éléments entiers sur au plus `max_lines` lignes de `width` pixels.

    Un élément n'est jamais coupé : s'il ne tient plus, il est renvoyé à la ligne suivante ; ceux qui ne
    tiennent pas du tout sont laissés de côté (les premiers, les plus proches dans le temps, sont gardés).
    Un élément seul plus large qu'une ligne est raccourci avec « … ». Renvoie le texte (lignes séparées
    par « \\n »)."""
    lines, cur = [], prefix
    for it in items:
        cand = (cur + sep + it) if cur not in ("", prefix) else (cur + it)
        if measure(cand) <= width:
            cur = cand
            continue
        if cur not in ("", prefix):
            lines.append(cur)
            if len(lines) >= max_lines:
                cur = None
                break
            cur = ""
            cand = it
            if measure(cand) <= width:
                cur = cand
                continue
        cur = fit_text(cand, width, measure)
        lines.append(cur)
        cur = ""
        if len(lines) >= max_lines:
            cur = None
            break
    if cur not in (None, "", prefix):
        lines.append(cur)
    if not lines:
        lines = [prefix.rstrip()]
    return "\n".join(lines[:max_lines])
