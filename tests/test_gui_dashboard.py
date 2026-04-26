from __future__ import annotations

from jkcheese.gui import format_reading_summary
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
