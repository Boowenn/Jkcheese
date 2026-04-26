from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .advice import AdviceReport, build_advice
from .card_tracker import (
    DEFAULT_CARD_STATE_PATH,
    DEFAULT_POOL_SIZES,
    CardTrackerError,
    CoreAdviceReport,
    build_core_advice,
    format_core_advice,
    load_card_state,
    reset_card_state,
)
from .chase_calculator import (
    ChaseCalculatorError,
    ChaseInput,
    build_chase_report,
    build_chase_reports_from_state,
    format_chase_report,
    format_chase_reports,
    parse_contested_counts,
    visible_counts_from_shop,
)
from .economy import build_economy_rhythm, format_economy_rhythm
from .gui import JkcheeseGui
from .item_advice import build_item_advice, format_item_advice
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
from .opponent_monitor import (
    DEFAULT_OPPONENT_TEMPLATE_PATH,
    DEFAULT_SCOUT_REGIONS,
    DEFAULT_SCOUT_STRIDE,
    DEFAULT_SCOUT_THRESHOLD,
    OpponentMonitorError,
    format_opponent_scout,
    label_scout_templates,
    parse_scout_labels,
    scan_opponent,
)
from .region_capture import crop_regions
from .shop_recognition import (
    DEFAULT_CHAMPION_DICTIONARY_PATH,
    DEFAULT_NAME_OCR_THRESHOLD,
    DEFAULT_SHOP_TEMPLATE_PATH,
    DEFAULT_TEMPLATE_THRESHOLD,
    ShopRecognitionError,
    format_shop_scan,
    label_shop_templates,
    parse_shop_labels,
    scan_shop,
)
from .shop_hits import build_shop_hit_alerts, format_shop_hit_alerts
from .single_instance import SingleInstance, notify_already_running


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

    tempo = subparsers.add_parser("tempo", help="Print stage-aware economy rhythm advice")
    _add_tempo_args(tempo)

    capture_tempo = subparsers.add_parser(
        "capture-tempo",
        help="Capture a screenshot, read stage/gold/level/HP, and print economy rhythm advice",
    )
    capture_tempo.add_argument("--index", type=int, default=0)
    capture_tempo.add_argument("--output", type=Path, default=Path("captures") / "tempo")
    capture_tempo.add_argument("--launch-if-needed", action="store_true")
    capture_tempo.add_argument("--debug-output", type=Path, default=None)
    _add_tempo_args(capture_tempo)

    lineups = subparsers.add_parser("lineups", help="Fetch S-tier Golden Spatula lineups from 实时铲榜")
    lineups.add_argument("--source", default=DEFAULT_LINEUP_URL)
    lineups.add_argument("--limit", type=int, default=10)

    recommend_lineup = subparsers.add_parser("recommend-lineup", help="Recommend S-tier lineups from live card tokens")
    recommend_lineup.add_argument("--source", default=DEFAULT_LINEUP_URL)
    recommend_lineup.add_argument("--seen", nargs="*", default=[])
    recommend_lineup.add_argument("--limit", type=int, default=5)

    item_advice = subparsers.add_parser(
        "item-advice",
        help="Recommend main carry, main tank, and items from S-tier lineups",
    )
    item_advice.add_argument("--shop", nargs="*", default=[], help="Recognized current shop cards")
    _add_core_advice_args(item_advice)

    core_advice = subparsers.add_parser(
        "core-advice",
        help="Track owned cards and recommend S-tier lineups from live tokens",
    )
    _add_core_advice_args(core_advice)

    capture_core_advice = subparsers.add_parser(
        "capture-core-advice",
        help="Capture a screenshot, then print card warnings and S-tier lineup advice",
    )
    capture_core_advice.add_argument("--index", type=int, default=0)
    capture_core_advice.add_argument("--output", type=Path, default=Path("captures") / "core")
    capture_core_advice.add_argument("--launch-if-needed", action="store_true")
    _add_core_advice_args(capture_core_advice)

    reset_cards = subparsers.add_parser("reset-cards", help="Clear the local card count tracker")
    reset_cards.add_argument("--state", type=Path, default=DEFAULT_CARD_STATE_PATH)

    chase = subparsers.add_parser("chase", help="Estimate 4/5-cost three-star chase odds")
    chase.add_argument("--name", default="", help="Target card name")
    chase.add_argument("--cost", type=int, required=True, help="Target cost, usually 4 or 5")
    chase.add_argument("--owned", type=int, required=True, help="Copies you already own")
    chase.add_argument("--contested", type=int, default=0, help="Suspected copies held by opponents")
    chase.add_argument("--level", type=int, required=True)
    chase.add_argument("--gold", type=int, required=True)
    chase.add_argument("--reserve-gold", type=int, default=0)
    chase.add_argument("--visible", type=int, default=0, help="Copies already visible in the current shop")
    chase.add_argument("--pool-size", type=int, default=None, help="Per-champion pool size override")
    chase.add_argument("--same-cost-units", type=int, default=None, help="Same-cost champion count override")
    chase.add_argument("--cost-odds", type=float, default=None, help="Override current cost odds as percent")
    chase.add_argument("--other-held", type=int, default=0, help="Other same-cost copies suspected out of pool")

    scout_scan = subparsers.add_parser("scout-scan", help="Scan an opponent screenshot for trained 4/5-cost targets")
    scout_scan.add_argument("--input", type=Path, required=True)
    scout_scan.add_argument("--templates", type=Path, default=DEFAULT_OPPONENT_TEMPLATE_PATH)
    scout_scan.add_argument("--output", type=Path, default=Path("captures") / "opponent_scout")
    scout_scan.add_argument("--target", nargs="*", default=[], help="Only scan these trained card names")
    scout_scan.add_argument("--regions", nargs="+", default=list(DEFAULT_SCOUT_REGIONS))
    scout_scan.add_argument("--threshold", type=float, default=DEFAULT_SCOUT_THRESHOLD)
    scout_scan.add_argument("--stride", type=int, default=DEFAULT_SCOUT_STRIDE)
    scout_scan.add_argument("--no-debug", action="store_true")

    capture_scout = subparsers.add_parser(
        "capture-scout",
        help="Capture the current manually selected opponent board and scan trained targets",
    )
    capture_scout.add_argument("--index", type=int, default=0)
    capture_scout.add_argument("--output", type=Path, default=Path("captures") / "opponent_scout")
    capture_scout.add_argument("--templates", type=Path, default=DEFAULT_OPPONENT_TEMPLATE_PATH)
    capture_scout.add_argument("--target", nargs="*", default=[])
    capture_scout.add_argument("--regions", nargs="+", default=list(DEFAULT_SCOUT_REGIONS))
    capture_scout.add_argument("--threshold", type=float, default=DEFAULT_SCOUT_THRESHOLD)
    capture_scout.add_argument("--stride", type=int, default=DEFAULT_SCOUT_STRIDE)
    capture_scout.add_argument("--launch-if-needed", action="store_true")
    capture_scout.add_argument("--state", type=Path, default=DEFAULT_CARD_STATE_PATH)
    capture_scout.add_argument("--level", type=int, default=None)
    capture_scout.add_argument("--gold", type=int, default=None)
    capture_scout.add_argument("--reserve-gold", type=int, default=0)
    capture_scout.add_argument("--focus-costs", nargs="+", type=int, default=[4, 5])

    scout_label = subparsers.add_parser("scout-label", help="Teach opponent-scout templates from manual boxes")
    scout_label.add_argument("--input", type=Path, required=True)
    scout_label.add_argument("--label", nargs="+", required=True, help="Examples: 千珏:4@720,420,90,90")
    scout_label.add_argument("--templates", type=Path, default=DEFAULT_OPPONENT_TEMPLATE_PATH)
    scout_label.add_argument("--output", type=Path, default=Path("captures") / "opponent_templates")

    shop_scan = subparsers.add_parser("shop-scan", help="Scan shop slots from an existing screenshot")
    shop_scan.add_argument("--input", type=Path, required=True)
    shop_scan.add_argument("--output", type=Path, default=Path("captures") / "shop_scan")
    shop_scan.add_argument("--templates", type=Path, default=DEFAULT_SHOP_TEMPLATE_PATH)
    shop_scan.add_argument("--champions", type=Path, default=DEFAULT_CHAMPION_DICTIONARY_PATH)
    shop_scan.add_argument("--candidate", nargs="*", default=[], help="Extra Chinese card-name OCR candidates")
    shop_scan.add_argument("--threshold", type=float, default=DEFAULT_TEMPLATE_THRESHOLD)
    shop_scan.add_argument("--name-ocr-threshold", type=float, default=DEFAULT_NAME_OCR_THRESHOLD)
    shop_scan.add_argument("--disable-name-ocr", action="store_true")
    shop_scan.add_argument("--no-debug", action="store_true")

    capture_shop_scan = subparsers.add_parser(
        "capture-shop-scan",
        help="Capture a screenshot, scan shop slots, and feed recognized names into core advice",
    )
    capture_shop_scan.add_argument("--index", type=int, default=0)
    capture_shop_scan.add_argument("--output", type=Path, default=Path("captures") / "shop_scan")
    capture_shop_scan.add_argument("--templates", type=Path, default=DEFAULT_SHOP_TEMPLATE_PATH)
    capture_shop_scan.add_argument("--champions", type=Path, default=DEFAULT_CHAMPION_DICTIONARY_PATH)
    capture_shop_scan.add_argument("--candidate", nargs="*", default=[], help="Extra Chinese card-name OCR candidates")
    capture_shop_scan.add_argument("--threshold", type=float, default=DEFAULT_TEMPLATE_THRESHOLD)
    capture_shop_scan.add_argument("--name-ocr-threshold", type=float, default=DEFAULT_NAME_OCR_THRESHOLD)
    capture_shop_scan.add_argument("--disable-name-ocr", action="store_true")
    capture_shop_scan.add_argument("--launch-if-needed", action="store_true")
    capture_shop_scan.add_argument("--level", type=int, default=None, help="Manual level override for chase odds")
    capture_shop_scan.add_argument("--gold", type=int, default=None, help="Manual gold override for chase odds")
    capture_shop_scan.add_argument("--reserve-gold", type=int, default=0, help="Gold to preserve before chase odds")
    capture_shop_scan.add_argument("--contested", nargs="*", default=[], help="Suspected contested copies, e.g. 千珏=2")
    _add_core_advice_args(capture_shop_scan)

    shop_label = subparsers.add_parser("shop-label", help="Label shop slots to teach local card templates")
    shop_label.add_argument("--input", type=Path, required=True)
    shop_label.add_argument("--label", nargs="+", required=True, help="Examples: 2=丽桑卓:1 5=雷克塞:1")
    shop_label.add_argument("--templates", type=Path, default=DEFAULT_SHOP_TEMPLATE_PATH)
    shop_label.add_argument("--output", type=Path, default=Path("captures") / "shop_templates")

    return parser


