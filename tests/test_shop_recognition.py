from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from jkcheese.regions import default_preset
from jkcheese.shop_recognition import (
    format_shop_scan,
    label_shop_templates,
    parse_shop_labels,
    scan_shop,
)


def test_parse_shop_labels_reads_slot_name_and_cost():
    labels = parse_shop_labels(["2=丽桑卓:1", "5=雷克塞@1"])

    assert [(label.slot, label.name, label.cost) for label in labels] == [(2, "丽桑卓", 1), (5, "雷克塞", 1)]


def test_shop_scan_detects_occupied_and_empty_slots(tmp_path):
    screen = tmp_path / "screen.png"
    _make_shop_screen(screen, occupied_slots={2: ("丽桑卓", 1)})

    report = scan_shop(screen, output_dir=tmp_path / "debug", templates_path=tmp_path / "templates.json")

    assert report.slots[0].occupied is False
    assert report.slots[1].occupied is True
    assert report.slots[1].name == ""
    assert report.slots[1].crop_path is not None
    assert report.slots[1].crop_path.exists()


def test_shop_template_label_enables_name_recognition(tmp_path):
    screen = tmp_path / "screen.png"
    templates = tmp_path / "templates.json"
    _make_shop_screen(screen, occupied_slots={2: ("丽桑卓", 1), 5: ("雷克塞", 1)})

    label_shop_templates(screen, parse_shop_labels(["2=丽桑卓:1", "5=雷克塞:1"]), templates_path=templates)
    report = scan_shop(screen, templates_path=templates)

    assert report.recognized_names == ("丽桑卓", "雷克塞")
    assert report.slots[1].name == "丽桑卓"
    assert report.slots[1].cost == 1
    assert report.slots[4].name == "雷克塞"
    assert "丽桑卓" in format_shop_scan(report)


def _make_shop_screen(path: Path, occupied_slots: dict[int, tuple[str, int]]) -> None:
    preset = default_preset()
    image = Image.new("RGB", preset.base_size, (7, 10, 12))
    draw = ImageDraw.Draw(image)
    for index in range(1, 6):
        box = preset.get(f"shop_slot_{index}").box_for(preset.base_size, preset.base_size)
        draw.rectangle(box, fill=(15, 19, 22), outline=(38, 54, 62), width=2)
        if index in occupied_slots:
            name, cost = occupied_slots[index]
            _draw_card(image, box, name, cost)
    image.save(path)


def _draw_card(image: Image.Image, box: tuple[int, int, int, int], name: str, cost: int) -> None:
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    for offset in range(0, width, 8):
        shade = 50 + (offset % 80)
        draw.line((left + offset, top, left + width - offset // 2, top + int(height * 0.74)), fill=(shade, shade, shade))
    draw.rectangle((left, top + int(height * 0.76), right, bottom), fill=(25, 36, 48))
    font = _font(20)
    draw.text((left + 18, bottom - 34), name, fill=(245, 245, 245), font=font)
    draw.text((right - 28, bottom - 34), str(cost), fill=(230, 40, 40), font=_font(18))


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in (Path(r"C:\Windows\Fonts\msyhbd.ttc"), Path(r"C:\Windows\Fonts\simhei.ttf")):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()
