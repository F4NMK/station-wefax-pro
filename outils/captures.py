#!/usr/bin/env python3
"""Captures d'écran des fenêtres de l'application (guide et revue d'ergonomie), sans poste radio.

Usage : xvfb-run -a -s "-screen 0 1600x900x24" python outils/captures.py DOSSIER_SORTIE [image_de_carte.png]
L'application s'ouvre dans un dossier de données temporaire (mêmes protections que l'autotest).
"""
import os
import subprocess
import sys
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "captures")
CHART = sys.argv[2] if len(sys.argv) > 2 else None
sys.argv = [sys.argv[0], "aucun_test"]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import autotest as AT  # noqa: E402  (protections : dossier temporaire, dialogues neutralisés, pas de CAT)

tk = AT.tk


def shot(root, name, widget=None):
    root.update()
    AT.pump(root, 0.6)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{name}.png"
    if widget is not None:
        frame = widget.winfo_toplevel().wm_frame()
        subprocess.run(["import", "-window", frame, str(target)], check=False)
    else:
        subprocess.run(["import", "-window", "root", str(target)], check=False)
    print("capture", target)


def new_toplevels(root, before):
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w not in before]


def demo_data(app):
    """Données de DÉMONSTRATION (bulletin, observation, carte) pour illustrer le guide."""
    import json
    import shutil
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    day = Path(app.portable_ws.reception_day_dir(now))
    days = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
    st = lambda d, h: f"{days[d.weekday()]} {d.day:02d}. {h:02d}Z"
    h0 = (now.hour // 6) * 6
    t0 = now.replace(hour=h0, minute=0, second=0, microsecond=0)
    body = (
        f"ZCZC 766\nFQMM81 EDZW {now:%d}1400\nWEATHER AND SEA BULLETIN FOR WESTERN MEDITERRANEAN SEA\n"
        "LIGURIAN SEA (43.5N   8.4E) SST: 18 C\n"
        f"{st(t0, t0.hour)}: SW       5    7   1.5 M //\n"
        f"{st(t0 + timedelta(hours=6), (t0 + timedelta(hours=6)).hour)}: W-NW   6-7    8   2.5 M //\n=\nNNNN\n"
    )
    br = day / "bulletins_radio"
    br.mkdir(parents=True, exist_ok=True)
    sep = "=" * 78
    (br / "DEMO_DDH7_original.txt").write_text(
        f"Station : DDH7 (7646.0 kHz)\nDébut UTC   : {(now - timedelta(hours=5)).isoformat()} | Fin\n"
        f"Produit     : Méditerranée | Zones\n{sep}\n\n{body}",
        encoding="utf-8",
    )
    syn = f"ZCZC 801\nSMFR01 LFPW {now:%d}{h0:02d}00\nAAXX {now:%d}{h0:02d}1\n07690 41570 72512 10132 40115 52018 =\nNNNN\n"
    (br / "DEMO_SYNOP_original.txt").write_text(
        f"Station : DDK9 (10100.8 kHz)\nDébut UTC   : {(now - timedelta(hours=1)).isoformat()} | Fin\n"
        f"Produit     : Observations | -\n{sep}\n\n{syn}",
        encoding="utf-8",
    )
    if CHART:
        src = Path(CHART)
        cartes = day / "cartes"
        cartes.mkdir(parents=True, exist_ok=True)
        stem = src.name.replace("_carte.png", "")
        for f in src.parent.glob(stem + "*"):
            shutil.copy2(f, cartes / f.name)
        meta = cartes / (stem + ".json")
        try:
            j = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            j = {"station": "DDK3", "lines": 1200}
        j.update({"utc_reception_fin": (now - timedelta(hours=2)).isoformat(), "programme": "Analyse de surface"})
        meta.write_text(json.dumps(j), encoding="utf-8")
    try:
        app._show_settings("METEO")
        AT.pump(app.root, 0.5)
        app.ent_press.delete(0, "end")
        app.ent_press.insert(0, "1010,8")
        app.obs_time.set(now.strftime("%Y-%m-%d %H:%M UTC"))
        app.cmb_ptrend.set("Baisse (1,6 à 3,5 hPa)")
        app.cmb_wind.set("Ouest")
        app.cmb_wind_force.set("Force 4")
        app.cmb_sea.set("Peu agitée (0,5 à 1,25 m)")
        app.cmb_sky.set("Nuageux")
    except Exception as exc:
        print("observation de démonstration :", exc)
    AT.pump(app.root, 2)
    app._outlook_busy = True
    nc = app.hybrid_arbiter.compute_nowcast()
    app._show_sector_outlook(nc)
    if nc:
        from wefax_station.weather.nowcast import nowcast_lines

        print("\n".join(nowcast_lines(nc)))
    app.settings_window.withdraw()


def desk_compiled(app):
    app._open_bulletin_desk()
    AT.pump(app.root, 1)
    app._desk_included = {d["id"] for d in getattr(app, "_desk_docs", {}).values()}
    app._desk_nb.select(1)
    app._desk_compile()
    AT.pump(app.root, 0.5)
    try:
        app._desk_text.see("1.0")
        idx = app._desk_text.search("SITUATION ACTUELLE", "1.0")
        if idx:
            app._desk_text.see(idx)
            app._desk_text.yview(idx)
    except Exception:
        pass


def main():
    root = tk.Tk()
    root.geometry("1600x900+0+0")
    app = AT.StationWefaxApp(root)
    AT.pump(root, 4)
    app.radio.port_open = True
    demo_data(app)
    if CHART:
        app._view_archive(CHART)
    AT.pump(root, 1)
    shot(root, "01_fenetre_principale")
    windows = [
        ("02_reglages_radio", lambda: app._show_settings("RADIO")),
        ("03_reglages_image", lambda: app._show_settings("IMAGE")),
        ("04_reglages_operateur", lambda: app._show_settings("METEO")),
        ("05_reglages_plan", lambda: app._show_settings("PLAN")),
        ("06_meteo_bulletin", app._open_bulletin_desk),
        ("06b_meteo_bulletin_redige", lambda: desk_compiled(app)),
        ("07_telescripteur", app.bulletins_ui.show),
        ("08_resultats_scan", app._open_scan_results),
        ("09_historique", app._history),
        ("10_diagnostics", app._show_diagnostics),
        ("11_aide", app._general_help),
        ("12_winlink", getattr(app, "_open_winlink_desk", lambda: None)),
        ("13_sources", lambda: app.schedule_planner.open_sources_window(refresh=False)),
        ("14_correction_geometrie", app._geometry_dialog),
    ]
    real_launch = getattr(app, "_wl_launch_express", None)
    for name, opener in windows:
        before = set(root.winfo_children())
        try:
            opener()
        except Exception as exc:
            print("ÉCHEC", name, repr(exc))
            continue
        AT.pump(root, 1.0)
        tops = new_toplevels(root, before)
        persistent = [
            getattr(app, n, None) for n in ("settings_window", "diagnostics_window")
        ]
        persistent = [w for w in persistent if w is not None and w.winfo_ismapped()]
        target = tops[-1] if tops else (persistent[0] if persistent else None)
        if target is not None:
            try:
                target.lift()
            except tk.TclError:
                pass
            shot(root, name, target)
            shot(root, name + "_ecran")
            for t in tops:
                try:
                    t.destroy()
                except tk.TclError:
                    pass
        else:
            shot(root, name)
        for persistent in ("settings_window", "diagnostics_window"):
            try:
                getattr(app, persistent).withdraw()
            except Exception:
                pass
    root.destroy()


if __name__ == "__main__":
    main()
