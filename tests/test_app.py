from __future__ import annotations

import argparse

from jkcheese.app import build_parser
from jkcheese import app


def test_parser_allows_gui_mode_without_subcommand():
    parser = build_parser()
    args = parser.parse_args([])

    assert isinstance(args, argparse.Namespace)
    assert args.command is None


def test_gui_duplicate_instance_exits_quietly(monkeypatch):
    class Guard:
        def acquire(self):
            return False

        def release(self):
            raise AssertionError("release should not be called when acquire fails")

    monkeypatch.setattr(app, "SingleInstance", Guard)
    monkeypatch.setattr(app, "JkcheeseGui", lambda: (_ for _ in ()).throw(AssertionError("GUI should not open")))

    parser = build_parser()
    assert app.run_cli(parser.parse_args([])) == 0


def test_parser_reads_screenshot_command():
    parser = build_parser()
    args = parser.parse_args(["screenshot", "--index", "1"])

    assert args.command == "screenshot"
    assert args.index == 1


def test_parser_reads_regions_command():
    parser = build_parser()
    args = parser.parse_args(["regions", "--input", "screen.png", "--names", "gold", "level"])

    assert args.command == "regions"
    assert str(args.input) == "screen.png"
    assert args.names == ["gold", "level"]


def test_parser_reads_capture_regions_command():
    parser = build_parser()
    args = parser.parse_args(["capture-regions", "--index", "2", "--names", "shop"])

    assert args.command == "capture-regions"
    assert args.index == 2
    assert args.names == ["shop"]


def test_parser_reads_read_command():
    parser = build_parser()
    args = parser.parse_args(["read", "--input", "screen.png"])

    assert args.command == "read"
    assert str(args.input) == "screen.png"


def test_parser_reads_capture_read_command():
    parser = build_parser()
    args = parser.parse_args(["capture-read", "--index", "3"])

    assert args.command == "capture-read"
    assert args.index == 3


def test_parser_reads_advise_command():
    parser = build_parser()
    args = parser.parse_args(["advise", "--input", "screen.png", "--debug-output", "debug"])

    assert args.command == "advise"
    assert str(args.input) == "screen.png"
    assert str(args.debug_output) == "debug"


def test_parser_reads_capture_advise_command():
    parser = build_parser()
    args = parser.parse_args(["capture-advise", "--index", "4", "--debug-output", "debug"])

    assert args.command == "capture-advise"
    assert args.index == 4
    assert str(args.debug_output) == "debug"


def test_parser_reads_tempo_command():
    parser = build_parser()
    args = parser.parse_args(["tempo", "--stage", "4-2", "--level", "8", "--gold", "34", "--hp", "45"])

    assert args.command == "tempo"
    assert args.stage == "4-2"
    assert args.level == 8
    assert args.gold == 34
    assert args.hp == 45


def test_parser_reads_capture_tempo_command():
    parser = build_parser()
    args = parser.parse_args(["capture-tempo", "--index", "2", "--stage", "3-2", "--gold", "30"])

    assert args.command == "capture-tempo"
    assert args.index == 2
    assert args.stage == "3-2"
    assert args.gold == 30


def test_parser_reads_lineups_command():
    parser = build_parser()
    args = parser.parse_args(["lineups", "--limit", "3"])

    assert args.command == "lineups"
    assert args.limit == 3


def test_parser_reads_recommend_lineup_command():
    parser = build_parser()
    args = parser.parse_args(["recommend-lineup", "--seen", "机甲", "远征", "--limit", "2"])

    assert args.command == "recommend-lineup"
    assert args.seen == ["机甲", "远征"]
    assert args.limit == 2


def test_parser_reads_item_advice_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "item-advice",
            "--shop",
            "薇古丝",
            "盖伦",
            "--seen",
            "新星",
            "--items",
            "眼泪",
            "拳套",
            "--limit",
            "2",
        ]
    )

    assert args.command == "item-advice"
    assert args.shop == ["薇古丝", "盖伦"]
    assert args.seen == ["新星"]
    assert args.items == ["眼泪", "拳套"]
    assert args.limit == 2


