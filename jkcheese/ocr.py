from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from .regions import RegionPreset, default_preset


@dataclass(frozen=True, slots=True)
class OcrField:
    name: str
    region_name: str
    roi: tuple[int, int, int, int]
    min_area: int
    min_width: int
    min_height: int
    min_x: int = 0
    max_right: int | None = None
    max_score: float = 0.48
    mode: str = "number"


@dataclass(frozen=True, slots=True)
class OcrReading:
    name: str
    text: str
    value: int | None
    confidence: float
    source_region: str


@dataclass(frozen=True, slots=True)
class Component:
    box: tuple[int, int, int, int]
    area: int
    image: Image.Image


@dataclass(frozen=True, slots=True)
class DebugExport:
    field_name: str
    region_path: Path
    roi_path: Path
    mask_path: Path


FIELDS: tuple[OcrField, ...] = (
    OcrField(
        name="stage",
        region_name="stage",
        roi=(0, 4, 170, 64),
        min_area=18,
        min_width=3,
        min_height=8,
        max_score=0.55,
        mode="stage",
    ),
    OcrField(
        name="gold",
        region_name="gold",
        roi=(45, 5, 118, 45),
        min_area=35,
        min_width=4,
        min_height=8,
        min_x=15,
        max_score=0.48,
    ),
    OcrField(
        name="level",
        region_name="level",
        roi=(0, 0, 58, 50),
        min_area=40,
        min_width=4,
        min_height=10,
        max_right=36,
        max_score=0.52,
    ),
    OcrField(
        name="player_hp",
        region_name="player_hp",
        roi=(0, 0, 120, 70),
        min_area=80,
        min_width=6,
        min_height=15,
        min_x=30,
        max_right=112,
        max_score=0.48,
    ),
)


def read_screenshot(image_path: Path, preset: RegionPreset | None = None) -> list[OcrReading]:
    preset = preset or default_preset()
    image_path = image_path.resolve()
    readings: list[OcrReading] = []

    with Image.open(image_path) as image:
        source = image.convert("RGB")
        for field in FIELDS:
            region = preset.get(field.region_name)
            crop = source.crop(region.box_for(source.size, preset.base_size))
            readings.append(read_field_crop(crop, field))

    return readings


def export_ocr_debug(
    image_path: Path,
    output_dir: Path,
    preset: RegionPreset | None = None,
) -> list[DebugExport]:
    preset = preset or default_preset()
    image_path = image_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    exports: list[DebugExport] = []
    with Image.open(image_path) as image:
        source = image.convert("RGB")
        for field in FIELDS:
            region = preset.get(field.region_name)
            region_crop = source.crop(region.box_for(source.size, preset.base_size))
            roi_crop = region_crop.crop(field.roi)
            mask = _foreground_mask(roi_crop)

            region_path = output_dir / f"{field.name}_region.png"
            roi_path = output_dir / f"{field.name}_roi.png"
            mask_path = output_dir / f"{field.name}_mask.png"

            region_crop.save(region_path)
            roi_crop.save(roi_path)
            mask.convert("L").save(mask_path)

            exports.append(
                DebugExport(
                    field_name=field.name,
                    region_path=region_path,
                    roi_path=roi_path,
                    mask_path=mask_path,
                )
            )

    return exports


def read_field_crop(image: Image.Image, field: OcrField) -> OcrReading:
    roi = image.convert("RGB").crop(field.roi)
    mask = _foreground_mask(roi)
    components = _filter_components(_components(mask), field)

    if field.mode == "stage":
        return _read_stage_components(components, field)

    digits: list[str] = []
    scores: list[float] = []
    for component in components:
        digit, score = _recognize_digit(component.image)
        if score <= field.max_score:
            digits.append(digit)
            scores.append(score)

    text = "".join(digits)
    value = int(text) if text else None
    confidence = 0.0 if not scores else max(0.0, min(1.0, 1.0 - (sum(scores) / len(scores))))

    return OcrReading(
        name=field.name,
        text=text,
        value=value,
        confidence=round(confidence, 3),
        source_region=field.region_name,
    )


