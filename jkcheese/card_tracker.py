from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Iterable

from .lineups import Lineup, LineupRecommendation, recommend_lineups


DEFAULT_CARD_STATE_PATH = Path("captures") / "card_state.json"
DEFAULT_POOL_SIZES = {1: 30, 2: 25, 3: 18, 4: 10, 5: 9}
TOKEN_SPLIT_RE = re.compile(r"[\s,，、/|;；]+")
COUNT_SUFFIX_RE = re.compile(r"^(?P<name>.+?)(?:[xX*×=])(?P<count>\d+)$")
COST_PREFIX_RE = re.compile(r"^(?P<cost>[1-5一二三四五])费(?P<name>.+)$")
COST_SUFFIX_RE = re.compile(r"^(?P<name>.+?)(?P<cost>[1-5一二三四五])费$")
COST_MARK_RE = re.compile(r"^(?P<name>.+?)[@#:]?(?:cost|c|费)?(?P<cost>[1-5一二三四五])$", re.IGNORECASE)
COST_ONLY_RE = re.compile(r"^(?P<cost>[1-5一二三四五])费$")
DEFAULT_FOCUS_COSTS = (4, 5)
CHINESE_COSTS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
STATE_VERSION = 1


class CardTrackerError(RuntimeError):
    """Raised when the local card tracker state cannot be read or written."""


@dataclass(slots=True)
class CardTrackerState:
    counts: dict[str, int] = field(default_factory=dict)
    costs: dict[str, int] = field(default_factory=dict)
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class ParsedTokenCount:
    token: str
    count: int
    cost: int | None = None


@dataclass(frozen=True, slots=True)
class UpgradeWarning:
    token: str
    count: int
    cost: int | None
    pool_size: int | None
    severity: str
    title: str
    detail: str
    matched_lineups: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CoreAdviceReport:
    state: CardTrackerState
    state_path: Path
    seen_tokens: tuple[str, ...]
    owned_updates: tuple[ParsedTokenCount, ...]
    recommendation_tokens: tuple[str, ...]
    focus_costs: tuple[int, ...]
    pool_sizes: dict[int, int]
    warnings: tuple[UpgradeWarning, ...]
    recommendations: tuple[LineupRecommendation, ...]


def normalize_tokens(values: str | Iterable[str]) -> tuple[str, ...]:
    """Split user-entered shop/bench text into stable tokens."""

    if isinstance(values, str):
        raw_values = TOKEN_SPLIT_RE.split(values)
    else:
        raw_values = []
        for value in values:
            raw_values.extend(TOKEN_SPLIT_RE.split(str(value)))

    tokens: list[str] = []
    for value in raw_values:
        token = value.strip()
        if token:
            tokens.append(token)
    return tuple(tokens)


def parse_owned_counts(values: str | Iterable[str]) -> tuple[ParsedTokenCount, ...]:
    """Parse owned cards such as Vexx7, 4费Vexx7, 五费Vex=3, or Vex@4x7."""

    totals: dict[str, int] = {}
    costs: dict[str, int] = {}
    pending_cost: int | None = None
    for token in normalize_tokens(values):
        cost_only = COST_ONLY_RE.match(token)
        if cost_only:
            pending_cost = _parse_cost(cost_only.group("cost"))
            continue

        name, count, cost = _parse_owned_token(token)
        if cost is None and pending_cost is not None:
            cost = pending_cost
        pending_cost = None

        if not name or count <= 0:
            continue
        totals[name] = totals.get(name, 0) + count
        if cost is not None:
            costs[name] = cost
    return tuple(ParsedTokenCount(token=token, count=count, cost=costs.get(token)) for token, count in totals.items())


