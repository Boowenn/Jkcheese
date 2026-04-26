from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from jkcheese.ocr import export_ocr_debug, read_screenshot


def _test_font(size: int):
    candidates = (
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    pytest.skip("No Windows test font available")


def test_read_screenshot_reads_core_numbers(tmp_path):
    image = Image.new("RGB", (1920, 1080), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    bright = (245, 238, 205)
    draw.text((650, 12), "3-2", font=_test_font(34), fill=bright)
    draw.text((972, 817), "23", font=_test_font(30), fill=bright)
    draw.text((281, 816), "8", font=_test_font(27), fill=bright)
    draw.text((1725, 131), "100", font=_test_font(43), fill=bright)

    path = tmp_path / "screen.png"
    image.save(path)

    readings = {reading.name: reading for reading in read_screenshot(path)}

    assert readings["gold"].value == 23
    assert readings["level"].value == 8
    assert readings["player_hp"].value == 100
    assert readings["stage"].text == "3-2"
    assert readings["gold"].confidence > 0.5
    assert readings["level"].confidence > 0.5
    assert readings["player_hp"].confidence > 0.5


def test_export_ocr_debug_writes_region_roi_and_mask(tmp_path):
    image = Image.new("RGB", (1920, 1080), (0, 0, 0))
    path = tmp_path / "screen.png"
    image.save(path)

    exports = export_ocr_debug(path, tmp_path / "debug")

    assert {export.field_name for export in exports} == {"stage", "gold", "level", "player_hp"}
    for export in exports:
        assert export.region_path.exists()
        assert export.roi_path.exists()
        assert export.mask_path.exists()
