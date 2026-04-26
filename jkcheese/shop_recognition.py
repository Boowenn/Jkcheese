from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, ImageStat

from .ocr import _components, _recognize_digit
from .regions import RegionPreset, default_preset


DEFAULT_SHOP_TEMPLATE_PATH = Path("captures") / "shop_templates.json"
DEFAULT_CHAMPION_DICTIONARY_PATH = Path("captures") / "champions.json"
SHOP_SLOT_COUNT = 5
SHOP_SLOT_NAMES = tuple(f"shop_slot_{index}" for index in range(1, SHOP_SLOT_COUNT + 1))
SIGNATURE_SIZE = (16, 16)
NAME_SIGNATURE_SIZE = (96, 32)
OCCUPIED_STDDEV_THRESHOLD = 14.0
DEFAULT_TEMPLATE_THRESHOLD = 0.92
DEFAULT_NAME_OCR_THRESHOLD = 0.63
DEFAULT_NAME_OCR_MARGIN = 0.015
LABEL_RE = re.compile(r"^(?P<slot>[1-5])\s*[=:]\s*(?P<name>[^:@=]+?)(?:\s*[:@]\s*(?P<cost>[1-5]))?$")

DEFAULT_CHAMPION_NAMES = (
    "潘森",
    "俄洛伊",
    "茂凯",
    "厄加特",
    "卡莎",
    "丽桑卓",
    "雷克塞",
    "薇古丝",
    "娜美",
    "安妮",
    "波比",
    "塔姆",
    "维克托",
    "小鱼人",
    "菲兹",
    "拉克丝",
    "盖伦",
    "亚托克斯",
    "阿狸",
    "阿卡丽",
    "卡特琳娜",
    "艾克",
    "艾希",
    "卢锡安",
    "希维尔",
    "伊泽瑞尔",
    "凯特琳",
    "金克丝",
    "蔚",
    "薇恩",
    "锐雯",
    "瑟提",
    "孙悟空",
    "李青",
    "嘉文四世",
    "墨菲特",
    "布里茨",
    "布隆",
    "慎",
    "赵信",
    "贾克斯",
    "沃里克",
    "德莱厄斯",
    "德莱文",
    "莎弥拉",
    "霞",
    "洛",
    "悠米",
    "妮蔻",
    "佐伊",
    "辛德拉",
    "乐芙兰",
    "妖姬",
    "泽拉斯",
    "奥莉安娜",
    "库奇",
    "兰博",
    "凯南",
    "崔丝塔娜",
    "吉格斯",
    "莫甘娜",
    "凯尔",
    "凯隐",
    "千珏",
    "烬",
    "奎桑提",
    "亚索",
    "永恩",
    "诺提勒斯",
    "奇亚娜",
    "奎因",
    "艾瑞莉娅",
    "刀妹",
    "塞拉斯",
    "加里奥",
    "科加斯",
    "雷克顿",
    "内瑟斯",
    "婕拉",
    "尼菈",
    "莉莉娅",
    "阿木木",
    "蒙多",
    "萨勒芬妮",
    "娑娜",
    "卡尔玛",
    "厄斐琉斯",
    "佛耶戈",
    "卑尔维斯",
    "索拉卡",
    "贝蕾亚",
)


class ShopRecognitionError(RuntimeError):
    """Raised when shop scanning or template calibration fails."""


@dataclass(frozen=True, slots=True)
class ShopTemplate:
    name: str
    cost: int | None
    signature: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ShopLabel:
    slot: int
    name: str
    cost: int | None = None


@dataclass(frozen=True, slots=True)
class ShopSlotReading:
    slot: int
    occupied: bool
    name: str = ""
    cost: int | None = None
    confidence: float = 0.0
    source: str = "empty"
    crop_path: Path | None = None
    name_path: Path | None = None
    cost_path: Path | None = None


@dataclass(frozen=True, slots=True)
class ShopScanReport:
    image_path: Path
    output_dir: Path | None
    slots: tuple[ShopSlotReading, ...]
    templates_path: Path
    template_count: int
    candidate_count: int = 0

    @property
    def recognized_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for slot in self.slots:
            if slot.name and slot.name not in names:
                names.append(slot.name)
        return tuple(names)


