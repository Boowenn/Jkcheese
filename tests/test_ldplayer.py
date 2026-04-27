from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from jkcheese.ldplayer import LDPlayerClient, LDPlayerError, _silent_subprocess_kwargs, decode_bytes


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "LDPlayer9"
    root.mkdir()
    (root / "ldconsole.exe").write_bytes(b"")
    (root / "adb.exe").write_bytes(b"")
    return root


def test_decode_bytes_understands_gb18030():
    assert decode_bytes("金铲铲之战".encode("gb18030")) == "金铲铲之战"


def test_windows_subprocesses_run_without_console_windows():
    kwargs = _silent_subprocess_kwargs()
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW
        assert "startupinfo" in kwargs
    else:
        assert kwargs == {}


def test_list_instances_parses_installed_game(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    appsinfo = root / "vms" / "leidian0"
    appsinfo.mkdir(parents=True)
    (appsinfo / "appsinfo.data").write_text(
        json.dumps(
            [
                {
                    "appName": "金铲铲之战",
                    "packageName": "com.tencent.jkchess",
                    "version": "1148",
                }
            ]
        ),
        encoding="utf-8",
    )

    client = LDPlayerClient(root)

    def fake_run(*args, **kwargs):
        if args[0] == "list2":
            return "0,雷电模拟器,0,0,0,-1,-1,1920,1080,280"
        if args[0] == "isrunning":
            return "running"
        raise AssertionError(args)

    monkeypatch.setattr(client, "_run", fake_run)

    instances = client.list_instances()

    assert len(instances) == 1
    assert instances[0].index == 0
    assert instances[0].has_game is True
    assert instances[0].game is not None
    assert instances[0].game.app_name == "金铲铲之战"


def test_serial_for_index_prefers_expected_device(tmp_path, monkeypatch):
    client = LDPlayerClient(make_root(tmp_path))
    monkeypatch.setattr(client, "list_adb_devices", lambda: ["emulator-5554", "emulator-5556"])
    assert client.serial_for_index(0) == "emulator-5554"
    assert client.serial_for_index(1) == "emulator-5556"


def test_serial_for_index_raises_when_no_match(tmp_path, monkeypatch):
    client = LDPlayerClient(make_root(tmp_path))
    monkeypatch.setattr(client, "list_adb_devices", lambda: ["emulator-5558"])
    with pytest.raises(LDPlayerError):
        client.serial_for_index(1)


def test_capture_screenshot_writes_png(tmp_path, monkeypatch):
    client = LDPlayerClient(make_root(tmp_path))
    monkeypatch.setattr(client, "is_running", lambda index: True)
    monkeypatch.setattr(client, "wait_for_boot", lambda index: None)
    monkeypatch.setattr(client, "serial_for_index", lambda index: "emulator-5554")
    monkeypatch.setattr(
        client,
        "_run_adb",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=b"\x89PNG\r\n\x1a\npayload", stderr=b""),
    )

    output = tmp_path / "captures" / "shot.png"
    saved = client.capture_screenshot(0, output)

    assert saved == output.resolve()
    assert output.read_bytes().startswith(b"\x89PNG")


def test_capture_screenshot_can_launch_if_needed(tmp_path, monkeypatch):
    client = LDPlayerClient(make_root(tmp_path))
    state = {"running": False}

    def is_running(index):
        return state["running"]

    def launch(index):
        state["running"] = True

    monkeypatch.setattr(client, "is_running", is_running)
    monkeypatch.setattr(client, "launch", launch)
    monkeypatch.setattr(client, "wait_for_running", lambda index: None)
    monkeypatch.setattr(client, "wait_for_boot", lambda index: None)
    monkeypatch.setattr(client, "serial_for_index", lambda index: "emulator-5554")
    monkeypatch.setattr(
        client,
        "_run_adb",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=b"\x89PNG\r\n\x1a\npayload", stderr=b""),
    )

    saved = client.capture_screenshot(0, tmp_path / "auto.png", launch_if_needed=True)

    assert state["running"] is True
    assert saved.exists()


def test_capture_screenshot_rejects_non_png(tmp_path, monkeypatch):
    client = LDPlayerClient(make_root(tmp_path))
    monkeypatch.setattr(client, "is_running", lambda index: True)
    monkeypatch.setattr(client, "wait_for_boot", lambda index: None)
    monkeypatch.setattr(client, "serial_for_index", lambda index: "emulator-5554")
    monkeypatch.setattr(
        client,
        "_run_adb",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=b"not-png", stderr=b""),
    )

    with pytest.raises(LDPlayerError):
        client.capture_screenshot(0, tmp_path / "bad.png")
