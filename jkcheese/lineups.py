from __future__ import annotations

from dataclasses import dataclass
import csv
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import json
from xml.etree import ElementTree
from zipfile import ZipFile

from .proto_sheet import ProtoSheetError, decode_related_sheet


DEFAULT_LINEUP_URL = "https://docs.qq.com/sheet/DTmFrR3dDWVBsYmxo?tab=99oz3s"
DEFAULT_TAB_ID = "99oz3s"
DEFAULT_LOCAL_LINEUP_FILES = (
    "lineups.xlsx",
    "lineups.csv",
    "阵容码.xlsx",
    "阵容码.csv",
    "阵容.xlsx",
    "阵容.csv",
)
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
    champions: tuple[str, ...] = ()
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
    """Fetch S and S- Golden Spatula lineups from the public Tencent Docs sheet."""

    local_path = resolve_local_lineup_source(url)
    if local_path is not None:
        return load_lineups_from_file(local_path)
    if url != DEFAULT_LINEUP_URL and not _is_url_source(url):
        raise LineupSourceError(f"Local lineup file was not found: {url}")

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


def _is_url_source(source: str) -> bool:
    return urlparse(source).scheme in {"http", "https"}


def extract_s_lineups_from_grid(grid: dict[int, dict[int, str]]) -> tuple[Lineup, ...]:
    marker_row = _find_marker_row(grid)
    if marker_row is None:
        raise LineupSourceError("Could not find the S lineup section marker in 实时铲榜.")

    lineups: list[Lineup] = []
    block_index = 0
    in_block = False
    for row in range(marker_row + 1, max(grid.keys(), default=marker_row) + 1):
        name_cell = grid.get(row, {}).get(0, "")
        if not name_cell:
            if in_block:
                block_index += 1
                in_block = False
                if block_index >= 2:
                    break
            continue
        if not _looks_like_lineup_name(name_cell):
            if in_block:
                block_index += 1
                in_block = False
                if block_index >= 2:
                    break
            continue
        in_block = True
        name, inline_notes = _split_name_and_notes(name_cell)
        row_values = tuple(grid.get(row, {}).values())
        code = _first_code(row_values)
        notes = tuple(dict.fromkeys((*inline_notes, *_row_notes(row_values, name, code))))
        tier = "S" if block_index == 0 else "S-"
        lineups.append(
            Lineup(name=name, tier=tier, notes=notes, code=code, champions=parse_lineup_code(code), source_row=row)
        )

    if not lineups:
        raise LineupSourceError("No S/S- lineups were found in 实时铲榜.")
    return tuple(lineups)


def recommend_lineups(lineups: tuple[Lineup, ...], seen: str | tuple[str, ...] = (), limit: int = 5) -> tuple[LineupRecommendation, ...]:
    tokens = _normalize_seen(seen)
    recommendations: list[LineupRecommendation] = []
    for index, lineup in enumerate(lineups):
        champion_matches = tuple(token for token in tokens if _token_matches_any(token, lineup.champions))
        haystack = " ".join((lineup.name, lineup.code_title, *lineup.notes))
        text_matches = tuple(token for token in tokens if token and token not in champion_matches and token in haystack)
        matched = (*champion_matches, *text_matches)
        score = len(champion_matches) * 20 + len(text_matches) * 8 + max(0, 5 - index)
        if matched:
            reason = "Matched lineup-code heroes: " + ", ".join(champion_matches)
            if text_matches:
                reason += " | text: " + ", ".join(text_matches)
        elif tokens:
            reason = "No supplied live tokens matched this lineup code; falling back to source order."
        else:
            reason = "No live card tokens supplied yet; keeping source order."
        recommendations.append(LineupRecommendation(lineup=lineup, score=score, matched_tokens=matched, reason=reason))

    recommendations.sort(key=lambda item: (-item.score, lineups.index(item.lineup)))
    return tuple(recommendations[:limit])


LINEUP_CODE_TO_NAME = {
    "01d": "亚托克斯",
    "00e": "贝蕾亚",
    "01b": "凯特琳",
    "045": "科加斯",
    "03e": "伊泽瑞尔",
    "042": "蕾欧娜",
    "046": "丽桑卓",
    "034": "内瑟斯",
    "01a": "波比",
    "068": "雷克塞",
    "02a": "泰隆",
    "033": "提莫",
    "02b": "崔斯特",
    "016": "维迦",
    "00d": "阿卡丽",
    "00f": "卑尔维斯",
    "017": "纳尔",
    "031": "古拉加斯",
    "035": "格温",
    "014": "小木灵",
    "02c": "贾克斯",
    "012": "金克丝",
    "03d": "米利欧",
    "04e": "莫德凯撒",
    "025": "潘森",
    "02d": "派克",
    "041": "佐伊",
    "010": "阿萝拉",
    "043": "黛安娜",
    "015": "菲兹",
    "011": "俄洛伊",
    "020": "卡莎",
    "030": "璐璐",
    "01e": "茂凯",
    "001": "厄运小姐",
    "036": "奥恩",
    "021": "拉亚斯特",
    "032": "莎弥拉",
    "024": "厄加特",
    "02e": "维克托",
    "026": "奥瑞利安索尔",
    "019": "库奇",
    "027": "超级机甲",
    "022": "卡尔玛",
    "01f": "千珏",
    "044": "乐芙兰",
    "02f": "易",
    "037": "娜美",
    "039": "努努和威朗普",
    "018": "拉莫斯",
    "03c": "锐雯",
    "04f": "塔姆",
    "03f": "霞",
    "01c": "巴德",
    "038": "布里茨",
    "013": "菲奥娜",
    "050": "格雷福斯",
    "023": "烬",
    "058": "莫甘娜",
    "03b": "慎",
    "029": "娑娜",
    "03a": "薇古丝",
    "047": "劫",
}

