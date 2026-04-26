from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .card_tracker import CardTrackerState, DEFAULT_FOCUS_COSTS, DEFAULT_POOL_SIZES
from .shop_recognition import ShopScanReport


DEFAULT_SAME_COST_UNITS = {1: 13, 2: 13, 3: 13, 4: 13, 5: 8}
DEFAULT_LEVEL_ODDS = {
    1: {1: 100, 2: 0, 3: 0, 4: 0, 5: 0},
    2: {1: 100, 2: 0, 3: 0, 4: 0, 5: 0},
    3: {1: 75, 2: 25, 3: 0, 4: 0, 5: 0},
    4: {1: 55, 2: 30, 3: 15, 4: 0, 5: 0},
    5: {1: 45, 2: 33, 3: 20, 4: 2, 5: 0},
    6: {1: 35, 2: 35, 3: 25, 4: 5, 5: 0},
    7: {1: 19, 2: 30, 3: 35, 4: 15, 5: 1},
    8: {1: 15, 2: 20, 3: 32, 4: 30, 5: 3},
    9: {1: 10, 2: 15, 3: 30, 4: 30, 5: 15},
    10: {1: 5, 2: 10, 3: 20, 4: 40, 5: 25},
    11: {1: 1, 2: 2, 3: 12, 4: 50, 5: 35},
}
DEFAULT_ROLL_COST = 2
DEFAULT_SHOP_SLOTS = 5
THREE_STAR_COPIES = 9


class ChaseCalculatorError(RuntimeError):
    """Raised when chase calculator inputs are invalid."""


@dataclass(frozen=True, slots=True)
class ChaseInput:
    name: str = ""
    cost: int = 4
    owned: int = 0
    contested: int = 0
    level: int = 8
    gold: int = 0
    reserve_gold: int = 0
    visible: int = 0
    pool_size: int | None = None
    same_cost_units: int | None = None
    cost_odds_percent: float | None = None
    other_held: int = 0
    roll_cost: int = DEFAULT_ROLL_COST
    shop_slots: int = DEFAULT_SHOP_SLOTS


@dataclass(frozen=True, slots=True)
class ChaseReport:
    chase_input: ChaseInput
    pool_size: int
    same_cost_units: int
    cost_odds_percent: float
    needed_before_visible: int
    visible_buys: int
    needed: int
    remaining_target: int
    total_same_cost_remaining: int
    roll_budget: int
    rolls: int
    attempts: int
    probability: float
    expected_hits: float
    risk: str
    title: str
    detail: str
    notes: tuple[str, ...] = ()


