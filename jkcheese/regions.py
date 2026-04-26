from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Region:
    name: str
    x: int
    y: int
    width: int
    height: int

    def box_for(self, source_size: tuple[int, int], base_size: tuple[int, int]) -> tuple[int, int, int, int]:
        source_width, source_height = source_size
        base_width, base_height = base_size
        scale_x = source_width / base_width
        scale_y = source_height / base_height

        left = round(self.x * scale_x)
        top = round(self.y * scale_y)
        right = round((self.x + self.width) * scale_x)
        bottom = round((self.y + self.height) * scale_y)

        return (
            max(0, min(source_width, left)),
            max(0, min(source_height, top)),
            max(0, min(source_width, right)),
            max(0, min(source_height, bottom)),
        )


@dataclass(frozen=True, slots=True)
class RegionPreset:
    name: str
    width: int
    height: int
    regions: tuple[Region, ...]

    @property
    def base_size(self) -> tuple[int, int]:
        return (self.width, self.height)

    def get(self, name: str) -> Region:
        for region in self.regions:
            if region.name == name:
                return region
        raise KeyError(f"Unknown region: {name}")


GAME_1920X1080 = RegionPreset(
    name="game-1920x1080",
    width=1920,
    height=1080,
    regions=(
        Region("stage", 590, 0, 210, 72),
        Region("level", 262, 799, 185, 58),
        Region("gold", 900, 806, 210, 58),
        Region("player_hp", 1695, 104, 210, 92),
        Region("traits", 110, 110, 275, 410),
        Region("opponents", 1686, 95, 230, 755),
        Region("scout_board", 420, 235, 1080, 490),
        Region("bench", 410, 704, 1120, 112),
        Region("shop", 260, 856, 1420, 224),
        Region("shop_buy_xp", 280, 878, 188, 84),
        Region("shop_refresh", 280, 979, 188, 82),
        Region("shop_slot_1", 496, 878, 222, 186),
        Region("shop_slot_2", 728, 878, 229, 186),
        Region("shop_slot_3", 963, 878, 226, 186),
        Region("shop_slot_4", 1199, 878, 221, 186),
        Region("shop_slot_5", 1432, 878, 227, 186),
    ),
)


PRESETS = {
    GAME_1920X1080.name: GAME_1920X1080,
}


def default_preset() -> RegionPreset:
    return GAME_1920X1080


def get_preset(name: str) -> RegionPreset:
    try:
        return PRESETS[name]
    except KeyError as exc:
        available = ", ".join(sorted(PRESETS))
        raise KeyError(f"Unknown preset {name!r}. Available presets: {available}") from exc