def load_card_state(path: Path = DEFAULT_CARD_STATE_PATH) -> CardTrackerState:
    if not path.exists():
        return CardTrackerState()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CardTrackerError(f"Could not read card tracker state: {path}") from exc

    raw_counts = payload.get("counts", {})
    if not isinstance(raw_counts, dict):
        raw_counts = {}
    raw_costs = payload.get("costs", {})
    if not isinstance(raw_costs, dict):
        raw_costs = {}

    counts: dict[str, int] = {}
    for token, count in raw_counts.items():
        try:
            normalized_count = int(count)
        except (TypeError, ValueError):
            continue
        if normalized_count > 0:
            counts[str(token)] = normalized_count

    costs: dict[str, int] = {}
    for token, cost in raw_costs.items():
        try:
            normalized_cost = int(cost)
        except (TypeError, ValueError):
            continue
        if normalized_cost in range(1, 6) and str(token) in counts:
            costs[str(token)] = normalized_cost

    updated_at = str(payload.get("updated_at", ""))
    return CardTrackerState(counts=counts, costs=costs, updated_at=updated_at)


def save_card_state(state: CardTrackerState, path: Path = DEFAULT_CARD_STATE_PATH) -> None:
    payload = {
        "version": STATE_VERSION,
        "updated_at": state.updated_at,
        "counts": dict(sorted(state.counts.items(), key=lambda item: (-item[1], item[0]))),
        "costs": dict(sorted(state.costs.items(), key=lambda item: item[0])),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise CardTrackerError(f"Could not write card tracker state: {path}") from exc


def reset_card_state(path: Path = DEFAULT_CARD_STATE_PATH) -> CardTrackerState:
    state = CardTrackerState(updated_at=_now())
    save_card_state(state, path)
    return state


def apply_owned_counts(
    state: CardTrackerState,
    owned: str | Iterable[str],
    *,
    mode: str = "add",
) -> tuple[ParsedTokenCount, ...]:
    updates = parse_owned_counts(owned)
    if mode not in {"add", "replace"}:
        raise CardTrackerError(f"Unknown card tracking mode: {mode}")

    if mode == "replace":
        state.counts = {}
        state.costs = {}

    for item in updates:
        if mode == "add":
            state.counts[item.token] = state.counts.get(item.token, 0) + item.count
        else:
            state.counts[item.token] = item.count
        if item.cost is not None:
            state.costs[item.token] = item.cost

    if updates or mode == "replace":
        state.updated_at = _now()
    return updates


def build_upgrade_warnings(
    state: CardTrackerState,
    lineups: tuple[Lineup, ...] = (),
    focus_costs: tuple[int, ...] = DEFAULT_FOCUS_COSTS,
    pool_sizes: dict[int, int] | None = None,
) -> tuple[UpgradeWarning, ...]:
    resolved_pool_sizes = _normalize_pool_sizes(pool_sizes)
    warnings: list[UpgradeWarning] = []
    for token, count in sorted(state.counts.items(), key=lambda item: (-item[1], item[0])):
        cost = state.costs.get(token)
        warning = _warning_for_count(
            token,
            count,
            cost,
            _matching_lineup_names(token, lineups),
            focus_costs,
            resolved_pool_sizes,
        )
        if warning is not None:
            warnings.append(warning)
    return tuple(warnings)


def build_core_advice(
    *,
    state_path: Path = DEFAULT_CARD_STATE_PATH,
    lineups: tuple[Lineup, ...] = (),
    seen: str | Iterable[str] = (),
    owned: str | Iterable[str] = (),
    mode: str = "add",
    reset: bool = False,
    limit: int = 5,
    focus_costs: tuple[int, ...] = DEFAULT_FOCUS_COSTS,
    pool_sizes: dict[int, int] | None = None,
) -> CoreAdviceReport:
    resolved_pool_sizes = _normalize_pool_sizes(pool_sizes)
    state = CardTrackerState(updated_at=_now()) if reset else load_card_state(state_path)
    owned_updates = apply_owned_counts(state, owned, mode=mode)
    if reset and not owned_updates:
        state.updated_at = _now()
    save_card_state(state, state_path)

    seen_tokens = normalize_tokens(seen)
    recommendation_tokens = _unique((*seen_tokens, *state.counts.keys()))
    recommendations = recommend_lineups(lineups, recommendation_tokens, limit=limit) if lineups else ()
    warnings = build_upgrade_warnings(state, lineups, focus_costs=focus_costs, pool_sizes=resolved_pool_sizes)

    return CoreAdviceReport(
        state=state,
        state_path=state_path,
        seen_tokens=seen_tokens,
        owned_updates=owned_updates,
        recommendation_tokens=recommendation_tokens,
        focus_costs=focus_costs,
        pool_sizes=resolved_pool_sizes,
        warnings=warnings,
        recommendations=recommendations,
    )


def format_core_advice(report: CoreAdviceReport) -> str:
    lines: list[str] = []
    if report.seen_tokens:
        lines.append("Live tokens: " + ", ".join(report.seen_tokens))
    if report.owned_updates:
        updates = ", ".join(f"{_display_token(item.token, item.cost)}+{item.count}" for item in report.owned_updates)
        lines.append("Owned update: " + updates)
    lines.append("Focus costs: " + ", ".join(f"{cost}-cost" for cost in report.focus_costs))
    lines.append("Pool sizes: " + _format_pool_sizes(report.pool_sizes))

    if report.state.counts:
        counts = ", ".join(
            f"{_display_token(token, report.state.costs.get(token))}={count}"
            for token, count in _sorted_counts(report.state.counts)
        )
        lines.append("Tracked copies: " + counts)
    else:
        lines.append("Tracked copies: none")

    lines.append("")
    lines.append("Upgrade warnings:")
    if report.warnings:
        for warning in report.warnings:
            related = f" | S line: {', '.join(warning.matched_lineups)}" if warning.matched_lineups else ""
            pool = f" | pool: {warning.count}/{warning.pool_size}" if warning.pool_size is not None else ""
            lines.append(f"- [{warning.severity}] {warning.title}: {warning.detail}{pool}{related}")
    else:
        lines.append("- No focused 4/5-cost pair or three-star warning yet.")

    if report.recommendations:
        lines.append("")
        lines.append("S lineup recommendations:")
        for item in report.recommendations:
            matched = f" | matched: {', '.join(item.matched_tokens)}" if item.matched_tokens else ""
            notes = f" | notes: {'; '.join(item.lineup.notes)}" if item.lineup.notes else ""
            lines.append(f"- [{item.lineup.tier}] {item.lineup.name} (score {item.score}){matched}{notes}")
            lines.append(f"  reason: {item.reason}")

    lines.append("")
    lines.append(f"State file: {report.state_path.resolve()}")
    return "\n".join(lines)


def _warning_for_count(
    token: str,
    count: int,
    cost: int | None,
    matched_lineups: tuple[str, ...],
    focus_costs: tuple[int, ...],
    pool_sizes: dict[int, int],
) -> UpgradeWarning | None:
    related = " This token appears in a current S-tier lineup." if matched_lineups else ""
    cost_label = f"{cost}-cost " if cost is not None else ""
    display = f"{cost_label}{token}"
    pool_size = pool_sizes.get(cost) if cost is not None else None
    pool_note = ""
    if pool_size is not None:
        remaining_self = max(0, 9 - count)
        remaining_pool = max(0, pool_size - count)
        pool_note = f" Public pool for a {cost}-cost unit is about {pool_size}; you hold {count}, need {remaining_self} for 3-star, and at most {remaining_pool} are untracked."

    if cost is not None and cost not in focus_costs and count < 9:
        return None

    if count >= 9:
        return UpgradeWarning(
            token=token,
            count=count,
            cost=cost,
            pool_size=pool_size,
            severity="complete",
            title=f"{display} three-star complete",
            detail=f"{count}/9 copies tracked. Stop chasing extra copies and protect economy/positioning.{pool_note}{related}",
            matched_lineups=matched_lineups,
        )
    if count == 8:
        return UpgradeWarning(
            token=token,
            count=count,
            cost=cost,
            pool_size=pool_size,
            severity="critical",
            title=f"{display} one copy from three-star",
            detail=f"{count}/9 copies tracked. Buy/hold this immediately if it is part of your S-line plan.{pool_note}{related}",
            matched_lineups=matched_lineups,
        )
    if count == 7:
        return UpgradeWarning(
            token=token,
            count=count,
            cost=cost,
            pool_size=pool_size,
            severity="critical" if cost in {4, 5} else "high",
            title=f"{display} two copies from three-star",
            detail=f"{count}/9 copies tracked. Protect bench space, scout duplicates, and plan reroll timing.{pool_note}{related}",
            matched_lineups=matched_lineups,
        )
    if count == 6:
        return UpgradeWarning(
            token=token,
            count=count,
            cost=cost,
            pool_size=pool_size,
            severity="high" if cost in {4, 5} else "medium",
            title=f"{display} three-star setup",
            detail=f"{count}/9 copies tracked. For 4/5-cost carries, start deciding whether the chase is worth economy and HP.{pool_note}{related}",
            matched_lineups=matched_lineups,
        )
    if count in {4, 5} and cost in {4, 5}:
        return UpgradeWarning(
            token=token,
            count=count,
            cost=cost,
            pool_size=pool_size,
            severity="high" if cost == 5 else "medium",
            title=f"{display} expensive three-star angle",
            detail=f"{count}/9 copies tracked. This is early but valuable for 4/5-cost monitoring; hold if bench/economy allow.{pool_note}{related}",
            matched_lineups=matched_lineups,
        )
    if count == 3:
        return UpgradeWarning(
            token=token,
            count=count,
            cost=cost,
            pool_size=pool_size,
            severity="high" if cost == 5 else "medium",
            title=f"{display} two-star ready",
            detail=f"{count}/9 copies tracked. Upgrade first, then decide whether a 4/5-cost three-star chase is realistic.{pool_note}{related}",
            matched_lineups=matched_lineups,
        )
    if count == 2 and cost in {4, 5}:
        return UpgradeWarning(
            token=token,
            count=count,
            cost=cost,
            pool_size=pool_size,
            severity="medium" if cost == 5 else "info",
            title=f"{display} expensive pair",
            detail=f"{count}/9 copies tracked. Watch shops closely; high-cost pairs are the start of real win-condition pivots.{pool_note}{related}",
            matched_lineups=matched_lineups,
        )
    return None


def _matching_lineup_names(token: str, lineups: tuple[Lineup, ...]) -> tuple[str, ...]:
    needle = token.casefold()
    matches: list[str] = []
    for lineup in lineups:
        haystack = " ".join((lineup.name, lineup.code_title, lineup.code, *lineup.notes)).casefold()
        if needle and needle in haystack:
            matches.append(lineup.name)
    return tuple(matches[:3])


def _parse_owned_token(token: str) -> tuple[str, int, int | None]:
    count = 1
    name = token.strip()
    count_match = COUNT_SUFFIX_RE.match(name)
    if count_match:
        name = count_match.group("name").strip()
        count = int(count_match.group("count"))

    cost: int | None = None
    for pattern in (COST_PREFIX_RE, COST_SUFFIX_RE, COST_MARK_RE):
        match = pattern.match(name)
        if match:
            name = match.group("name").strip()
            cost = _parse_cost(match.group("cost"))
            break

    return name, count, cost


def _parse_cost(value: str) -> int | None:
    if value in CHINESE_COSTS:
        return CHINESE_COSTS[value]
    try:
        cost = int(value)
    except ValueError:
        return None
    return cost if cost in range(1, 6) else None


def _normalize_pool_sizes(pool_sizes: dict[int, int] | None) -> dict[int, int]:
    resolved = dict(DEFAULT_POOL_SIZES)
    if pool_sizes:
        for cost, pool_size in pool_sizes.items():
            if int(cost) in range(1, 6) and int(pool_size) > 0:
                resolved[int(cost)] = int(pool_size)
    return resolved


def _display_token(token: str, cost: int | None) -> str:
    return f"{token}({cost}费)" if cost is not None else f"{token}(费用未知)"


def _format_pool_sizes(pool_sizes: dict[int, int]) -> str:
    return ", ".join(f"{cost}-cost={pool_sizes[cost]}" for cost in sorted(pool_sizes))


def _sorted_counts(counts: dict[str, int]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _unique(tokens: Iterable[str]) -> tuple[str, ...]:
    unique_tokens: list[str] = []
    for token in tokens:
        cleaned = token.strip()
        if cleaned and cleaned not in unique_tokens:
            unique_tokens.append(cleaned)
    return tuple(unique_tokens)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