LINEUP_CODE_RE = re.compile(r"02(?:[0-9a-fA-F]{3}){1,12}TFTSet\d+")


def parse_lineup_code(text: str) -> tuple[str, ...]:
    match = LINEUP_CODE_RE.search(text or "")
    if not match:
        return ()
    code = match.group(0)
    suffix_index = code.find("TFTSet")
    hex_core = code[2:suffix_index].lower()
    champions: list[str] = []
    for index in range(0, len(hex_core), 3):
        chunk = hex_core[index : index + 3]
        if chunk == "000":
            continue
        champion = LINEUP_CODE_TO_NAME.get(chunk)
        if champion and champion not in champions:
            champions.append(champion)
    return tuple(champions)


def extract_lineup_code(text: str) -> str:
    match = LINEUP_CODE_RE.search(text or "")
    return match.group(0) if match else ""


def resolve_local_lineup_source(source: str = DEFAULT_LINEUP_URL) -> Path | None:
    candidate = Path(source)
    if candidate.exists() and candidate.is_file():
        return candidate
    if source != DEFAULT_LINEUP_URL:
        return None

    search_roots = [Path.cwd(), Path.cwd() / "data", _appdata_config_dir()]
    for root in search_roots:
        for name in DEFAULT_LOCAL_LINEUP_FILES:
            path = root / name
            if path.exists() and path.is_file():
                return path
    return None


def load_lineups_from_file(path: Path | str) -> tuple[Lineup, ...]:
    source_path = Path(path)
    suffix = source_path.suffix.lower()
    if suffix == ".csv":
        rows = _read_csv_rows(source_path)
    elif suffix == ".xlsx":
        rows = _read_xlsx_rows(source_path)
    else:
        raise LineupSourceError(f"Unsupported local lineup file type: {source_path.suffix}. Use .xlsx or .csv.")
    return extract_lineups_from_rows(rows)


def extract_lineups_from_rows(rows: tuple[tuple[str, ...], ...]) -> tuple[Lineup, ...]:
    lineups: list[Lineup] = []
    for row_number, row in enumerate(rows, start=1):
        values = tuple(_normalize_display_text(value) for value in row if _normalize_display_text(value))
        if not values:
            continue
        row_text = " ".join(values)
        code = extract_lineup_code(row_text)
        if not code:
            continue
        champions = parse_lineup_code(code)
        name = _name_from_row(values, code, row_number)
        tier = _tier_from_row(values)
        notes = tuple(
            value
            for value in values
            if value != name and code not in value and value.upper() not in {"S", "S-", "A", "B"}
        )
        lineups.append(Lineup(name=name, tier=tier, notes=notes, code=code, champions=champions, source_row=row_number))

    if not lineups:
        raise LineupSourceError("No TFTSet lineup codes were found in the local lineup file.")
    return tuple(lineups)


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


def _appdata_config_dir() -> Path:
    return Path.home() / "AppData" / "Roaming" / "Jkcheese"


def _read_csv_rows(path: Path) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for encoding in ("utf-8-sig", "gb18030", "cp936"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                rows = [tuple(cell.strip() for cell in row) for row in csv.reader(handle)]
            return tuple(rows)
        except UnicodeDecodeError:
            continue
    raise LineupSourceError(f"Could not decode local lineup CSV: {path}")


def _read_xlsx_rows(path: Path) -> tuple[tuple[str, ...], ...]:
    namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with ZipFile(path) as workbook:
            shared_strings = _read_shared_strings(workbook, namespace)
            sheet_names = sorted(name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet"))
            rows: list[tuple[str, ...]] = []
            for sheet_name in sheet_names:
                sheet_root = ElementTree.fromstring(workbook.read(sheet_name))
                for row in sheet_root.findall(".//a:sheetData/a:row", namespace):
                    cells: list[str] = []
                    for cell in row.findall("a:c", namespace):
                        cells.append(_xlsx_cell_text(cell, shared_strings, namespace))
                    rows.append(tuple(cells))
            return tuple(rows)
    except (OSError, KeyError, ElementTree.ParseError) as exc:
        raise LineupSourceError(f"Could not read local lineup workbook: {path}") from exc


def _read_shared_strings(workbook: ZipFile, namespace: dict[str, str]) -> tuple[str, ...]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return ()
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("a:si", namespace):
        parts = [node.text or "" for node in item.findall(".//a:t", namespace)]
        strings.append("".join(parts))
    return tuple(strings)


def _xlsx_cell_text(cell: ElementTree.Element, shared_strings: tuple[str, ...], namespace: dict[str, str]) -> str:
    value_node = cell.find("a:v", namespace)
    if value_node is None or value_node.text is None:
        inline_nodes = cell.findall(".//a:is//a:t", namespace)
        return "".join(node.text or "" for node in inline_nodes).strip()
    raw_value = value_node.text
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(raw_value)].strip()
        except (IndexError, ValueError):
            return ""
    return raw_value.strip()


def _name_from_row(values: tuple[str, ...], code: str, row_number: int) -> str:
    for value in values:
        if code in value or extract_lineup_code(value):
            continue
        if value.upper() in {"S", "S-", "A", "B"}:
            continue
        if any("\u4e00" <= char <= "\u9fff" for char in value):
            return value
    return f"阵容{row_number}"


def _tier_from_row(values: tuple[str, ...]) -> str:
    for value in values:
        normalized = value.upper().strip()
        if normalized in {"S", "S-", "A", "B"}:
            return normalized
    return "LOCAL"


def _token_matches_any(token: str, champions: tuple[str, ...]) -> bool:
    if not token:
        return False
    return any(token == champion or token in champion or champion in token for champion in champions)


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
