from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .regions import RegionPreset, default_preset


@dataclass(frozen=True, slots=True)
class RegionCrop:
    name: str
    path: Path
    box: tuple[int, int, int, int]


def crop_regions(
    image_path: Path,
    output_dir: Path,
    preset: RegionPreset | None = None,
    names: list[str] | tuple[str, ...] | None = None,
) -> list[RegionCrop]:
    preset = preset or default_preset()
    image_path = image_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = preset.regions if not names else tuple(preset.get(name) for name in names)
    results: list[RegionCrop] = []

    with Image.open(image_path) as image:
        source_size = image.size
        for region in selected:
            box = region.box_for(source_size, preset.base_size)
            output_path = output_dir / f"{image_path.stem}_{region.name}.png"
            image.crop(box).save(output_path)
            results.append(RegionCrop(name=region.name, path=output_path, box=box))

    return results
