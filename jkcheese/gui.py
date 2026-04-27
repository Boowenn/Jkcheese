from __future__ import annotations

import os
import re
import threading
import time
import tkinter as tk
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .advice import build_advice
from .card_tracker import build_core_advice, format_core_advice, load_card_state, reset_card_state
from .chase_calculator import build_chase_reports_from_state, format_chase_reports, visible_counts_from_shop
from .config import AppConfig
from .capture_cleanup import cleanup_capture_dir
from .economy import build_economy_rhythm, format_economy_rhythm
from .item_advice import build_item_advice, format_item_advice
from .ldplayer import GAME_PACKAGE, LDPlayerClient, LDPlayerError
from .lineups import fetch_jcc_s_lineups, recommend_lineups
from .ocr import OcrReading, read_screenshot
from .opponent_monitor import format_opponent_scout, scan_opponent
from .regions import default_preset
from .region_capture import crop_regions
from .shop_hits import build_shop_hit_alerts, format_shop_hit_alerts
from .shop_recognition import format_shop_scan, scan_shop as scan_shop_screenshot
from .version import __version__


PANEL_FONT = ("Microsoft YaHei UI", 10)
TITLE_FONT = ("Microsoft YaHei UI", 18, "bold")
SUBTITLE_FONT = ("Microsoft YaHei UI", 10)
CARD_BG = "#fffaf0"
ROOT_BG = "#efe6d2"
DARK_BG = "#17362f"
ACCENT = "#c77b2a"
MATCH_STAGE_RE = re.compile(r"^[1-9]\s*-\s*[1-9]$")
MATCH_END_CONFIRMATIONS = 2
TRANSPARENT_COLOR = "#ff00ff"
HIGHLIGHT_COLORS = {
    "critical": "#ff3b30",
    "high": "#ff9500",
    "medium": "#ffd60a",
    "info": "#30d5c8",
    "skip": "#9aa0a6",
}


@dataclass(frozen=True, slots=True)
class ScreenRect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ShopHighlight:
    slot: int
    name: str
    severity: str
    title: str
    box: tuple[int, int, int, int]


