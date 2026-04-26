from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .advice import build_advice
from .card_tracker import build_core_advice, format_core_advice, reset_card_state
from .chase_calculator import build_chase_reports_from_state, format_chase_reports, visible_counts_from_shop
from .config import AppConfig
from .ldplayer import GAME_PACKAGE, LDPlayerClient, LDPlayerError
from .lineups import fetch_jcc_s_lineups, recommend_lineups
from .ocr import read_screenshot
from .region_capture import crop_regions
from .shop_hits import build_shop_hit_alerts, format_shop_hit_alerts
from .shop_recognition import format_shop_scan, scan_shop as scan_shop_screenshot
from .version import __version__


def _reading_value(readings, name: str) -> int | None:
    for reading in readings:
        if reading.name == name:
            return reading.value
    return None


class JkcheeseGui:
    def __init__(self) -> None:
        self.config = AppConfig.load()
        self.root = tk.Tk()
        self.root.title(f"Jkcheese v{__version__}")
        self.root.geometry("1040x760")
        self.root.minsize(980, 700)

        self.ldplayer_root_var = tk.StringVar(value=self.config.ldplayer_root)
        self.instance_var = tk.StringVar(value=str(self.config.instance_index))
        self.capture_dir_var = tk.StringVar(value=self.config.capture_dir)
        self.status_var = tk.StringVar(value="Ready")
        self.instance_name_var = tk.StringVar(value="-")
        self.game_installed_var = tk.StringVar(value="-")
        self.game_process_var = tk.StringVar(value="-")
        self.apk_path_var = tk.StringVar(value="-")
        self.last_capture_var = tk.StringVar(value="-")
        self.last_regions_var = tk.StringVar(value="-")
        self.last_reading_var = tk.StringVar(value="-")
        self.last_advice_var = tk.StringVar(value="-")
        self.last_lineups_var = tk.StringVar(value="-")
        self.last_core_var = tk.StringVar(value="-")
        self.live_tokens_var = tk.StringVar(value="")
        self.owned_cards_var = tk.StringVar(value="")
        self._busy = False

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(4, weight=1)

        top = ttk.Frame(self.root, padding=16)
        top.grid(row=0, column=0, sticky="nsew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="LDPlayer Root").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(top, textvariable=self.ldplayer_root_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(top, text="Browse", command=self._pick_ldplayer_root).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(top, text="Instance").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        ttk.Spinbox(top, from_=0, to=32, textvariable=self.instance_var, width=8).grid(
            row=1, column=1, sticky="w", pady=(10, 0)
        )

        ttk.Label(top, text="Capture Folder").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        ttk.Entry(top, textvariable=self.capture_dir_var).grid(row=2, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(top, text="Browse", command=self._pick_capture_dir).grid(row=2, column=2, padx=(8, 0), pady=(10, 0))

        status = ttk.LabelFrame(self.root, text="Status", padding=16)
        status.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        status.columnconfigure(1, weight=1)

        self._add_status_row(status, 0, "State", self.status_var)
        self._add_status_row(status, 1, "Instance Name", self.instance_name_var)
        self._add_status_row(status, 2, "Game Installed", self.game_installed_var)
        self._add_status_row(status, 3, "Game Process", self.game_process_var)
        self._add_status_row(status, 4, "APK Path", self.apk_path_var)
        self._add_status_row(status, 5, "Last Capture", self.last_capture_var)
        self._add_status_row(status, 6, "Last Regions", self.last_regions_var)
        self._add_status_row(status, 7, "Last Reading", self.last_reading_var)
        self._add_status_row(status, 8, "Last Advice", self.last_advice_var)
        self._add_status_row(status, 9, "S Lineups", self.last_lineups_var)
        self._add_status_row(status, 10, "Core Advice", self.last_core_var)

        actions = ttk.LabelFrame(self.root, text="Actions", padding=16)
        actions.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))

        self.refresh_button = ttk.Button(actions, text="Refresh Status", command=self.refresh_status)
        self.launch_button = ttk.Button(actions, text="Launch Emulator", command=self.launch_instance)
        self.run_game_button = ttk.Button(actions, text="Launch Game", command=self.launch_game)
        self.capture_button = ttk.Button(actions, text="Capture Screenshot", command=self.capture_screenshot)
        self.capture_regions_button = ttk.Button(actions, text="Capture Regions", command=self.capture_regions)
        self.read_button = ttk.Button(actions, text="Read Numbers", command=self.capture_readings)
        self.advice_button = ttk.Button(actions, text="Get Advice", command=self.capture_advice)
        self.lineups_button = ttk.Button(actions, text="S Lineups", command=self.fetch_s_lineups)
        self.open_folder_button = ttk.Button(actions, text="Open Capture Folder", command=self.open_capture_folder)

        self.refresh_button.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="ew")
        self.launch_button.grid(row=0, column=1, padx=8, pady=4, sticky="ew")
        self.run_game_button.grid(row=0, column=2, padx=8, pady=4, sticky="ew")
        self.capture_button.grid(row=0, column=3, padx=(8, 0), pady=4, sticky="ew")
        self.capture_regions_button.grid(row=1, column=0, padx=(0, 8), pady=4, sticky="ew")
        self.read_button.grid(row=1, column=1, padx=8, pady=4, sticky="ew")
        self.advice_button.grid(row=1, column=2, padx=8, pady=4, sticky="ew")
        self.lineups_button.grid(row=1, column=3, padx=(8, 0), pady=4, sticky="ew")
        self.open_folder_button.grid(row=2, column=0, columnspan=4, padx=0, pady=4, sticky="ew")

        for column in range(4):
            actions.columnconfigure(column, weight=1)

        core = ttk.LabelFrame(self.root, text="Core Helper", padding=16)
        core.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))
        core.columnconfigure(1, weight=1)

        ttk.Label(core, text="Live Tokens").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(core, textvariable=self.live_tokens_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(core, text="Owned Copies").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(core, textvariable=self.owned_cards_var).grid(row=1, column=1, sticky="ew", pady=3)

        self.core_button = ttk.Button(core, text="Core Advice", command=self.get_core_advice)
        self.shop_scan_button = ttk.Button(core, text="Scan Shop", command=self.scan_shop)
        self.reset_cards_button = ttk.Button(core, text="Reset Card Counts", command=self.reset_card_counts)
        self.core_button.grid(row=0, column=2, padx=(8, 0), pady=3, sticky="ew")
        self.shop_scan_button.grid(row=1, column=2, padx=(8, 0), pady=3, sticky="ew")
        self.reset_cards_button.grid(row=0, column=3, rowspan=2, padx=(8, 0), pady=3, sticky="nsew")

        hint = (
            "Live tokens rank S lineups. Owned copies drive cost-aware star warnings, "
            "e.g. 4费Vexx7, 五费Nami=3, or Vex@4x7. Focus is 4/5-cost units."
            " Default pools: 1=30, 2=25, 3=18, 4=10, 5=9."
        )
        ttk.Label(core, text=hint).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        log_frame = ttk.LabelFrame(self.root, text="Log", padding=12)
        log_frame.grid(row=4, column=0, sticky="nsew", padx=16, pady=(0, 16))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", height=14, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _add_status_row(self, parent: ttk.Widget, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=2)
        ttk.Label(parent, textvariable=variable).grid(row=row, column=1, sticky="nw", pady=2)

    def _pick_ldplayer_root(self) -> None:
        selected = filedialog.askdirectory(title="Select LDPlayer root")
        if selected:
            self.ldplayer_root_var.set(selected)

    def _pick_capture_dir(self) -> None:
        selected = filedialog.askdirectory(title="Select capture folder")
        if selected:
            self.capture_dir_var.set(selected)

    def _save_config(self) -> None:
        self.config.ldplayer_root = self.ldplayer_root_var.get().strip()
        self.config.instance_index = self._current_index()
        self.config.capture_dir = self.capture_dir_var.get().strip()
        self.config.save()

    def _current_index(self) -> int:
        value = self.instance_var.get().strip() or "0"
        return int(value)

    def _client(self) -> LDPlayerClient:
        root = self.ldplayer_root_var.get().strip()
        if not root:
            raise LDPlayerError("Please choose the LDPlayer root first.")
        return LDPlayerClient(Path(root))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for button in (
            self.refresh_button,
            self.launch_button,
            self.run_game_button,
            self.capture_button,
            self.capture_regions_button,
            self.read_button,
            self.advice_button,
            self.lineups_button,
            self.core_button,
            self.shop_scan_button,
            self.reset_cards_button,
            self.open_folder_button,
        ):
            button.configure(state=state)

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _run_task(self, label: str, fn) -> None:
        if self._busy:
            return

        self._set_busy(True)
        self.status_var.set(label)
        self._log(label)

        def worker() -> None:
            try:
                result = fn()
            except Exception as exc:
                self.root.after(0, lambda: self._task_failed(label, exc))
            else:
                self.root.after(0, lambda: self._task_done(label, result))

        threading.Thread(target=worker, daemon=True).start()

    def _task_done(self, label: str, result) -> None:
        self._set_busy(False)
        self.status_var.set("Ready")
        if result:
            self._log(str(result))

    def _task_failed(self, label: str, exc: Exception) -> None:
        self._set_busy(False)
        self.status_var.set("Error")
        self._log(f"{label} failed: {exc}")
        messagebox.showerror("Jkcheese", str(exc))

    def refresh_status(self) -> None:
        def task() -> str:
            client = self._client()
            instance = client.get_instance(self._current_index())
            self.root.after(0, lambda: self.instance_name_var.set(instance.name))
            self.root.after(0, lambda: self.game_installed_var.set("Yes" if instance.has_game else "No"))

            if not instance.has_game:
                self.root.after(0, lambda: self.game_process_var.set("-"))
                self.root.after(0, lambda: self.apk_path_var.set("-"))
                return f"Instance {instance.index} is available but the game was not detected."

            if not instance.running:
                self.root.after(0, lambda: self.game_process_var.set("Emulator stopped"))
                self.root.after(0, lambda: self.apk_path_var.set("-"))
                return f"Instance {instance.index} is stopped."

            game_running = client.is_package_running(instance.index, GAME_PACKAGE)
            apk_path = client.resolve_package_path(instance.index, GAME_PACKAGE) or "-"

            self.root.after(0, lambda: self.game_process_var.set("Running" if game_running else "Not running"))
            self.root.after(0, lambda: self.apk_path_var.set(apk_path))
            return f"Status refreshed for instance {instance.index}."

        self._run_task("Refreshing status", task)

    def launch_instance(self) -> None:
        def task() -> str:
            client = self._client()
            index = self._current_index()
            client.launch(index)
            client.wait_for_running(index)
            return f"Instance {index} launched."

        self._run_task("Launching emulator", task)

    def launch_game(self) -> None:
        def task() -> str:
            client = self._client()
            index = self._current_index()
            if not client.is_running(index):
                client.launch(index)
                client.wait_for_running(index)
            client.wait_for_boot(index)
            client.run_app(index, GAME_PACKAGE)
            return f"Game launch command sent to instance {index}."

        self._run_task("Launching game", task)

    def capture_screenshot(self) -> None:
        def task() -> str:
            client = self._client()
            index = self._current_index()
            capture_dir_text = self.capture_dir_var.get().strip()
            if not capture_dir_text:
                raise LDPlayerError("Please choose a capture folder first.")
            capture_dir = Path(capture_dir_text)
            filename = time.strftime("jkcheese_%Y%m%d_%H%M%S.png")
            output = capture_dir / filename
            saved = client.capture_screenshot(index, output, launch_if_needed=True)
            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            return f"Screenshot saved to {saved}"

        self._run_task("Capturing screenshot", task)

    def capture_regions(self) -> None:
        def task() -> str:
            client = self._client()
            index = self._current_index()
            capture_dir_text = self.capture_dir_var.get().strip()
            if not capture_dir_text:
                raise LDPlayerError("Please choose a capture folder first.")

            session_dir = Path(capture_dir_text) / time.strftime("regions_%Y%m%d_%H%M%S")
            screenshot_path = session_dir / "screen.png"
            saved = client.capture_screenshot(index, screenshot_path, launch_if_needed=True)
            region_dir = session_dir / "regions"
            results = crop_regions(saved, region_dir)

            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self.last_regions_var.set(str(region_dir)))
            return f"Captured {len(results)} regions to {region_dir}"

        self._run_task("Capturing regions", task)

    def capture_readings(self) -> None:
        def task() -> str:
            client = self._client()
            index = self._current_index()
            capture_dir_text = self.capture_dir_var.get().strip()
            if not capture_dir_text:
                raise LDPlayerError("Please choose a capture folder first.")

            session_dir = Path(capture_dir_text) / time.strftime("read_%Y%m%d_%H%M%S")
            screenshot_path = session_dir / "screen.png"
            saved = client.capture_screenshot(index, screenshot_path, launch_if_needed=True)
            readings = read_screenshot(saved)
            summary = ", ".join(f"{reading.name}={reading.text or '?'}" for reading in readings)

            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self.last_reading_var.set(summary))
            return f"Read {summary}"

        self._run_task("Reading numbers", task)

    def capture_advice(self) -> None:
        def task() -> str:
            client = self._client()
            index = self._current_index()
            capture_dir_text = self.capture_dir_var.get().strip()
            if not capture_dir_text:
                raise LDPlayerError("Please choose a capture folder first.")

            session_dir = Path(capture_dir_text) / time.strftime("advice_%Y%m%d_%H%M%S")
            screenshot_path = session_dir / "screen.png"
            saved = client.capture_screenshot(index, screenshot_path, launch_if_needed=True)
            report = build_advice(read_screenshot(saved))
            reading_summary = ", ".join(f"{reading.name}={reading.text or '?'}" for reading in report.readings)
            advice_summary = "; ".join(item.title for item in report.advice)

            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self.last_reading_var.set(reading_summary))
            self.root.after(0, lambda: self.last_advice_var.set(advice_summary))

            warning_lines = [warning.message for warning in report.warnings]
            advice_lines = [f"{item.title}: {item.detail}" for item in report.advice]
            details = warning_lines + advice_lines
            return "\n".join(details)

        self._run_task("Getting advice", task)

    def fetch_s_lineups(self) -> None:
        def task() -> str:
            lineups = fetch_jcc_s_lineups()
            recommendations = recommend_lineups(lineups, limit=5)
            summary = "; ".join(item.lineup.name for item in recommendations)
            self.root.after(0, lambda: self.last_lineups_var.set(summary))

            lines = ["S-tier lineups from 实时铲榜:"]
            for item in recommendations:
                notes = f" ({'; '.join(item.lineup.notes)})" if item.lineup.notes else ""
                lines.append(f"- {item.lineup.name}{notes}")
            return "\n".join(lines)

        self._run_task("Fetching S lineups", task)

    def get_core_advice(self) -> None:
        def task() -> str:
            capture_dir = self._capture_dir()
            state_path = capture_dir / "card_state.json"
            lineups = fetch_jcc_s_lineups()
            report = build_core_advice(
                state_path=state_path,
                lineups=lineups,
                seen=self.live_tokens_var.get(),
                owned=self.owned_cards_var.get(),
                mode="add",
                limit=5,
            )

            warning_summary = "; ".join(warning.title for warning in report.warnings[:3])
            if not warning_summary:
                warning_summary = "No upgrade warning"
            lineup_summary = "; ".join(item.lineup.name for item in report.recommendations[:3])

            self.root.after(0, lambda: self.last_core_var.set(warning_summary))
            if lineup_summary:
                self.root.after(0, lambda: self.last_lineups_var.set(lineup_summary))
            self.root.after(0, lambda: self.owned_cards_var.set(""))
            return format_core_advice(report)

        self._run_task("Building core advice", task)

    def scan_shop(self) -> None:
        def task() -> str:
            client = self._client()
            index = self._current_index()
            capture_dir = self._capture_dir()
            session_dir = capture_dir / time.strftime("shop_%Y%m%d_%H%M%S")
            screenshot_path = session_dir / "screen.png"
            saved = client.capture_screenshot(index, screenshot_path, launch_if_needed=True)
            report = scan_shop_screenshot(
                saved,
                output_dir=session_dir / "shop",
                templates_path=capture_dir / "shop_templates.json",
                champions_path=capture_dir / "champions.json",
            )
            readings = read_screenshot(saved)
            detected_level = _reading_value(readings, "level")
            detected_gold = _reading_value(readings, "gold")
            lineups = fetch_jcc_s_lineups()
            core_report = build_core_advice(
                state_path=capture_dir / "card_state.json",
                lineups=lineups,
                seen=(*report.recognized_names, self.live_tokens_var.get()),
                owned=self.owned_cards_var.get(),
                mode="add",
                limit=5,
            )
            hit_alerts = build_shop_hit_alerts(report, core_report.state, lineups=lineups)
            lineup_summary = "; ".join(item.lineup.name for item in core_report.recommendations[:3])
            shop_summary = ", ".join(report.recognized_names) if report.recognized_names else "No named shop cards"
            hit_summary = "; ".join(f"槽位{alert.slot} {alert.name}" for alert in hit_alerts[:3])
            chase_output = "四费/五费追三概率:\n- 未能稳定读取等级或金币；可用 CLI 的 chase 命令手动计算。"
            if detected_level is not None and detected_gold is not None:
                chase_output = format_chase_reports(
                    build_chase_reports_from_state(
                        core_report.state,
                        level=detected_level,
                        gold=detected_gold,
                        visible_counts=visible_counts_from_shop(report),
                    )
                )
            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self.last_lineups_var.set(lineup_summary or "-"))
            self.root.after(0, lambda: self.last_core_var.set(hit_summary or shop_summary))
            return (
                format_shop_scan(report)
                + "\n\n"
                + format_shop_hit_alerts(hit_alerts)
                + "\n\n"
                + chase_output
                + "\n\n"
                + format_core_advice(core_report)
            )

        self._run_task("Scanning shop", task)

    def reset_card_counts(self) -> None:
        def task() -> str:
            state_path = self._capture_dir() / "card_state.json"
            reset_card_state(state_path)
            self.root.after(0, lambda: self.last_core_var.set("Card counts reset"))
            return f"Card tracker reset: {state_path}"

        self._run_task("Resetting card counts", task)

    def open_capture_folder(self) -> None:
        capture_dir = self._capture_dir()
        capture_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(capture_dir))

    def _capture_dir(self) -> Path:
        capture_dir_text = self.capture_dir_var.get().strip()
        if not capture_dir_text:
            raise LDPlayerError("Please choose a capture folder first.")
        return Path(capture_dir_text)

    def _on_close(self) -> None:
        try:
            self._save_config()
        finally:
            self.root.destroy()

    def run(self) -> None:
        self.refresh_status()
        self.root.mainloop()
