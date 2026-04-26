from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .advice import AdviceReport, build_advice
from .gui import JkcheeseGui
from .ldplayer import GAME_PACKAGE, LDPlayerClient, LDPlayerError
from .lineups import (
    DEFAULT_LINEUP_URL,
    Lineup,
    LineupRecommendation,
    LineupSourceError,
    fetch_jcc_s_lineups,
    recommend_lineups,
)
from .ocr import OcrReading, export_ocr_debug, read_screenshot
from .region_capture import crop_regions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jkcheese helper")
    parser.add_argument("--root", type=Path, default=Path(r"C:\leidian\LDPlayer9"))

    subparsers = parser.add_subparsers(dest="command")

    inspect = subparsers.add_parser("inspect", help="Show instance and game status")
    inspect.add_argument("--index", type=int, default=0)
    inspect.add_argument("--probe-package-path", action="store_true")

    launch = subparsers.add_parser("launch", help="Launch an instance")
    launch.add_argument("--index", type=int, default=0)

    run_game = subparsers.add_parser("run-game", help="Launch Golden Spatula")
    run_game.add_argument("--index", type=int, default=0)
    run_game.add_argument("--launch-if-needed", action="store_true")

    screenshot = subparsers.add_parser("screenshot", help="Capture a screenshot")
    screenshot.add_argument("--index", type=int, default=0)
    screenshot.add_argument("--output", type=Path, default=Path("captures") / "latest.png")
    screenshot.add_argument("--launch-if-needed", action="store_true")

    regions = subparsers.add_parser("regions", help="Crop known regions from an existing screenshot")
    regions.add_argument("--input", type=Path, required=True)
    regions.add_argument("--output", type=Path, default=Path("captures") / "regions")
    regions.add_argument("--names", nargs="*", default=None)

    capture_regions = subparsers.add_parser("capture-regions", help="Capture a screenshot and crop known regions")
    capture_regions.add_argument("--index", type=int, default=0)
    capture_regions.add_argument("--output", type=Path, default=Path("captures") / "regions")
    capture_regions.add_argument("--launch-if-needed", action="store_true")
    capture_regions.add_argument("--names", nargs="*", default=None)

    read = subparsers.add_parser("read", help="Read gold, level, and HP from an existing screenshot")
    read.add_argument("--input", type=Path, required=True)
    read.add_argument("--debug-output", type=Path, default=None)

    capture_read = subparsers.add_parser("capture-read", help="Capture a screenshot and read gold, level, and HP")
    capture_read.add_argument("--index", type=int, default=0)
    capture_read.add_argument("--output", type=Path, default=Path("captures") / "reads")
    capture_read.add_argument("--launch-if-needed", action="store_true")
    capture_read.add_argument("--debug-output", type=Path, default=None)

    advise = subparsers.add_parser("advise", help="Read a screenshot and print basic economy advice")
    advise.add_argument("--input", type=Path, required=True)
    advise.add_argument("--debug-output", type=Path, default=None)

    capture_advise = subparsers.add_parser("capture-advise", help="Capture a screenshot and print basic economy advice")
    capture_advise.add_argument("--index", type=int, default=0)
    capture_advise.add_argument("--output", type=Path, default=Path("captures") / "advice")
    capture_advise.add_argument("--launch-if-needed", action="store_true")
    capture_advise.add_argument("--debug-output", type=Path, default=None)

    lineups = subparsers.add_parser("lineups", help="Fetch S-tier Golden Spatula lineups from 实时铲榜")
    lineups.add_argument("--source", default=DEFAULT_LINEUP_URL)
    lineups.add_argument("--limit", type=int, default=10)

    recommend_lineup = subparsers.add_parser("recommend-lineup", help="Recommend S-tier lineups from live card tokens")
    recommend_lineup.add_argument("--source", default=DEFAULT_LINEUP_URL)
    recommend_lineup.add_argument("--seen", nargs="*", default=[])
    recommend_lineup.add_argument("--limit", type=int, default=5)

    return parser


def _print_readings(readings: list[OcrReading]) -> None:
    for reading in readings:
        value = reading.text if reading.text else "-"
        print(f"{reading.name}: {value} (confidence {reading.confidence:.3f})")


def _print_advice(report: AdviceReport) -> None:
    _print_readings(list(report.readings))
    if report.warnings:
        print("")
        print("Warnings:")
        for warning in report.warnings:
            print(f"- {warning.message}")

    print("")
    print("Advice:")
    for item in report.advice:
        print(f"- [{item.severity}] {item.title}: {item.detail}")


def _print_lineups(lineups: tuple[Lineup, ...], limit: int) -> None:
    for lineup in lineups[:limit]:
        notes = f" | notes: {'; '.join(lineup.notes)}" if lineup.notes else ""
        code = f" | code: {lineup.code}" if lineup.code else ""
        print(f"- [{lineup.tier}] {lineup.name}{notes}{code}")


def _print_lineup_recommendations(recommendations: tuple[LineupRecommendation, ...]) -> None:
    for item in recommendations:
        lineup = item.lineup
        matched = f" | matched: {', '.join(item.matched_tokens)}" if item.matched_tokens else ""
        notes = f" | notes: {'; '.join(lineup.notes)}" if lineup.notes else ""
        print(f"- [{lineup.tier}] {lineup.name} (score {item.score}){matched}{notes}")
        print(f"  reason: {item.reason}")
        if lineup.code:
            print(f"  code: {lineup.code}")