def scan_shop(
    image_path: Path,
    *,
    output_dir: Path | None = None,
    templates_path: Path = DEFAULT_SHOP_TEMPLATE_PATH,
    champions_path: Path | None = DEFAULT_CHAMPION_DICTIONARY_PATH,
    candidate_names: Iterable[str] = (),
    enable_name_ocr: bool = True,
    preset: RegionPreset | None = None,
    threshold: float = DEFAULT_TEMPLATE_THRESHOLD,
    name_ocr_threshold: float = DEFAULT_NAME_OCR_THRESHOLD,
) -> ShopScanReport:
    preset = preset or default_preset()
    templates_path = _resolve_path(templates_path)
    templates = load_shop_templates(templates_path)
    name_candidates = (
        load_champion_names(champions_path, extra=(*candidate_names, *(template.name for template in templates)))
        if enable_name_ocr
        else ()
    )
    output_dir = _resolve_path(output_dir) if output_dir is not None else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    image_path = image_path.resolve()
    readings: list[ShopSlotReading] = []
    with Image.open(image_path) as image:
        source = image.convert("RGB")
        for slot, region_name in enumerate(SHOP_SLOT_NAMES, start=1):
            crop = source.crop(preset.get(region_name).box_for(source.size, preset.base_size))
            reading = _scan_slot(slot, crop, templates, threshold, name_candidates, name_ocr_threshold)
            readings.append(_export_slot_debug(reading, crop, image_path, output_dir))

    return ShopScanReport(
        image_path=image_path,
        output_dir=output_dir,
        slots=tuple(readings),
        templates_path=templates_path,
        template_count=len(templates),
        candidate_count=len(name_candidates),
    )


def label_shop_templates(
    image_path: Path,
    labels: Iterable[ShopLabel],
    *,
    templates_path: Path = DEFAULT_SHOP_TEMPLATE_PATH,
    output_dir: Path | None = None,
    preset: RegionPreset | None = None,
) -> tuple[ShopTemplate, ...]:
    preset = preset or default_preset()
    templates_path = _resolve_path(templates_path)
    templates = list(load_shop_templates(templates_path))
    output_dir = _resolve_path(output_dir) if output_dir is not None else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    image_path = image_path.resolve()
    with Image.open(image_path) as image:
        source = image.convert("RGB")
        for label in labels:
            if label.slot not in range(1, SHOP_SLOT_COUNT + 1):
                raise ShopRecognitionError(f"Shop slot must be 1-{SHOP_SLOT_COUNT}: {label.slot}")
            region_name = f"shop_slot_{label.slot}"
            crop = source.crop(preset.get(region_name).box_for(source.size, preset.base_size))
            if not _is_occupied(crop):
                raise ShopRecognitionError(f"Shop slot {label.slot} looks empty; cannot create a template.")
            cost = label.cost if label.cost is not None else _read_cost(crop)
            template = ShopTemplate(name=label.name, cost=cost, signature=_signature(crop))
            templates = _replace_template(templates, template)
            if output_dir is not None:
                crop.save(output_dir / f"slot_{label.slot}_{_safe_name(label.name)}.png")

    save_shop_templates(tuple(templates), templates_path)
    return tuple(templates)


def load_shop_templates(path: Path = DEFAULT_SHOP_TEMPLATE_PATH) -> tuple[ShopTemplate, ...]:
    path = _resolve_path(path)
    if not path.exists():
        return ()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShopRecognitionError(f"Could not read shop templates: {path}") from exc

    raw_templates = payload.get("templates", [])
    if not isinstance(raw_templates, list):
        return ()

    templates: list[ShopTemplate] = []
    for item in raw_templates:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        cost = _normalize_cost(item.get("cost"))
        signature = tuple(int(value) for value in item.get("signature", []) if isinstance(value, int))
        if len(signature) != SIGNATURE_SIZE[0] * SIGNATURE_SIZE[1]:
            continue
        templates.append(ShopTemplate(name=name, cost=cost, signature=signature))
    return tuple(templates)


