from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Iterable

from .lineups import Lineup, LineupRecommendation, recommend_lineups


DEFAULT_CARD_STATE_PATH = Path("captures") / "card_state.json"
TOKEN_SPLIT_RE = re.compile(r"[\s,，、/|;；]+")
COUNT_SUFFIX_RE = re.compile(r"^(?P<name>.+?)(?:[xX*×:=：])(?P<count>\d+)$")
STATE_VERSION = 1


class CardTrackerError(RuntimeError):
    """Raised when the local card tracker state cannot be read or written."""


@dataclass(slots=True)
class CardTrackerState:
    counts: dict[str, int] = field(default_factory=dict)
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class ParsedTokenCount:
    token: str
    count: int


@dataclass(frozen=True, slots=True)
class UpgradeWarning:
    token: str
    count: int
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
    """Parse owned card counts such as Vexx7, Vex=7, or repeated Vex tokens."""

    totals: dict[str, int] = {}
    for token in normalize_tokens(values):
        match = COUNT_SUFFIX_RE.match(token)
        if match:
            name = match.group("name").strip()
            count = int(match.group("count"))
        else:
            name = token
            count = 1
        if not name or count <= 0:
            continue
        totals[name] = totals.get(name, 0) + count
    return tuple(ParsedTokenCount(token=token, count=count) for token, count in totals.items())


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

    counts: dict[str, int] = {}
    for token, count in raw_counts.items():
        try:
            normalized_count = int(count)
        except (TypeError, ValueError):
            continue
        if normalized_count > 0:
            counts[str(token)] = normalized_count

    updated_at = str(payload.get("updated_at", ""))
    return CardTrackerState(counts=counts, updated_at=updated_at)


def save_card_state(state: CardTrackerState, path: Path = DEFAULT_CARD_STATE_PATH) -> None:
    payload = {
        "version": STATE_VERSION,
        "updated_at": state.updated_at,
        "counts": dict(sorted(state.counts.items(), key=lambda item: (-item[1], item[0]))),
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

    for item in updates:
        if mode == "add":
            state.counts[item.token] = state.counts.get(item.token, 0) + item.count
        else:
            state.counts[item.token] = item.count

    if updates or mode == "replace":
        state.updated_at = _now()
    return updates


def build_upgrade_warnings(
    state: CardTrackerState,
    lineups: tuple[Lineup, ...] = (),
) -> tuple[UpgradeWarning, ...]:
    warnings: list[UpgradeWarning] = []
    for token, count in sorted(state.counts.items(), key=lambda item: (-item[1], item[0])):
        warning = _warning_for_count(token, count, _matching_lineup_names(token, lineups))
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
) -> CoreAdviceReport:
    state = CardTrackerState(updated_at=_now()) if reset else load_card_state(state_path)
    owned_updates = apply_owned_counts(state, owned, mode=mode)
    if reset and not owned_updates:
        state.updated_at = _now()
    save_card_state(state, state_path)

    seen_tokens = normalize_tokens(seen)
    recommendation_tokens = _unique((*seen_tokens, *state.counts.keys()))
    recommendations = recommend_lineups(lineups, recommendation_tokens, limit=limit) if lineups else ()
    warnings = build_upgrade_warnings(state, lineups)

    return CoreAdviceReport(
        state=state,
        state_path=state_path,
        seen_tokens=seen_tokens,
        owned_updates=owned_updates,
        recommendation_tokens=recommendation_tokens,
        warnings=warnings,
        recommendations=recommendations,
    )


def format_core_advice(report: CoreAdviceReport) -> str:
    lines: list[str] = []
    if report.seen_tokens:
        lines.append("Live tokens: " + ", ".join(report.seen_tokens))
    if report.owned_updates:
        updates = ", ".join(f"{item.token}+{item.count}" for item in report.owned_updates)
        lines.append("Owned update: " + updates)

    if report.state.counts:
        counts = ", ".join(f"{token}={count}" for token, count in _sorted_counts(report.state.counts))
        lines.append("Tracked copies: " + counts)
    else:
        lines.append("Tracked copies: none")

    lines.append("")
    lines.append("Upgrade warnings:")
    if report.warnings:
        for warning in report.warnings:
            related = f" | S line: {', '.join(warning.matched_lineups)}" if warning.matched_lineups else ""
            lines.append(f"- [{warning.severity}] {warning.title}: {warning.detail}{related}")
    else:
        lines.append("- No pair or three-star warning yet.")

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


def _warning_for_count(token: str, count: int, matched_lineups: tuple[str, ...]) -> UpgradeWarning | None:
    related = " This token appears in a current S-tier lineup." if matched_lineups else ""
    if count >= 9:
        return UpgradeWarning(
            token=token,
            count=count,
            severity="complete",
            title=f"{token} three-star complete",
            detail=f"{count}/9 copies tracked. Stop chasing extra copies and protect economy/positioning.{related}",
            matched_lineups=matched_lineups,
        )
    if count == 8:
        return UpgradeWarning(
            token=token,
            count=count,
            severity="critical",
            title=f"{token} one copy from three-star",
            detail=f"{count}/9 copies tracked. Buy/hold this if it is part of your S-line plan.{related}",
            matched_lineups=matched_lineups,
        )
    if count == 7:
        return UpgradeWarning(
            token=token,
            count=count,
            severity="high",
            title=f"{token} close to three-star",
            detail=f"{count}/9 copies tracked. Start protecting bench space and reroll timing.{related}",
            matched_lineups=matched_lineups,
        )
    if count == 6:
        return UpgradeWarning(
            token=token,
            count=count,
            severity="medium",
            title=f"{token} three-star setup",
            detail=f"{count}/9 copies tracked. You are entering real three-star territory.{related}",
            matched_lineups=matched_lineups,
        )
    if 3 <= count <= 5:
        return UpgradeWarning(
            token=token,
            count=count,
            severity="medium",
            title=f"{token} two-star ready",
            detail=f"{count}/9 copies tracked. Stabilize the upgraded unit before over-rerolling.{related}",
            matched_lineups=matched_lineups,
        )
    if count == 2:
        return UpgradeWarning(
            token=token,
            count=count,
            severity="info",
            title=f"{token} pair",
            detail=f"{count}/9 copies tracked. Watch the next shops for a quick upgrade.{related}",
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