def _add_core_advice_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", default=DEFAULT_LINEUP_URL)
    parser.add_argument("--seen", nargs="*", default=[], help="Current shop/trait/name tokens for lineup ranking")
    parser.add_argument("--owned", nargs="*", default=[], help="Owned card counts, for example 4费Vexx7 or 五费Nami=3")
    parser.add_argument("--state", type=Path, default=DEFAULT_CARD_STATE_PATH)
    parser.add_argument("--mode", choices=("add", "replace"), default="add")
    parser.add_argument("--reset", action="store_true", help="Start a fresh tracker before applying --owned")
    parser.add_argument("--focus-costs", nargs="+", type=int, default=[4, 5], help="Card costs to monitor closely")
    parser.add_argument(
        "--pool-sizes",
        default=",".join(f"{cost}:{size}" for cost, size in DEFAULT_POOL_SIZES.items()),
        help="Per-cost public pool sizes, for example 1:30,2:25,3:18,4:10,5:9",
    )
    parser.add_argument("--items", nargs="*", default=[], help="Item components, for example 大剑 眼泪 拳套")
    parser.add_argument("--limit", type=int, default=5)


def _add_tempo_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stage", default=None, help="Current stage, for example 3-2")
    parser.add_argument("--level", type=int, default=None)
    parser.add_argument("--gold", type=int, default=None)
    parser.add_argument("--hp", type=int, default=None)


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
    if report.rhythm is not None:
        print("")
        print(format_economy_rhythm(report.rhythm))


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


