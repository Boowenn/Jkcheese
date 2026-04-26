from __future__ import annotations

import os

from jkcheese.capture_cleanup import cleanup_capture_dir


def touch(path, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_cleanup_deletes_only_generated_capture_artifacts(tmp_path):
    now = 1_700_000_000.0
    old_session = tmp_path / "dashboard_20240101_120000"
    old_session.mkdir()
    touch(old_session / "screen.png", now - 10 * 24 * 60 * 60)
    os.utime(old_session, (now - 10 * 24 * 60 * 60, now - 10 * 24 * 60 * 60))

    kept_session = tmp_path / "dashboard_20240108_120000"
    kept_session.mkdir()
    touch(kept_session / "screen.png", now)
    os.utime(kept_session, (now, now))

    template = tmp_path / "shop_templates.json"
    template.write_text("{}", encoding="utf-8")
    manual_dir = tmp_path / "my_manual_notes"
    manual_dir.mkdir()
    touch(manual_dir / "screen.png", now - 30 * 24 * 60 * 60)

    report = cleanup_capture_dir(tmp_path, max_sessions=10, max_age_days=7, now=now)

    assert report.deleted_count == 1
    assert not old_session.exists()
    assert kept_session.exists()
    assert template.exists()
    assert manual_dir.exists()


def test_cleanup_can_clear_live_and_all_generated_sessions_at_match_end(tmp_path):
    live_dir = tmp_path / "_live"
    live_dir.mkdir()
    touch(live_dir / "screen.png", 1_700_000_000.0)
    session = tmp_path / "scout_20240108_120000"
    session.mkdir()
    touch(session / "screen.png", 1_700_000_000.0)
    state = tmp_path / "card_state.json"
    state.write_text("{}", encoding="utf-8")

    report = cleanup_capture_dir(tmp_path, max_sessions=0, max_age_days=0, now=1_700_000_001.0)

    assert report.deleted_count == 2
    assert not live_dir.exists()
    assert not session.exists()
    assert state.exists()
