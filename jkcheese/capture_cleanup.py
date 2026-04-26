from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import time


GENERATED_DIR_RE = re.compile(
    r"^(?:dashboard|shop|shop_scan|tempo|read|advice|regions|scout|core|opponent_scout)?_?\d{8}_\d{6}$"
)
GENERATED_FILE_RE = re.compile(r"^(?:jkcheese|screen)_\d{8}_\d{6}\.png$", re.IGNORECASE)
GENERATED_CONTAINER_NAMES = frozenset(
    {
        "advice",
        "core",
        "opponent_scout",
        "read",
        "reads",
        "regions",
        "scout",
        "shop",
        "shop_scan",
        "tempo",
    }
)
GENERATED_SINGLE_DIR_NAMES = frozenset({"_live"})


@dataclass(frozen=True, slots=True)
class CleanupReport:
    root: Path
    deleted_paths: tuple[Path, ...]
    kept_count: int

    @property
    def deleted_count(self) -> int:
        return len(self.deleted_paths)


def cleanup_capture_dir(
    capture_dir: Path,
    *,
    max_sessions: int = 40,
    max_age_days: int = 7,
    now: float | None = None,
) -> CleanupReport:
    """Delete old generated screenshots while preserving user config/template files."""

    root = capture_dir.resolve()
    if not root.exists():
        return CleanupReport(root=root, deleted_paths=(), kept_count=0)
    if not root.is_dir():
        return CleanupReport(root=root, deleted_paths=(), kept_count=0)

    candidates = _generated_candidates(root)
    cutoff = (now if now is not None else time.time()) - max(0, max_age_days) * 24 * 60 * 60
    newest_first = sorted(candidates, key=lambda path: _mtime(path), reverse=True)
    keep = set(newest_first[: max(0, max_sessions)])
    deleted: list[Path] = []

    for path in newest_first:
        should_delete = path not in keep or _mtime(path) < cutoff
        if not should_delete:
            continue
        if _delete_generated_path(root, path):
            deleted.append(path)

    remaining = len(_generated_candidates(root))
    return CleanupReport(root=root, deleted_paths=tuple(deleted), kept_count=remaining)


def _generated_candidates(root: Path) -> tuple[Path, ...]:
    candidates: list[Path] = []
    for child in root.iterdir():
        if child.is_dir() and GENERATED_DIR_RE.match(child.name):
            candidates.append(child)
        elif child.is_dir() and child.name in GENERATED_SINGLE_DIR_NAMES:
            candidates.append(child)
        elif child.is_dir() and child.name in GENERATED_CONTAINER_NAMES:
            candidates.extend(_generated_candidates(child))
        elif child.is_file() and GENERATED_FILE_RE.match(child.name):
            candidates.append(child)
    return tuple(candidates)


def _delete_generated_path(root: Path, path: Path) -> bool:
    resolved = path.resolve()
    if not _is_within(root, resolved):
        return False
    if resolved.is_dir():
        shutil.rmtree(resolved)
        return True
    if resolved.is_file():
        resolved.unlink()
        return True
    return False


def _is_within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
