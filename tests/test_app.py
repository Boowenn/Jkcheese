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
