from __future__ import annotations

from jkcheese.gui import format_overlay_summary, format_reading_summary
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