def _pulse_color(hex_color: str, factor: float) -> str:
    """Scale a hex color brightness by *factor* (0.0-1.0+), clamping to [0,255]."""
    hex_color = hex_color.lstrip("#")
    r = min(255, max(0, int(int(hex_color[0:2], 16) * factor)))
    g = min(255, max(0, int(int(hex_color[2:4], 16) * factor)))
    b = min(255, max(0, int(int(hex_color[4:6], 16) * factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def format_overlay_summary(
    *,
    shop_summary: str,
    lineup_summary: str,
    hit_summary: str,
    chase_summary: str,
    tempo_summary: str,
) -> str:
    lines = [
        f"商店: {shop_summary or '等待识别'}",
        f"必买: {hit_summary or '暂无'}",
        f"S/S-阵容: {lineup_summary or '等待匹配'}",
        f"追三: {chase_summary or '等待读数'}",
        f"节奏: {tempo_summary or '等待读数'}",
    ]
    return "\n".join(_shorten(line, 34) for line in lines)


def build_shop_highlights(alerts, source_size: tuple[int, int]) -> tuple[ShopHighlight, ...]:
    preset = default_preset()
    highlights: list[ShopHighlight] = []
    for alert in alerts:
        slot = int(alert.slot)
        if slot not in range(1, 6):
            continue
        box = preset.get(f"shop_slot_{slot}").box_for(source_size, preset.base_size)
        highlights.append(
            ShopHighlight(
                slot=slot,
                name=alert.name,
                severity=alert.severity,
                title=alert.title,
                box=box,
            )
        )
    return tuple(highlights)


def build_calibration_highlights(source_size: tuple[int, int]) -> tuple[ShopHighlight, ...]:
    preset = default_preset()
    highlights: list[ShopHighlight] = []
    for slot in range(1, 6):
        highlights.append(
            ShopHighlight(
                slot=slot,
                name=f"槽{slot}",
                severity="info",
                title="校准",
                box=preset.get(f"shop_slot_{slot}").box_for(source_size, preset.base_size),
            )
        )
    return tuple(highlights)


def map_capture_box_to_screen(
    box: tuple[int, int, int, int],
    source_size: tuple[int, int],
    target: ScreenRect,
) -> tuple[int, int, int, int]:
    source_width, source_height = source_size
    if source_width <= 0 or source_height <= 0:
        return (0, 0, 0, 0)
    scale_x = target.width / source_width
    scale_y = target.height / source_height
    left, top, right, bottom = box
    return (
        round(left * scale_x),
        round(top * scale_y),
        round(right * scale_x),
        round(bottom * scale_y),
    )


def choose_highlight_target_rect(
    auto_rect: ScreenRect | None,
    *,
    offset_x: int = 0,
    offset_y: int = 0,
) -> ScreenRect | None:
    if auto_rect is None:
        return None
    return ScreenRect(
        x=auto_rect.x + offset_x,
        y=auto_rect.y + offset_y,
        width=auto_rect.width,
        height=auto_rect.height,
    )


def overlay_geometry_for_position(
    screen_width: int,
    overlay_x: int | None,
    overlay_y: int | None,
    *,
    width: int = 340,
    height: int = 150,
) -> str:
    if overlay_x is not None and overlay_y is not None:
        return f"{width}x{height}+{overlay_x}+{overlay_y}"
    x = max(20, screen_width - width - 28)
    y = 72
    return f"{width}x{height}+{x}+{y}"


def _shorten(text: str, limit: int) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)] + "…"


def _first_detail_line(text: str, marker: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if marker in stripped:
            return stripped.lstrip("- ").strip()
    return ""


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def find_ldplayer_client_rect(preferred_title: str = "") -> ScreenRect | None:
    if os.name != "nt":
        return None

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    candidates: list[tuple[int, str]] = []

    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        title_lower = title.lower()
        preferred = preferred_title.strip().lower()
        is_preferred = bool(preferred and preferred != "-" and preferred in title_lower)
        is_ldplayer = any(token in title_lower for token in ("ldplayer", "雷电", "雷電", "leidian"))
        if (is_preferred or is_ldplayer) and "jkcheese" not in title_lower:
            candidates.append((int(hwnd), title))
        return True

    user32.EnumWindows(enum_windows_proc(callback), 0)
    if not candidates:
        return None

    hwnd = wintypes.HWND(candidates[0][0])
    client_rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
        return None
    point = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        return None

    width = max(0, client_rect.right - client_rect.left)
    height = max(0, client_rect.bottom - client_rect.top)
    if width <= 0 or height <= 0:
        return None
    return ScreenRect(x=point.x, y=point.y, width=width, height=height)


def _set_window_click_through(window: tk.Toplevel, enabled: bool) -> None:
    if os.name != "nt":
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = wintypes.HWND(window.winfo_id())
    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_long.argtypes = (wintypes.HWND, ctypes.c_int)
    get_long.restype = ctypes.c_ssize_t
    set_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    set_long.restype = ctypes.c_ssize_t

    gwl_exstyle = -20
    ws_ex_transparent = 0x00000020
    ws_ex_layered = 0x00080000
    ws_ex_toolwindow = 0x00000080
    ws_ex_noactivate = 0x08000000
    style = get_long(hwnd, gwl_exstyle)
    style |= ws_ex_layered | ws_ex_toolwindow
    if enabled:
        style |= ws_ex_transparent | ws_ex_noactivate
    else:
        style &= ~ws_ex_transparent
        style &= ~ws_ex_noactivate
    set_long(hwnd, gwl_exstyle, style)


def _make_window_click_through(window: tk.Toplevel) -> None:
    _set_window_click_through(window, True)


def _reading_value(readings, name: str) -> int | None:
    for reading in readings:
        if reading.name == name:
            return reading.value
    return None


def _reading_text(readings, name: str) -> str:
    for reading in readings:
        if reading.name == name:
            return reading.text
    return ""


def format_reading_summary(readings: list[OcrReading] | tuple[OcrReading, ...]) -> str:
    names = {"stage": "阶段", "level": "等级", "gold": "金币", "player_hp": "血量"}
    parts: list[str] = []
    for reading in readings:
        if reading.name not in names:
            continue
        value = reading.text or "?"
        parts.append(f"{names[reading.name]}={value}({reading.confidence:.2f})")
    return "  ".join(parts) if parts else "暂未读取"


def format_lineup_panel(core_report) -> str:
    lines = ["S/S- 阵容推荐"]
    if not core_report.recommendations:
        lines.append("- 暂无推荐，先扫描商店或点击 S/S- 阵容。")
        return "\n".join(lines)
    for index, item in enumerate(core_report.recommendations[:5], start=1):
        matched = f" | 命中: {', '.join(item.matched_tokens)}" if item.matched_tokens else ""
        notes = f" | 备注: {'; '.join(item.lineup.notes)}" if item.lineup.notes else ""
        lines.append(f"{index}. [{item.lineup.tier}] {item.lineup.name}  分数 {item.score}{matched}{notes}")
    return "\n".join(lines)


def format_star_panel(core_report, hit_alerts=()) -> str:
    lines = ["三星警告 / 商店必买"]
    if hit_alerts:
        lines.append("商店提醒:")
        for alert in hit_alerts[:5]:
            cost = f"{alert.cost}费" if alert.cost is not None else "费用未知"
            lines.append(f"- [{alert.severity}] 槽位{alert.slot} {alert.name}({cost})：{alert.title}")
    else:
        lines.append("商店提醒: 暂无必须买的关键牌。")

    if core_report.warnings:
        lines.append("")
        lines.append("已记录棋子:")
        for warning in core_report.warnings[:6]:
            related = f" | S/S- 阵容: {', '.join(warning.matched_lineups)}" if warning.matched_lineups else ""
            lines.append(f"- [{warning.severity}] {warning.title}{related}")
    else:
        lines.append("")
        lines.append("已记录棋子: 暂无 4/5 费三星追踪警告。")
    return "\n".join(lines)


class JkcheeseGui:
    def __init__(self) -> None:
        self.config = AppConfig.load()
        self.root = tk.Tk()
        self.root.title(f"金铲铲只读助手 Jkcheese v{__version__}")
        self.root.geometry(self._default_main_geometry())
        self.root.minsize(960, 620)
        self.root.configure(bg=ROOT_BG)

        self.ldplayer_root_var = tk.StringVar(value=self.config.ldplayer_root)
        self.instance_var = tk.StringVar(value=str(self.config.instance_index))
        self.capture_dir_var = tk.StringVar(value=self.config.capture_dir)
        self.status_var = tk.StringVar(value="准备就绪")
        self.instance_name_var = tk.StringVar(value="-")
        self.game_installed_var = tk.StringVar(value="-")
        self.game_process_var = tk.StringVar(value="-")
        self.apk_path_var = tk.StringVar(value="-")
        self.last_capture_var = tk.StringVar(value="-")
        self.last_regions_var = tk.StringVar(value="-")
        self.last_reading_var = tk.StringVar(value="暂未读取")
        self.last_advice_var = tk.StringVar(value="-")
        self.last_lineups_var = tk.StringVar(value="-")
        self.last_core_var = tk.StringVar(value="-")
        self.last_item_var = tk.StringVar(value="-")
        self.last_tempo_var = tk.StringVar(value="-")
        self.auto_scan_var = tk.BooleanVar(value=self.config.auto_scan_enabled)
        self.overlay_enabled_var = tk.BooleanVar(value=self.config.overlay_enabled)
        self.highlight_drag_var = tk.BooleanVar(value=self.config.highlight_drag_enabled)
        self.auto_scan_status_var = tk.StringVar(value="自动识别：等待启动")
        self.cleanup_status_var = tk.StringVar(value="自动清理：对局结束后清理本局截图")
        self.auto_shop_var = tk.StringVar(value="商店：等待识别")
        self.overlay_text_var = tk.StringVar(value="Jkcheese 实战悬浮\n等待自动识别商店。")
        self.live_tokens_var = tk.StringVar(value="")
        self.owned_cards_var = tk.StringVar(value="")
        self.item_components_var = tk.StringVar(value="")
        self.highlight_offset_x_var = tk.IntVar(value=self.config.highlight_offset_x)
        self.highlight_offset_y_var = tk.IntVar(value=self.config.highlight_offset_y)
        self.stage_value_var = tk.StringVar(value="?")
        self.level_value_var = tk.StringVar(value="?")
        self.gold_value_var = tk.StringVar(value="?")
        self.hp_value_var = tk.StringVar(value="?")
        self._busy = False
        self._auto_scan_running = False
        self._auto_scan_job: str | None = None
        self._last_match_active = False
        self._match_inactive_seen = 0
        self._closed = False
        self._preview_image = None
        self._overlay: tk.Toplevel | None = None
        self._overlay_drag: tuple[int, int] | None = None
        self._highlight_overlay: tk.Toplevel | None = None
        self._highlight_canvas: tk.Canvas | None = None
        self._highlight_drag: tuple[int, int] | None = None
        self._highlight_auto_rect: ScreenRect | None = None
        self._highlight_anim_phase: float = 0.0
        self._highlight_anim_job: str | None = None
        self._highlight_items: list[tuple] = []  # (slot_rect_ids, severity, left, top, right, bottom)
        self._panels: dict[str, tk.Text] = {}

        self._build_ui()
        self._build_overlay()
        self._build_shop_highlight_overlay()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(1000, self._schedule_auto_scan)

    def _default_main_geometry(self) -> str:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1220, max(960, screen_width - 80))
        height = min(720, max(620, screen_height - 120))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 3)
        return f"{width}x{height}+{x}+{y}"

    def _build_ui(self) -> None:
        self._configure_styles()
        self.root.columnconfigure(0, weight=0, minsize=390)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = tk.Frame(self.root, bg=DARK_BG, padx=20, pady=10)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="金铲铲只读助手",
            bg=DARK_BG,
            fg="#fff7e4",
            font=TITLE_FONT,
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="一键看清：截图状态、S/S- 阵容、三星警告、追三概率、装备主 C、当前节奏",
            bg=DARK_BG,
            fg="#d8e6dc",
            font=SUBTITLE_FONT,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.primary_button = tk.Button(
            header,
            text="一键扫描当前局势",
            command=self.scan_shop,
            bg=ACCENT,
            fg="white",
            activebackground="#ad651f",
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=8,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        self.primary_button.grid(row=0, column=1, rowspan=2, sticky="e")

        left = self._build_left_scroll_column()

        right = tk.Frame(self.root, bg="#f7f1e3", padx=12, pady=10)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        self._build_connection_card(left)
        self._build_snapshot_card(left)
        self._build_inputs_card(left)
        self._build_right_dashboard(right)

    def _build_left_scroll_column(self) -> tk.Frame:
        outer = tk.Frame(self.root, bg=ROOT_BG, padx=10, pady=10)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=ROOT_BG, highlightthickness=0, width=400)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        frame = tk.Frame(canvas, bg=ROOT_BG)
        frame.columnconfigure(0, weight=1)
        window_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        def update_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def update_window_width(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def on_mousewheel(event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        frame.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_window_width)
        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))
        return frame

    def _build_overlay(self) -> None:
        overlay = tk.Toplevel(self.root)
        overlay.title("Jkcheese 悬浮提示")
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.82)
        overlay.configure(bg="#14231f")
        overlay.geometry(self._default_overlay_geometry())
        overlay.configure(cursor="fleur")
        overlay.bind("<ButtonPress-1>", self._start_overlay_drag)
        overlay.bind("<B1-Motion>", self._drag_overlay)
        overlay.bind("<ButtonRelease-1>", self._finish_overlay_drag)

        header = tk.Label(
            overlay,
            text="Jkcheese 只读提醒 · 拖动移动",
            bg="#c77b2a",
            fg="white",
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=8,
            pady=3,
            cursor="fleur",
        )
        header.pack(fill="x")
        header.bind("<ButtonPress-1>", self._start_overlay_drag)
        header.bind("<B1-Motion>", self._drag_overlay)
        header.bind("<ButtonRelease-1>", self._finish_overlay_drag)

        label = tk.Label(
            overlay,
            textvariable=self.overlay_text_var,
            bg="#14231f",
            fg="#fff7e4",
            justify="left",
            anchor="nw",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=10,
            pady=8,
            cursor="fleur",
        )
        label.pack(fill="both", expand=True)
        label.bind("<ButtonPress-1>", self._start_overlay_drag)
        label.bind("<B1-Motion>", self._drag_overlay)
        label.bind("<ButtonRelease-1>", self._finish_overlay_drag)

        self._overlay = overlay
        self._on_overlay_toggled()

    def _build_shop_highlight_overlay(self) -> None:
        overlay = tk.Toplevel(self.root)
        overlay.title("Jkcheese 商店高亮")
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-transparentcolor", TRANSPARENT_COLOR)
        overlay.configure(bg=TRANSPARENT_COLOR)
        overlay.withdraw()

        canvas = tk.Canvas(
            overlay,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
        )
        canvas.pack(fill="both", expand=True)
        overlay.bind("<ButtonPress-1>", self._start_highlight_drag)
        overlay.bind("<B1-Motion>", self._drag_highlight)
        canvas.bind("<ButtonPress-1>", self._start_highlight_drag)
        canvas.bind("<B1-Motion>", self._drag_highlight)
        self._highlight_overlay = overlay
        self._highlight_canvas = canvas
        overlay.update_idletasks()
        _set_window_click_through(overlay, not self.highlight_drag_var.get())

    def _default_overlay_geometry(self) -> str:
        return overlay_geometry_for_position(
            self.root.winfo_screenwidth(),
            self.config.overlay_x,
            self.config.overlay_y,
        )

    def _start_overlay_drag(self, event) -> None:
        self._overlay_drag = (event.x_root, event.y_root)

    def _drag_overlay(self, event) -> None:
        if self._overlay is None or self._overlay_drag is None:
            return
        old_x, old_y = self._overlay_drag
        delta_x = event.x_root - old_x
        delta_y = event.y_root - old_y
        x = self._overlay.winfo_x() + delta_x
        y = self._overlay.winfo_y() + delta_y
        self._overlay.geometry(f"+{x}+{y}")
        self.config.overlay_x = x
        self.config.overlay_y = y
        self._overlay_drag = (event.x_root, event.y_root)

    def _finish_overlay_drag(self, _event=None) -> None:
        if self._overlay_drag is None:
            return
        self._overlay_drag = None
        self._save_config()

    def _start_highlight_drag(self, event) -> None:
        if not self.highlight_drag_var.get():
            return
        self._highlight_drag = (event.x_root, event.y_root)

    def _drag_highlight(self, event) -> None:
        if not self.highlight_drag_var.get() or self._highlight_overlay is None or self._highlight_drag is None:
            return
        old_x, old_y = self._highlight_drag
        delta_x = event.x_root - old_x
        delta_y = event.y_root - old_y
        x = self._highlight_overlay.winfo_x() + delta_x
        y = self._highlight_overlay.winfo_y() + delta_y
        width = self._highlight_overlay.winfo_width()
        height = self._highlight_overlay.winfo_height()
        self._highlight_overlay.geometry(f"+{x}+{y}")
        if self._highlight_auto_rect is not None:
            self.highlight_offset_x_var.set(x - self._highlight_auto_rect.x)
            self.highlight_offset_y_var.set(y - self._highlight_auto_rect.y)
            self._save_config()
        self._highlight_drag = (event.x_root, event.y_root)

    def _draw_shop_highlights(self, alerts, source_size: tuple[int, int], *, force_calibration: bool = False) -> None:
        if self._highlight_overlay is None or self._highlight_canvas is None:
            return
        if not self.overlay_enabled_var.get():
            self._hide_shop_highlights()
            return

        highlights = build_shop_highlights(alerts, source_size)
        if not highlights:
            if force_calibration or self.highlight_drag_var.get():
                highlights = build_calibration_highlights(source_size)
            else:
                self._hide_shop_highlights()
                return

        auto_rect = find_ldplayer_client_rect(self.instance_name_var.get())
        if auto_rect is None and (force_calibration or self.highlight_drag_var.get()):
            auto_rect = ScreenRect(x=80, y=80, width=960, height=540)
        self._highlight_auto_rect = auto_rect
        rect = choose_highlight_target_rect(
            auto_rect,
            offset_x=int(self.highlight_offset_x_var.get()),
            offset_y=int(self.highlight_offset_y_var.get()),
        )
        if rect is None:
            self._hide_shop_highlights()
            self.auto_scan_status_var.set("自动识别：已更新，未定位到雷电窗口")
            return

        overlay = self._highlight_overlay
        canvas = self._highlight_canvas
        overlay.geometry(f"{rect.width}x{rect.height}+{rect.x}+{rect.y}")
        canvas.configure(width=rect.width, height=rect.height)
        canvas.delete("all")

        self._highlight_items = []
        for highlight in highlights:
            left, top, right, bottom = map_capture_box_to_screen(highlight.box, source_size, rect)
            color = HIGHLIGHT_COLORS.get(highlight.severity, "#ffd60a")
            line_width = 6 if highlight.severity in {"critical", "high"} else 4
            rect_id = canvas.create_rectangle(
                left + 4,
                top + 4,
                right - 4,
                bottom - 4,
                outline=color,
                width=line_width,
                tags=("glow",),
            )
            self._highlight_items.append((rect_id, highlight.severity, left, top, right, bottom))
            label = f"买 {highlight.name}"
            label_x = left + 10
            label_y = max(8, top - 30)
            text_id = canvas.create_text(
                label_x,
                label_y,
                text=label,
                anchor="nw",
                fill="#ffffff",
                font=("Microsoft YaHei UI", 16, "bold"),
            )
            box = canvas.bbox(text_id)
            if box is not None:
                bg_id = canvas.create_rectangle(
                    box[0] - 8,
                    box[1] - 4,
                    box[2] + 8,
                    box[3] + 4,
                    fill=color,
                    outline=color,
                )
                canvas.tag_raise(text_id, bg_id)

        # 启动高亮呼吸动画
        self._start_highlight_animation()

        if self.highlight_drag_var.get() or force_calibration:
            canvas.create_rectangle(8, 8, 232, 36, fill="#17362f", outline="#ffd60a", width=2)
            canvas.create_text(
                18,
                15,
                text="拖动任意位置校准，调好后取消勾选",
                anchor="nw",
                fill="#fff7e4",
                font=("Microsoft YaHei UI", 10, "bold"),
            )

        overlay.deiconify()
        overlay.lift()
        overlay.attributes("-topmost", True)
        _set_window_click_through(overlay, not self.highlight_drag_var.get())

    def _hide_shop_highlights(self) -> None:
        self._stop_highlight_animation()
        self._highlight_items = []
        if self._highlight_canvas is not None:
            self._highlight_canvas.delete("all")
        if self._highlight_overlay is not None:
            self._highlight_overlay.withdraw()

    def _start_highlight_animation(self) -> None:
        """启动高亮边框呼吸脉冲动画（参考 JinChanChanTool 的渐变发光效果）。"""
        self._stop_highlight_animation()
        self._highlight_anim_phase = 0.0
        self._highlight_anim_tick()

    def _stop_highlight_animation(self) -> None:
        if self._highlight_anim_job is not None:
            self.root.after_cancel(self._highlight_anim_job)
            self._highlight_anim_job = None

    def _highlight_anim_tick(self) -> None:
        """每帧更新高亮边框亮度，产生呼吸脉冲效果。"""
        if self._closed or not self._highlight_items or self._highlight_canvas is None:
            return
        import math
        self._highlight_anim_phase += 0.12
        if self._highlight_anim_phase > 2 * math.pi:
            self._highlight_anim_phase -= 2 * math.pi
        # 脉冲因子 0.7 ~ 1.0
        pulse = 0.85 + 0.15 * math.sin(self._highlight_anim_phase)
        canvas = self._highlight_canvas
        for rect_id, severity, left, top, right, bottom in self._highlight_items:
            base_color = HIGHLIGHT_COLORS.get(severity, "#ffd60a")
            pulsed = _pulse_color(base_color, pulse)
            base_width = 6 if severity in {"critical", "high"} else 4
            pulsed_width = max(2, round(base_width * (0.8 + 0.4 * math.sin(self._highlight_anim_phase))))
            try:
                canvas.itemconfigure(rect_id, outline=pulsed, width=pulsed_width)
            except tk.TclError:
                pass
        self._highlight_anim_job = self.root.after(50, self._highlight_anim_tick)

    def show_highlight_calibration(self) -> None:
        self.highlight_drag_var.set(True)
        self._on_highlight_drag_toggled()
        self._draw_shop_highlights((), default_preset().base_size, force_calibration=True)

    def reset_overlay_position(self) -> None:
        self.config.overlay_x = None
        self.config.overlay_y = None
        if self._overlay is not None:
            self._overlay.geometry(self._default_overlay_geometry())
            if self.overlay_enabled_var.get():
                self._overlay.deiconify()
                self._overlay.lift()
                self._overlay.attributes("-topmost", True)
        self._save_config()

    def _on_overlay_toggled(self) -> None:
        if self._overlay is None:
            return
        if self.overlay_enabled_var.get():
            self._overlay.deiconify()
            self._overlay.attributes("-topmost", True)
        else:
            self._overlay.withdraw()
            self._hide_shop_highlights()
        self._save_config()

    def _on_highlight_drag_toggled(self) -> None:
        enabled = self.highlight_drag_var.get()
        if self._highlight_overlay is not None:
            _set_window_click_through(self._highlight_overlay, not enabled)
        if enabled:
            self.auto_scan_status_var.set("高亮框校准：可自由拖动，调完请取消勾选")
            self._draw_shop_highlights((), default_preset().base_size, force_calibration=True)
        else:
            self.auto_scan_status_var.set("高亮框校准：已记住偏移并点击穿透")
        self._save_config()

    def _on_auto_settings_changed(self) -> None:
        enabled = self.auto_scan_var.get()
        self.auto_scan_status_var.set("自动识别：已开启" if enabled else "自动识别：已暂停")
        self._save_config()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TLabel", font=PANEL_FONT, background=CARD_BG, foreground="#26352f")
        style.configure("TButton", font=PANEL_FONT, padding=6)
        style.configure("TEntry", font=PANEL_FONT)
        style.configure("TSpinbox", font=PANEL_FONT)

    def _card(self, parent: tk.Widget, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=ROOT_BG)
        outer.grid(sticky="ew", pady=(0, 12))
        outer.columnconfigure(0, weight=1)
        tk.Label(
            outer,
            text=title,
            bg=ROOT_BG,
            fg="#1c332d",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        card = tk.Frame(outer, bg=CARD_BG, padx=12, pady=12, highlightbackground="#dfc9a5", highlightthickness=1)
        card.grid(row=1, column=0, sticky="ew")
        card.columnconfigure(1, weight=1)
        return card

    def _build_connection_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "连接与路径")
        tk.Label(card, text="雷电目录", bg=CARD_BG, font=PANEL_FONT).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(card, textvariable=self.ldplayer_root_var).grid(row=0, column=1, sticky="ew", pady=3, padx=(8, 4))
        ttk.Button(card, text="选择", command=self._pick_ldplayer_root).grid(row=0, column=2, pady=3)

        tk.Label(card, text="实例编号", bg=CARD_BG, font=PANEL_FONT).grid(row=1, column=0, sticky="w", pady=3)
        ttk.Spinbox(card, from_=0, to=32, textvariable=self.instance_var, width=8).grid(
            row=1, column=1, sticky="w", pady=3, padx=(8, 4)
        )

        tk.Label(card, text="截图目录", bg=CARD_BG, font=PANEL_FONT).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(card, textvariable=self.capture_dir_var).grid(row=2, column=1, sticky="ew", pady=3, padx=(8, 4))
        ttk.Button(card, text="选择", command=self._pick_capture_dir).grid(row=2, column=2, pady=3)

        button_bar = tk.Frame(card, bg=CARD_BG)
        button_bar.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        for col in range(3):
            button_bar.columnconfigure(col, weight=1)
        self.refresh_button = ttk.Button(button_bar, text="刷新状态", command=self.refresh_status)
        self.launch_button = ttk.Button(button_bar, text="启动模拟器", command=self.launch_instance)
        self.run_game_button = ttk.Button(button_bar, text="启动游戏", command=self.launch_game)
        self.refresh_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.launch_button.grid(row=0, column=1, sticky="ew", padx=4)
        self.run_game_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        self.open_folder_button = ttk.Button(card, text="打开截图目录", command=self.open_capture_folder)
        self.open_folder_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        auto_bar = tk.Frame(card, bg=CARD_BG)
        auto_bar.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        auto_bar.columnconfigure(0, weight=1)
        auto_bar.columnconfigure(1, weight=1)
        auto_bar.columnconfigure(2, weight=1)
        auto_bar.columnconfigure(3, weight=1)
        self.auto_scan_check = ttk.Checkbutton(
            auto_bar,
            text="自动识别商店",
            variable=self.auto_scan_var,
            command=self._on_auto_settings_changed,
        )
        self.overlay_check = ttk.Checkbutton(
            auto_bar,
            text="显示悬浮窗",
            variable=self.overlay_enabled_var,
            command=self._on_overlay_toggled,
        )
        self.highlight_drag_check = ttk.Checkbutton(
            auto_bar,
            text="自由拖高亮框",
            variable=self.highlight_drag_var,
            command=self._on_highlight_drag_toggled,
        )
        self.highlight_preview_button = ttk.Button(auto_bar, text="显示校准框", command=self.show_highlight_calibration)
        self.overlay_reset_button = ttk.Button(auto_bar, text="重置位置", command=self.reset_overlay_position)
        self.auto_scan_check.grid(row=0, column=0, sticky="w")
        self.overlay_check.grid(row=0, column=1, sticky="w")
        self.overlay_reset_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self.highlight_drag_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.highlight_preview_button.grid(row=1, column=2, sticky="ew", padx=(6, 0), pady=(4, 0))

        status = tk.Frame(card, bg="#f0e6d2", padx=8, pady=8)
        status.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        status.columnconfigure(1, weight=1)
        self._status_line(status, 0, "状态", self.status_var)
        self._status_line(status, 1, "模拟器", self.instance_name_var)
        self._status_line(status, 2, "游戏", self.game_process_var)
        self._status_line(status, 3, "APK", self.apk_path_var)
        self._status_line(status, 4, "自动", self.auto_scan_status_var)
        self._status_line(status, 5, "清理", self.cleanup_status_var)

    def _build_snapshot_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "截图状态")
        self.preview_label = tk.Label(
            card,
            text="还没有截图\n点击“一键扫描当前局势”",
            bg="#1f2d2a",
            fg="#f8edd7",
            width=40,
            height=10,
            font=("Microsoft YaHei UI", 11),
        )
        self.preview_label.grid(row=0, column=0, columnspan=4, sticky="ew")

        metrics = tk.Frame(card, bg=CARD_BG)
        metrics.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        for col in range(4):
            metrics.columnconfigure(col, weight=1)
        self._metric(metrics, 0, "阶段", self.stage_value_var)
        self._metric(metrics, 1, "等级", self.level_value_var)
        self._metric(metrics, 2, "金币", self.gold_value_var)
        self._metric(metrics, 3, "血量", self.hp_value_var)

        self.capture_button = ttk.Button(card, text="只截图", command=self.capture_screenshot)
        self.read_button = ttk.Button(card, text="读取数字", command=self.capture_readings)
        self.tempo_button = ttk.Button(card, text="节奏建议", command=self.capture_tempo_advice)
        self.capture_regions_button = ttk.Button(card, text="导出区域", command=self.capture_regions)
        self.capture_button.grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=(10, 0))
        self.read_button.grid(row=2, column=1, sticky="ew", padx=4, pady=(10, 0))
        self.tempo_button.grid(row=2, column=2, sticky="ew", padx=4, pady=(10, 0))
        self.capture_regions_button.grid(row=2, column=3, sticky="ew", padx=(4, 0), pady=(10, 0))

    def _build_inputs_card(self, parent: tk.Widget) -> None:
        card = self._card(parent, "自动识别 / 高级兜底")
        tk.Label(card, textvariable=self.auto_shop_var, bg=CARD_BG, fg="#17362f", font=PANEL_FONT).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        tk.Label(
            card,
            text="主流程会自动截图识别商店、读阶段/金币，并把结果喂给 S/S- 阵容、三星警告和追三概率。",
            bg=CARD_BG,
            fg="#6b5a43",
            font=("Microsoft YaHei UI", 9),
            wraplength=380,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        tk.Label(card, text="额外羁绊", bg=CARD_BG, font=PANEL_FONT).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(card, textvariable=self.live_tokens_var).grid(row=2, column=1, sticky="ew", pady=3, padx=(8, 0))
        tk.Label(card, text="手动拥有", bg=CARD_BG, font=PANEL_FONT).grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(card, textvariable=self.owned_cards_var).grid(row=3, column=1, sticky="ew", pady=3, padx=(8, 0))
        tk.Label(card, text="装备散件", bg=CARD_BG, font=PANEL_FONT).grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(card, textvariable=self.item_components_var).grid(row=4, column=1, sticky="ew", pady=3, padx=(8, 0))

        buttons = tk.Frame(card, bg=CARD_BG)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        for col in range(2):
            buttons.columnconfigure(col, weight=1)
        self.core_button = ttk.Button(buttons, text="刷新阵容/三星", command=self.get_core_advice)
        self.shop_scan_button = ttk.Button(buttons, text="扫描商店", command=self.scan_shop)
        self.item_button = ttk.Button(buttons, text="装备主 C", command=self.get_item_advice)
        self.scout_button = ttk.Button(buttons, text="侦查对手", command=self.scout_opponent)
        self.reset_cards_button = ttk.Button(buttons, text="重置棋子计数", command=self.reset_card_counts)
        self.lineups_button = ttk.Button(buttons, text="查看 S/S- 阵容", command=self.fetch_s_lineups)
        self.core_button.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=3)
        self.shop_scan_button.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=3)
        self.item_button.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=3)
        self.scout_button.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=3)
        self.reset_cards_button.grid(row=2, column=0, sticky="ew", padx=(0, 4), pady=3)
        self.lineups_button.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=3)

        tk.Label(
            card,
            text="兜底例：手动拥有 4费千珏x7；散件 大剑 眼泪 拳套。工具只读截图，只提示买哪张，不会替你点游戏。",
            bg=CARD_BG,
            fg="#6b5a43",
            font=("Microsoft YaHei UI", 9),
            wraplength=370,
            justify="left",
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_right_dashboard(self, parent: tk.Widget) -> None:
        self._panel(parent, "current", "当前建议", row=0, column=0, columnspan=2, height=5)
        self._panel(parent, "lineups", "S/S- 阵容推荐", row=1, column=0, height=6)
        self._panel(parent, "stars", "三星警告 / 商店必买", row=1, column=1, height=6)
        self._panel(parent, "chase", "追三概率", row=2, column=0, height=5)
        self._panel(parent, "items", "装备和主 C", row=2, column=1, height=5)
        self._panel(parent, "log", "运行日志 / 详细结果", row=3, column=0, columnspan=2, height=5)

        self._set_panel("current", "点击“一键扫描当前局势”，这里会显示该升人口、存钱、小 D 还是 all in。")
        self._set_panel("lineups", "等待扫描。")
        self._set_panel("stars", "等待扫描。")
        self._set_panel("chase", "等待扫描。")
        self._set_panel("items", "等待扫描。")
        self._set_panel("log", "准备就绪。")

    def _panel(self, parent: tk.Widget, key: str, title: str, *, row: int, column: int, height: int, columnspan: int = 1) -> None:
        frame = tk.Frame(parent, bg="#f7f1e3")
        frame.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=6, pady=6)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        tk.Label(
            frame,
            text=title,
            bg="#f7f1e3",
            fg="#17362f",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        text = tk.Text(
            frame,
            height=height,
            wrap="word",
            bg="#fffdf7",
            fg="#23312d",
            relief="flat",
            padx=10,
            pady=8,
            font=PANEL_FONT,
            state="disabled",
        )
        text.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        text.configure(yscrollcommand=scrollbar.set)
        self._panels[key] = text

    def _metric(self, parent: tk.Widget, column: int, label: str, variable: tk.StringVar) -> None:
        box = tk.Frame(parent, bg="#f0e0c2", padx=8, pady=6)
        box.grid(row=0, column=column, sticky="ew", padx=3)
        tk.Label(box, text=label, bg="#f0e0c2", fg="#6d5432", font=("Microsoft YaHei UI", 9)).pack()
        tk.Label(box, textvariable=variable, bg="#f0e0c2", fg="#17362f", font=("Microsoft YaHei UI", 15, "bold")).pack()

    def _status_line(self, parent: tk.Widget, row: int, label: str, variable: tk.StringVar) -> None:
        tk.Label(parent, text=label, bg="#f0e6d2", fg="#6d5432", font=("Microsoft YaHei UI", 9)).grid(
            row=row, column=0, sticky="nw", padx=(0, 8), pady=1
        )
        tk.Label(parent, textvariable=variable, bg="#f0e6d2", fg="#26352f", font=("Microsoft YaHei UI", 9)).grid(
            row=row, column=1, sticky="nw", pady=1
        )

    def _pick_ldplayer_root(self) -> None:
        selected = filedialog.askdirectory(title="选择雷电模拟器目录")
        if selected:
            self.ldplayer_root_var.set(selected)

    def _pick_capture_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择截图目录")
        if selected:
            self.capture_dir_var.set(selected)

    def _save_config(self) -> None:
        self.config.ldplayer_root = self.ldplayer_root_var.get().strip()
        self.config.instance_index = self._current_index()
        self.config.capture_dir = self.capture_dir_var.get().strip()
        self.config.auto_scan_enabled = self.auto_scan_var.get()
        self.config.overlay_enabled = self.overlay_enabled_var.get()
        self.config.highlight_drag_enabled = self.highlight_drag_var.get()
        self.config.highlight_offset_x = int(self.highlight_offset_x_var.get())
        self.config.highlight_offset_y = int(self.highlight_offset_y_var.get())
        self.config.save()

    def _current_index(self) -> int:
        value = self.instance_var.get().strip() or "0"
        return int(value)

    def _client(self) -> LDPlayerClient:
        root = self.ldplayer_root_var.get().strip()
        if not root:
            raise LDPlayerError("请先选择雷电模拟器目录。")
        return LDPlayerClient(Path(root))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for button in (
            self.primary_button,
            self.refresh_button,
            self.launch_button,
            self.run_game_button,
            self.capture_button,
            self.capture_regions_button,
            self.read_button,
            self.tempo_button,
            self.lineups_button,
            self.core_button,
            self.shop_scan_button,
            self.scout_button,
            self.item_button,
            self.reset_cards_button,
            self.open_folder_button,
            self.auto_scan_check,
            self.overlay_check,
            self.overlay_reset_button,
            self.highlight_drag_check,
            self.highlight_preview_button,
        ):
            button.configure(state=state)

    def _set_panel(self, key: str, message: str) -> None:
        panel = self._panels[key]
        panel.configure(state="normal")
        panel.delete("1.0", "end")
        panel.insert("end", message)
        panel.configure(state="disabled")

    def _queue_panel(self, key: str, message: str) -> None:
        self.root.after(0, lambda: self._set_panel(key, message))

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        panel = self._panels.get("log")
        if panel is not None:
            panel.configure(state="normal")
            panel.insert("end", f"[{timestamp}] {message}\n")
            panel.see("end")
            panel.configure(state="disabled")

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
        self.status_var.set("准备就绪")
        if result:
            self._log(str(result))

    def _task_failed(self, label: str, exc: Exception) -> None:
        self._set_busy(False)
        self.status_var.set("出错")
        self._log(f"{label} 失败: {exc}")
        messagebox.showerror("Jkcheese", str(exc))

    def _show_preview(self, path: Path) -> None:
        try:
            image = Image.open(path).convert("RGB")
            image.thumbnail((390, 220), Image.Resampling.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(image)
        except OSError:
            return
        self.preview_label.configure(image=self._preview_image, text="", width=390, height=220)

    def _update_reading_widgets(self, readings: list[OcrReading]) -> None:
        self.stage_value_var.set(_reading_text(readings, "stage") or "?")
        level = _reading_value(readings, "level")
        gold = _reading_value(readings, "gold")
        hp = _reading_value(readings, "player_hp")
        self.level_value_var.set("?" if level is None else str(level))
        self.gold_value_var.set("?" if gold is None else str(gold))
        self.hp_value_var.set("?" if hp is None else str(hp))
        self.last_reading_var.set(format_reading_summary(readings))

    def _capture_dir(self) -> Path:
        capture_dir_text = self.capture_dir_var.get().strip()
        if not capture_dir_text:
            raise LDPlayerError("请先选择截图目录。")
        return Path(capture_dir_text)

    def _cleanup_old_captures(self, capture_dir: Path) -> None:
        report = cleanup_capture_dir(
            capture_dir,
            max_sessions=self.config.capture_retention_sessions,
            max_age_days=self.config.capture_retention_days,
        )
        if report.deleted_count:
            message = f"自动清理：删掉 {report.deleted_count} 个旧截图，保留 {report.kept_count} 个。"
        else:
            message = f"自动清理：已开启，保留最近 {report.kept_count} 个。"
        self.root.after(0, lambda: self.cleanup_status_var.set(message))

    def _cleanup_finished_match(self, capture_dir: Path) -> str:
        report = cleanup_capture_dir(capture_dir, max_sessions=0, max_age_days=0)
        reset_card_state(capture_dir / "card_state.json")
        message = f"检测到对局结束，已清理本局截图 {report.deleted_count} 个，并重置本局棋子计数。"
        self.root.after(0, lambda: self.cleanup_status_var.set(message))
        self.root.after(0, lambda: self.auto_shop_var.set("商店：等待下一局"))
        self.root.after(0, lambda: self.overlay_text_var.set("Jkcheese 实战悬浮\n对局已结束，截图已自动清理。\n等待下一局商店识别。"))
        self.root.after(0, self._hide_shop_highlights)
        return message

    def _handle_match_state(self, readings: list[OcrReading], capture_dir: Path) -> str:
        stage = _reading_text(readings, "stage").strip()
        match_active = bool(MATCH_STAGE_RE.match(stage))
        if match_active:
            self._last_match_active = True
            self._match_inactive_seen = 0
            return ""

        if not self._last_match_active:
            return ""

        self._match_inactive_seen += 1
        if self._match_inactive_seen < MATCH_END_CONFIRMATIONS:
            return "疑似对局结束，等待下一次截图确认后自动清理。"

        self._last_match_active = False
        self._match_inactive_seen = 0
        return self._cleanup_finished_match(capture_dir)

    def _auto_scan_paths(self, capture_dir: Path, *, auto: bool) -> tuple[Path, Path]:
        if auto:
            session_dir = capture_dir / "_live"
        else:
            session_dir = capture_dir / time.strftime("dashboard_%Y%m%d_%H%M%S")
        return session_dir, session_dir / "screen.png"

    def _overlay_summary_from_scan(
        self,
        *,
        shop_summary: str,
        core_report,
        hit_alerts,
        chase_output: str,
        rhythm_report,
    ) -> str:
        lineup_summary = "; ".join(item.lineup.name for item in core_report.recommendations[:2])
        if hit_alerts:
            hit_summary = "; ".join(f"槽{alert.slot}买{alert.name}" for alert in hit_alerts[:3])
        else:
            hit_summary = "暂无必买"
        chase_summary = _first_detail_line(chase_output, "结论") or _first_detail_line(chase_output, "暂无") or ""
        tempo_summary = "; ".join(item.title for item in rhythm_report.advice[:2])
        return format_overlay_summary(
            shop_summary=shop_summary,
            lineup_summary=lineup_summary,
            hit_summary=hit_summary,
            chase_summary=chase_summary,
            tempo_summary=tempo_summary,
        )

    def _schedule_auto_scan(self) -> None:
        if self._closed:
            return
        if self.auto_scan_var.get():
            self._start_auto_scan()
        interval_ms = max(5, self.config.auto_scan_interval_seconds) * 1000
        self._auto_scan_job = self.root.after(interval_ms, self._schedule_auto_scan)

    def _start_auto_scan(self) -> None:
        if self._busy or self._auto_scan_running:
            return
        self._auto_scan_running = True
        self.auto_scan_status_var.set("自动识别：扫描中")

        def worker() -> None:
            try:
                result = self._scan_current_state(auto=True)
            except Exception as exc:
                self.root.after(0, lambda: self._auto_scan_failed(exc))
            else:
                self.root.after(0, lambda: self._auto_scan_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _auto_scan_done(self, result: str) -> None:
        self._auto_scan_running = False
        self.auto_scan_status_var.set("自动识别：已更新")
        if result:
            self._log(result)

    def _auto_scan_failed(self, exc: Exception) -> None:
        self._auto_scan_running = False
        self.auto_scan_status_var.set("自动识别：等待游戏画面")
        self._log(f"自动识别跳过: {exc}")

    def refresh_status(self) -> None:
        def task() -> str:
            client = self._client()
            instance = client.get_instance(self._current_index())
            self.root.after(0, lambda: self.instance_name_var.set(instance.name))
            self.root.after(0, lambda: self.game_installed_var.set("已安装" if instance.has_game else "未检测到"))

            if not instance.has_game:
                self.root.after(0, lambda: self.game_process_var.set("-"))
                self.root.after(0, lambda: self.apk_path_var.set("-"))
                return f"实例 {instance.index} 可用，但未检测到金铲铲。"

            if not instance.running:
                self.root.after(0, lambda: self.game_process_var.set("模拟器未启动"))
                self.root.after(0, lambda: self.apk_path_var.set("-"))
                return f"实例 {instance.index} 未启动。"

            game_running = client.is_package_running(instance.index, GAME_PACKAGE)
            apk_path = client.resolve_package_path(instance.index, GAME_PACKAGE) or "-"
            self.root.after(0, lambda: self.game_process_var.set("运行中" if game_running else "未运行"))
            self.root.after(0, lambda: self.apk_path_var.set(apk_path))
            return f"已刷新实例 {instance.index}。"

        self._run_task("刷新状态", task)

    def launch_instance(self) -> None:
        def task() -> str:
            client = self._client()
            index = self._current_index()
            client.launch(index)
            client.wait_for_running(index)
            return f"实例 {index} 已启动。"

        self._run_task("启动模拟器", task)

    def launch_game(self) -> None:
        def task() -> str:
            client = self._client()
            index = self._current_index()
            if not client.is_running(index):
                client.launch(index)
                client.wait_for_running(index)
            client.wait_for_boot(index)
            client.run_app(index, GAME_PACKAGE)
            return f"已发送启动金铲铲命令到实例 {index}。"

        self._run_task("启动游戏", task)

    def capture_screenshot(self) -> None:
        def task() -> str:
            client = self._client()
            capture_dir = self._capture_dir()
            output = capture_dir / f"jkcheese_{time.strftime('%Y%m%d_%H%M%S')}.png"
            saved = client.capture_screenshot(self._current_index(), output, launch_if_needed=True)
            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self._show_preview(saved))
            self._cleanup_old_captures(capture_dir)
            return f"截图已保存：{saved}"

        self._run_task("截图", task)

    def capture_regions(self) -> None:
        def task() -> str:
            client = self._client()
            capture_dir = self._capture_dir()
            session_dir = capture_dir / time.strftime("regions_%Y%m%d_%H%M%S")
            screenshot_path = session_dir / "screen.png"
            saved = client.capture_screenshot(self._current_index(), screenshot_path, launch_if_needed=True)
            region_dir = session_dir / "regions"
            results = crop_regions(saved, region_dir)
            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self.last_regions_var.set(str(region_dir)))
            self.root.after(0, lambda: self._show_preview(saved))
            self._cleanup_old_captures(capture_dir)
            return f"已导出 {len(results)} 个区域到 {region_dir}"

        self._run_task("导出区域", task)

    def capture_readings(self) -> None:
        def task() -> str:
            client = self._client()
            capture_dir = self._capture_dir()
            session_dir = capture_dir / time.strftime("read_%Y%m%d_%H%M%S")
            screenshot_path = session_dir / "screen.png"
            saved = client.capture_screenshot(self._current_index(), screenshot_path, launch_if_needed=True)
            readings = read_screenshot(saved)
            summary = format_reading_summary(readings)
            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self._show_preview(saved))
            self.root.after(0, lambda: self._update_reading_widgets(readings))
            self._queue_panel("current", f"读数已更新：\n{summary}")
            self._cleanup_old_captures(capture_dir)
            return "读数已更新。"

        self._run_task("读取数字", task)

    def capture_advice(self) -> None:
        def task() -> str:
            client = self._client()
            capture_dir = self._capture_dir()
            session_dir = capture_dir / time.strftime("advice_%Y%m%d_%H%M%S")
            screenshot_path = session_dir / "screen.png"
            saved = client.capture_screenshot(self._current_index(), screenshot_path, launch_if_needed=True)
            report = build_advice(read_screenshot(saved))
            reading_summary = format_reading_summary(report.readings)
            advice_lines = [f"- [{item.severity}] {item.title}: {item.detail}" for item in report.advice]
            rhythm_text = format_economy_rhythm(report.rhythm) if report.rhythm is not None else ""
            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self._show_preview(saved))
            self.root.after(0, lambda: self._update_reading_widgets(list(report.readings)))
            self.root.after(0, lambda: self.last_advice_var.set("; ".join(item.title for item in report.advice) or "-"))
            self._queue_panel("current", f"截图读数：{reading_summary}\n\n" + "\n".join(advice_lines) + "\n\n" + rhythm_text)
            self._cleanup_old_captures(capture_dir)
            return "当前建议已刷新。"

        self._run_task("刷新当前建议", task)

    def capture_tempo_advice(self) -> None:
        def task() -> str:
            client = self._client()
            capture_dir = self._capture_dir()
            session_dir = capture_dir / time.strftime("tempo_%Y%m%d_%H%M%S")
            screenshot_path = session_dir / "screen.png"
            saved = client.capture_screenshot(self._current_index(), screenshot_path, launch_if_needed=True)
            readings = read_screenshot(saved)
            report = build_economy_rhythm(
                stage=_reading_text(readings, "stage"),
                level=_reading_value(readings, "level"),
                gold=_reading_value(readings, "gold"),
                hp=_reading_value(readings, "player_hp"),
            )
            tempo_summary = "; ".join(item.title for item in report.advice[:2])
            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self._show_preview(saved))
            self.root.after(0, lambda: self._update_reading_widgets(readings))
            self.root.after(0, lambda: self.last_tempo_var.set(tempo_summary or "-"))
            self._queue_panel("current", format_economy_rhythm(report))
            self._cleanup_old_captures(capture_dir)
            return "节奏建议已刷新。"

        self._run_task("节奏建议", task)

    def fetch_s_lineups(self) -> None:
        def task() -> str:
            lineups = fetch_jcc_s_lineups()
            recommendations = recommend_lineups(lineups, limit=5)
            summary = "; ".join(item.lineup.name for item in recommendations)
            lines = ["S/S- 阵容推荐"]
            for index, item in enumerate(recommendations, start=1):
                notes = f" | 备注: {'; '.join(item.lineup.notes)}" if item.lineup.notes else ""
                lines.append(f"{index}. {item.lineup.name}{notes}")
            self.root.after(0, lambda: self.last_lineups_var.set(summary))
            self._queue_panel("lineups", "\n".join(lines))
            return "S/S- 阵容已刷新。"

        self._run_task("获取 S/S- 阵容", task)

    def get_core_advice(self) -> None:
        def task() -> str:
            capture_dir = self._capture_dir()
            lineups = fetch_jcc_s_lineups()
            report = build_core_advice(
                state_path=capture_dir / "card_state.json",
                lineups=lineups,
                seen=self.live_tokens_var.get(),
                owned=self.owned_cards_var.get(),
                mode="add",
                limit=5,
            )
            item_report = build_item_advice(
                report.recommendations,
                state=report.state,
                seen_tokens=report.seen_tokens,
                item_components=self.item_components_var.get(),
                limit=3,
            )
            warning_summary = "; ".join(warning.title for warning in report.warnings[:3]) or "暂无三星警告"
            lineup_summary = "; ".join(item.lineup.name for item in report.recommendations[:3])
            item_summary = "; ".join(f"{plan.lineup_name}: {plan.main_carry}" for plan in item_report.plans[:2]) or "-"
            self.root.after(0, lambda: self.last_core_var.set(warning_summary))
            self.root.after(0, lambda: self.last_lineups_var.set(lineup_summary or "-"))
            self.root.after(0, lambda: self.last_item_var.set(item_summary))
            self.root.after(0, lambda: self.owned_cards_var.set(""))
            self._queue_panel("lineups", format_lineup_panel(report))
            self._queue_panel("stars", format_star_panel(report))
            self._queue_panel("items", format_item_advice(item_report))
            self._queue_panel("log", format_core_advice(report))
            return "阵容和三星警告已刷新。"

        self._run_task("阵容 / 三星", task)

    def get_item_advice(self) -> None:
        def task() -> str:
            capture_dir = self._capture_dir()
            lineups = fetch_jcc_s_lineups()
            core_report = build_core_advice(
                state_path=capture_dir / "card_state.json",
                lineups=lineups,
                seen=self.live_tokens_var.get(),
                owned=self.owned_cards_var.get(),
                mode="add",
                limit=5,
            )
            item_report = build_item_advice(
                core_report.recommendations,
                state=core_report.state,
                seen_tokens=core_report.seen_tokens,
                item_components=self.item_components_var.get(),
                limit=3,
            )
            item_summary = "; ".join(f"{plan.lineup_name}: {plan.main_carry}" for plan in item_report.plans[:2]) or "-"
            self.root.after(0, lambda: self.last_item_var.set(item_summary))
            self.root.after(0, lambda: self.owned_cards_var.set(""))
            self._queue_panel("items", format_item_advice(item_report))
            self._queue_panel("lineups", format_lineup_panel(core_report))
            return "装备和主 C 已刷新。"

        self._run_task("装备 / 主 C", task)

    def _scan_current_state(self, *, auto: bool) -> str:
        client = self._client()
        capture_dir = self._capture_dir()
        session_dir, screenshot_path = self._auto_scan_paths(capture_dir, auto=auto)
        saved = client.capture_screenshot(self._current_index(), screenshot_path, launch_if_needed=not auto)
        source_size = _image_size(saved)
        shop_report = scan_shop_screenshot(
            saved,
            output_dir=session_dir / "shop",
            templates_path=capture_dir / "shop_templates.json",
            champions_path=capture_dir / "champions.json",
        )
        readings = read_screenshot(saved)
        match_message = self._handle_match_state(readings, capture_dir)
        if match_message:
            return match_message

        detected_level = _reading_value(readings, "level")
        detected_gold = _reading_value(readings, "gold")
        rhythm_report = build_economy_rhythm(
            stage=_reading_text(readings, "stage"),
            level=detected_level,
            gold=detected_gold,
            hp=_reading_value(readings, "player_hp"),
        )
        lineups = fetch_jcc_s_lineups()
        core_report = build_core_advice(
            state_path=capture_dir / "card_state.json",
            lineups=lineups,
            seen=(*shop_report.recognized_names, self.live_tokens_var.get()),
            owned=self.owned_cards_var.get(),
            mode="add",
            limit=5,
        )
        hit_alerts = build_shop_hit_alerts(shop_report, core_report.state, lineups=lineups)
        item_report = build_item_advice(
            core_report.recommendations,
            state=core_report.state,
            shop_names=shop_report.recognized_names,
            seen_tokens=core_report.seen_tokens,
            item_components=self.item_components_var.get(),
            limit=3,
        )
        if detected_level is not None and detected_gold is not None:
            chase_output = format_chase_reports(
                build_chase_reports_from_state(
                    core_report.state,
                    level=detected_level,
                    gold=detected_gold,
                    visible_counts=visible_counts_from_shop(shop_report),
                )
            )
        else:
            chase_output = "四费/五费追三概率:\n- 等级或金币没读稳，先等下一次自动识别。"

        reading_summary = format_reading_summary(readings)
        shop_summary = ", ".join(shop_report.recognized_names) if shop_report.recognized_names else "未识别到商店牌名"
        lineup_summary = "; ".join(item.lineup.name for item in core_report.recommendations[:3]) or "-"
        hit_summary = "; ".join(f"槽位{alert.slot} {alert.name}" for alert in hit_alerts[:3]) or shop_summary
        item_summary = "; ".join(f"{plan.lineup_name}: {plan.main_carry}" for plan in item_report.plans[:2]) or "-"
        tempo_summary = "; ".join(item.title for item in rhythm_report.advice[:2]) or "-"
        overlay_summary = self._overlay_summary_from_scan(
            shop_summary=shop_summary,
            core_report=core_report,
            hit_alerts=hit_alerts,
            chase_output=chase_output,
            rhythm_report=rhythm_report,
        )

        self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
        self.root.after(0, lambda: self._show_preview(saved))
        self.root.after(0, lambda: self._update_reading_widgets(readings))
        self.root.after(0, lambda: self.last_lineups_var.set(lineup_summary))
        self.root.after(0, lambda: self.last_core_var.set(hit_summary))
        self.root.after(0, lambda: self.last_item_var.set(item_summary))
        self.root.after(0, lambda: self.last_tempo_var.set(tempo_summary))
        self.root.after(0, lambda: self.auto_shop_var.set(f"商店：{shop_summary}"))
        self.root.after(0, lambda: self.overlay_text_var.set(overlay_summary))
        self.root.after(0, lambda: self._draw_shop_highlights(hit_alerts, source_size))

        self._queue_panel(
            "current",
            f"截图读数：{reading_summary}\n商店来牌：{shop_summary}\n\n{format_economy_rhythm(rhythm_report)}",
        )
        self._queue_panel("lineups", format_lineup_panel(core_report))
        self._queue_panel("stars", format_star_panel(core_report, hit_alerts))
        self._queue_panel("chase", chase_output)
        self._queue_panel("items", format_item_advice(item_report))
        self._queue_panel(
            "log",
            "\n\n".join(
                (
                    format_shop_scan(shop_report),
                    format_shop_hit_alerts(hit_alerts),
                    format_item_advice(item_report),
                    format_economy_rhythm(rhythm_report),
                    chase_output,
                    format_core_advice(core_report),
                )
            ),
        )
        if hit_alerts:
            self.root.after(0, self.root.bell)
        if not auto:
            self._cleanup_old_captures(capture_dir)
        return "自动识别已更新。" if auto else "一键扫描完成。"

    def scan_shop(self) -> None:
        self._run_task("一键扫描当前局势", lambda: self._scan_current_state(auto=False))

    def scout_opponent(self) -> None:
        def task() -> str:
            client = self._client()
            capture_dir = self._capture_dir()
            session_dir = capture_dir / time.strftime("scout_%Y%m%d_%H%M%S")
            screenshot_path = session_dir / "screen.png"
            saved = client.capture_screenshot(self._current_index(), screenshot_path, launch_if_needed=True)
            report = scan_opponent(
                saved,
                templates_path=capture_dir / "opponent_templates.json",
                output_dir=session_dir / "matches",
            )
            readings = read_screenshot(saved)
            detected_level = _reading_value(readings, "level")
            detected_gold = _reading_value(readings, "gold")
            if detected_level is not None and detected_gold is not None:
                chase_output = format_chase_reports(
                    build_chase_reports_from_state(
                        load_card_state(capture_dir / "card_state.json"),
                        level=detected_level,
                        gold=detected_gold,
                        contested_counts=report.contested_counts,
                    )
                )
            else:
                chase_output = "四费/五费追三概率:\n- 等级或金币没读稳，可用 CLI capture-scout 加 --level/--gold。"

            summary = "; ".join(f"{name}={count}" for name, count in report.contested_counts.items()) or "暂无侦查命中"
            self.root.after(0, lambda: self.last_capture_var.set(str(saved)))
            self.root.after(0, lambda: self._show_preview(saved))
            self.root.after(0, lambda: self._update_reading_widgets(readings))
            self.root.after(0, lambda: self.last_core_var.set(summary))
            self._queue_panel("stars", format_opponent_scout(report))
            self._queue_panel("chase", chase_output)
            self._cleanup_old_captures(capture_dir)
            return "对手侦查完成。"

        self._run_task("侦查对手", task)

    def reset_card_counts(self) -> None:
        def task() -> str:
            state_path = self._capture_dir() / "card_state.json"
            reset_card_state(state_path)
            self.root.after(0, lambda: self.last_core_var.set("棋子计数已重置"))
            self._queue_panel("stars", "三星警告 / 商店必买\n- 棋子计数已重置。")
            return f"棋子计数已重置：{state_path}"

        self._run_task("重置棋子计数", task)

    def open_capture_folder(self) -> None:
        capture_dir = self._capture_dir()
        capture_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(capture_dir))

    def _on_close(self) -> None:
        self._closed = True
        if self._auto_scan_job is not None:
            try:
                self.root.after_cancel(self._auto_scan_job)
            except tk.TclError:
                pass
            self._auto_scan_job = None
        try:
            self._save_config()
        finally:
            if self._overlay is not None:
                try:
                    self._overlay.destroy()
                except tk.TclError:
                    pass
            if self._highlight_overlay is not None:
                try:
                    self._highlight_overlay.destroy()
                except tk.TclError:
                    pass
            self.root.destroy()

    def run(self) -> None:
        self.refresh_status()
        self.root.mainloop()