def load_champion_names(
    path: Path | None = DEFAULT_CHAMPION_DICTIONARY_PATH,
    *,
    extra: Iterable[str] = (),
) -> tuple[str, ...]:
    names: list[str] = [*DEFAULT_CHAMPION_NAMES]
    path = _resolve_path(path)
    if path is not None and path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ShopRecognitionError(f"Could not read champion dictionary: {path}") from exc
        names.extend(_extract_champion_names(payload))
    names.extend(str(value) for value in extra)
    return _unique_names(names)


def save_shop_templates(templates: tuple[ShopTemplate, ...], path: Path = DEFAULT_SHOP_TEMPLATE_PATH) -> None:
    path = _resolve_path(path)
    payload = {
        "version": 1,
        "templates": [
            {"name": template.name, "cost": template.cost, "signature": list(template.signature)}
            for template in sorted(templates, key=lambda item: (item.name, item.cost or 0))
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise ShopRecognitionError(f"Could not write shop templates: {path}") from exc


def parse_shop_labels(values: Iterable[str]) -> tuple[ShopLabel, ...]:
    labels: list[ShopLabel] = []
    for value in values:
        match = LABEL_RE.match(value.strip())
        if not match:
            raise ShopRecognitionError(f"Invalid shop label {value!r}; use 2=丽桑卓:1.")
        labels.append(
            ShopLabel(
                slot=int(match.group("slot")),
                name=match.group("name").strip(),
                cost=_normalize_cost(match.group("cost")),
            )
        )
    return tuple(labels)


def format_shop_scan(report: ShopScanReport) -> str:
    lines = [
        f"Shop scan: {report.image_path}",
        f"Templates: {report.template_count} from {report.templates_path}",
    ]
    if report.candidate_count:
        lines.append(f"Name OCR candidates: {report.candidate_count}")
    if report.output_dir is not None:
        lines.append(f"Debug exported to: {report.output_dir}")

    for reading in report.slots:
        if not reading.occupied:
            lines.append(f"- Slot {reading.slot}: empty")
            continue
        cost = f"{reading.cost}费" if reading.cost is not None else "费用未知"
        if reading.name:
            lines.append(
                f"- Slot {reading.slot}: {reading.name} ({cost}, confidence {reading.confidence:.3f}, {reading.source})"
            )
        else:
            lines.append(f"- Slot {reading.slot}: occupied unknown ({cost}, confidence {reading.confidence:.3f})")
    return "\n".join(lines)


def _scan_slot(
    slot: int,
    crop: Image.Image,
    templates: tuple[ShopTemplate, ...],
    threshold: float,
    name_candidates: tuple[str, ...],
    name_ocr_threshold: float,
) -> ShopSlotReading:
    occupied = _is_occupied(crop)
    if not occupied:
        return ShopSlotReading(slot=slot, occupied=False)

    cost = _read_cost(crop)
    best_template, confidence = _best_template(crop, templates)
    if best_template is not None and confidence >= threshold:
        return ShopSlotReading(
            slot=slot,
            occupied=True,
            name=best_template.name,
            cost=cost if cost is not None else best_template.cost,
            confidence=round(confidence, 3),
            source="template",
        )

    name, ocr_confidence = _recognize_name_by_rendering(crop, name_candidates, name_ocr_threshold)
    if name:
        return ShopSlotReading(
            slot=slot,
            occupied=True,
            name=name,
            cost=cost,
            confidence=round(ocr_confidence, 3),
            source="name-ocr",
        )

    return ShopSlotReading(slot=slot, occupied=True, cost=cost, confidence=round(confidence, 3), source="unknown")


def _export_slot_debug(
    reading: ShopSlotReading,
    crop: Image.Image,
    image_path: Path,
    output_dir: Path | None,
) -> ShopSlotReading:
    if output_dir is None:
        return reading

    stem = image_path.stem
    crop_path = output_dir / f"{stem}_slot_{reading.slot}.png"
    name_path = output_dir / f"{stem}_slot_{reading.slot}_name.png"
    cost_path = output_dir / f"{stem}_slot_{reading.slot}_cost.png"
    crop.save(crop_path)
    _name_crop(crop).save(name_path)
    _cost_crop(crop).save(cost_path)

    return ShopSlotReading(
        slot=reading.slot,
        occupied=reading.occupied,
        name=reading.name,
        cost=reading.cost,
        confidence=reading.confidence,
        source=reading.source,
        crop_path=crop_path,
        name_path=name_path,
        cost_path=cost_path,
    )


def _replace_template(templates: list[ShopTemplate], template: ShopTemplate) -> list[ShopTemplate]:
    kept = [item for item in templates if not (item.name == template.name and item.cost == template.cost)]
    kept.append(template)
    return kept


def _best_template(crop: Image.Image, templates: tuple[ShopTemplate, ...]) -> tuple[ShopTemplate | None, float]:
    if not templates:
        return None, 0.0

    signature = _signature(crop)
    best_template: ShopTemplate | None = None
    best_score = 0.0
    for template in templates:
        score = _similarity(signature, template.signature)
        if score > best_score:
            best_template = template
            best_score = score
    return best_template, best_score


def _recognize_name_by_rendering(
    crop: Image.Image,
    candidates: tuple[str, ...],
    threshold: float,
) -> tuple[str, float]:
    if not candidates:
        return "", 0.0

    actual = _normalize_name_mask(_name_mask(_name_crop(crop)))
    if actual.getbbox() is None:
        return "", 0.0

    best_by_name: dict[str, float] = {}
    for name, template in _rendered_name_templates(candidates):
        score = 1.0 - _difference_score(actual, template)
        if score > best_by_name.get(name, 0.0):
            best_by_name[name] = score

    if not best_by_name:
        return "", 0.0

    ranked = sorted(best_by_name.items(), key=lambda item: item[1], reverse=True)
    best_name, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_score < threshold:
        return "", best_score
    if second_score and best_score - second_score < DEFAULT_NAME_OCR_MARGIN:
        return "", best_score
    return best_name, best_score


@lru_cache(maxsize=16)
def _rendered_name_templates(candidates: tuple[str, ...]) -> tuple[tuple[str, Image.Image], ...]:
    templates: list[tuple[str, Image.Image]] = []
    font_paths = _name_font_candidates()
    if not font_paths:
        return ()

    for name in candidates:
        for font_path in font_paths:
            for size in range(18, 30, 2):
                templates.append((name, _normalize_name_mask(_render_name(name, font_path, size))))
    return tuple(templates)


def _render_name(name: str, font_path: Path, size: int) -> Image.Image:
    image = Image.new("L", (220, 64), 0)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), size)
    draw.text((0, 0), name, fill=255, font=font)
    return image.point(lambda pixel: 255 if pixel > 20 else 0).convert("1")


