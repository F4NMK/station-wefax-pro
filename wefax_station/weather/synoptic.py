"""Moteur heuristique d'analyse synoptique."""

import math
import numpy as np
import cv2


class SynopticWeatherAnalysisEngine:
    @staticmethod
    def _analyze_sector_patch(patch: np.ndarray) -> dict:
        if patch.size == 0:
            return {"iso_tightness": 8.0, "front_density": 1.0, "angle_deg": 90.0}
        _, bw = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        line_density = float(np.mean(bw > 0)) * 100.0
        thick = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        front_density = float(np.mean(thick > 0)) * 100.0
        iso_tightness = max(0.0, line_density - front_density)

        gx = cv2.Sobel(patch.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(patch.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
        grad_angle = 0.5 * math.atan2(
            2.0 * float(np.mean(gx * gy)), float(np.mean(gx * gx) - np.mean(gy * gy)) + 1e-6
        )
        iso_deg = (math.degrees(grad_angle) + 90.0) % 180.0
        return {
            "iso_tightness": round(iso_tightness, 1),
            "front_density": round(front_density, 1),
            "angle_deg": round(iso_deg, 1),
        }

    @classmethod
    def analyze_full_map_and_target(
        cls, img_gray: np.ndarray, roi_box: tuple, qth_point: tuple, sensors: dict
    ) -> dict:
        h, w = img_gray.shape

        sectors_def = {
            "Atlantique Nord & UK (Amont Ouest/NO)": (
                int(w * 0.06),
                int(h * 0.15),
                int(w * 0.45),
                int(h * 0.55),
            ),
            "Açores & Ibérie (Amont Sud-Ouest)": (int(w * 0.08), int(h * 0.55), int(w * 0.44), int(h * 0.90)),
            "Scandinavie & Mer du Nord (Amont Nord)": (
                int(w * 0.45),
                int(h * 0.08),
                int(w * 0.82),
                int(h * 0.44),
            ),
            "Europe Centrale & Alpes (Amont Est/NE)": (
                int(w * 0.52),
                int(h * 0.38),
                int(w * 0.88),
                int(h * 0.65),
            ),
            "Méditerranée & Golfe de Gênes": (int(w * 0.46), int(h * 0.60), int(w * 0.78), int(h * 0.88)),
        }

        macro = {
            name: cls._analyze_sector_patch(img_gray[sy0:sy1, sx0:sx1])
            for name, (sx0, sy0, sx1, sy1) in sectors_def.items()
        }

        atl = macro["Atlantique Nord & UK (Amont Ouest/NO)"]
        ibe = macro["Açores & Ibérie (Amont Sud-Ouest)"]
        ceu = macro["Europe Centrale & Alpes (Amont Est/NE)"]
        med = macro["Méditerranée & Golfe de Gênes"]

        upstream_summary = []
        if atl["front_density"] > 2.2 or atl["iso_tightness"] > 14.0:
            upstream_summary.append(
                f"• Atlantique / UK : Rail dépressionnaire actif en amont (Fronts={atl['front_density']}%, "
                f"Gradient={atl['iso_tightness']}%) dirigeant des perturbations vers l'Europe de l'Ouest."
            )
        else:
            upstream_summary.append(
                f"• Atlantique / UK : Circulation modérée (Gradient={atl['iso_tightness']}%), "
                "sans tempête océanique immédiate en amont."
            )

        if ibe["iso_tightness"] < 10.5 and ibe["front_density"] < 1.8:
            upstream_summary.append(
                f"• Açores / Ibérie : Dorsale anticyclonique au Sud-Ouest (Gradient={ibe['iso_tightness']}%)."
            )
        else:
            upstream_summary.append(
                f"• Ibérie / Proche-Atlantique : Talweg ou activité frontale (Fronts={ibe['front_density']}%) "
                "pouvant remonter vers le bassin méditerranéen."
            )

        if med["front_density"] > 2.0 or med["iso_tightness"] > 13.5:
            upstream_summary.append(
                f"• Méditerranée & Gênes : Creusement dépressionnaire / activité frontale "
                f"(Fronts={med['front_density']}%, Isobares={med['iso_tightness']}%)."
            )
        else:
            upstream_summary.append(
                f"• Méditerranée & Gênes : Champ de pression calme à modéré (Gradient={med['iso_tightness']}%)."
            )

        dipole_diff = (med["iso_tightness"] + ceu["iso_tightness"]) - ibe["iso_tightness"]

        if roi_box and len(roi_box) == 4:
            x0, y0, x1, y1 = roi_box
            x0, x1 = max(0, min(x0, x1)), min(w, max(x0, x1))
            y0, y1 = max(0, min(y0, y1)), min(h, max(y0, y1))
            roi = (
                img_gray[y0:y1, x0:x1]
                if (x1 - x0) > 25 and (y1 - y0) > 25
                else img_gray[int(h * 0.58) : int(h * 0.78), int(w * 0.52) : int(w * 0.68)]
            )
            roi_label = f"Secteur 06/83 ({x1-x0}x{y1-y0} px)"
        else:
            roi = img_gray[int(h * 0.58) : int(h * 0.78), int(w * 0.52) : int(w * 0.68)]
            roi_label = "Secteur 06 Le Cannet / 83 Mt Vinaigre"

        local_m = cls._analyze_sector_patch(roi)
        loc_iso, loc_front, loc_deg = local_m["iso_tightness"], local_m["front_density"], local_m["angle_deg"]

        if 25 <= loc_deg < 65:
            flow_dir = "Sud-Ouest / Nord-Est (Flux méditerranéen doux et humide)"
        elif 65 <= loc_deg < 115:
            flow_dir = "Ouest / Est (Circulation zonale ou Retour d'Est)"
        elif 115 <= loc_deg < 155:
            flow_dir = "Nord-Ouest / Sud-Est (Axe Rhône-Corse : Mistral ou creusement Gênes)"
        else:
            flow_dir = "Méridien Nord / Sud (Échange thermique transalpin)"

        if loc_iso > 15.5:
            grad_desc = f"FORT ({loc_iso}% — Isobares serrées -> Vent fort)"
            wind_risk = 3
        elif loc_iso > 9.5:
            grad_desc = f"MODÉRÉ ({loc_iso}% — Flux synoptique régulier)"
            wind_risk = 2
        else:
            grad_desc = f"FAIBLE ({loc_iso}% — Marais barométrique / Brises thermiques)"
            wind_risk = 1

        p_hpa = sensors.get("pressure_hpa")
        p_trend = sensors.get("pressure_trend", "Non renseigné")
        wind_obs = sensors.get("wind_obs", "Non renseigné")
        temp_c = sensors.get("temp_c")
        rh_pct = sensors.get("rh_pct")
        sky_obs = sensors.get("sky_obs", "Non renseigné")

        spread_c = None
        dew_str = "N/A"
        if temp_c is not None and rh_pct is not None and rh_pct > 0:
            a, b = 17.27, 237.7
            alpha = ((a * temp_c) / (b + temp_c)) + math.log(max(1.0, rh_pct) / 100.0)
            td = (b * alpha) / (a - alpha)
            spread_c = temp_c - td
            dew_str = f"{td:.1f}°C (Écart T-Td = {spread_c:.1f}°C)"

        reliability = 62
        questions = []
        if float(np.std(img_gray)) > 35:
            reliability += 8
        if p_hpa is not None:
            reliability += 8
        else:
            questions.append("Quelle est la pression barométrique QNH (hPa) au QTH ?")
        if p_trend != "Non renseigné":
            reliability += 10
        else:
            questions.append("Quelle est la tendance barométrique sur 3h (Stable, Baisse, Chute rapide) ?")
        if wind_obs != "Non renseigné":
            reliability += 5
        if sky_obs != "Non renseigné":
            reliability += 5

        falling_fast = "Chute rapide" in p_trend
        falling_mod = "Baisse" in p_trend

        if ("Pluie" in sky_obs or "Orage" in sky_obs) or (loc_front > 2.4 and (falling_mod or falling_fast)):
            present_state = f"Temps perturbé actif sur 06/83 (Convergence humide, Rosée : {dew_str})."
        elif p_hpa and p_hpa >= 1018 and loc_iso < 11.0:
            present_state = f"Hautes pressions protectrices sur Alpes/Méditerranée (QNH={p_hpa:.0f} hPa)."
        else:
            present_state = (
                f"Situation de transition sur 06/83 (QNH={p_hpa if p_hpa else '--'} hPa, Vent: {wind_obs})."
            )

        if falling_fast or (falling_mod and (med["front_density"] > 2.0 or atl["front_density"] > 2.4)):
            alert = "ORANGE (Dégradation Active)"
            fc_6_12 = (
                "DÉGRADATION SOUS 6H-12H : Le système perturbé repéré en amont provoque un renforcement "
                "des pluies et du vent (convergence humide sur l'Estérel 83 et les reliefs du 06)."
            )
            fc_24_48 = (
                f"À H+24 / H+48 : Bascule du flux à l'Ouest/Nord-Ouest à l'arrière du front "
                f"(Gradient Atlantique={atl['iso_tightness']}%), retour d'un temps plus sec mais venté."
            )
            reliability = min(97, reliability + 4)
        elif atl["front_density"] > 2.3 and (not falling_fast and not falling_mod):
            alert = "JAUNE (Perturbation Atlantique en approche)"
            fc_6_12 = "MAINTIEN TEMPORAIRE À H+6 / H+12 : Voile pré-frontal (Cirrus/Altocumulus) gagnant par l'Ouest."
            fc_24_48 = (
                f"DÉGRADATION À H+24 / H+48 : Le front actif situé sur l'Atlantique/UK "
                f"(Densité={atl['front_density']}%) atteindra le Sud-Est sous 24 à 36h."
            )
        elif dipole_diff > 4.0 or ("Nord-Ouest" in wind_obs and wind_risk >= 2):
            alert = "JAUNE (Flux de Nord-Ouest / Mistral)"
            fc_6_12 = "VENT SOUTENU (H+6 / H+12) : Gradient marqué entre dorsale ibérique et Golfe de Gênes."
            fc_24_48 = "À H+24 / H+48 : Temps sec et lumineux par effet de foehn sur le 06, Mistral soutenu sur le 83."
        else:
            alert = "VERT (Stabilité Synoptique)"
            fc_6_12 = "CONDITIONS CALMES À H+6 / H+12 : Brises thermiques côtières et nuages bas locaux."
            fc_24_48 = (
                "À H+24 / H+48 : Maintien d'un champ de pression élevé sur le bassin nord-méditerranéen."
            )

        return {
            "roi_label": roi_label,
            "upstream_summary": upstream_summary,
            "grad_desc": grad_desc,
            "flow_dir": flow_dir,
            "dew_str": dew_str,
            "present_state": present_state,
            "fc_6_12": fc_6_12,
            "fc_24_48": fc_24_48,
            "alert": alert,
            "reliability_pct": max(45, min(97, int(reliability))),
            "questions": questions,
        }
