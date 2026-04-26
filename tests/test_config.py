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
