from __future__ import annotations

from dataclasses import dataclass

from .ocr import OcrReading


LOW_CONFIDENCE = 0.65


@dataclass(frozen=True, slots=True)
class AdviceItem:
    title: str
    detail: str
    severity: str = "info"


@dataclass(frozen=True, slots=True)
class ReadingWarning:
    field_name: str
    message: str


@dataclass(frozen=True, slots=True)
class AdviceReport:
    readings: tuple[OcrReading, ...]
    warnings: tuple[ReadingWarning, ...]
    advice: tuple[AdviceItem, ...]

    def reading(self, name: str) -> OcrReading | None:
        for reading in self.readings:
            if reading.name == name:
                return reading
        return None


def build_advice(readings: list[OcrReading] | tuple[OcrReading, ...]) -> AdviceReport:
    readings_tuple = tuple(readings)
    warnings = _build_warnings(readings_tuple)

    gold = _value(readings_tuple, "gold")
    level = _value(readings_tuple, "level")
    hp = _value(readings_tuple, "player_hp")
    advice: list[AdviceItem] = []

    if warnings:
        advice.append(
            AdviceItem(
                title="Check OCR confidence",
                detail="One or more readings are uncertain. Export debug crops before making decisions from this read.",
                severity="warning",
            )
        )

    if hp is not None and hp <= 30:
        advice.append(
            AdviceItem(
                title="Stabilize soon",
                detail="HP is low. Prioritize board strength over interest until the board can stop heavy losses.",
                severity="warning",
            )
        )

    if gold is not None:
        if gold >= 50:
            advice.append(
                AdviceItem(
                    title="Protect interest",
                    detail="Gold is at or above 50. Spend carefully unless HP or board strength demands a roll-down.",
                )
            )
        elif gold >= 30:
            advice.append(
                AdviceItem(
                    title="Aim for next breakpoint",
                    detail="Gold is healthy but below 50. Preserve economy toward the next interest breakpoint.",
                )
            )
        elif gold < 10:
            advice.append(
                AdviceItem(
                    title="Economy is thin",
                    detail="Gold is low. Avoid extra refreshes unless a short-term spike is necessary.",
                    severity="warning",
                )
            )

    if level is not None and gold is not None:
        if level <= 5 and gold >= 40:
            advice.append(
                AdviceItem(
                    title="Prepare a level push",
                    detail="Gold is strong for the current level. Consider leveling on a standard timing if board tempo supports it.",
                )
            )
        elif level >= 8 and hp is not None and hp <= 45:
            advice.append(
                AdviceItem(
                    title="Convert gold to board strength",
                    detail="At level 8 with pressure on HP, spending for upgrades is usually more valuable than holding economy.",
                    severity="warning",
                )
            )

    if hp is not None and hp >= 70 and gold is not None and gold >= 30:
        advice.append(
            AdviceItem(
                title="You can lean economy",
                detail="HP and gold are both comfortable. You have room to play for interest and stronger timings.",
            )
        )

    if not advice:
        advice.append(
            AdviceItem(
                title="Keep scouting",
                detail="Readings are available, but no strong economy signal was detected from gold, level, and HP alone.",
            )
        )

    return AdviceReport(readings=readings_tuple, warnings=tuple(warnings), advice=tuple(advice))


def _build_warnings(readings: tuple[OcrReading, ...]) -> list[ReadingWarning]:
    warnings: list[ReadingWarning] = []
    for reading in readings:
        if reading.value is None:
            warnings.append(
                ReadingWarning(
                    field_name=reading.name,
                    message=f"{reading.name} was not read.",
                )
            )
        elif reading.confidence < LOW_CONFIDENCE:
            warnings.append(
                ReadingWarning(
                    field_name=reading.name,
                    message=f"{reading.name} confidence is low ({reading.confidence:.3f}).",
                )
            )
    return warnings


def _value(readings: tuple[OcrReading, ...], name: str) -> int | None:
    for reading in readings:
        if reading.name == name:
            return reading.value
    return None
