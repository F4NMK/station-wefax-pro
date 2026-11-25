"""Poste « Météo & bulletin » : tout ce qu'il faut pour rédiger le bulletin, au même endroit.

Onglets :
1. Réceptions 24 h — cartes WEFAX et bulletins RTTY / NAVTEX archivés (heure, station, fiabilité),
   ouverture du fichier, choix de ce qui entre dans le bulletin ;
2. Bulletin — texte compilé et modifiable : sources reçues, analyse des bulletins texte (prévisions
   ponctuelles vent / mer lues et résumées en français, avertissements), observations de l'opérateur,
   évolution, qualité de réception ; copier, enregistrer, rapport ADRASEC ;
3. Statistiques — par station : cartes et bulletins reçus, fiabilité moyenne, dernière mesure de la
   table de propagation ; aide au choix des fréquences selon l'heure.

Les faits (ce qui a été reçu) et les hypothèses (calculs, projections) restent séparés, comme dans le
bulletin documentaire existant (core/bulletin_text.py), qui est réutilisé pour la partie opérateur.
"""

import json
import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from wefax_station.core.bulletin_text import build_bulletin
from wefax_station.ui.placement import show_over_root
from wefax_station.ui.theme import UITheme
from wefax_station.version import SOFTWARE_TITLE
from wefax_station.weather.plain_language import clean_raw
from wefax_station.weather.rtty_parse import gale_warnings, parse_point_forecasts