def _name_font_candidates() -> tuple[Path, ...]:
    candidates = (
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\dengb.ttf"),
    )
    return tuple(path for path in candidates if path.exists())


def _name_mask(image: Image.Image) -> Image.Image:
    source = image.convert("RGB")
    output = Image.new("1", source.size, 0)
    source_pixels = source.load()
    output_pixels = output.load()
    for y in range(source.height):
        for x in range(source.width):
            r, g, b = source_pixels[x, y]
            if r > 150 and g > 145 and b > 130 and max(r, g, b) - min(r, g, b) < 95:
                output_pixels[x, y] = 1

    cleaned = Image.new("1", source.size, 0)
    for component in _components(output):
        if component.area < 3:
            continue
        cleaned.paste(component.image, component.box)
    return cleaned


def _normalize_name_mask(mask: Image.Image, size: tuple[int, int] = NAME_SIGNATURE_SIZE) -> Image.Image:
    bbox = mask.getbbox()
    if bbox is None:
        return Image.new("1", size, 0)

    crop = mask.crop(bbox).convert("L")
    target_width, target_height = size
    scale = min((target_width - 4) / crop.width, (target_height - 4) / crop.height)
    new_size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
    crop = crop.resize(new_size, Image.Resampling.LANCZOS)
    crop = crop.point(lambda pixel: 255 if pixel > 80 else 0).convert("1")

    output = Image.new("1", size, 0)
    output.paste(crop, ((target_width - new_size[0]) // 2, (target_height - new_size[1]) // 2))
    return output


def _is_occupied(crop: Image.Image) -> bool:
    art = _art_crop(crop).convert("L")
    stddev = ImageStat.Stat(art).stddev[0]
    return stddev >= OCCUPIED_STDDEV_THRESHOLD


def _read_cost(crop: Image.Image) -> int | None:
    mask = _cost_mask(_cost_crop(crop))
    components = [item for item in _components(mask) if item.area >= 8]
    if not components:
        return _cost_from_bar_color(crop)
    digit_component = max(components, key=lambda item: (item.box[2], item.area))
    digit, score = _recognize_digit(digit_component.image)
    if digit in {"1", "2", "3", "4", "5"} and score <= 0.45:
        return int(digit)
    return _cost_from_bar_color(crop)


def _signature(crop: Image.Image) -> tuple[int, ...]:
    art = _art_crop(crop).convert("L")
    sample = art.resize(SIGNATURE_SIZE, Image.Resampling.LANCZOS)
    pixels = sample.get_flattened_data() if hasattr(sample, "get_flattened_data") else sample.getdata()
    return tuple(pixels)


def _similarity(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    diff = sum(abs(left - right) for left, right in zip(a, b)) / (len(a) * 255)
    return max(0.0, min(1.0, 1.0 - diff))


def _difference_score(a: Image.Image, b: Image.Image) -> float:
    a_pixels = a.load()
    b_pixels = b.load()
    width, height = a.size
    diff = 0
    active = 0

    for y in range(height):
        for x in range(width):
            av = bool(a_pixels[x, y])
            bv = bool(b_pixels[x, y])
            if av != bv:
                diff += 1
            if av or bv:
                active += 1

    return diff / (active or 1)


def _art_crop(crop: Image.Image) -> Image.Image:
    width, height = crop.size
    return crop.crop((0, 0, width, max(1, int(height * 0.78))))


def _name_crop(crop: Image.Image) -> Image.Image:
    width, height = crop.size
    return crop.crop((0, max(0, int(height * 0.76)), max(1, int(width * 0.75)), height))


def _cost_crop(crop: Image.Image) -> Image.Image:
    width, height = crop.size
    return crop.crop((max(0, width - 48), max(0, height - 48), width, height))


def _cost_mask(image: Image.Image) -> Image.Image:
    source = image.convert("RGB")
    output = Image.new("1", source.size, 0)
    source_pixels = source.load()
    output_pixels = output.load()
    for y in range(source.height):
        for x in range(source.width):
            r, g, b = source_pixels[x, y]
            if (r > 130 and g < 130 and b < 130) or (r > 230 and g > 220 and b > 170):
                output_pixels[x, y] = 1
    return output


def _cost_from_bar_color(crop: Image.Image) -> int | None:
    width, height = crop.size
    sample = crop.crop((5, int(height * 0.83), max(6, int(width * 0.25)), max(6, height - 5)))
    r, g, b = ImageStat.Stat(sample.convert("RGB")).mean
    if r < 30 and g < 30 and b < 35:
        return None
    if r > 90 and b > 80 and g < 90:
        return 4
    if b > 95 and r < 90:
        return 3
    return None


def _normalize_cost(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        cost = int(value)
    except (TypeError, ValueError):
        return None
    return cost if cost in range(1, 6) else None


def _extract_champion_names(payload: object) -> tuple[str, ...]:
    if isinstance(payload, dict):
        raw_values = payload.get("champions", payload.get("names", []))
    else:
        raw_values = payload

    names: list[str] = []
    if isinstance(raw_values, list):
        for value in raw_values:
            if isinstance(value, str):
                names.append(value)
            elif isinstance(value, dict):
                name = value.get("name")
                if isinstance(name, str):
                    names.append(name)
    return tuple(names)


def _unique_names(values: Iterable[str]) -> tuple[str, ...]:
    names: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in names:
            names.append(cleaned)
    return tuple(names)


def _resolve_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path if path.is_absolute() else Path.cwd() / path


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value).strip("_") or "template"