def build_chase_report(chase_input: ChaseInput) -> ChaseReport:
    _validate_input(chase_input)
    pool_size = chase_input.pool_size or DEFAULT_POOL_SIZES[chase_input.cost]
    same_cost_units = chase_input.same_cost_units or DEFAULT_SAME_COST_UNITS[chase_input.cost]
    cost_odds_percent = (
        chase_input.cost_odds_percent
        if chase_input.cost_odds_percent is not None
        else _default_cost_odds(chase_input.level, chase_input.cost)
    )
    cost_odds = cost_odds_percent / 100

    owned = min(pool_size, max(0, chase_input.owned))
    contested = max(0, chase_input.contested)
    needed_before_visible = max(0, THREE_STAR_COPIES - owned)
    visible_affordable = max(0, (chase_input.gold - chase_input.reserve_gold) // chase_input.cost)
    visible_buys = min(max(0, chase_input.visible), needed_before_visible, visible_affordable)
    needed = max(0, needed_before_visible - visible_buys)
    remaining_target = max(0, pool_size - owned - contested - visible_buys)
    total_same_cost_remaining = max(
        remaining_target,
        same_cost_units * pool_size - owned - contested - visible_buys - max(0, chase_input.other_held),
    )

    gold_after_visible = max(0, chase_input.gold - chase_input.reserve_gold - visible_buys * chase_input.cost)
    future_buy_gold = needed * chase_input.cost
    roll_budget = max(0, gold_after_visible - future_buy_gold)
    rolls = roll_budget // chase_input.roll_cost
    attempts = rolls * chase_input.shop_slots

    probability, expected_hits = _roll_distribution(
        needed=needed,
        attempts=attempts,
        cost_odds=cost_odds,
        remaining_target=remaining_target,
        total_same_cost_remaining=total_same_cost_remaining,
    )
    risk, title, detail = _classify_report(
        chase_input,
        needed=needed,
        remaining_target=remaining_target,
        probability=probability,
        roll_budget=roll_budget,
        gold_after_visible=gold_after_visible,
        future_buy_gold=future_buy_gold,
        cost_odds_percent=cost_odds_percent,
    )

    return ChaseReport(
        chase_input=chase_input,
        pool_size=pool_size,
        same_cost_units=same_cost_units,
        cost_odds_percent=cost_odds_percent,
        needed_before_visible=needed_before_visible,
        visible_buys=visible_buys,
        needed=needed,
        remaining_target=remaining_target,
        total_same_cost_remaining=total_same_cost_remaining,
        roll_budget=roll_budget,
        rolls=rolls,
        attempts=attempts,
        probability=round(probability, 4),
        expected_hits=round(expected_hits, 2),
        risk=risk,
        title=title,
        detail=detail,
        notes=_build_notes(chase_input, cost_odds_percent, future_buy_gold, gold_after_visible),
    )


def build_chase_reports_from_state(
    state: CardTrackerState,
    *,
    level: int,
    gold: int,
    visible_counts: dict[str, int] | None = None,
    contested_counts: dict[str, int] | None = None,
    focus_costs: tuple[int, ...] = DEFAULT_FOCUS_COSTS,
    reserve_gold: int = 0,
) -> tuple[ChaseReport, ...]:
    visible_counts = visible_counts or {}
    contested_counts = contested_counts or {}
    reports: list[ChaseReport] = []
    names = set(state.counts) | set(visible_counts)
    for name in sorted(names):
        cost = state.costs.get(name)
        if cost is None or cost not in focus_costs:
            continue
        owned = state.counts.get(name, 0)
        visible = visible_counts.get(name, 0)
        if owned < 2 and visible == 0:
            continue
        reports.append(
            build_chase_report(
                ChaseInput(
                    name=name,
                    cost=cost,
                    owned=owned,
                    contested=contested_counts.get(name, 0),
                    level=level,
                    gold=gold,
                    reserve_gold=reserve_gold,
                    visible=visible,
                )
            )
        )
    return tuple(sorted(reports, key=lambda report: (-report.probability, report.needed, report.chase_input.name)))


def visible_counts_from_shop(report: ShopScanReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for reading in report.slots:
        if reading.occupied and reading.name:
            counts[reading.name] = counts.get(reading.name, 0) + 1
    return counts


def format_chase_report(report: ChaseReport) -> str:
    target = report.chase_input.name or "目标棋子"
    cost = report.chase_input.cost
    probability = f"{report.probability * 100:.1f}%"
    lines = [
        f"追三概率: {target}({cost}费)",
        f"- 结论: [{report.risk}] {report.title}",
        f"- 当前: 已有{report.chase_input.owned}/9，商店可见{report.chase_input.visible}，同行疑似卡{report.chase_input.contested}，还差{report.needed}张。",
        f"- 牌库: 单种{report.pool_size}张，同费用约{report.same_cost_units}种；目标剩余{report.remaining_target}张，同费用剩余估算{report.total_same_cost_remaining}张。",
        f"- 预算: {report.chase_input.gold}金币，预留{report.chase_input.reserve_gold}，买牌后可用于D牌约{report.roll_budget}金币，可D {report.rolls}次，看{report.attempts}个商店格。",
        f"- 概率: 本波补齐三星约{probability}，期望命中{report.expected_hits}张。",
        f"- 建议: {report.detail}",
    ]
    if report.notes:
        lines.append("- 备注: " + " ".join(report.notes))
    return "\n".join(lines)


def format_chase_reports(reports: tuple[ChaseReport, ...]) -> str:
    lines = ["四费/五费追三概率:"]
    if not reports:
        lines.append("- 暂无已记录的4/5费追三目标。先在 Owned Copies 里记录，例如 `4费千珏x7`。")
        return "\n".join(lines)
    for index, report in enumerate(reports):
        if index:
            lines.append("")
        lines.append(format_chase_report(report))
    return "\n".join(lines)


def parse_contested_counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        token = str(value).strip()
        if not token:
            continue
        if "=" in token:
            name, count_text = token.split("=", 1)
        elif "x" in token:
            name, count_text = token.rsplit("x", 1)
        else:
            name, count_text = token, "1"
        name = name.strip()
        try:
            count = int(count_text)
        except ValueError as exc:
            raise ChaseCalculatorError(f"Invalid contested count: {value!r}") from exc
        if name and count > 0:
            counts[name] = counts.get(name, 0) + count
    return counts


def _validate_input(chase_input: ChaseInput) -> None:
    if chase_input.cost not in range(1, 6):
        raise ChaseCalculatorError("Cost must be 1-5.")
    if chase_input.level not in DEFAULT_LEVEL_ODDS and chase_input.cost_odds_percent is None:
        raise ChaseCalculatorError("Unknown level odds; pass --cost-odds to override.")
    if chase_input.gold < 0 or chase_input.owned < 0 or chase_input.contested < 0:
        raise ChaseCalculatorError("Gold, owned, and contested counts cannot be negative.")
    if chase_input.roll_cost <= 0 or chase_input.shop_slots <= 0:
        raise ChaseCalculatorError("Roll cost and shop slot count must be positive.")
    if chase_input.cost_odds_percent is not None and not 0 <= chase_input.cost_odds_percent <= 100:
        raise ChaseCalculatorError("Cost odds must be between 0 and 100.")
    if chase_input.pool_size is not None and chase_input.pool_size <= 0:
        raise ChaseCalculatorError("Pool size must be positive.")
    if chase_input.same_cost_units is not None and chase_input.same_cost_units <= 0:
        raise ChaseCalculatorError("Same-cost unit count must be positive.")


def _roll_distribution(
    *,
    needed: int,
    attempts: int,
    cost_odds: float,
    remaining_target: int,
    total_same_cost_remaining: int,
) -> tuple[float, float]:
    if needed <= 0:
        return 1.0, 0.0
    if attempts <= 0 or remaining_target < needed or cost_odds <= 0:
        return 0.0, 0.0

    dp = [0.0 for _ in range(needed + 1)]
    dp[0] = 1.0
    for _ in range(attempts):
        next_dp = [0.0 for _ in range(needed + 1)]
        for hits, chance in enumerate(dp):
            if chance <= 0:
                continue
            if hits >= needed:
                next_dp[needed] += chance
                continue
            slot_hit = _slot_hit_probability(
                cost_odds=cost_odds,
                remaining_target=remaining_target - hits,
                total_same_cost_remaining=total_same_cost_remaining - hits,
            )
            next_dp[min(needed, hits + 1)] += chance * slot_hit
            next_dp[hits] += chance * (1 - slot_hit)
        dp = next_dp

    expected_hits = sum(hits * chance for hits, chance in enumerate(dp))
    return dp[needed], expected_hits


def _slot_hit_probability(*, cost_odds: float, remaining_target: int, total_same_cost_remaining: int) -> float:
    if remaining_target <= 0 or total_same_cost_remaining <= 0:
        return 0.0
    return max(0.0, min(1.0, cost_odds * remaining_target / total_same_cost_remaining))


def _default_cost_odds(level: int, cost: int) -> float:
    return float(DEFAULT_LEVEL_ODDS.get(level, {}).get(cost, 0))


def _classify_report(
    chase_input: ChaseInput,
    *,
    needed: int,
    remaining_target: int,
    probability: float,
    roll_budget: int,
    gold_after_visible: int,
    future_buy_gold: int,
    cost_odds_percent: float,
) -> tuple[str, str, str]:
    if needed <= 0:
        return "complete", "已经能成三星。", "先买下可见牌，停止无意义D牌，转为保血和站位。"
    if remaining_target < needed:
        return "impossible", "牌库剩余不够，不能硬追。", "先侦查同行或等对手被淘汰，否则这波数学上补不齐。"
    if cost_odds_percent <= 0:
        return "impossible", "当前等级刷不到这个费用。", "先升人口，不要在这个等级追。"
    if gold_after_visible < future_buy_gold:
        return "danger", "买牌金币都不够，不能追。", "至少先留出买到目标牌所需金币，再考虑D牌。"
    if roll_budget < chase_input.roll_cost:
        return "danger", "可D金币不足。", "这波最多只能等自然商店，不适合all in。"
    if probability >= 0.7:
        return "good", "概率不错，可以追。", "如果血量安全且这是主C/主坦，允许这波大D。"
    if probability >= 0.45:
        return "medium", "可以追，但要设止损。", "建议边D边看命中，没到关键张数就保留转阵容空间。"
    if probability >= 0.2:
        return "risky", "风险偏高。", "除非已经锁定前二或必须赌命，否则别把经济一次打空。"
    return "avoid", "概率很低，不建议硬追。", "优先升人口、补质量或转向当前S阵容更稳定的主线。"


def _build_notes(
    chase_input: ChaseInput,
    cost_odds_percent: float,
    future_buy_gold: int,
    gold_after_visible: int,
) -> tuple[str, ...]:
    notes: list[str] = []
    if chase_input.cost not in DEFAULT_FOCUS_COSTS:
        notes.append("模块8主要为4/5费设计，低费牌仅作参考。")
    notes.append(f"本次按{chase_input.level}级{chase_input.cost}费概率{cost_odds_percent:.1f}%估算。")
    notes.append(f"保守预留未来买牌金币{future_buy_gold}。")
    if gold_after_visible < future_buy_gold:
        notes.append("当前金币不足以买齐所有剩余目标牌。")
    if chase_input.cost_odds_percent is None:
        notes.append("如果游戏内概率条不同，请用 --cost-odds 覆盖。")
    return tuple(notes)
