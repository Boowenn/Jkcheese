from __future__ import annotations

from PIL import Image

from jkcheese.region_capture import crop_regions
from jkcheese.regions import GAME_1920X1080, Region, RegionPreset, default_preset


def test_region_box_scales_to_source_size():
    region = Region("sample", 10, 20, 30, 40)

    assert region.box_for((200, 300), (100, 100)) == (20, 60, 80, 180)


def test_default_preset_contains_core_regions():
    preset = default_preset()
    names = {region.name for region in preset.regions}

    assert preset is GAME_1920X1080
    assert {"gold", "level", "player_hp", "shop", "shop_slot_1", "shop_slot_5"} <= names


def test_region_preset_get_rejects_unknown_region():
    preset = RegionPreset(name="tiny", width=100, height=100, regions=(Region("known", 0, 0, 10, 10),))

    try:
        preset.get("missing")
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Expected KeyError")


def test_crop_regions_writes_selected_files(tmp_path):
    source = tmp_path / "screen.png"
    Image.new("RGB", (1920, 1080), "black").save(source)

    results = crop_regions(source, tmp_path / "regions", names=["gold", "level"])

    assert [result.name for result in results] == ["gold", "level"]
    assert results[0].path.name == "screen_gold.png"
    assert results[0].path.exists()
    assert results[1].path.exists()

    with Image.open(results[0].path) as crop:
        assert crop.size == (210, 58)
