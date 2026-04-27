from __future__ import annotations

from types import SimpleNamespace

from jkcheese.gui import (
    BUY_HINT_STALE_LIMIT,
    BUY_HINT_WAITING_STATUS,
    BuyHintTracker,
    ScreenRect,
    build_calibration_highlights,
    build_shop_highlights,
    buy_hint_signature,
    choose_highlight_target_rect,
    format_buy_hint_status,
    format_overlay_summary,
    format_reading_summary,
    highlight_draw_rect,
    highlight_overlay_click_through_enabled,
    highlight_offset_for_position,
    map_capture_box_to_screen,
    overlay_geometry_for_position,
    should_reset_legacy_overlay_position,
    should_reset_stale_highlight_offset,
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
    assert "S/S-阵容: S级机甲九五" in output


def test_shop_highlights_map_alerts_to_shop_slot_boxes():
    highlights = build_shop_highlights(
        [SimpleNamespace(slot=2, name="千珏", severity="critical", title="立刻买")],
        (1920, 1080),
    )

    assert len(highlights) == 1
    assert highlights[0].slot == 2
    assert highlights[0].name == "千珏"
    assert highlights[0].box == (728, 878, 957, 1064)


def test_calibration_highlights_show_all_shop_slots():
    highlights = build_calibration_highlights((1920, 1080))

    assert [item.slot for item in highlights] == [1, 2, 3, 4, 5]
    assert highlights[0].box == (496, 878, 718, 1064)


def test_map_capture_box_to_screen_scales_to_window_client_rect():
    mapped = map_capture_box_to_screen(
        (960, 540, 1440, 810),
        (1920, 1080),
        ScreenRect(x=100, y=200, width=960, height=540),
    )

    assert mapped == (480, 270, 720, 405)


def test_highlight_draw_rect_uses_exact_slot_edges():
    assert highlight_draw_rect((496, 878, 718, 1064)) == (496, 878, 718, 1064)


def test_choose_highlight_target_rect_applies_saved_offset():
    auto_rect = ScreenRect(x=10, y=20, width=300, height=200)

    assert choose_highlight_target_rect(auto_rect, offset_x=30, offset_y=-10) == ScreenRect(
        x=40,
        y=10,
        width=300,
        height=200,
    )


def test_highlight_offset_for_position_uses_auto_window_origin():
    auto_rect = ScreenRect(x=100, y=200, width=960, height=540)

    assert highlight_offset_for_position(75, 230, auto_rect) == (-25, 30)


def test_highlight_offset_without_auto_rect_is_zero():
    assert highlight_offset_for_position(75, 230, None) == (0, 0)


def test_overlay_geometry_restores_saved_free_position():
    assert overlay_geometry_for_position(1920, 420, 96) == "340x150+420+96"


def test_overlay_geometry_falls_back_to_top_left_when_no_saved_position():
    assert overlay_geometry_for_position(1280, None, None) == "340x150+28+72"


def test_legacy_overlay_position_migration_detects_old_right_default():
    assert should_reset_legacy_overlay_position(1920, 1552, 72) is True


def test_legacy_overlay_position_migration_preserves_user_left_position():
    assert should_reset_legacy_overlay_position(1920, 420, 96) is False


def test_stale_highlight_offset_migration_resets_large_drag_offsets():
    assert should_reset_stale_highlight_offset(-494, 277) is True
    assert should_reset_stale_highlight_offset(24, -18) is False


def test_highlight_overlay_is_always_mouse_click_through():
    assert highlight_overlay_click_through_enabled() is True
    assert highlight_overlay_click_through_enabled(calibration_visible=True) is True


def test_buy_hint_status_is_read_only_and_filters_severity():
    alerts = [
        SimpleNamespace(slot=2, name="千珏", severity="critical", title="buy"),
        SimpleNamespace(slot=4, name="卡莎", severity="info", title="watch"),
    ]

    assert buy_hint_signature(alerts, "medium") == ((2, "千珏", "critical"),)
    assert format_buy_hint_status(alerts, "medium") == "拿牌提醒：槽2 千珏"


def test_buy_hint_tracker_only_logs_new_targets():
    tracker = BuyHintTracker()
    alerts = [SimpleNamespace(slot=2, name="千珏", severity="critical", title="buy")]

    first = tracker.update(alerts, ("千珏",), "medium")
    second = tracker.update(alerts, ("千珏",), "medium")

    assert first.should_log is True
    assert first.should_bell is True
    assert second.should_log is False
    assert second.should_bell is False


def test_buy_hint_tracker_warns_when_target_never_changes():
    tracker = BuyHintTracker()
    alerts = [SimpleNamespace(slot=2, name="千珏", severity="critical", title="buy")]

    update = None
    for _ in range(BUY_HINT_STALE_LIMIT + 1):
        update = tracker.update(alerts, ("千珏",), "medium")

    assert update is not None
    assert update.status == "拿牌提醒：目标未变化，可能金币不足或备战席已满"
    assert update.should_log is True
    assert update.should_bell is False

    repeated_stale = tracker.update(alerts, ("千珏",), "medium")
    assert repeated_stale.should_log is False
    assert repeated_stale.should_bell is False


def test_buy_hint_tracker_clear_resets_stale_guard():
    tracker = BuyHintTracker()
    alerts = [SimpleNamespace(slot=2, name="千珏", severity="critical", title="buy")]
    for _ in range(BUY_HINT_STALE_LIMIT + 1):
        tracker.update(alerts, ("千珏",), "medium")

    waiting = tracker.update([], (), "medium")
    first_after_clear = tracker.update(alerts, ("千珏",), "medium")

    assert waiting.status == BUY_HINT_WAITING_STATUS
    assert first_after_clear.should_log is True
    assert first_after_clear.should_bell is True
