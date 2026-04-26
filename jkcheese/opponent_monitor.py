from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable

from PIL import Image, ImageStat

from .regions import RegionPreset, default_preset


DEFAULT_OPPONENT_TEMPLATE_PATH = Path("captures") / "opponent_templates.json"
DEFAULT_SCOUT_REGIONS = ("scout_board", "bench")
DEFAULT_SCOUT_THRESHOLD = 0.88
DEFAULT_SCOUT_STRIDE = 18
SCOUT_SIGNATURE_SIZE = (24, 24)
SCOUT_TEMPLATE_VERSION = 1
SCOUT_LABEL_RE = re.compile(
    r"^(?P<name>[^:@=]+?)\s*(?:[:@](?P<cost>[1-5]))?\s*@\s*"
    r"(?P<x>\d+)\s*,\s*(?P<y>\d+)\s*,\s*(?P<w>\d+)\s*,\s*(?P<h>\d+)$"
)


class OpponentMonitorError(RuntimeError):
    """Raised when opponent scout templates or scans cannot be completed."""


@dataclass(frozen=True, slots=True)
class ScoutTemplate:
    name: str
    cost: int | None
    width: int
    height: int
    signature: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ScoutLabel:
    name: str
    cost: int | None
    box: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class ScoutMatch:
    name: str
    cost: int | None
    confidence: float
    region: str
    box: tuple[int, int, int, int]
    crop_path: Path | None = None


@dataclass(frozen=True, slots=True)
class OpponentScoutReport:
    image_path: Path
    templates_path: Path
    template_count: int
    output_dir: Path | None
    matches: tuple[ScoutMatch, ...]

    @property
    def contested_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for match in self.matches:
            counts[match.name] = counts.get(match.name, 0) + 1
        return counts


def parse_scout_labels(values: Iterable[str]) -> tuple[ScoutLabel, ...]:
    labels: list[ScoutLabel] = []
    for value in values:
        match = SCOUT_LABEL_RE.match(value.strip())
        if not match:
            raise OpponentMonitorError(f"Invalid scout label {value!r}; use 千珏:4@720,420,90,90.")
        x = int(match.group("x"))
        y = int(match.group("y"))
        width = int(match.group("w"))
        height = int(match.group("h"))
        if width <= 0 or height <= 0:
            raise OpponentMonitorError(f"Scout label box must be positive: {value!r}")
        labels.append(
            ScoutLabel(
                name=match.group("name").strip(),
                cost=_normalize_cost(match.group("cost")),
                box=(x, y, x + width, y + height),
            )
        )
    return tuple(labels)


def label_scout_templates(
    image_path: Path,
    labels: Iterable[ScoutLabel],
    *,
    templates_path: Path = DEFAULT_OPPONENT_TEMPLATE_PATH,
    output_dir: Path | None = None,
) -> tuple[ScoutTemplate, ...]:
    templates_path = _resolve_path(templates_path)
    output_dir = _resolve_path(output_dir) if output_dir is not None else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
    templates = list(load_scout_templates(templates_path))

    image_path = image_path.resolve()
    with Image.open(image_path) as image:
        source = image.convert("RGB")
        for label in labels:
            crop = source.crop(_clamp_box(label.box, source.size))
            if not _is_detailed(crop):
                raise OpponentMonitorError(f"Scout label for {label.name} looks too empty/noisy; choose a tighter crop.")
            template = ScoutTemplate(
                name=label.name,
                cost=label.cost,
                width=crop.width,
                height=crop.height,
                signature=_signature(crop),
            )
            templates = _replace_template(templates, template)
            if output_dir is not None:
                crop.save(output_dir / f"{_safe_name(label.name)}_{label.cost or 'x'}.png")

    save_scout_templates(tuple(templates), templates_path)
    return tuple(templates)


