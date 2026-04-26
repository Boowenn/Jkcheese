from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from jkcheese.opponent_monitor import (
    format_opponent_scout,
    label_scout_templates,
    parse_scout_labels,
    scan_opponent,
)
from jkcheese.regions import default_preset


def test_parse_scout_labels_reads_name_cost_and_box():
    labels = parse_scout_labels(["千珏:4@720,420,90,80"])

    assert labels[0].name == "千珏"
    assert labels[0].cost == 4
    assert labels[0].box == (720, 420, 810, 500)


def test_scout_label_then_scan_counts_two_matching_targets(tmp_path):
    screen = tmp_path / "screen.png"
    templates = tmp_path / "opponent_templates.json"
    _make_scout_screen(screen)

    label_scout_templates(screen, parse_scout_labels(["千珏:4@540,355,64,64"]), templates_path=templates)
    report = scan_opponent(screen, templates_path=templates, output_dir=tmp_path / "matches", threshold=0.96, stride=8)

    assert report.contested_counts == {"千珏": 2}
    assert len(report.matches) == 2
    assert all(match.crop_path and match.crop_path.exists() for match in report.matches)
    assert "千珏(4费): 疑似同行持有 2 张" in format_opponent_scout(report)


def test_scout_scan_can_filter_targets(tmp_path):
    screen = tmp_path / "screen.png"
    templates = tmp_path / "opponent_templates.json"
    _make_scout_screen(screen)

    label_scout_templates(
        screen,
        parse_scout_labels(["千珏:4@540,355,64,64", "卡莎:5@756,355,64,64"]),
        templates_path=templates,
    )
    report = scan_opponent(screen, templates_path=templates, target_names=("卡莎",), threshold=0.96, stride=8)

    assert report.contested_counts == {"卡莎": 1}


def _make_scout_screen(path: Path) -> None:
    preset = default_preset()
    image = Image.new("RGB", preset.base_size, (8, 14, 18))
    draw = ImageDraw.Draw(image)
    board = preset.get("scout_board").box_for(preset.base_size, preset.base_size)
    bench = preset.get("bench").box_for(preset.base_size, preset.base_size)
    draw.rectangle(board, fill=(22, 42, 34))
    draw.rectangle(bench, fill=(24, 30, 38))
    _draw_unit(draw, (540, 355, 604, 419), (50, 210, 225), (180, 70, 230))
    _draw_unit(draw, (884, 507, 948, 571), (50, 210, 225), (180, 70, 230))
    _draw_unit(draw, (756, 355, 820, 419), (210, 120, 40), (80, 40, 180))
    image.save(path)


def _draw_unit(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    primary: tuple[int, int, int],
    secondary: tuple[int, int, int],
) -> None:
    left, top, right, bottom = box
    draw.rounded_rectangle(box, radius=9, fill=(18, 22, 26), outline=(230, 190, 80), width=3)
    draw.ellipse((left + 8, top + 6, right - 8, bottom - 10), fill=primary)
    draw.polygon(
        ((left + 12, bottom - 14), ((left + right) // 2, top + 10), (right - 12, bottom - 14)),
        fill=secondary,
    )
    draw.rectangle((left + 18, top + 42, right - 18, bottom - 8), fill=(245, 245, 250))
