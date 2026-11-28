#!/usr/bin/env python3
"""Construit le guide illustré autonome (un seul fichier HTML, images incluses, lisible hors ligne).

Usage : python outils/construire_guide.py
Entrées : docs/guide_source.html, docs/img/*.jpg ; sortie : docs/Guide_Station_WEFAX_PRO.html
"""
import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from wefax_station.version import SOFTWARE_VERSION  # noqa: E402

FONT = 'font-family="Segoe UI, system-ui, sans-serif"'


def _box(x, y, w, h, title, sub="", fill="#e0f2fe", stroke="#0e7490"):
    t = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
    t += f'<text x="{x + w / 2}" y="{y + (h / 2 if not sub else h / 2 - 7)}" text-anchor="middle" dominant-baseline="middle" {FONT} font-size="15" font-weight="700" fill="#0b2530">{title}</text>'
    if sub:
        for i, line in enumerate(sub.split("|")):
            t += f'<text x="{x + w / 2}" y="{y + h / 2 + 12 + 15 * i}" text-anchor="middle" {FONT} font-size="12" fill="#334155">{line}</text>'
    return t


def _arrow(x1, y1, x2, y2, label="", color="#0e7490", dy=-8):
    t = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.5" marker-end="url(#ah)"/>'
    if label:
        for i, line in enumerate(label.split("|")):
            t += f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 + dy + 14 * i}" text-anchor="middle" {FONT} font-size="12" fill="#0b3b4a">{line}</text>'
    return t


DEFS = (
    '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
    '<path d="M0,0 L10,5 L0,10 z" fill="#0e7490"/></marker></defs>'
)


def chain(lang):
    fr = lang == "fr"
    w, h = 1000, 210
    s = f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img">{DEFS}'
    items = [
        ("Antenne" if fr else "Antenna", "HF 2-14 MHz|MF 490/518 kHz"),
        ("Récepteur" if fr else "Receiver", "USB-D, −1,9 kHz|AGC FAST" if fr else "USB-D, −1.9 kHz|AGC FAST"),
        ("Audio USB", "44 100 Hz|1500-2300 Hz"),
        ("Démodulateurs" if fr else "Demodulators", "WEFAX FM|RTTY · SITOR-B"),
        ("Archives", "cartes PNG + JSON|bulletins texte" if fr else "PNG + JSON charts|text bulletins"),
        ("Bulletin", "situation + 3-6 h|indice de fiabilité" if fr else "situation + 3-6 h|reliability index"),
    ]
    bw, gap, y = 140, 32, 50
    for i, (t, sub) in enumerate(items):
        x = 12 + i * (bw + gap)
        fill = "#fef3c7" if i == len(items) - 1 else "#e0f2fe"
        s += _box(x, y, bw, 90, t, sub, fill=fill)
        if i:
            s += _arrow(x - gap + 2, y + 45, x - 2, y + 45)
    s += (
        f'<text x="12" y="175" {FONT} font-size="13" fill="#7c2d12">'
        + ("CI-V / CAT : réception seulement — commandes d'émission bloquées (1C, 17)" if fr else "CI-V / CAT: receive only — transmit commands blocked (1C, 17)")
        + "</text>"
    )
    s += (
        f'<text x="12" y="197" {FONT} font-size="13" fill="#334155">'
        + ("Programme des émetteurs (UTC) → l'automatisme choisit la fréquence et le moment" if fr else "Transmitter schedules (UTC) → the scheduler picks frequency and timing")
        + "</text>"
    )
    return s + "</svg>"


