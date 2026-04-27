from __future__ import annotations

from dataclasses import dataclass

from .card_tracker import CardTrackerState, DEFAULT_FOCUS_COSTS, DEFAULT_POOL_SIZES
from .lineups import Lineup
from .shop_recognition import ShopScanReport, ShopSlotReading, is_trusted_shop_name


@dataclass(frozen=True, slots=True)
class ShopHitAlert:
    slot: int
    name: str
    cost: int | None
    current_count: int
    after_buy_count: int
    severity: str
    title: str
    detail: str
    matched_lineups: tuple[str, ...] = ()


def build_shop_hit_alerts(
    report: ShopScanReport,
    state: CardTrackerState,
    *,
    lineups: tuple[Lineup, ...] = (),
    focus_costs: tuple[int, ...] = DEFAULT_FOCUS_COSTS,
    pool_sizes: dict[int, int] | None = None,
) -> tuple[ShopHitAlert, ...]:
    resolved_pool_sizes = _normalize_pool_sizes(pool_sizes)
    alerts: list[ShopHitAlert] = []
    for reading in report.slots:
        if not is_trusted_shop_name(reading):
            continue
        alert = _alert_for_reading(
            reading,
            state,
            lineups=lineups,
            focus_costs=focus_costs,
            pool_sizes=resolved_pool_sizes,
        )
        if alert is not None:
            alerts.append(alert)
    return tuple(alerts)


def format_shop_hit_alerts(alerts: tuple[ShopHitAlert, ...]) -> str:
    lines = ["Shop-hit 提醒:"]
    if not alerts:
        lines.append("- 暂无必须买的关键牌；继续观察 S 阵容牌、4费和5费追三牌。")
        return "\n".join(lines)

    for alert in alerts:
        lineups = f" | S阵容: {', '.join(alert.matched_lineups)}" if alert.matched_lineups else ""
        cost = f"{alert.cost}费" if alert.cost is not None else "费用未知"
        lines.append(
            f"- [{alert.severity}] 槽位{alert.slot} {alert.name}({cost}): {alert.title} "
            f"{alert.detail}{lineups}"
        )
    return "\n".join(lines)


def _alert_for_reading(
    reading: ShopSlotReading,
    state: CardTrackerState,
    *,
    lineups: tuple[Lineup, ...],
    focus_costs: tuple[int, ...],
    pool_sizes: dict[int, int],
) -> ShopHitAlert | None:
    name = reading.name
    cost = reading.cost if reading.cost is not None else state.costs.get(name)
    current = state.counts.get(name, 0)
    after_buy = current + 1
    matched_lineups = _matching_lineups(name, lineups)
    pool_note = _pool_note(cost, current, after_buy, pool_sizes)

    if current >= 9:
        return ShopHitAlert(
            slot=reading.slot,
            name=name,
            cost=cost,
            current_count=current,
            after_buy_count=current,
            severity="skip",
            title="已经三星，通常不用再买。",
            detail=pool_note,
            matched_lineups=matched_lineups,
        )
    if current == 8:
        return ShopHitAlert(
            slot=reading.slot,
            name=name,
            cost=cost,
            current_count=current,
            after_buy_count=after_buy,
            severity="critical",
            title="立刻买这张，买下就是9/9三星。",
            detail=pool_note,
            matched_lineups=matched_lineups,
        )
    if current == 7:
        severity = "critical" if cost in focus_costs else "high"
        return ShopHitAlert(
            slot=reading.slot,
            name=name,
            cost=cost,
            current_count=current,
            after_buy_count=after_buy,
            severity=severity,
            title="强烈建议买这张，买后8/9只差最后一张。",
            detail=pool_note,
            matched_lineups=matched_lineups,
        )
    if current in {5, 6}:
        severity = "high" if cost in focus_costs else "medium"
        return ShopHitAlert(
            slot=reading.slot,
            name=name,
            cost=cost,
            current_count=current,
            after_buy_count=after_buy,
            severity=severity,
            title="建议买这张，追三进度进入关键区。",
            detail=pool_note,
            matched_lineups=matched_lineups,
        )
    if current == 2:
        return ShopHitAlert(
            slot=reading.slot,
            name=name,
            cost=cost,
            current_count=current,
            after_buy_count=after_buy,
            severity="medium",
            title="可以买，买下可凑二星。",
            detail=pool_note,
            matched_lineups=matched_lineups,
        )
    if matched_lineups:
        severity = "medium" if cost in focus_costs or current > 0 else "info"
        return ShopHitAlert(
            slot=reading.slot,
            name=name,
            cost=cost,
            current_count=current,
            after_buy_count=after_buy,
            severity=severity,
            title="命中当前 S 阵容关键词，经济允许就优先买/留。",
            detail=pool_note,
            matched_lineups=matched_lineups,
        )
    if cost in focus_costs and current > 0:
        return ShopHitAlert(
            slot=reading.slot,
            name=name,
            cost=cost,
            current_count=current,
            after_buy_count=after_buy,
            severity="info",
            title="高费牌已有进度，可以买下继续观察追三窗口。",
            detail=pool_note,
            matched_lineups=matched_lineups,
        )
    return None


def _pool_note(cost: int | None, current: int, after_buy: int, pool_sizes: dict[int, int]) -> str:
    progress = f"已记录{current}张，买后{after_buy}/9。"
    if cost is None:
        return progress
    pool_size = pool_sizes.get(cost)
    if pool_size is None:
        return progress
    remaining = max(0, pool_size - current)
    return f"{progress}当前按{cost}费牌库约{pool_size}张估算，未记录剩余最多约{remaining}张。"


def _matching_lineups(name: str, lineups: tuple[Lineup, ...]) -> tuple[str, ...]:
    needle = name.casefold()
    matches: list[str] = []
    for lineup in lineups:
        haystack = " ".join((lineup.name, lineup.code_title, lineup.code, *lineup.notes, *lineup.champions)).casefold()
        if needle and needle in haystack:
            matches.append(lineup.name)
    return tuple(matches[:3])


def _normalize_pool_sizes(pool_sizes: dict[int, int] | None) -> dict[int, int]:
    resolved = dict(DEFAULT_POOL_SIZES)
    if pool_sizes:
        for cost, pool_size in pool_sizes.items():
            if int(cost) in range(1, 6) and int(pool_size) > 0:
                resolved[int(cost)] = int(pool_size)
    return resolved