def _export_debug_if_requested(image_path: Path, debug_output: Path | None) -> None:
    if debug_output is None:
        return
    target = debug_output if debug_output.is_absolute() else Path.cwd() / debug_output
    exports = export_ocr_debug(image_path, target)
    print(f"Debug exported to: {target.resolve()}")
    for export in exports:
        print(f"{export.field_name}: {export.region_path.name}, {export.roi_path.name}, {export.mask_path.name}")


def run_cli(args: argparse.Namespace) -> int:
    if args.command is None:
        gui = JkcheeseGui()
        gui.run()
        return 0

    if args.command == "regions":
        output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        results = crop_regions(args.input, output, names=args.names)
        print(f"Cropped {len(results)} regions to: {output.resolve()}")
        for result in results:
            print(f"{result.name}: {result.path}")
        return 0

    if args.command == "read":
        readings = read_screenshot(args.input)
        _print_readings(readings)
        _export_debug_if_requested(args.input, args.debug_output)
        return 0

    if args.command == "advise":
        readings = read_screenshot(args.input)
        _print_advice(build_advice(readings))
        _export_debug_if_requested(args.input, args.debug_output)
        return 0

    if args.command == "lineups":
        lineups = fetch_jcc_s_lineups(args.source)
        print(f"Fetched {len(lineups)} S-tier lineups from 实时铲榜.")
        _print_lineups(lineups, args.limit)
        return 0

    if args.command == "recommend-lineup":
        lineups = fetch_jcc_s_lineups(args.source)
        recommendations = recommend_lineups(lineups, tuple(args.seen), limit=args.limit)
        print(f"Recommendations from {len(lineups)} S-tier lineups.")
        _print_lineup_recommendations(recommendations)
        return 0

    client = LDPlayerClient(args.root)

    if args.command == "inspect":
        instance = client.get_instance(args.index)
        print(f"LDPlayer root: {client.root}")
        print(f"Instance: [{instance.index}] {instance.name}")
        print(f"Resolution: {instance.width}x{instance.height} @ {instance.dpi}dpi")
        print(f"Emulator running: {'yes' if instance.running else 'no'}")
        print(f"Game installed: {'yes' if instance.has_game else 'no'}")
        if instance.has_game:
            game = instance.game
            assert game is not None
            print(f"Game label: {game.app_name or GAME_PACKAGE}")
            print(f"Game version: {game.version or '-'}")
        if instance.running and instance.has_game:
            print(f"Game process: {'running' if client.is_package_running(instance.index) else 'not running'}")
            if args.probe_package_path:
                print(f"APK path: {client.resolve_package_path(instance.index) or '-'}")
        return 0

    if args.command == "launch":
        client.launch(args.index)
        print(f"Launch command sent to instance {args.index}.")
        return 0

    if args.command == "run-game":
        if not client.is_running(args.index):
            if not args.launch_if_needed:
                raise LDPlayerError(
                    f"Instance {args.index} is not running. Use launch first or add --launch-if-needed."
                )
            client.launch(args.index)
            client.wait_for_running(args.index)
        client.wait_for_boot(args.index)
        client.run_app(args.index, GAME_PACKAGE)
        print(f"Game launch command sent to instance {args.index}.")
        return 0

    if args.command == "screenshot":
        output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        if output.name == "latest.png":
            output = output.parent / f"jkcheese_{time.strftime('%Y%m%d_%H%M%S')}.png"
        saved = client.capture_screenshot(args.index, output, launch_if_needed=args.launch_if_needed)
        print(f"Screenshot saved to: {saved}")
        return 0

    if args.command == "capture-regions":
        base_output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        session_dir = base_output / time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = session_dir / "screen.png"
        saved = client.capture_screenshot(args.index, screenshot_path, launch_if_needed=args.launch_if_needed)
        region_dir = session_dir / "regions"
        results = crop_regions(saved, region_dir, names=args.names)
        print(f"Screenshot saved to: {saved}")
        print(f"Cropped {len(results)} regions to: {region_dir.resolve()}")
        for result in results:
            print(f"{result.name}: {result.path}")
        return 0

    if args.command == "capture-read":
        base_output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        session_dir = base_output / time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = session_dir / "screen.png"
        saved = client.capture_screenshot(args.index, screenshot_path, launch_if_needed=args.launch_if_needed)
        readings = read_screenshot(saved)
        print(f"Screenshot saved to: {saved}")
        _print_readings(readings)
        _export_debug_if_requested(saved, args.debug_output)
        return 0

    if args.command == "capture-advise":
        base_output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        session_dir = base_output / time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = session_dir / "screen.png"
        saved = client.capture_screenshot(args.index, screenshot_path, launch_if_needed=args.launch_if_needed)
        readings = read_screenshot(saved)
        print(f"Screenshot saved to: {saved}")
        _print_advice(build_advice(readings))
        _export_debug_if_requested(saved, args.debug_output)
        return 0

    raise LDPlayerError(f"Unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_cli(args)
    except LDPlayerError as exc:
        print(f"Error: {exc}")
        return 1
    except LineupSourceError as exc:
        print(f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
