from __future__ import annotations

import argparse

from jkcheese.app import build_parser


def test_parser_allows_gui_mode_without_subcommand():
    parser = build_parser()
    args = parser.parse_args([])

    assert isinstance(args, argparse.Namespace)
    assert args.command is None


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


def test_parser_reads_core_advice_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "core-advice",
            "--seen",
            "Mecha",
            "Vanguard",
            "--owned",
            "Vexx7",
            "--mode",
            "replace",
            "--limit",
            "3",
        ]
    )

    assert args.command == "core-advice"
    assert args.seen == ["Mecha", "Vanguard"]
    assert args.owned == ["Vexx7"]
    assert args.mode == "replace"
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