def icom(lang):
    fr = lang == "fr"
    s = f'<svg viewBox="0 0 1000 250" xmlns="http://www.w3.org/2000/svg" role="img">{DEFS}'
    s += _box(30, 60, 230, 120, "PC Windows", "Station WEFAX PRO|COMx « IC-705 Serial Port A »|« USB Audio CODEC »" if fr else "Station WEFAX PRO|COMx \"IC-705 Serial Port A\"|\"USB Audio CODEC\"")
    s += _box(560, 60, 230, 120, "IC-705 / IC-7300", "USB-D · FIL1 · AGC FAST|CI-V A4 (IC-705) · 94 (IC-7300)", fill="#fef3c7", stroke="#b45309")
    s += _arrow(262, 100, 556, 100, "CI-V : fréquence, mode, S-mètre" if fr else "CI-V: frequency, mode, S-meter", dy=-10)
    s += _arrow(556, 140, 262, 140, "audio de réception (AF ≈ 50 %)" if fr else "receive audio (AF ≈ 50 %)", dy=20)
    s += f'<text x="409" y="200" text-anchor="middle" {FONT} font-size="13" fill="#0b3b4a">' + ("un seul câble USB de données" if fr else "one USB data cable") + "</text>"
    s += _box(840, 75, 130, 90, "Antenne" if fr else "Antenna", "HF / MF", fill="#ecfdf5", stroke="#059669")
    s += _arrow(836, 120, 794, 120)
    s += f'<text x="30" y="238" {FONT} font-size="12" fill="#7c2d12">' + ("Winlink : le logiciel libère le port COM et la carte son pendant la session Winlink Express / VARA" if fr else "Winlink: the software releases the COM port and sound card during the Winlink Express / VARA session") + "</text>"
    return s + "</svg>"


def yaesu(lang):
    fr = lang == "fr"
    s = f'<svg viewBox="0 0 1000 300" xmlns="http://www.w3.org/2000/svg" role="img">{DEFS}'
    s += _box(30, 30, 230, 100, "PC Windows", "port COM CAT|carte son USB du poste" if fr else "CAT COM port|radio USB sound card")
    s += _box(560, 30, 260, 100, "FT-991A · FT-710 · FTDX10…", "DATA-USB · AGC FAST|CAT 38 400 bauds" if fr else "DATA-USB · AGC FAST|CAT 38 400 baud", fill="#fef3c7", stroke="#b45309")
    s += _arrow(262, 65, 556, 65, "CAT (commandes « ; »)" if fr else "CAT (\";\" commands)", dy=-10)
    s += _arrow(556, 100, 262, 100, "audio USB" if fr else "USB audio", dy=20)
    s += _box(30, 180, 230, 100, "PC Windows", "port COM CAT|interface audio externe" if fr else "CAT COM port|external audio interface")
    s += _box(560, 180, 260, 100, "FT-817/818 · 857 · 897", "DIG MODE = USER-U|CAT trames 5 octets" if fr else "DIG MODE = USER-U|CAT 5-byte frames", fill="#fef3c7", stroke="#b45309")
    s += _arrow(262, 215, 556, 215, "câble CAT" if fr else "CAT cable", dy=-10)
    s += _arrow(556, 250, 262, 250, "audio par interface (ex. sortie DATA)" if fr else "audio via interface (e.g. DATA jack)", dy=20)
    s += f'<text x="860" y="150" {FONT} font-size="12" fill="#92400e">' + ("simulateur seulement" if fr else "simulator only") + "</text>"
    return s + "</svg>"


SVGS = {
    "chain_fr": chain("fr"),
    "chain_en": chain("en"),
    "icom_fr": icom("fr"),
    "icom_en": icom("en"),
    "yaesu_fr": yaesu("fr"),
    "yaesu_en": yaesu("en"),
}


def build(src=ROOT / "docs" / "guide_source.html", out=ROOT / "docs" / "Guide_Station_WEFAX_PRO.html"):
    html = Path(src).read_text(encoding="utf-8").replace("{{version}}", SOFTWARE_VERSION)
    img_dir = Path(src).parent / "img"
    missing = []

    def img(m):
        f = img_dir / f"{m.group(1)}.jpg"
        if not f.is_file():
            missing.append(f.name)
            return ""
        return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode("ascii")

    html = re.sub(r"\{\{img:([\w-]+)\}\}", img, html)
    html = re.sub(r"\{\{svg:([\w-]+)\}\}", lambda m: SVGS.get(m.group(1), ""), html)
    if missing:
        raise SystemExit("Images manquantes : " + ", ".join(missing))
    leftover = re.findall(r"\{\{[^}]+\}\}", html)
    if leftover:
        raise SystemExit("Balises non remplacées : " + ", ".join(leftover))
    Path(out).write_text(html, encoding="utf-8")
    return Path(out)


if __name__ == "__main__":
    p = build()
    print(p, f"{p.stat().st_size // 1024} Ko")
