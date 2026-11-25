"""Bandeau des étapes de réception WEFAX (avec hystérésis anti-spam du journal)."""

import time
import tkinter as tk


class ReceptionStepBanner:
    STEPS = (
        ("AUDIO", "1. Flux Audio USB"),
        ("SIGNAL", "2. Signal Radio"),
        ("START", "3. APT START"),
        ("PHASE", "4. Phasage"),
        ("IMAGE", "5. Tracé Carte"),
        ("STOP", "6. APT STOP"),
        ("SAVED", "7. Sauvegarde"),
    )

    COLORS = {
        "idle": ("#111827", "#64748b", "#1e293b"),
        "candidate": ("#1e3a8a", "#bae6fd", "#38bdf8"),
        "active": ("#b45309", "#fef3c7", "#f59e0b"),
        "confirmed": ("#065f46", "#dcfce7", "#22c55e"),
        "error": ("#7f1d1d", "#fecaca", "#ef4444"),
    }

    def __init__(self, app):
        self.app = app
        self.states = {k: ("idle", "En attente") for k, _ in self.STEPS}
        self.last_logged = {}
        self.signal_hold_until_mono = 0.0
        self.cells = {}
        self.frame = None
        self._build_widget()

    def _build_widget(self):
        parent = getattr(self.app, "root", None)
        if parent is None:
            return
        self.frame = tk.Frame(parent, bg="#0b1120", padx=6, pady=3)
        canvas_w = getattr(self.app, "canvas", None)
        try:
            if canvas_w is not None and str(canvas_w.winfo_manager()) == "pack":
                self.frame.pack(fill="x", padx=6, pady=(2, 2), before=canvas_w)
            else:
                self.frame.pack(fill="x", padx=6, pady=(2, 2))
        except Exception:
            self.frame.pack(fill="x", padx=6, pady=(2, 2))

        for idx, (key, title) in enumerate(self.STEPS):
            self.frame.grid_columnconfigure(idx, weight=1, uniform="rx_step")
            cell = tk.Frame(self.frame, bg="#111827", bd=1, relief="solid", padx=5, pady=2)
            cell.grid(row=0, column=idx, sticky="ew", padx=2)
            lbl_t = tk.Label(
                cell, text=title, bg="#111827", fg="#94a3b8", font=("Segoe UI", 8, "bold"), anchor="w"
            )
            lbl_t.pack(fill="x")
            lbl_d = tk.Label(
                cell, text="En attente", bg="#111827", fg="#64748b", font=("Consolas", 7), anchor="w"
            )
            lbl_d.pack(fill="x")
            self.cells[key] = (cell, lbl_t, lbl_d)

    def set_step(self, step_key: str, status: str, detail: str = "", log_transition: bool = True):
        if step_key not in self.cells:
            return
        now_m = time.monotonic()

        # Hystérésis anti-clignotement sur SIGNAL :
        if step_key == "SIGNAL":
            drawing_active = int(getattr(self.app, "rx_current_line", 0)) >= 3 and not getattr(
                self.app, "waiting_after_stop", False
            )
            if status in ("confirmed", "active", "candidate"):
                self.signal_hold_until_mono = now_m + (10.0 if drawing_active else 6.0)
                if drawing_active and status == "candidate":
                    status = "confirmed"
                    detail = "Signal WEFAX en cours de tracé"
            elif status == "idle":
                if drawing_active or now_m < self.signal_hold_until_mono:
                    return

        prev_status, prev_detail = self.states.get(step_key, ("idle", ""))
        if prev_status == status and prev_detail == detail:
            return
        self.states[step_key] = (status, detail)

        bg, fg, border = self.COLORS.get(status, self.COLORS["idle"])
        cell, lbl_t, lbl_d = self.cells[step_key]
        try:
            cell.configure(bg=bg, highlightbackground=border, highlightthickness=1)
            lbl_t.configure(bg=bg, fg=fg)
            lbl_d.configure(bg=bg, fg=fg, text=(detail or status)[:34])
        except Exception:
            pass

        if log_transition:
            last_t, last_st = self.last_logged.get(step_key, (0.0, ""))
            if status != last_st and (step_key != "SIGNAL" or (now_m - last_t) >= 15.0):
                self.last_logged[step_key] = (now_m, status)
                try:
                    self.app.log_event(f"RX_BANNER {step_key} status={status} detail={detail}")
                except Exception:
                    pass