def scan_opponent(
    image_path: Path,
    *,
    templates_path: Path = DEFAULT_OPPONENT_TEMPLATE_PATH,
    output_dir: Path | None = None,
    target_names: Iterable[str] = (),
    regions: Iterable[str] = DEFAULT_SCOUT_REGIONS,
    threshold: float = DEFAULT_SCOUT_THRESHOLD,
    stride: int = DEFAULT_SCOUT_STRIDE,
    preset: RegionPreset | None = None,
) -> OpponentScoutReport:
    preset = preset or default_preset()
    templates_path = _resolve_path(templates_path)
    templates = _filter_templates(load_scout_templates(templates_path), target_names)
    output_dir = _resolve_path(output_dir) if output_dir is not None else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    image_path = image_path.resolve()
    matches: list[ScoutMatch] = []
    with Image.open(image_path) as image:
        source = image.convert("RGB")
        for region_name in tuple(regions):
            region = preset.get(region_name)
            region_box = region.box_for(source.size, preset.base_size)
            region_crop = source.crop(region_box)
            for template in templates:
                matches.extend(_scan_region(region_crop, region_box, region_name, template, threshold, stride))

    deduped = _dedupe_matches(matches)
    exported = _export_matches(deduped, image_path, output_dir)
    return OpponentScoutReport(
        image_path=image_path,
        templates_path=templates_path,
        template_count=len(templates),
        output_dir=output_dir,
        matches=tuple(exported),
    )


def load_scout_templates(path: Path = DEFAULT_OPPONENT_TEMPLATE_PATH) -> tuple[ScoutTemplate, ...]:
    path = _resolve_path(path)
    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OpponentMonitorError(f"Could not read opponent templates: {path}") from exc

    raw_templates = payload.get("templates", [])
    if not isinstance(raw_templates, list):
        return ()

    templates: list[ScoutTemplate] = []
    expected_signature = SCOUT_SIGNATURE_SIZE[0] * SCOUT_SIGNATURE_SIZE[1] * 3
    for item in raw_templates:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        cost = _normalize_cost(item.get("cost"))
        try:
            width = int(item.get("width", 0))
            height = int(item.get("height", 0))
        except (TypeError, ValueError):
            continue
        signature = tuple(int(value) for value in item.get("signature", []) if isinstance(value, int))
        if width <= 0 or height <= 0 or len(signature) != expected_signature:
            continue
        templates.append(ScoutTemplate(name=name, cost=cost, width=width, height=height, signature=signature))
    return tuple(templates)


