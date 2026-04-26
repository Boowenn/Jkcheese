from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def _config_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    return base / "Jkcheese"


def _default_ldplayer_root() -> str:
    candidates = [
        Path(r"C:\leidian\LDPlayer9"),
        Path(r"C:\LDPlayer\LDPlayer9"),
        Path(r"C:\Program Files\LDPlayer9"),
        Path(r"C:\Program Files (x86)\LDPlayer9"),
    ]
    for candidate in candidates:
        if (candidate / "ldconsole.exe").exists():
            return str(candidate)
    return ""


def default_capture_dir() -> Path:
    pictures = Path.home() / "Pictures"
    if pictures.exists():
        return pictures / "JkcheeseCaptures"
    return Path.home() / "JkcheeseCaptures"


@dataclass(slots=True)
class AppConfig:
    ldplayer_root: str = _default_ldplayer_root()
    instance_index: int = 0
    capture_dir: str = str(default_capture_dir())
    capture_retention_sessions: int = 80
    capture_retention_days: int = 1
    auto_scan_enabled: bool = True
    auto_scan_interval_seconds: int = 12
    overlay_enabled: bool = True

    @classmethod
    def load(cls) -> "AppConfig":
        path = _config_dir() / "config.json"
        if not path.exists():
            return cls()

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()

        config = cls()
        config.ldplayer_root = str(payload.get("ldplayer_root", config.ldplayer_root))
        config.instance_index = _safe_int(payload.get("instance_index"), config.instance_index, minimum=0)
        config.capture_dir = str(payload.get("capture_dir", config.capture_dir))
        config.capture_retention_sessions = _safe_int(
            payload.get("capture_retention_sessions"),
            config.capture_retention_sessions,
            minimum=5,
        )
        config.capture_retention_days = _safe_int(
            payload.get("capture_retention_days"),
            config.capture_retention_days,
            minimum=0,
        )
        config.auto_scan_enabled = _safe_bool(payload.get("auto_scan_enabled"), config.auto_scan_enabled)
        config.auto_scan_interval_seconds = _safe_int(
            payload.get("auto_scan_interval_seconds"),
            config.auto_scan_interval_seconds,
            minimum=5,
        )
        config.overlay_enabled = _safe_bool(payload.get("overlay_enabled"), config.overlay_enabled)
        return config

    def save(self) -> None:
        path = _config_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def _safe_int(value: object, default: int, *, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _safe_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default
