from __future__ import annotations

from types import SimpleNamespace

from jkcheese.gui import (
    ScreenRect,
    build_shop_highlights,
    choose_highlight_target_rect,
    format_overlay_summary,
    format_reading_summary,
    map_capture_box_to_screen,
)
from jkcheese.ocr import OcrReading


def reading(name: str, text: str, value: int | None, confidence: float) -> OcrReading:
    return OcrReading(name=name, text=text, value=value, confidence=confidence, source_region=name)


def test_format_reading_summary_uses_chinese_dashboard_labels():
    output = format_reading_summary(
        [
            reading("stage", "4-2", 42, 0.82),
            reading("level", "8", 8, 0.91),
            reading("gold", "50", 50, 0.88),
            reading("player_hp", "48", 48, 0.70),
        ]
    )

    assert "阶段=4-2" in output
    assert "等级=8" in output
    assert "金币=50" in output
    assert "血量=48" in output


def test_format_overlay_summary_keeps_combat_hints_compact():
    output = format_overlay_summary(
        shop_summary="千珏, 盖伦, 薇古丝",
        lineup_summary="S级机甲九五",
        hit_summary="槽2买千珏",
        chase_summary="结论: [medium] 可以小追",
        tempo_summary="小D稳血",
    )

    assert "商店: 千珏, 盖伦, 薇古丝" in output
    assert "必买: 槽2买千珏" in output
    assert "S阵容: S级机甲九五" in output


def test_shop_highlights_map_alerts_to_shop_slot_boxes():
    highlights = build_shop_highlights(
        [SimpleNamespace(slot=2, name="千珏", severity="critical", title="立刻买")],
        (1920, 1080),
    )

    assert len(highlights) == 1
    assert highlights[0].slot == 2
    assert highlights[0].name == "千珏"
    assert highlights[0].box == (728, 878, 957, 1064)


def test_map_capture_box_to_screen_scales_to_window_client_rect():
    mapped = map_capture_box_to_screen(
        (960, 540, 1440, 810),
        (1920, 1080),
        ScreenRect(x=100, y=200, width=960, height=540),
    )

    assert mapped == (480, 270, 720, 405)


def test_choose_highlight_target_rect_uses_manual_rect_only_while_dragging():
    auto_rect = ScreenRect(x=10, y=20, width=300, height=200)
    manual_rect = ScreenRect(x=40, y=50, width=300, height=200)

    assert choose_highlight_target_rect(auto_rect, manual_rect, drag_enabled=True) == manual_rect
    assert choose_highlight_target_rect(auto_rect, manual_rect, drag_enabled=False) == auto_rect
