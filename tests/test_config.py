from __future__ import annotations

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
    assert loaded.highlight_drag_enabled is True
    assert loaded.highlight_offset_x == 24
    assert loaded.highlight_offset_y == -18
