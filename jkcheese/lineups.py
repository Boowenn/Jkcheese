from __future__ import annotations

from dataclasses import dataclass
import re
import time
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import json

from .proto_sheet import ProtoSheetError, decode_related_sheet


DEFAULT_LINEUP_URL = "https://docs.qq.com/sheet/DTmFrR3dDWVBsYmxo?tab=99oz3s"
DEFAULT_TAB_ID = "99oz3s"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class LineupSourceError(RuntimeError):
    """Raised when the live lineup source cannot be loaded."""


@dataclass(frozen=True, slots=True)
class Lineup:
    name: str
    tier: str
    notes: tuple[str, ...] = ()
    code: str = ""
    source_row: int | None = None

    @property
    def code_title(self) -> str:
        match = re.search(r"【阵容码】#([^#]+)#", self.code)
        return match.group(1) if match else ""


@dataclass(frozen=True, slots=True)
class LineupRecommendation:
    lineup: Lineup
    score: int
    matched_tokens: tuple[str, ...]
    reason: str


def fetch_jcc_s_lineups(url: str = DEFAULT_LINEUP_URL, timeout: int = 20) -> tuple[Lineup, ...]:
    """Fetch S-tier Golden Spatula lineups from the public Tencent Docs sheet."""

    doc_id, tab_id = parse_docs_url(url)
    payload = _fetch_opendoc(doc_id, tab_id, url, timeout)
    try:
        related_sheet = payload["clientVars"]["collab_client_vars"]["initialAttributedText"]["text"][0]["related_sheet"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LineupSourceError("Tencent Docs response did not contain sheet data.") from exc

    try:
        grid = decode_related_sheet(related_sheet)
    except ProtoSheetError as exc:
        raise LineupSourceError(str(exc)) from exc
    return extract_s_lineups_from_grid(grid)


def parse_docs_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    doc_id = parsed.path.rstrip("/").split("/")[-1]
    tab = parse_qs(parsed.query).get("tab", [DEFAULT_TAB_ID])[0]
    if not doc_id:
        raise LineupSourceError("Tencent Docs URL is missing a document id.")
    return doc_id, tab or DEFAULT_TAB_ID


def extract_s_lineups_from_grid(grid: dict[int, dict[int, str]]) -> tuple[Lineup, ...]:
    marker_row = _find_marker_row(grid)
    if marker_row is None:
        raise LineupSourceError("Could not find the S lineup section marker in 实时铲榜.")

    lineups: list[Lineup] = []
    for row in range(marker_row + 1, max(grid.keys(), default=marker_row) + 1):
        name_cell = grid.get(row, {}).get(0, "")
        if not name_cell and lineups:
            break
        if not _looks_like_lineup_name(name_cell):
            if lineups:
                break
            continue
        name, inline_notes = _split_name_and_notes(name_cell)
        row_values = tuple(grid.get(row, {}).values())
        code = _first_code(row_values)
        notes = tuple(dict.fromkeys((*inline_notes, *_row_notes(row_values, name, code))))
        lineups.append(Lineup(name=name, tier="S", notes=notes, code=code, source_row=row))

    if not lineups:
        raise LineupSourceError("No S lineups were found in 实时铲榜.")
    return tuple(lineups)


def recommend_lineups(lineups: tuple[Lineup, ...], seen: str | tuple[str, ...] = (), limit: int = 5) -> tuple[LineupRecommendation, ...]:
    tokens = _normalize_seen(seen)
    recommendations: list[LineupRecommendation] = []
    for index, lineup in enumerate(lineups):
        haystack = " ".join((lineup.name, lineup.code_title, *lineup.notes))
        matched = tuple(token for token in tokens if token and token in haystack)
        score = len(matched) * 10 + max(0, 5 - index)
        if matched:
            reason = "Matched live tokens: " + ", ".join(matched)
        elif tokens:
            reason = "No supplied live tokens matched this lineup; falling back to 实时铲榜 order."
        else:
            reason = "No live card tokens supplied yet; keeping source order from 实时铲榜."
        recommendations.append(LineupRecommendation(lineup=lineup, score=score, matched_tokens=matched, reason=reason))

    recommendations.sort(key=lambda item: (-item.score, lineups.index(item.lineup)))
    return tuple(recommendations[:limit])


def _fetch_opendoc(doc_id: str, tab_id: str, source_url: str, timeout: int) -> dict:
    query = (
        "https://docs.qq.com/dop-api/opendoc?"
        f"outformat=1&normal=1&preview_token=&t={int(time.time() * 1000)}&id={doc_id}&tab={tab_id}"
    )
    request = Request(query, headers={"User-Agent": USER_AGENT, "Referer": source_url})
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset)
    except OSError as exc:
        raise LineupSourceError(f"Failed to fetch Tencent Docs lineup data: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise LineupSourceError("Tencent Docs lineup response was not JSON.") from exc


def _find_marker_row(grid: dict[int, dict[int, str]]) -> int | None:
    for row in sorted(grid):
        if any("↑神器" in value for value in grid[row].values()):
            return row
    return None


def _looks_like_lineup_name(value: str) -> bool:
    if not value:
        return False
    if "BUG" in value or "【阵容码】" in value or "http" in value:
        return False
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _split_name_and_notes(value: str) -> tuple[str, tuple[str, ...]]:
    parts = [_normalize_display_text(part) for part in value.split(" / ") if part.strip()]
    if not parts:
        return _normalize_display_text(value), ()
    return parts[0], tuple(parts[1:])


def _normalize_display_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _first_code(values: tuple[str, ...]) -> str:
    for value in values:
        if "【阵容码】" in value:
            return value.strip()
    return ""


def _row_notes(values: tuple[str, ...], name: str, code: str) -> tuple[str, ...]:
    notes: list[str] = []
    for value in values:
        normalized_value = _normalize_display_text(value)
        if not normalized_value or normalized_value == name or value == code:
            continue
        if "【阵容码】" in value or "http" in value:
            continue
        if normalized_value.startswith(f"{name} / "):
            continue
        if any(part in value for part in ("BUG", "FF175CEB")):
            continue
        if value.startswith("[") or value.startswith("$"):
            continue
        if any("\u4e00" <= char <= "\u9fff" for char in value):
            notes.append(normalized_value)
    return tuple(notes)


def _normalize_seen(seen: str | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(seen, str):
        raw_tokens = re.split(r"[\s,，、;；|/]+", seen)
    else:
        raw_tokens = list(seen)
    tokens: list[str] = []
    for token in raw_tokens:
        cleaned = token.strip()
        if cleaned and cleaned not in tokens:
            tokens.append(cleaned)
    return tuple(tokens)
