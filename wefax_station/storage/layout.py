"""Arborescence d'un jour de réception (2.11.0).

Avant 2.11.0, chaque jour comptait sept dossiers (audio, bulletins_operateur, bulletins_radio, cartes,
cartes_partielles, journaux, traductions) ; le dossier « cartes » mêlait pour chaque carte quatre images
(carte, décodée, traitée, confiance), deux fiches JSON, ainsi que les préférences et le brouillon du
bulletin. Désormais :

    <jour>/
      cartes/                  la carte finale (…_carte.png) et sa fiche (….json) — ce que l'on consulte
        partielles/            cartes incomplètes (début ou fin manquant)
        details/               images techniques (décodée, traitée, confiance) et registres
      bulletins/               texte original (…_original.txt) et traduction (…_traduction_fr.txt) côte à côte
        details/               registres des bulletins
      mes_bulletins/           bulletins météo rédigés par l'opérateur
      journaux/                journal de session
      audio/                   enregistrements bruts (si activés)

Les préférences et le brouillon du bulletin vont dans le dossier de l'opérateur (« brouillons »), plus dans
un dossier du jour. Les anciens noms restent LUS (archives des versions précédentes) : rien n'est déplacé ni
effacé sur le disque.
"""

from pathlib import Path

CARDS = "cartes"
PARTIAL = "partielles"  # sous-dossier de cartes/
DETAILS = "details"  # sous-dossier de cartes/ et de bulletins/
WINLINK = "winlink"  # sous-dossier de cartes/ : copies compactes pour Winlink / VARA HF (2.14.1)
BULLETINS = "bulletins"
MY_BULLETINS = "mes_bulletins"
LOGS = "journaux"
AUDIO = "audio"
DRAFTS = "brouillons"  # dans le dossier de l'opérateur

DAY_SUBDIRS = (CARDS, BULLETINS, MY_BULLETINS, LOGS, AUDIO)

# anciens dossiers (lecture seule)
LEGACY_BULLETINS = ("bulletins_radio",)
LEGACY_TRANSLATIONS = ("traductions",)
LEGACY_PARTIAL = ("cartes_partielles",)
LEGACY_MY_BULLETINS = ("bulletins_operateur",)

# catégorie de document (index des réceptions) -> dossier
CATEGORY_DIR = {"cartes": CARDS, "bulletins_radio": BULLETINS}

TECH_SUFFIXES = ("_decodee.png", "_traitee.png", "_confiance.png")


def cards_dir(day_dir):
    return Path(day_dir) / CARDS


def partial_dir(day_dir):
    return Path(day_dir) / CARDS / PARTIAL


def card_details_dir(day_dir):
    return Path(day_dir) / CARDS / DETAILS


def bulletins_dir(day_dir):
    return Path(day_dir) / BULLETINS


def record_dir(day_dir, category):
    return Path(day_dir) / CATEGORY_DIR.get(category, category) / DETAILS


def my_bulletins_dir(day_dir):
    return Path(day_dir) / MY_BULLETINS


def bulletin_text_dirs(day_dir):
    """Dossiers où chercher les textes originaux d'un jour (nouveau puis anciens noms)."""
    d = Path(day_dir)
    return [d / BULLETINS] + [d / n for n in LEGACY_BULLETINS]


def is_tech_file(name):
    return str(name).endswith(TECH_SUFFIXES)


def drafts_dir(operator_dir):
    p = Path(operator_dir) / DRAFTS
    p.mkdir(parents=True, exist_ok=True)
    return p
