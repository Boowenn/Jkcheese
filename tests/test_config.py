from __future__ import annotations

import json
from pathlib import Path

from jkcheese.config import AppConfig


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    config = AppConfig(
        ldplayer_root=r"C:\leidian\LDPlayer9",
        instance_index=2,
        capture_dir=str(Path(r"C:\captures")),
        capture_retention_sessions=12,
        capture_retention_days=2,
        auto_scan_enabled=False,
        auto_scan_interval_seconds=15,
        overlay_enabled=False,
        overlay_x=321,
        overlay_y=123,
        highlight_drag_enabled=True,
        highlight_offset_x=24,
        highlight_offset_y=-18,
        ui_position_version=1,
    )
    config.save()

    loaded = AppConfig.load()

    assert loaded.ldplayer_root == r"C:\leidian\LDPlayer9"
    assert loaded.instance_index == 2
    assert loaded.capture_dir == str(Path(r"C:\captures"))
    assert loaded.capture_retention_sessions == 12
    assert loaded.capture_retention_days == 2
    assert loaded.auto_scan_enabled is False
    assert loaded.auto_scan_interval_seconds == 15
    assert loaded.overlay_enabled is False
    assert loaded.overlay_x == 321
    assert loaded.overlay_y == 123
    assert loaded.highlight_drag_enabled is False
    assert loaded.highlight_offset_x == 24
    assert loaded.highlight_offset_y == -18
    assert loaded.ui_position_version == 1
    assert loaded.auto_buy_enabled is False


def test_legacy_auto_buy_config_is_migrated_off(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config_path = tmp_path / "Jkcheese" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"auto_buy_enabled": True}), encoding="utf-8")

    loaded = AppConfig.load()

    assert loaded.auto_buy_enabled is False


def test_legacy_highlight_drag_config_is_session_only(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config_path = tmp_path / "Jkcheese" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"highlight_drag_enabled": True}), encoding="utf-8")

    loaded = AppConfig.load()

    assert loaded.highlight_drag_enabled is False


def test_legacy_config_without_position_version_is_marked_for_gui_migration(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config_path = tmp_path / "Jkcheese" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"overlay_x": 1552, "overlay_y": 72}), encoding="utf-8")

    loaded = AppConfig.load()

    assert loaded.overlay_x == 1552
    assert loaded.overlay_y == 72
    assert loaded.ui_position_version == 0


def test_auto_buy_cannot_be_enabled_by_constructor():
    assert AppConfig(auto_buy_enabled=True).auto_buy_enabled is False


def test_highlight_drag_cannot_be_persisted_by_constructor():
    assert AppConfig(highlight_drag_enabled=True).highlight_drag_enabled is False
