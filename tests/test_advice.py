from __future__ import annotations

from jkcheese.advice import build_advice
from jkcheese.ocr import OcrReading


def reading(name: str, value: int | None, confidence: float) -> OcrReading:
    text = "" if value is None else str(value)
    return OcrReading(
        name=name,
        text=text,
        value=value,
        confidence=confidence,
        source_region=name,
    )


def test_build_advice_warns_on_low_confidence():
    report = build_advice(
        [
            reading("gold", 40, 0.9),
            reading("level", 8, 0.5),
            reading("player_hp", 80, 0.9),
        ]
    )

    assert report.warnings
    assert report.warnings[0].field_name == "level"
    assert report.advice[0].severity == "warning"


def test_build_advice_protects_interest_at_high_gold():
    report = build_advice(
        [
            reading("gold", 52, 0.9),
            reading("level", 7, 0.9),
            reading("player_hp", 78, 0.9),
        ]
    )

    titles = [item.title for item in report.advice]

    assert "Protect interest" in titles
    assert "You can lean economy" in titles


def test_build_advice_prioritizes_stabilizing_at_low_hp():
    report = build_advice(
        [
            reading("gold", 22, 0.9),
            reading("level", 8, 0.9),
            reading("player_hp", 24, 0.9),
        ]
    )

    assert any(item.title == "Stabilize soon" for item in report.advice)
    assert any(item.severity == "warning" for item in report.advice)


def test_build_advice_handles_missing_reading():
    report = build_advice(
        [
            reading("gold", None, 0.0),
            reading("level", 5, 0.9),
            reading("player_hp", 70, 0.9),
        ]
    )

    assert report.warnings[0].field_name == "gold"
    assert "not read" in report.warnings[0].message
