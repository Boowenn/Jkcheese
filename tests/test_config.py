from __future__ import annotations

from pathlib import Path

from jkcheese.config import AppConfig


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    config = AppConfig(
        ldplayer_root=r"C:\leidian\LDPlayer9",
        instance_index=2,
        capture_dir=str(Path(r"C:\captures")),
    )
    config.save()

    loaded = AppConfig.load()

    assert loaded.ldplayer_root == r"C:\leidian\LDPlayer9"
    assert loaded.instance_index == 2
    assert loaded.capture_dir == str(Path(r"C:\captures"))