def _print_core_advice(report: CoreAdviceReport) -> None:
    print(format_core_advice(report))


def _reading_value(readings: list[OcrReading], name: str) -> int | None:
    for reading in readings:
        if reading.name == name:
            return reading.value
    return None


def _reading_text(readings: list[OcrReading], name: str) -> str:
    for reading in readings:
        if reading.name == name:
            return reading.text
    return ""


def _tempo_report_from_readings(
    readings: list[OcrReading],
    *,
    stage: str | None = None,
    level: int | None = None,
    gold: int | None = None,
    hp: int | None = None,
):
    return build_economy_rhythm(
        stage=stage if stage is not None else _reading_text(readings, "stage"),
        level=level if level is not None else _reading_value(readings, "level"),
        gold=gold if gold is not None else _reading_value(readings, "gold"),
        hp=hp if hp is not None else _reading_value(readings, "player_hp"),
    )


def _parse_pool_sizes(value: str) -> dict[int, int]:
    pool_sizes = dict(DEFAULT_POOL_SIZES)
    for chunk in value.split(","):
        part = chunk.strip()
        if not part:
            continue
        if ":" not in part:
            raise CardTrackerError(f"Pool size entry must use cost:size, got {part!r}.")
        cost_text, size_text = part.split(":", 1)
        try:
            cost = int(cost_text)
            size = int(size_text)
        except ValueError as exc:
            raise CardTrackerError(f"Pool size entry must be numeric, got {part!r}.") from exc
        if cost not in range(1, 6) or size <= 0:
            raise CardTrackerError(f"Pool size entry out of range, got {part!r}.")
        pool_sizes[cost] = size
    return pool_sizes


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
        guard = SingleInstance()
        if not guard.acquire():
            notify_already_running()
            return 0
        try:
            gui = JkcheeseGui()
            gui.run()
        finally:
            guard.release()
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

    if args.command == "tempo":
        print(
            format_economy_rhythm(
                build_economy_rhythm(stage=args.stage, level=args.level, gold=args.gold, hp=args.hp)
            )
        )
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

    if args.command == "item-advice":
        lineups = fetch_jcc_s_lineups(args.source)
        state_path = args.state if args.state.is_absolute() else Path.cwd() / args.state
        seen_tokens = (*tuple(args.shop), *tuple(args.seen))
        core_report = build_core_advice(
            state_path=state_path,
            lineups=lineups,
            seen=seen_tokens,
            owned=tuple(args.owned),
            mode=args.mode,
            reset=args.reset,
            limit=args.limit,
            focus_costs=tuple(args.focus_costs),
            pool_sizes=_parse_pool_sizes(args.pool_sizes),
        )
        item_report = build_item_advice(
            core_report.recommendations,
            state=core_report.state,
            shop_names=tuple(args.shop),
            seen_tokens=core_report.seen_tokens,
            item_components=tuple(args.items),
            limit=min(3, args.limit),
        )
        print(format_item_advice(item_report))
        return 0

    if args.command == "core-advice":
        lineups = fetch_jcc_s_lineups(args.source)
        state_path = args.state if args.state.is_absolute() else Path.cwd() / args.state
        report = build_core_advice(
            state_path=state_path,
            lineups=lineups,
            seen=tuple(args.seen),
            owned=tuple(args.owned),
            mode=args.mode,
            reset=args.reset,
            limit=args.limit,
            focus_costs=tuple(args.focus_costs),
            pool_sizes=_parse_pool_sizes(args.pool_sizes),
        )
        _print_core_advice(report)
        print("")
        print(
            format_item_advice(
                build_item_advice(
                    report.recommendations,
                    state=report.state,
                    seen_tokens=report.seen_tokens,
                    item_components=tuple(args.items),
                    limit=min(3, args.limit),
                )
            )
        )
        return 0

    if args.command == "reset-cards":
        state_path = args.state if args.state.is_absolute() else Path.cwd() / args.state
        reset_card_state(state_path)
        print(f"Card tracker reset: {state_path.resolve()}")
        return 0

    if args.command == "chase":
        report = build_chase_report(
            ChaseInput(
                name=args.name,
                cost=args.cost,
                owned=args.owned,
                contested=args.contested,
                level=args.level,
                gold=args.gold,
                reserve_gold=args.reserve_gold,
                visible=args.visible,
                pool_size=args.pool_size,
                same_cost_units=args.same_cost_units,
                cost_odds_percent=args.cost_odds,
                other_held=args.other_held,
            )
        )
        print(format_chase_report(report))
        return 0

    if args.command == "scout-scan":
        output = None if args.no_debug else (args.output if args.output.is_absolute() else Path.cwd() / args.output)
        report = scan_opponent(
            args.input,
            templates_path=args.templates,
            output_dir=output,
            target_names=tuple(args.target),
            regions=tuple(args.regions),
            threshold=args.threshold,
            stride=args.stride,
        )
        print(format_opponent_scout(report))
        return 0

    if args.command == "scout-label":
        templates = label_scout_templates(
            args.input,
            parse_scout_labels(args.label),
            templates_path=args.templates,
            output_dir=args.output if args.output.is_absolute() else Path.cwd() / args.output,
        )
        target = args.templates if args.templates.is_absolute() else Path.cwd() / args.templates
        print(f"Saved {len(templates)} opponent scout templates to: {target.resolve()}")
        return 0

    if args.command == "shop-scan":
        output = None if args.no_debug else (args.output if args.output.is_absolute() else Path.cwd() / args.output)
        report = scan_shop(
            args.input,
            output_dir=output,
            templates_path=args.templates,
            champions_path=args.champions,
            candidate_names=tuple(args.candidate),
            enable_name_ocr=not args.disable_name_ocr,
            threshold=args.threshold,
            name_ocr_threshold=args.name_ocr_threshold,
        )
        print(format_shop_scan(report))
        return 0

    if args.command == "shop-label":
        templates = label_shop_templates(
            args.input,
            parse_shop_labels(args.label),
            templates_path=args.templates,
            output_dir=args.output if args.output.is_absolute() else Path.cwd() / args.output,
        )
        print(f"Saved {len(templates)} shop templates to: {(args.templates if args.templates.is_absolute() else Path.cwd() / args.templates).resolve()}")
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

    if args.command == "capture-tempo":
        base_output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        session_dir = base_output / time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = session_dir / "screen.png"
        saved = client.capture_screenshot(args.index, screenshot_path, launch_if_needed=args.launch_if_needed)
        readings = read_screenshot(saved)
        print(f"Screenshot saved to: {saved}")
        _print_readings(readings)
        print("")
        print(
            format_economy_rhythm(
                _tempo_report_from_readings(
                    readings,
                    stage=args.stage,
                    level=args.level,
                    gold=args.gold,
                    hp=args.hp,
                )
            )
        )
        _export_debug_if_requested(saved, args.debug_output)
        return 0

    if args.command == "capture-core-advice":
        base_output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        session_dir = base_output / time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = session_dir / "screen.png"
        saved = client.capture_screenshot(args.index, screenshot_path, launch_if_needed=args.launch_if_needed)
        lineups = fetch_jcc_s_lineups(args.source)
        state_path = args.state if args.state.is_absolute() else Path.cwd() / args.state
        report = build_core_advice(
            state_path=state_path,
            lineups=lineups,
            seen=tuple(args.seen),
            owned=tuple(args.owned),
            mode=args.mode,
            reset=args.reset,
            limit=args.limit,
            focus_costs=tuple(args.focus_costs),
            pool_sizes=_parse_pool_sizes(args.pool_sizes),
        )
        print(f"Screenshot saved to: {saved}")
        _print_core_advice(report)
        print("")
        print(
            format_item_advice(
                build_item_advice(
                    report.recommendations,
                    state=report.state,
                    seen_tokens=report.seen_tokens,
                    item_components=tuple(args.items),
                    limit=min(3, args.limit),
                )
            )
        )
        return 0

    if args.command == "capture-scout":
        base_output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        session_dir = base_output / time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = session_dir / "screen.png"
        saved = client.capture_screenshot(args.index, screenshot_path, launch_if_needed=args.launch_if_needed)
        scout_report = scan_opponent(
            saved,
            templates_path=args.templates,
            output_dir=session_dir / "matches",
            target_names=tuple(args.target),
            regions=tuple(args.regions),
            threshold=args.threshold,
            stride=args.stride,
        )
        print(f"Screenshot saved to: {saved}")
        print(format_opponent_scout(scout_report))

        readings = read_screenshot(saved)
        detected_level = args.level if args.level is not None else _reading_value(readings, "level")
        detected_gold = args.gold if args.gold is not None else _reading_value(readings, "gold")
        if detected_level is not None and detected_gold is not None:
            state_path = args.state if args.state.is_absolute() else Path.cwd() / args.state
            chase_reports = build_chase_reports_from_state(
                load_card_state(state_path),
                level=detected_level,
                gold=detected_gold,
                contested_counts=scout_report.contested_counts,
                focus_costs=tuple(args.focus_costs),
                reserve_gold=args.reserve_gold,
            )
            print("")
            print(format_chase_reports(chase_reports))
        else:
            print("")
            print("四费/五费追三概率:")
            print("- 未能稳定读取等级或金币；可加 --level 和 --gold 让本次侦查直接更新追三判断。")
        return 0

    if args.command == "capture-shop-scan":
        base_output = args.output if args.output.is_absolute() else Path.cwd() / args.output
        session_dir = base_output / time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = session_dir / "screen.png"
        saved = client.capture_screenshot(args.index, screenshot_path, launch_if_needed=args.launch_if_needed)
        scan_report = scan_shop(
            saved,
            output_dir=session_dir / "shop",
            templates_path=args.templates,
            champions_path=args.champions,
            candidate_names=tuple(args.candidate),
            enable_name_ocr=not args.disable_name_ocr,
            threshold=args.threshold,
            name_ocr_threshold=args.name_ocr_threshold,
        )
        print(f"Screenshot saved to: {saved}")
        print(format_shop_scan(scan_report))

        readings = read_screenshot(saved)
        detected_level = args.level if args.level is not None else _reading_value(readings, "level")
        detected_gold = args.gold if args.gold is not None else _reading_value(readings, "gold")
        lineups = fetch_jcc_s_lineups(args.source)
        state_path = args.state if args.state.is_absolute() else Path.cwd() / args.state
        pool_sizes = _parse_pool_sizes(args.pool_sizes)
        seen_tokens = (*scan_report.recognized_names, *tuple(args.seen))
        core_report = build_core_advice(
            state_path=state_path,
            lineups=lineups,
            seen=seen_tokens,
            owned=tuple(args.owned),
            mode=args.mode,
            reset=args.reset,
            limit=args.limit,
            focus_costs=tuple(args.focus_costs),
            pool_sizes=pool_sizes,
        )
        hit_alerts = build_shop_hit_alerts(
            scan_report,
            core_report.state,
            lineups=lineups,
            focus_costs=tuple(args.focus_costs),
            pool_sizes=pool_sizes,
        )
        print("")
        print(format_shop_hit_alerts(hit_alerts))
        item_report = build_item_advice(
            core_report.recommendations,
            state=core_report.state,
            shop_names=scan_report.recognized_names,
            seen_tokens=core_report.seen_tokens,
            item_components=tuple(args.items),
            limit=min(3, args.limit),
        )
        print("")
        print(format_item_advice(item_report))
        print("")
        print(format_economy_rhythm(_tempo_report_from_readings(readings, level=args.level, gold=args.gold)))
        if detected_level is not None and detected_gold is not None:
            chase_reports = build_chase_reports_from_state(
                core_report.state,
                level=detected_level,
                gold=detected_gold,
                visible_counts=visible_counts_from_shop(scan_report),
                contested_counts=parse_contested_counts(tuple(args.contested)),
                focus_costs=tuple(args.focus_costs),
                reserve_gold=args.reserve_gold,
            )
            print("")
            print(format_chase_reports(chase_reports))
        else:
            print("")
            print("四费/五费追三概率:")
            print("- 未能稳定读取等级或金币；可用 `chase` 命令手动输入 level/gold 计算。")
        print("")
        _print_core_advice(core_report)
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
    except CardTrackerError as exc:
        print(f"Error: {exc}")
        return 1
    except ShopRecognitionError as exc:
        print(f"Error: {exc}")
        return 1
    except ChaseCalculatorError as exc:
        print(f"Error: {exc}")
        return 1
    except OpponentMonitorError as exc:
        print(f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