def _read_stage_components(components: list[Component], field: OcrField) -> OcrReading:
    digits: list[str] = []
    scores: list[float] = []
    for component in components:
        digit, score = _recognize_digit(component.image)
        if score <= field.max_score:
            digits.append(digit)
            scores.append(score)

    raw_text = "".join(digits)
    if len(raw_text) >= 2:
        text = f"{raw_text[0]}-{raw_text[1]}"
        value = int(raw_text[:2])
    elif raw_text:
        text = raw_text
        value = int(raw_text)
    else:
        text = ""
        value = None
    confidence = 0.0 if not scores else max(0.0, min(1.0, 1.0 - (sum(scores) / len(scores))))

    return OcrReading(
        name=field.name,
        text=text,
        value=value,
        confidence=round(confidence, 3),
        source_region=field.region_name,
    )


def _foreground_mask(image: Image.Image) -> Image.Image:
    source = image.convert("RGB")
    width, height = source.size
    output = Image.new("1", source.size, 0)
    source_pixels = source.load()
    output_pixels = output.load()

    for y in range(height):
        for x in range(width):
            r, g, b = source_pixels[x, y]
            if r > 150 and g > 130 and b > 80 and (r + g + b) > 430:
                output_pixels[x, y] = 1

    return output


def _components(mask: Image.Image) -> list[Component]:
    width, height = mask.size
    pixels = mask.load()
    seen: set[tuple[int, int]] = set()
    components: list[Component] = []

    for start_y in range(height):
        for start_x in range(width):
            if not pixels[start_x, start_y] or (start_x, start_y) in seen:
                continue

            stack = [(start_x, start_y)]
            seen.add((start_x, start_y))
            points: list[tuple[int, int]] = []

            while stack:
                x, y = stack.pop()
                points.append((x, y))
                for nx in range(x - 1, x + 2):
                    for ny in range(y - 1, y + 2):
                        if (
                            0 <= nx < width
                            and 0 <= ny < height
                            and pixels[nx, ny]
                            and (nx, ny) not in seen
                        ):
                            seen.add((nx, ny))
                            stack.append((nx, ny))

            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
            components.append(Component(box=box, area=len(points), image=mask.crop(box)))

    return sorted(components, key=lambda component: component.box[0])


def _filter_components(components: Iterable[Component], field: OcrField) -> list[Component]:
    selected: list[Component] = []
    for component in components:
        left, _top, right, bottom = component.box
        width = right - left
        height = bottom - component.box[1]
        if component.area < field.min_area:
            continue
        if width < field.min_width or height < field.min_height:
            continue
        if left < field.min_x:
            continue
        if field.max_right is not None and right > field.max_right:
            continue
        selected.append(component)
    return selected


def _recognize_digit(component: Image.Image) -> tuple[str, float]:
    sample = _normalize(component)
    best_digit = ""
    best_score = 1.0

    for digit, template in _digit_templates():
        score = _difference_score(sample, template)
        if score < best_score:
            best_digit = digit
            best_score = score

    return best_digit, best_score


def _normalize(mask: Image.Image, size: tuple[int, int] = (20, 32)) -> Image.Image:
    bbox = mask.getbbox()
    if bbox is None:
        return Image.new("1", size, 0)

    crop = mask.crop(bbox).convert("L")
    target_width, target_height = size
    scale = min((target_width - 2) / crop.width, (target_height - 2) / crop.height)
    new_size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
    crop = crop.resize(new_size, Image.Resampling.LANCZOS)
    crop = crop.point(lambda pixel: 255 if pixel > 80 else 0).convert("1")

    output = Image.new("1", size, 0)
    output.paste(crop, ((target_width - new_size[0]) // 2, (target_height - new_size[1]) // 2))
    return output


@lru_cache(maxsize=1)
def _digit_templates() -> tuple[tuple[str, Image.Image], ...]:
    templates: list[tuple[str, Image.Image]] = []
    for font_path in _font_candidates():
        for size in range(26, 42, 2):
            font = ImageFont.truetype(str(font_path), size)
            for digit in "0123456789":
                image = Image.new("L", (64, 72), 0)
                draw = ImageDraw.Draw(image)
                draw.text((8, 4), digit, fill=255, font=font)
                mask = image.point(lambda pixel: 255 if pixel > 20 else 0).convert("1")
                templates.append((digit, _normalize(mask)))
    return tuple(templates)


def _font_candidates() -> tuple[Path, ...]:
    candidates = (
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    )
    available = tuple(path for path in candidates if path.exists())
    if available:
        return available
    raise RuntimeError("No digit template font was found")


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
