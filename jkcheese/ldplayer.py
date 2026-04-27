from __future__ import annotations

import json
import locale
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


GAME_PACKAGE = "com.tencent.jkchess"


class LDPlayerError(RuntimeError):
    pass


@dataclass(slots=True)
class InstalledApp:
    package_name: str
    app_name: str = ""
    version: str = ""


@dataclass(slots=True)
class InstanceInfo:
    index: int
    name: str
    running: bool
    width: int
    height: int
    dpi: int
    apps: list[InstalledApp] = field(default_factory=list)

    @property
    def has_game(self) -> bool:
        return any(app.package_name == GAME_PACKAGE for app in self.apps)

    @property
    def game(self) -> InstalledApp | None:
        for app in self.apps:
            if app.package_name == GAME_PACKAGE:
                return app
        return None


def decode_bytes(raw: bytes) -> str:
    candidates = [
        "utf-8",
        "gb18030",
        "cp936",
        locale.getpreferredencoding(False),
        "cp932",
        "latin-1",
    ]
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _silent_subprocess_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}

    kwargs: dict[str, object] = {}
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if create_no_window:
        kwargs["creationflags"] = create_no_window

    startup_info_type = getattr(subprocess, "STARTUPINFO", None)
    startf_use_show_window = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    if startup_info_type is not None and startf_use_show_window:
        startupinfo = startup_info_type()
        startupinfo.dwFlags |= startf_use_show_window
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo

    return kwargs


def _read_appsinfo(path: Path) -> list[InstalledApp]:
    if not path.exists():
        return []

    try:
        payload = json.loads(decode_bytes(path.read_bytes()).strip())
    except json.JSONDecodeError as exc:
        raise LDPlayerError(f"Failed to parse app info: {path}") from exc

    apps: list[InstalledApp] = []
    for item in payload:
        apps.append(
            InstalledApp(
                package_name=item.get("packageName", ""),
                app_name=item.get("appName", ""),
                version=item.get("version", ""),
            )
        )
    return apps


class LDPlayerClient:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.ldconsole = self.root / "ldconsole.exe"
        self.adb_exe = self.root / "adb.exe"
        if not self.ldconsole.exists():
            raise LDPlayerError(f"ldconsole.exe not found: {self.ldconsole}")
        if not self.adb_exe.exists():
            raise LDPlayerError(f"adb.exe not found: {self.adb_exe}")

    def _run(self, *args: object, timeout: int = 30, check: bool = True) -> str:
        command = [str(self.ldconsole), *(str(arg) for arg in args)]
        result = subprocess.run(
            command,
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            **_silent_subprocess_kwargs(),
        )
        stdout = decode_bytes(result.stdout).strip()
        stderr = decode_bytes(result.stderr).strip()
        if check and result.returncode != 0:
            detail = stderr or stdout or f"exit={result.returncode}"
            raise LDPlayerError(f"Command failed: {' '.join(command)}\n{detail}")
        return stdout or stderr

    def _run_adb(
        self,
        *args: object,
        timeout: int = 30,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        command = [str(self.adb_exe), *(str(arg) for arg in args)]
        result = subprocess.run(
            command,
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            **_silent_subprocess_kwargs(),
        )
        if check and result.returncode != 0:
            detail = decode_bytes(result.stderr).strip() or decode_bytes(result.stdout).strip()
            raise LDPlayerError(f"ADB command failed: {' '.join(command)}\n{detail}")
        return result

    def list_instances(self) -> list[InstanceInfo]:
        output = self._run("list2")
        instances: list[InstanceInfo] = []

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 10:
                continue

            index = int(parts[0])
            instances.append(
                InstanceInfo(
                    index=index,
                    name=parts[1],
                    running=self.is_running(index),
                    width=int(parts[7]),
                    height=int(parts[8]),
                    dpi=int(parts[9]),
                    apps=_read_appsinfo(self.root / "vms" / f"leidian{index}" / "appsinfo.data"),
                )
            )

        return instances

    def get_instance(self, index: int) -> InstanceInfo:
        for instance in self.list_instances():
            if instance.index == index:
                return instance
        raise LDPlayerError(f"Instance {index} was not found")

    def is_running(self, index: int) -> bool:
        return self._run("isrunning", "--index", index).strip().lower() == "running"

    def launch(self, index: int) -> None:
        self._run("launch", "--index", index)

    def run_app(self, index: int, package_name: str) -> None:
        self._run("runapp", "--index", index, "--packagename", package_name)

    def adb(self, index: int, command: str, timeout: int = 30) -> str:
        return self._run("adb", "--index", index, "--command", command, timeout=timeout)

    def resolve_package_path(self, index: int, package_name: str = GAME_PACKAGE) -> str | None:
        output = self.adb(index, f"shell pm path {package_name}", timeout=15)
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                return line.removeprefix("package:")
        return None

    def is_package_running(self, index: int, package_name: str = GAME_PACKAGE) -> bool:
        return bool(self.adb(index, f"shell pidof {package_name}", timeout=15).strip())

    def list_adb_devices(self) -> list[str]:
        result = self._run_adb("devices", timeout=15)
        devices: list[str] = []
        for line in decode_bytes(result.stdout).splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices attached"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def serial_for_index(self, index: int) -> str:
        devices = self.list_adb_devices()
        expected = f"emulator-{5554 + index * 2}"
        if expected in devices:
            return expected
        if len(devices) == 1 and index == 0:
            return devices[0]
        detail = ", ".join(devices) if devices else "no connected devices"
        raise LDPlayerError(f"Could not match instance {index} to an ADB serial. Devices: {detail}")

    def wait_for_running(self, index: int, timeout: int = 90) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_running(index):
                return
            time.sleep(1)
        raise LDPlayerError(f"Instance {index} did not reach running state in {timeout} seconds")

    def wait_for_boot(self, index: int, timeout: int = 120) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                boot_completed = self.adb(index, "shell getprop sys.boot_completed", timeout=10)
            except LDPlayerError:
                time.sleep(2)
                continue
            if boot_completed.strip() == "1":
                return
            time.sleep(2)
        raise LDPlayerError(f"Android on instance {index} did not finish booting in {timeout} seconds")

    def capture_screenshot(
        self,
        index: int,
        output_path: Path,
        launch_if_needed: bool = False,
    ) -> Path:
        if not self.is_running(index):
            if not launch_if_needed:
                raise LDPlayerError(
                    f"Instance {index} is not running. Use launch first or add --launch-if-needed."
                )
            self.launch(index)
            self.wait_for_running(index)

        self.wait_for_boot(index)

        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        serial = self.serial_for_index(index)
        result = self._run_adb("-s", serial, "exec-out", "screencap", "-p", timeout=30)
        image_bytes = result.stdout
        if not image_bytes.startswith(b"\x89PNG"):
            detail = decode_bytes(result.stderr).strip() or decode_bytes(image_bytes[:200]).strip()
            raise LDPlayerError(f"Screenshot output was not a valid PNG stream: {detail}")

        output_path.write_bytes(image_bytes)
        return output_path
