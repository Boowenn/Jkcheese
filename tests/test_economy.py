from __future__ import annotations

from jkcheese.economy import build_economy_rhythm, format_economy_rhythm, parse_stage


def test_parse_stage_accepts_common_forms():
    assert parse_stage("3-2").label == "3-2"
    assert parse_stage("4:1").label == "4-1"
    assert parse_stage("42").label == "4-2"
    assert parse_stage("9-9") is None


def test_rhythm_recommends_level_six_on_stage_three_two():
    report = build_economy_rhythm(stage="3-2", level=5, gold=32, hp=78)

    titles = [item.title for item in report.advice]
    assert "该升 6" in titles
    assert any(item.action == "save" for item in report.advice)


def test_rhythm_recommends_all_in_when_hp_is_critical():
    report = build_economy_rhythm(stage="4-5", level=8, gold=38, hp=22)

    assert report.advice[0].action == "all_in"
    assert report.advice[0].severity == "critical"


def test_rhythm_recommends_level_eight_or_all_in_at_stage_four_two():
    level_report = build_economy_rhythm(stage="4-2", level=7, gold=46, hp=70)
    all_in_report = build_economy_rhythm(stage="4-2", level=8, gold=50, hp=48)

    assert any(item.title == "该升 8" for item in level_report.advice)
    assert any(item.title == "该 all in 找四费两星" for item in all_in_report.advice)
    assert not any(item.action == "save" for item in all_in_report.advice)


def test_format_rhythm_includes_readings_and_actions():
    report = build_economy_rhythm(stage="5-1", level=8, gold=55, hp=82)
    output = format_economy_rhythm(report)

    assert "阶段 / 经济节奏建议" in output
    assert "阶段=5-1" in output
    assert "该考虑升 9" in output


def test_late_stage_missing_hp_does_not_recommend_greedy_save():
    report = build_economy_rhythm(stage="4-3", level=8, gold=52, hp=None)

    assert "hp" in report.missing
    assert not any(item.action == "save" for item in report.advice)
    assert not any(item.title == "可存钱上 9" for item in report.advice)
