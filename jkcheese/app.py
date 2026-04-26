from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .gui import JkcheeseGui
from .ldplayer import GAME_PACKAGE, LDPlayerClient, LDPlayerError
from .ocr import OcrReading, read_screenshot
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

    capture_read = subparsers.add_parser("capture-read", help="Capture a screenshot and read gold, level, and HP")
    capture_read.add_argument("--index", type=int, default=0)
    capture_read.add_argument("--output", type=Path, default=Path("captures") / "reads")
    capture_read.add_argument("--launch-if-needed", action="store_true")

    return parser


def _print_readings(readings: list[OcrReading]) -> None:
    for reading in readings:
        value = reading.text if reading.text else "-"
        print(f"{reading.name}: {value} (confidence {reading.confidence:.3f})")


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
    except KeyboardInterrupt:
        print("Interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