def save_scout_templates(templates: tuple[ScoutTemplate, ...], path: Path = DEFAULT_OPPONENT_TEMPLATE_PATH) -> None:
    path = _resolve_path(path)
    payload = {
        "version": SCOUT_TEMPLATE_VERSION,
        "templates": [
            {
                "name": template.name,
                "cost": template.cost,
                "width": template.width,
                "height": template.height,
                "signature": list(template.signature),
            }
            for template in sorted(templates, key=lambda item: (item.name, item.cost or 0, item.width, item.height))
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise OpponentMonitorError(f"Could not write opponent templates: {path}") from exc


def format_opponent_scout(report: OpponentScoutReport) -> str:
    lines = [
        f"Opponent scout: {report.image_path}",
        f"Templates: {report.template_count} from {report.templates_path}",
    ]
    if report.output_dir is not None:
        lines.append(f"Debug exported to: {report.output_dir}")
    lines.append("")
    lines.append("同行/卡牌监测:")
    if not report.matches:
        lines.append("- 没有识别到已训练的目标棋子。")
        lines.append("- 如果你确定画面里有目标牌，请用 scout-label 先训练一个更紧的截图模板。")
        return "\n".join(lines)

    counts = report.contested_counts
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        related = [match for match in report.matches if match.name == name]
        best = max(match.confidence for match in related)
        cost = next((match.cost for match in related if match.cost is not None), None)
        cost_label = f"{cost}费" if cost is not None else "费用未知"
        lines.append(f"- {name}({cost_label}): 疑似同行持有 {count} 张，最高置信度 {best:.3f}")
    lines.append("Contested 参数: " + " ".join(f"{name}={count}" for name, count in sorted(counts.items())))
    lines.append("提示: 这里只统计当前截图识别到的模板目标；对手卖牌、战斗遮挡、召唤物或皮肤动画都需要复查。")
    return "\n".join(lines)


def _scan_region(
    region_crop: Image.Image,
    region_box: tuple[int, int, int, int],
    region_name: str,
    template: ScoutTemplate,
    threshold: float,
    stride: int,
) -> list[ScoutMatch]:
    matches: list[ScoutMatch] = []
    step = max(4, stride)
    if template.width > region_crop.width or template.height > region_crop.height:
        return matches

    x_positions = _scan_positions(region_crop.width, template.width, step)
    y_positions = _scan_positions(region_crop.height, template.height, step)
    for y in y_positions:
        for x in x_positions:
            crop = region_crop.crop((x, y, x + template.width, y + template.height))
            if not _is_detailed(crop):
                continue
            score = _similarity(_signature(crop), template.signature)
            if score >= threshold:
                left = region_box[0] + x
                top = region_box[1] + y
                matches.append(
                    ScoutMatch(
                        name=template.name,
                        cost=template.cost,
                        confidence=round(score, 3),
                        region=region_name,
                        box=(left, top, left + template.width, top + template.height),
                    )
                )
    return matches


def _scan_positions(region_size: int, template_size: int, stride: int) -> tuple[int, ...]:
    if region_size <= template_size:
        return (0,)
    positions = list(range(0, region_size - template_size + 1, stride))
    last = region_size - template_size
    if positions[-1] != last:
        positions.append(last)
    return tuple(positions)


def _dedupe_matches(matches: list[ScoutMatch]) -> list[ScoutMatch]:
    kept: list[ScoutMatch] = []
    for match in sorted(matches, key=lambda item: item.confidence, reverse=True):
        if any(_overlap(match.box, existing.box) > 0.45 for existing in kept if existing.name == match.name):
            continue
        kept.append(match)
    return sorted(kept, key=lambda item: (item.name, item.region, item.box[1], item.box[0]))


def _export_matches(matches: list[ScoutMatch], image_path: Path, output_dir: Path | None) -> list[ScoutMatch]:
    if output_dir is None:
        return matches
    exported: list[ScoutMatch] = []
    with Image.open(image_path) as image:
        source = image.convert("RGB")
        for index, match in enumerate(matches, start=1):
            crop_path = output_dir / f"match_{index}_{_safe_name(match.name)}_{match.confidence:.3f}.png"
            source.crop(match.box).save(crop_path)
            exported.append(
                ScoutMatch(
                    name=match.name,
                    cost=match.cost,
                    confidence=match.confidence,
                    region=match.region,
                    box=match.box,
                    crop_path=crop_path,
                )
            )
    return exported


def _filter_templates(
    templates: tuple[ScoutTemplate, ...],
    target_names: Iterable[str],
) -> tuple[ScoutTemplate, ...]:
    targets = {name.strip() for name in target_names if name.strip()}
    if not targets:
        return templates
    return tuple(template for template in templates if template.name in targets)


def _replace_template(templates: list[ScoutTemplate], template: ScoutTemplate) -> list[ScoutTemplate]:
    kept = [
        item
        for item in templates
        if not (
            item.name == template.name
            and item.cost == template.cost
            and item.width == template.width
            and item.height == template.height
        )
    ]
    kept.append(template)
    return kept


def _signature(crop: Image.Image) -> tuple[int, ...]:
    sample = crop.convert("RGB").resize(SCOUT_SIGNATURE_SIZE, Image.Resampling.LANCZOS)
    pixels = sample.get_flattened_data() if hasattr(sample, "get_flattened_data") else sample.getdata()
    return tuple(channel for pixel in pixels for channel in pixel)


def _similarity(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    diff = sum(abs(left - right) for left, right in zip(a, b)) / (len(a) * 255)
    return max(0.0, min(1.0, 1.0 - diff))


def _overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return intersection / max(1, min(area_a, area_b))


def _is_detailed(crop: Image.Image) -> bool:
    return ImageStat.Stat(crop.convert("L")).stddev[0] >= 8.0


def _clamp_box(box: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    left, top, right, bottom = box
    return (
        max(0, min(width, left)),
        max(0, min(height, top)),
        max(0, min(width, right)),
        max(0, min(height, bottom)),
    )


def _normalize_cost(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        cost = int(value)
    except (TypeError, ValueError):
        return None
    return cost if cost in range(1, 6) else None


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value).strip("_") or "target"