def _parse_dt(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class BulletinDeskMixin:
    # ------------------------------------------------------------- données
    def _desk_documents(self, hours=24):
        ws = getattr(self, "portable_ws", None)
        if ws is None:
            return []
        idx = ws.operator_dir() / "index_receptions.json"
        try:
            docs = json.loads(idx.read_text(encoding="utf-8")).get("documents", [])
        except (OSError, ValueError):
            docs = []
        now = datetime.now(timezone.utc)
        out = []
        for d in docs:
            start = _parse_dt(d.get("start_utc"))
            if start is None or now - start > timedelta(hours=hours):
                continue
            rec_path = ws.root_dir / d.get("record_rel_path", "")
            rec = {}
            try:
                rec = json.loads(rec_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            files = [ws.root_dir / s["rel_path"] for s in rec.get("sources", []) if s.get("rel_path")]
            files += [ws.root_dir / s["rel_path"] for s in rec.get("derived", []) if s.get("rel_path")]
            q = rec.get("quality", {})
            kind = (
                "Carte WEFAX"
                if d.get("category") == "cartes"
                else ("NAVTEX" if "NAVTEX" in d.get("station", "") else "Bulletin RTTY")
            )
            out.append(
                {
                    "id": d.get("document_id"),
                    "kind": kind,
                    "start": start,
                    "station": d.get("station", "?"),
                    "freq": d.get("freq_khz"),
                    "status": d.get("status", ""),
                    "rel": q.get("reliability_pct"),
                    "grade": q.get("reliability_grade", ""),
                    "product": q.get("product", ""),
                    "files": files,
                }
            )
        out.sort(key=lambda x: x["start"], reverse=True)
        return out

    @staticmethod
    def _doc_text(doc):
        orig = next((f for f in doc["files"] if f.name.endswith("_original.txt")), None)
        if orig is None or not orig.is_file():
            return ""
        text = orig.read_text(encoding="utf-8", errors="ignore")
        return text.split("=" * 78)[-1] if "=" * 78 in text else text

    # ------------------------------------------------------------- fenêtre
    def _open_bulletin_desk(self):
        win = getattr(self, "_desk_win", None)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            self._desk_refresh()
            return
        win = tk.Toplevel(self.root)
        win.title(f"Météo & bulletin — {SOFTWARE_TITLE}")
        win.configure(bg=UITheme.BG_PANEL)
        win.geometry("1000x720")
        show_over_root(win, self.root)
        win.minsize(680, 460)
        self._desk_win = win
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._desk_nb = nb

        # --- 1. réceptions
        t1 = tk.Frame(nb, bg=UITheme.BG_PANEL)
        nb.add(t1, text="1 · Réceptions 24 h")
        cols = (
            ("inc", "Bulletin", 64),
            ("time", "UTC", 110),
            ("kind", "Type", 110),
            ("station", "Station", 80),
            ("freq", "kHz", 80),
            ("rel", "Fiabilité", 80),
            ("status", "État", 90),
            ("info", "Contenu", 330),
        )
        tree = ttk.Treeview(t1, columns=[c[0] for c in cols], show="headings", selectmode="extended")
        for k, title, w in cols:
            tree.heading(k, text=title)
            tree.column(k, width=w, stretch=k == "info", anchor="w")
        ys = ttk.Scrollbar(t1, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ys.set)
        tree.grid(row=1, column=0, sticky="nsew", padx=(6, 0), pady=4)
        ys.grid(row=1, column=1, sticky="ns", pady=4)
        t1.rowconfigure(1, weight=1)
        t1.columnconfigure(0, weight=1)
        tk.Label(
            t1,
            text="Clic sur la colonne « Bulletin » pour inclure / exclure ; double-clic pour ouvrir le fichier.",
            bg=UITheme.BG_PANEL,
            fg=UITheme.TEXT_MUTED,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=6)
        bar = tk.Frame(t1, bg=UITheme.BG_PANEL)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        tk.Button(bar, text="↻ Actualiser", command=self._desk_refresh).pack(side="left", padx=(0, 6))
        tk.Button(bar, text="📂 Ouvrir", command=lambda: self._desk_open(tree)).pack(side="left", padx=(0, 6))
        tk.Button(
            bar,
            text="➜ Rédiger le bulletin avec la sélection",
            bg="#047857",
            fg="#ffffff",
            command=lambda: (self._desk_compile(), nb.select(1)),
        ).pack(side="left")
        tree.bind("<Double-1>", lambda e: self._desk_open(tree))
        tree.bind("<Button-1>", lambda e: self._desk_toggle(tree, e), add="+")
        self._desk_tree = tree

        # --- 2. bulletin
        t2 = tk.Frame(nb, bg=UITheme.BG_PANEL)
        nb.add(t2, text="2 · Bulletin")
        # 2.8.3 — deux rangées (huit boutons sur une ligne débordaient de la fenêtre) : le bulletin en haut,
        # les outils qui l'alimentent en dessous.
        bar2 = tk.Frame(t2, bg=UITheme.BG_PANEL)
        bar2.pack(fill="x", padx=6, pady=(6, 2))
        bar3 = tk.Frame(t2, bg=UITheme.BG_PANEL)
        bar3.pack(fill="x", padx=6, pady=(0, 6))
        tk.Label(bar2, text="Bulletin :", bg=UITheme.BG_PANEL, fg=UITheme.TEXT_MUTED, width=9, anchor="w").pack(
            side="left"
        )
        tk.Label(bar3, text="Alimenter :", bg=UITheme.BG_PANEL, fg=UITheme.TEXT_MUTED, width=9, anchor="w").pack(
            side="left"
        )
        for bar, text, cmd, bg in (
            (bar2, "↻ Recompiler", self._desk_compile, "#047857"),
            (bar2, "📋 Copier", lambda: self._desk_copy(), "#334155"),
            (bar2, "💾 Enregistrer…", lambda: self._desk_save(), "#334155"),
            (bar2, "📋 Rapport ADRASEC", lambda: self.bulletins_ui._generate_orsec_bulletin_dialog(), "#d97706"),
            (bar3, "✏️ Annoter la carte…", self._annotate_card, "#334155"),
            (bar3, "📐 Repérer la carte…", self._start_georef, "#334155"),
            (bar3, "👁 Observations locales…", lambda: self._show_settings("METEO"), "#334155"),
            (bar3, "🧭 Vent géostrophique…", self._weather_dialog, "#334155"),  # (n'est plus dans le menu)
        ):
            b = tk.Button(bar, text=text, command=cmd, bg=bg, fg="#ffffff", relief="flat", padx=8, pady=3)
            b.pack(side="left", padx=(0, 6))
            if "Rapport ADRASEC" in text:
                self.register_report_button(b)
        self._desk_text = tk.Text(
            t2,
            wrap="word",
            bg="#0b1220",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
            font=("Consolas", 10),
            padx=10,
            pady=8,
        )
        self._desk_text.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # --- 3. statistiques
        t3 = tk.Frame(nb, bg=UITheme.BG_PANEL)
        nb.add(t3, text="3 · Statistiques de réception")
        self._desk_stats = tk.Text(
            t3, wrap="none", bg="#0b1220", fg="#e2e8f0", font=("Consolas", 10), padx=10, pady=8
        )
        self._desk_stats.pack(fill="both", expand=True, padx=6, pady=6)
        self._desk_included = set()
        self._desk_refresh(first=True)
        self._desk_compile()

    # ------------------------------------------------------------- actions
    def _desk_refresh(self, first=False):
        tree = getattr(self, "_desk_tree", None)
        if tree is None or not tree.winfo_exists():
            return
        docs = self._desk_documents()
        self._desk_docs = {d["id"]: d for d in docs}
        if first:
            # par défaut : les bulletins texte et la dernière carte de chaque station
            seen = set()
            for d in docs:
                if d["kind"] != "Carte WEFAX":
                    self._desk_included.add(d["id"])
                elif d["station"] not in seen:
                    seen.add(d["station"])
                    self._desk_included.add(d["id"])
        tree.delete(*tree.get_children())
        for d in docs:
            info = d["product"] or ""
            if d["kind"] != "Carte WEFAX":
                pts = parse_point_forecasts(self._doc_text(d))
                if pts:
                    info = f"{len(pts)} point(s) de prévision : " + ", ".join(p["point"] for p in pts[:4])
            tree.insert(
                "",
                "end",
                iid=d["id"],
                values=(
                    "☑" if d["id"] in self._desk_included else "☐",
                    d["start"].strftime("%d/%m %H:%M"),
                    d["kind"],
                    d["station"],
                    f"{d['freq']:.1f}" if d["freq"] else "",
                    f"{d['rel']} % {d['grade']}" if d["rel"] is not None else "—",
                    d["status"],
                    info,
                ),
            )
        self._desk_fill_stats(docs)

    def _desk_toggle(self, tree, event):
        if tree.identify_column(event.x) != "#1":
            return
        iid = tree.identify_row(event.y)
        if not iid:
            return
        if iid in self._desk_included:
            self._desk_included.discard(iid)
        else:
            self._desk_included.add(iid)
        tree.set(iid, "inc", "☑" if iid in self._desk_included else "☐")

    def _desk_open(self, tree):
        sel = tree.selection()
        if not sel:
            return
        d = self._desk_docs.get(sel[0])
        if not d:
            return
        # 2.8.8 : un bulletin texte s'ouvre dans le téléscripteur (texte reçu + lecture en français)
        if d["kind"] != "Carte WEFAX" and hasattr(self, "bulletins_ui"):
            self.bulletins_ui.show_document(d["id"])
            return
        prefer = ("_carte.png", "_traduction_fr.txt", "_original.txt", "_traitee.png")
        f = next((f for p in prefer for f in d["files"] if f.name.endswith(p) and f.is_file()), None)
        if f is None:
            messagebox.showinfo("Ouvrir", "Fichier introuvable (purgé par la rétention ?).", parent=tree)
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(f))  # noqa: S606 — ouverture par l'application associée
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(f)])
            else:
                subprocess.Popen(["xdg-open", str(f)])
        except Exception as exc:
            messagebox.showwarning("Ouvrir", str(exc), parent=tree)

    def _desk_compile(self):
        txt = getattr(self, "_desk_text", None)
        if txt is None or not txt.winfo_exists():
            return
        now = datetime.now(timezone.utc)
        docs = [d for d in getattr(self, "_desk_docs", {}).values() if d["id"] in self._desk_included]
        charts = [d for d in docs if d["kind"] == "Carte WEFAX"]
        texts = [d for d in docs if d["kind"] != "Carte WEFAX"]
        zone = self.zone_var.get() if hasattr(self, "zone_var") else ""
        op = (
            self.operator_callsign_var.get().strip().upper() if hasattr(self, "operator_callsign_var") else ""
        )
        L = [
            f"BULLETIN MÉTÉO MARINE — {now:%d/%m/%Y %H:%M} UTC" + (f" — {op}" if op else ""),
            f"Zone d'analyse : {self.analysis_zone()['label']} — {self.analysis_zone()['source']}",
            "=" * 72,
            "",
            "CE QU'IL FAUT RETENIR",
            "",
        ]
        arb = getattr(self, "hybrid_arbiter", None)
        combined = "\n".join(clean_raw(self._doc_text(d)) for d in texts)
        if arb is not None and combined.strip():
            # 2.8.6 — même méthode que le rapport 1 clic : bulletins triés par heure, messages sans
            # prévision écartés, prévision la plus récente pour chaque zone, zones illisibles signalées.
            from wefax_station.weather import dossier as weather_dossier

            dos = weather_dossier.assemble(
                [
                    {
                        "station": d["station"],
                        "freq": d["freq"] or 0.0,
                        "time": d["start"],
                        "product": d.get("product") or d.get("status", ""),
                        "body": self._doc_text(d),
                    }
                    for d in texts
                ]
            )
            plain, _it = arb.interpret_text("", dossier=dos)
            L += plain.split("\n")
        else:
            dos = None
            L.append(
                "Aucun bulletin texte sélectionné : seules les cartes et vos observations sont disponibles."
            )
        # 2.10.0 — situation actuelle et prévision 3 à 6 h, avec indice de fiabilité
        if arb is not None and hasattr(arb, "_nowcast_block"):
            L += [""] + arb._nowcast_block(dos)
        L += [
            "",
            "=" * 72,
            "A. CARTES WEFAX REÇUES",
        ]
        if charts:
            for d in sorted(charts, key=lambda x: x["start"]):
                L.append(
                    f"  • {d['start']:%d/%m %H:%M} UTC — {d['station']} ({d['freq']:.1f} kHz) — "
                    f"fiabilité {d['rel'] if d['rel'] is not None else '?'} % — {d['status'].lower()}"
                )
            L.append("    (heure de réception ; l'échéance figure dans le cartouche de chaque carte)")
        else:
            L.append("  Aucune carte sélectionnée.")
        L += ["", "B. BULLETINS TEXTE REÇUS (RTTY DWD / NAVTEX)"]
        if not texts:
            L.append("  Aucun bulletin texte sélectionné.")
        for d in sorted(texts, key=lambda x: x["start"]):
            L.append(
                f"  ▸ {d['start']:%d/%m %H:%M} UTC — {d['station']} ({d['freq']:.1f} kHz) — réception "
                f"{'fiable' if (d['rel'] or 0) >= 70 else 'à vérifier'} ({d['rel'] if d['rel'] is not None else '?'} %)"
            )
            for w in gale_warnings(self._doc_text(d), translate=True):
                L.append(f"    ⚠ {w}")
        L += ["", "C. OBSERVATIONS, ÉVOLUTION ET COMPLÉMENTS DE L'OPÉRATEUR", ""]
        observations = {}
        if hasattr(self, "ent_press"):
            observations = {
                "Date UTC": self.obs_time.get(),
                "Pression hPa": self.ent_press.get(),
                "Tendance 3 h": self.cmb_ptrend.get(),
                "Température °C": self.ent_temp.get(),
                "Humidité %": self.ent_rh.get(),
                "Vent": self.cmb_wind.get(),
                "Ciel": self.cmb_sky.get(),
            }
        cards = []
        for p in Path(self.archive_dir).glob("*.json"):
            try:
                c = json.loads(p.read_text(encoding="utf-8"))
                if c.get("annotations"):
                    c["file"] = p.name
                    cards.append(c)
            except (OSError, ValueError):
                pass
        doc = build_bulletin(cards, zone, observations, now=now).split("\n")
        # on ne reprend que les parties 1 à 4 du bulletin documentaire (sans l'en-tête)
        start = next((i for i, x in enumerate(doc) if x.startswith("1. ")), 0)
        L += ["  " + x if x else "" for x in doc[start:]]
        L += ["", "D. QUALITÉ DE RÉCEPTION"]
        arb = getattr(self, "hybrid_arbiter", None)
        if arb is not None:
            best = sorted((e for e in arb.prop.entries.values() if e.active), key=lambda e: -e.quality)[:5]
            for e in best:
                L.append(
                    f"  • {e.station} {e.freq_khz:.1f} kHz ({e.mode}) : {e.quality} % — {e.detail} "
                    f"(il y a {int(e.age_s() // 60)} min)"
                )
            if not best:
                L.append("  Aucune mesure récente.")
        if texts:
            # 2.11.0 — plus de copie intégrale des textes reçus (jusqu'à 2 500 caractères chacun) : le
            # bulletin reste lisible ; les originaux et leur traduction sont dans le dossier « bulletins ».
            L += ["", f"Textes originaux ({len(texts)}) et traductions : dossier « bulletins » du jour."]
        L += [
            "",
            "Faits reçus et hypothèses de l'opérateur sont distingués. Ce bulletin ne remplace pas",
            "les avis officiels (Météo-France, CROSS, NAVTEX).",
        ]
        txt.delete("1.0", "end")
        txt.insert("1.0", "\n".join(L))

    def _desk_copy(self):
        text = self._desk_text.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.lbl_status.configure(text="Bulletin copié dans le presse-papiers.")

    def _desk_save(self):
        op = (
            self.operator_callsign_var.get().strip().upper() if hasattr(self, "operator_callsign_var") else ""
        )
        name = f"BULLETIN_METEO{('_' + op) if op else ''}_{datetime.now(timezone.utc):%Y%m%d_%H%M}Z.txt"
        ws = getattr(self, "portable_ws", None)
        init = ws.reception_day_dir() / "mes_bulletins" if ws is not None else Path(self.archive_dir)
        init.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self._desk_win,
            initialdir=str(init),
            initialfile=name,
            defaultextension=".txt",
            filetypes=[("Texte", "*.txt")],
        )
        if path:
            Path(path).write_text(self._desk_text.get("1.0", "end-1c") + "\n", encoding="utf-8")
            self.log_event(f"📝 Bulletin enregistré : {Path(path).name}")

    def _desk_fill_stats(self, docs):
        box = getattr(self, "_desk_stats", None)
        if box is None or not box.winfo_exists():
            return
        per = {}
        for d in docs:
            s = per.setdefault(d["station"], {"cartes": 0, "textes": 0, "rel": [], "hours": []})
            s["cartes" if d["kind"] == "Carte WEFAX" else "textes"] += 1
            if d["rel"] is not None:
                s["rel"].append(d["rel"])
            s["hours"].append(d["start"].hour)
        arb = getattr(self, "hybrid_arbiter", None)
        L = [
            "RÉCEPTIONS DES DERNIÈRES 24 H PAR STATION",
            "",
            f"{'Station':<10}{'Cartes':>8}{'Textes':>8}{'Fiab. moy.':>12}  Heures UTC de réception      Dernière mesure",
            "-" * 96,
        ]
        for sid in sorted(per):
            s = per[sid]
            mean = f"{sum(s['rel']) / len(s['rel']):.0f} %" if s["rel"] else "—"
            hours = ",".join(f"{h:02d}" for h in sorted(set(s["hours"])))
            e = arb.prop.get(sid) if arb is not None else None
            last = f"{e.quality} % il y a {int(e.age_s() // 60)} min ({e.source})" if e else "—"
            L.append(f"{sid:<10}{s['cartes']:>8}{s['textes']:>8}{mean:>12}  {hours:<28} {last}")
        if not per:
            L.append("Aucune réception archivée sur 24 h.")
        if arb is not None:
            L += ["", "TABLE DE PROPAGATION (toutes stations mesurées)", ""]
            for e in sorted(arb.prop.entries.values(), key=lambda e: (e.mode, -e.quality)):
                L.append(
                    f"  {e.mode:<7}{e.station:<11}{e.freq_khz:>9.1f} kHz  {e.quality:>3} %  "
                    f"{'émission ✓' if e.active else '          '}  il y a {int(e.age_s() // 60):>4} min  {e.detail}"
                )
        box.delete("1.0", "end")
        box.insert("1.0", "\n".join(L))
