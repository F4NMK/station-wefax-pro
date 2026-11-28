"""Range les jours de réception enregistrés avant la 2.11.0 dans la nouvelle arborescence.

Simulation par défaut : rien n'est modifié, la liste des déplacements est affichée.
    python outils/reorganiser_archives.py "D:\\Downloads\\StationWEFAXPro"
    python outils/reorganiser_archives.py "D:\\Downloads\\StationWEFAXPro" --appliquer

Avec --appliquer, les fichiers sont DÉPLACÉS (jamais effacés, jamais écrasés : un fichier déjà présent à
la destination est laissé en place) :
    bulletins_radio/*            -> bulletins/            (registres -> bulletins/details/)
    traductions/*                -> bulletins/
    cartes_partielles/*          -> cartes/partielles/    (images techniques -> cartes/partielles/details/)
    cartes/*_decodee|_traitee|_confiance.png, WEFAX_*_record.json -> cartes/details/
    bulletins_operateur/*        -> mes_bulletins/
    cartes/preferences.json      -> laissé en place (doublon des préférences du profil)
Les fiches JSON des cartes sont mises à jour (liste « files ») pour pointer vers details/.
Les dossiers anciens devenus vides sont supprimés.
"""

import json
import shutil
import sys
from pathlib import Path

TECH = ("_decodee.png", "_traitee.png", "_confiance.png")


def plan_day(day):
    moves = []

    def add(src, dst):
        if src.is_file() and not dst.exists():
            moves.append((src, dst))

    for sub, target in (("bulletins_radio", "bulletins"), ("traductions", "bulletins")):
        d = day / sub
        if d.is_dir():
            for f in d.iterdir():
                dest = day / target / ("details" if f.name.endswith("_record.json") else "") / f.name
                add(f, dest)
    for src_dir, dst_dir in ((day / "cartes", day / "cartes"), (day / "cartes_partielles", day / "cartes" / "partielles")):
        if not src_dir.is_dir():
            continue
        for f in src_dir.iterdir():
            if not f.is_file():
                continue
            if f.name.endswith(TECH) or f.name.endswith("_record.json"):
                add(f, dst_dir / "details" / f.name)
            elif src_dir != dst_dir:
                add(f, dst_dir / f.name)
    d = day / "bulletins_operateur"
    if d.is_dir():
        for f in d.iterdir():
            add(f, day / "mes_bulletins" / f.name)
    return moves


def fix_card_json(path):
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    files = meta.get("files")
    if not isinstance(files, list):
        return False
    new = [("details/" + n) if n.endswith(TECH) and "/" not in n else n for n in files]
    if new == files:
        return False
    meta["files"] = new
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    apply = "--appliquer" in argv
    days = sorted(p for p in root.glob("donnees/operateurs/*/receptions/*") if p.is_dir())
    total = 0
    for day in days:
        moves = plan_day(day)
        if not moves:
            continue
        print(f"{day} : {len(moves)} fichier(s)")
        for src, dst in moves:
            print(f"   {src.relative_to(day)}  ->  {dst.relative_to(day)}")
            if apply:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
        total += len(moves)
        if apply:
            for js in list((day / "cartes").glob("*.json")) + list((day / "cartes" / "partielles").glob("*.json")):
                fix_card_json(js)
            for old in ("bulletins_radio", "traductions", "cartes_partielles", "bulletins_operateur"):
                d = day / old
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
    print(("Déplacés : " if apply else "À déplacer (simulation, rien n'a été modifié) : ") + str(total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
