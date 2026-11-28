"""Profil opérateur : indicatif, espace de travail, préférences persistantes."""

from wefax_station.core.schedules import SCHEDULE_REV
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
import numpy as np
from PIL import Image
from wefax_station.core.stations import is_rtty_frequency
from wefax_station.radio.controller import UnifiedRadioController
from wefax_station.storage.atomic import atomic_json, atomic_png
from wefax_station.version import SOFTWARE_VERSION


class OperatorProfileMixin:
    def _init_operator_workspace_on_startup(self):
        last_op = ""
        if self.global_state_path.exists():
            try:
                data = json.loads(self.global_state_path.read_text(encoding="utf-8"))
                last_op = data.get("last_operator", "").strip().upper()
            except Exception:
                pass
        if last_op:
            self.operator_callsign_var.set(last_op)
        self._switch_operator_workspace25(self.operator_callsign_var.get(), load_prefs=True)

    def _on_operator_name_changed25(self, *args):
        if self._operator_debounce_id is not None:
            try:
                self.root.after_cancel(self._operator_debounce_id)
            except tk.TclError:
                pass
        self._operator_debounce_id = self.root.after(650, self._apply_operator_change25)

    def _apply_operator_change25(self):
        self._operator_debounce_id = None
        op_name = self.operator_callsign_var.get().strip().upper()
        self._switch_operator_workspace25(op_name, load_prefs=True)
        self._refresh_canvas()

    @staticmethod
    def _sanitize_operator_folder25(name: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip().upper()).strip("_")
        return clean if clean else "DEFAUT_F4NMK"

    # Avec l'espace portable (cas normal) puis repli historique tant que celui-ci n'existe pas
    def _switch_operator_workspace25(self, operator_name: str, load_prefs: bool = True):
        if not hasattr(self, "portable_ws"):
            return self._switch_operator_workspace_legacy(operator_name, load_prefs=load_prefs)

        ws = self.portable_ws
        tag = ws.operator_tag(operator_name)
        op_root = ws.operator_dir(tag)
        prof_dir = ws.profile_dir(tag)
        day_dir = ws.reception_day_dir(callsign=tag)

        self.base_root_dir = str(ws.root_dir)
        self.operator_root_dir = op_root
        self.archive_dir = str(day_dir / "cartes")
        Path(self.archive_dir).mkdir(parents=True, exist_ok=True)
        self.config_path = prof_dir / "preferences_poste_hf.json"
        self.schedule_path = prof_dir / "programmes_wefax.json"
        session_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.csv_path = day_dir / "journaux" / f"journal_{tag}_{session_stamp}.csv"
        ws._init_rotating_file_logger()

        if not self.schedule_path.exists():
            try:
                atomic_json(
                    self.schedule_path,
                    {"status": "Programme indicatif local opérateur", "stations": self.schedule_data, "schedule_rev": SCHEDULE_REV},
                )
            except OSError:
                pass

        try:
            atomic_json(
                ws.root_dir / "configuration" / "last_operator.json",
                {"last_operator": tag, "updated_utc": datetime.now(timezone.utc).isoformat()},
            )
        except OSError:
            pass

        if load_prefs and self.config_path.exists():
            self._load_preferences()
            if is_rtty_frequency(self.radio.actual_freq_khz):
                is_day = 7 <= datetime.now(timezone.utc).hour <= 17
                def_f = 13882.5 if is_day else 7880.0
                self.radio.actual_freq_khz = def_f
                self.radio.update_station_metadata_by_freq(def_f)

        if hasattr(self, "lbl_archive_state"):
            self.lbl_archive_state.configure(text=f"Portable : {tag} ({day_dir.name})")
        self.log_event(f"📁 Espace portable actif : Opérateur={tag} | Jour UTC={day_dir}")
        from wefax_station.storage import portable as _portable

        while _portable.MIGRATION_NOTES:  # 2.10.0 : reprise des données de la version précédente
            self.log_event(_portable.MIGRATION_NOTES.pop(0))
        if _portable.MIGRATION_PENDING_INDEX and hasattr(self, "portable_ws"):
            _portable.MIGRATION_PENDING_INDEX.clear()
            try:
                n_idx = self.portable_ws.rebuild_operator_index()
                self.log_event(f"📇 Index des réceptions reconstruit après la reprise : {n_idx} document(s).")
            except Exception as exc:
                self.log_event(f"Index des réceptions non reconstruit : {exc!r}")

    def _switch_operator_workspace_legacy(self, operator_name: str, load_prefs: bool = True):
        # 2.8.5 — avant l'ouverture de l'espace portable (quelques dixièmes de seconde au démarrage) on ne
        # crée plus l'ancienne arborescence « Operateurs/<indicatif>/Cartes, Bulletins, Journaux » : elle
        # doublait donnees/operateurs/<indicatif>/ et restait vide. Les fichiers de démarrage suffisent.
        if Path(self.base_root_dir, "configuration").is_dir():
            self.operator_root_dir = Path(self.archive_dir)
            return
        folder_tag = self._sanitize_operator_folder25(operator_name)
        op_root = Path(self.base_root_dir) / "Operateurs" / folder_tag
        for sub in ("", "Cartes", "Bulletins", "Journaux"):
            (op_root / sub).mkdir(parents=True, exist_ok=True)

        self.operator_root_dir = op_root
        self.archive_dir = str(op_root)
        self.config_path = op_root / "preferences_poste_hf.json"
        self.schedule_path = op_root / "programmes_wefax.json"
        session_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.csv_path = op_root / "Journaux" / f"journal_{folder_tag}_{session_stamp}.csv"

        if not self.schedule_path.exists():
            try:
                atomic_json(
                    self.schedule_path,
                    {"status": "Programme indicatif local opérateur", "stations": self.schedule_data, "schedule_rev": SCHEDULE_REV},
                )
            except OSError:
                pass

        try:
            atomic_json(
                self.global_state_path, {"last_operator": operator_name.strip().upper(), "folder": folder_tag}
            )
        except OSError:
            pass

        if load_prefs and self.config_path.exists():
            self._load_preferences()

        if hasattr(self, "lbl_archive_state"):
            self.lbl_archive_state.configure(text=f"Espace : {folder_tag}")
        self.log_event(f"📁 Espace opérateur actif [{folder_tag}] : {op_root}")

    def _logo_path(self):
        cfg = getattr(self, "config_path", None)
        return (Path(cfg).parent if cfg else Path(self.archive_dir)) / "logo_personnalise.png"

    def _draft_path(self):
        """2.11.0 — brouillon du bulletin dans <opérateur>/brouillons (plus dans le dossier des cartes du jour)."""
        op = getattr(self, "operator_root_dir", None)
        if op:
            from wefax_station.storage.layout import drafts_dir

            try:
                return drafts_dir(op) / "bulletin_brouillon.txt"
            except Exception:
                pass
        return Path(self.archive_dir) / "bulletin_brouillon.txt"

    def _load_preferences(self):
        try:
            target_cfg = (
                self.config_path
                if self.config_path.exists()
                else (Path(self.archive_dir) / "preferences.json")
            )
            if not target_cfg.exists():
                return
            cfg = json.loads(target_cfg.read_text(encoding="utf-8"))
            if cfg.get("zone") and hasattr(self, "zone_var"):
                self.zone_var.set(cfg.get("zone"))
            if hasattr(self, "qsy_policy"):
                self.qsy_policy.set(cfg.get("qsy_policy", "Confirmation"))
            if hasattr(self, "prevent_sleep"):
                self.prevent_sleep.set(bool(cfg.get("prevent_sleep", True)))
            if hasattr(self, "sharpness_var"):
                self.sharpness_var.set(str(cfg.get("sharpness", "AUTO")))
                self._apply_sharpness(save=False)
            if hasattr(self, "winlink_copy_var"):
                self.winlink_copy_var.set(str(cfg.get("winlink_copy", "OFF")))
                self._apply_winlink_copy(save=False)
            self.wefax_bandpass_active = bool(cfg.get("wefax_bandpass", False))
            self._apply_wefax_bandpass(save=False)
            if hasattr(self, "adrasec_var"):
                # profil créé avant la 2.8.5 (clé absente) : comportement ADRASEC conservé
                self.adrasec_var.set(bool(cfg.get("adrasec_member", True)))
                if hasattr(self, "_apply_adrasec_mode"):
                    self._apply_adrasec_mode()

            # 2.11.0 — logo rangé avec le profil : dans le dossier des cartes DU JOUR il était perdu le
            # lendemain (et chaque jour en recevait une copie)
            logo = self._logo_path()
            if not logo.exists():
                logo = Path(self.archive_dir) / "logo_personnalise.png"
            if cfg.get("logo") and logo.exists():
                with Image.open(logo) as im:
                    self.custom_logo_pil = im.convert("RGBA").copy()
                self._refresh_logo_preview()

            rf = cfg.get("radio_hf", {})
            if rf:
                if hasattr(self, "cmb_proto") and rf.get("protocol") in UnifiedRadioController.PROTOCOLS:
                    self.cmb_proto.set(rf["protocol"])
                    self.radio.protocol = rf["protocol"]
                if hasattr(self, "cmb_port") and rf.get("port"):
                    self.cmb_port.set(rf["port"])
                if hasattr(self, "cmb_baud") and rf.get("baud"):
                    self.cmb_baud.set(str(rf["baud"]))
                if hasattr(self, "ent_civ") and rf.get("civ_hex"):
                    self.ent_civ.delete(0, "end")
                    self.ent_civ.insert(0, str(rf["civ_hex"]))
                    try:
                        self.radio.civ_addr = int(str(rf["civ_hex"]).replace("0x", "").strip(), 16)
                    except ValueError:
                        pass
                self.apply_usb_offset.set(bool(rf.get("apply_usb_offset", True)))
                if rf.get("carrier_freq_khz"):
                    self.radio.actual_freq_khz = float(rf["carrier_freq_khz"])
                    self.radio.update_station_metadata_by_freq(self.radio.actual_freq_khz)
                    offset = self.radio.usb_dial_offset_khz if self.apply_usb_offset.get() else 0.0
                    self.radio.actual_dial_khz = round(self.radio.actual_freq_khz + offset, 3)
                if rf.get("if_filter"):
                    self.radio.actual_filter_str = str(rf["if_filter"])
                    fil_num = 3 if "3" in self.radio.actual_filter_str else 1
                    if hasattr(self, "grp_if_filter"):
                        self.grp_if_filter.set_value(fil_num, trigger_callback=False)
                if "preamp" in rf:
                    self.radio.actual_preamp = int(rf["preamp"])
                    if hasattr(self, "grp_preamp"):
                        self.grp_preamp.set_value(self.radio.actual_preamp, trigger_callback=False)
                if "attenuator" in rf:
                    self.radio.actual_att = bool(rf["attenuator"])
                    if hasattr(self, "btn_att"):
                        self.btn_att.set_state(self.radio.actual_att)
                if "auto_rf_loop" in rf:
                    self.auto_rf_loop_active = bool(rf["auto_rf_loop"])
                    if hasattr(self, "btn_auto_rf"):
                        self.btn_auto_rf.set_state(self.auto_rf_loop_active)
                if "auto_rf_gain" in rf:
                    self.auto_rf_gain_active = bool(rf["auto_rf_gain"])
                    if hasattr(self, "_apply_auto_rf_gain"):
                        self._apply_auto_rf_gain(save=False)
                if "auto_day_night" in rf:
                    self.auto_day_night_active = bool(rf["auto_day_night"])
                    if hasattr(self, "btn_daynight"):
                        self.btn_daynight.set_state(self.auto_day_night_active)
                if hasattr(self, "cmb_audio") and rf.get("audio_device"):
                    vals = list(self.cmb_audio["values"])
                    if rf["audio_device"] in vals:
                        self.cmb_audio.set(rf["audio_device"])

            di = cfg.get("dsp_and_image", {})
            if di:
                self.upstream_hf_cond_active = bool(di.get("upstream_hf_cond", True))
                self.btn_hf_cond.set_state(self.upstream_hf_cond_active)
                self.qrn_blanker_var.set(bool(di.get("qrn_blanker", True)))
                self.btn_qrn_blanker.set_state(self.qrn_blanker_var.get())
                self.auto_margin_once_active = bool(di.get("auto_margin_once", True))
                self.btn_auto_margin_once.set_state(self.auto_margin_once_active)
                self.auto_save_png_active = bool(di.get("auto_save_png", True))
                self.btn_autosave_png.set_state(self.auto_save_png_active)

                self.fft_notch_var.set(bool(di.get("fft_notch", True)))
                self.btn_fft2d.set_state(self.fft_notch_var.get())
                self.tensor_var.set(bool(di.get("structure_tensor", True)))
                self.btn_tensor.set_state(self.tensor_var.get())
                self.adapt_bin_var.set(bool(di.get("adaptive_bin", False)))
                self.btn_bin.set_state(self.adapt_bin_var.get())

                if "slant_slider" in di and hasattr(self, "sld_slant"):
                    self.sld_slant.set(float(di["slant_slider"]))
                if "split_ratio" in di and hasattr(self, "sld_split"):
                    self.split_ratio = float(di["split_ratio"])
                    self.sld_split.set(int(round(self.split_ratio * 100)))
                if di.get("display_mode") in ("PROCESSED", "RAW", "SPLIT"):
                    self.display_mode = di["display_mode"]
                    self.grp_display_mode.set_value(self.display_mode, trigger_callback=False)
                if "dept_overlay" in di:
                    self.dept_overlay_var.set(bool(di["dept_overlay"]))
                    self.btn_overlay_dept.set_state(self.dept_overlay_var.get())
                if isinstance(di.get("qth_rel_pos"), list) and len(di["qth_rel_pos"]) == 2:
                    self.qth_rel_pos = [float(di["qth_rel_pos"][0]), float(di["qth_rel_pos"][1])]
                if "roi_rel_radius" in di:
                    self.roi_rel_radius = float(di["roi_rel_radius"])
                self._recompute_roi_from_qth()

            draft = self._draft_path()
            if not draft.exists():
                draft = Path(self.archive_dir) / "bulletin_brouillon.txt"  # emplacement avant 2.11.0
            if draft.exists():
                self._set_bulletin(draft.read_text(encoding="utf-8"))
                self.bulletin_dirty = True

            self._sync_ui_from_hardware()
        except Exception as exc:
            self.log_event("Préférences opérateur ignorées : " + repr(exc))

    def _save_preferences(self):
        if not hasattr(self, "config_path"):
            return
        try:
            if self.custom_logo_pil is not None:
                atomic_png(
                    self._logo_path(),
                    np.asarray(self.custom_logo_pil.convert("RGBA")),
                )
            payload = {
                "version": SOFTWARE_VERSION,
                "operator": self.operator_callsign_var.get().strip().upper(),
                "zone": self.zone_var.get() if hasattr(self, "zone_var") else "",
                "qsy_policy": self.qsy_policy.get() if hasattr(self, "qsy_policy") else "Confirmation",
                "prevent_sleep": bool(self.prevent_sleep.get()) if hasattr(self, "prevent_sleep") else True,
                "logo": self.custom_logo_pil is not None,
                "sharpness": str(self.sharpness_var.get()) if hasattr(self, "sharpness_var") else "AUTO",
                "winlink_copy": str(self.winlink_copy_var.get()) if hasattr(self, "winlink_copy_var") else "OFF",
                "wefax_bandpass": bool(getattr(self, "wefax_bandpass_active", False)),
                "adrasec_member": bool(self.adrasec_var.get()) if hasattr(self, "adrasec_var") else False,
                "radio_hf": {
                    "protocol": self.cmb_proto.get() if hasattr(self, "cmb_proto") else self.radio.protocol,
                    "port": self.cmb_port.get() if hasattr(self, "cmb_port") else "",
                    "baud": int(self.cmb_baud.get() or 19200) if hasattr(self, "cmb_baud") else 19200,
                    "civ_hex": (
                        self.ent_civ.get().strip()
                        if hasattr(self, "ent_civ")
                        else f"{self.radio.civ_addr:02X}"
                    ),
                    "active_station_id": self.radio.active_station_id,
                    "carrier_freq_khz": float(self.radio.actual_freq_khz),
                    "apply_usb_offset": bool(self.apply_usb_offset.get()),
                    "if_filter": self.radio.actual_filter_str,
                    "preamp": int(self.radio.actual_preamp),
                    "attenuator": bool(self.radio.actual_att),
                    "auto_rf_loop": bool(self.auto_rf_loop_active),
                    "auto_rf_gain": bool(getattr(self, "auto_rf_gain_active", False)),
                    "auto_day_night": bool(self.auto_day_night_active),
                    "audio_device": self.cmb_audio.get() if hasattr(self, "cmb_audio") else "",
                },
                "dsp_and_image": {
                    "rx_decoding_active": bool(self.rx_decoding_active),
                    "apt_auto_start": bool(self.apt_auto_start_active),
                    "upstream_hf_cond": bool(self.upstream_hf_cond_active),
                    "qrn_blanker": bool(self.qrn_blanker_var.get()),
                    "auto_margin_once": bool(self.auto_margin_once_active),
                    "auto_save_png": bool(self.auto_save_png_active),
                    "fft_notch": bool(self.fft_notch_var.get()),
                    "structure_tensor": bool(self.tensor_var.get()),
                    "adaptive_bin": bool(self.adapt_bin_var.get()),
                    "slant_slider": float(self.sld_slant.get()) if hasattr(self, "sld_slant") else 0.0,
                    "split_ratio": float(self.split_ratio),
                    "display_mode": self.display_mode,
                    "dept_overlay": bool(self.dept_overlay_var.get()),
                    "qth_rel_pos": list(self.qth_rel_pos),
                    "roi_rel_radius": float(self.roi_rel_radius),
                },
                "saved_utc": datetime.now(timezone.utc).isoformat(),
            }
            atomic_json(self.config_path, payload)
            # 2.11.0 — plus de copie « preferences.json » dans le dossier des cartes du jour (doublon)
            self.log_event(f"💾 Paramètres HF et réglages opérateur sauvegardés : {self.config_path.name}")
        except Exception as exc:
            self.log_event("ECHEC sauvegarde préférences opérateur : " + repr(exc))