def test_parser_reads_core_advice_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "core-advice",
            "--seen",
            "Mecha",
            "Vanguard",
            "--owned",
            "4费Vexx7",
            "--mode",
            "replace",
            "--focus-costs",
            "4",
            "5",
            "--pool-sizes",
            "1:29,2:22,3:16,4:12,5:10",
            "--limit",
            "3",
        ]
    )

    assert args.command == "core-advice"
    assert args.seen == ["Mecha", "Vanguard"]
    assert args.owned == ["4费Vexx7"]
    assert args.mode == "replace"
    assert args.focus_costs == [4, 5]
    assert args.pool_sizes == "1:29,2:22,3:16,4:12,5:10"
    assert args.limit == 3


def test_parser_reads_capture_core_advice_command():
    parser = build_parser()
    args = parser.parse_args(["capture-core-advice", "--index", "2", "--owned", "Vex=8"])

    assert args.command == "capture-core-advice"
    assert args.index == 2
    assert args.owned == ["Vex=8"]


def test_parser_reads_reset_cards_command():
    parser = build_parser()
    args = parser.parse_args(["reset-cards", "--state", "cards.json"])

    assert args.command == "reset-cards"
    assert str(args.state) == "cards.json"


def test_parser_reads_chase_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "chase",
            "--name",
            "千珏",
            "--cost",
            "4",
            "--owned",
            "8",
            "--contested",
            "1",
            "--level",
            "8",
            "--gold",
            "30",
            "--cost-odds",
            "30",
        ]
    )

    assert args.command == "chase"
    assert args.name == "千珏"
    assert args.cost == 4
    assert args.owned == 8
    assert args.contested == 1
    assert args.level == 8
    assert args.gold == 30
    assert args.cost_odds == 30


def test_parser_reads_scout_scan_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "scout-scan",
            "--input",
            "screen.png",
            "--templates",
            "opponent_templates.json",
            "--target",
            "千珏",
            "--regions",
            "scout_board",
            "bench",
            "--threshold",
            "0.9",
        ]
    )

    assert args.command == "scout-scan"
    assert str(args.input) == "screen.png"
    assert str(args.templates) == "opponent_templates.json"
    assert args.target == ["千珏"]
    assert args.regions == ["scout_board", "bench"]
    assert args.threshold == 0.9


def test_parser_reads_capture_scout_command():
    parser = build_parser()
    args = parser.parse_args(["capture-scout", "--index", "1", "--target", "千珏", "--level", "8", "--gold", "30"])

    assert args.command == "capture-scout"
    assert args.index == 1
    assert args.target == ["千珏"]
    assert args.level == 8
    assert args.gold == 30


def test_parser_reads_scout_label_command():
    parser = build_parser()
    args = parser.parse_args(["scout-label", "--input", "screen.png", "--label", "千珏:4@720,420,90,80"])

    assert args.command == "scout-label"
    assert str(args.input) == "screen.png"
    assert args.label == ["千珏:4@720,420,90,80"]


def test_parser_reads_shop_scan_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "shop-scan",
            "--input",
            "screen.png",
            "--templates",
            "templates.json",
            "--champions",
            "champions.json",
            "--candidate",
            "潘森",
            "--name-ocr-threshold",
            "0.7",
        ]
    )

    assert args.command == "shop-scan"
    assert str(args.input) == "screen.png"
    assert str(args.templates) == "templates.json"
    assert str(args.champions) == "champions.json"
    assert args.candidate == ["潘森"]
    assert args.name_ocr_threshold == 0.7


def test_parser_reads_capture_shop_scan_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "capture-shop-scan",
            "--index",
            "1",
            "--seen",
            "机甲",
            "--level",
            "8",
            "--gold",
            "30",
            "--contested",
            "千珏=2",
        ]
    )

    assert args.command == "capture-shop-scan"
    assert args.index == 1
    assert args.seen == ["机甲"]
    assert args.level == 8
    assert args.gold == 30
    assert args.contested == ["千珏=2"]


def test_parser_reads_shop_label_command():
    parser = build_parser()
    args = parser.parse_args(["shop-label", "--input", "screen.png", "--label", "2=丽桑卓:1"])

    assert args.command == "shop-label"
    assert str(args.input) == "screen.png"
    assert args.label == ["2=丽桑卓:1"]
