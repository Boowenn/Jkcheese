from __future__ import annotations

from jkcheese.card_tracker import CardTrackerState
from jkcheese.chase_calculator import (
    ChaseInput,
    build_chase_report,
    build_chase_reports_from_state,
    format_chase_report,
    parse_contested_counts,
)


def test_chase_report_blocks_when_pool_cannot_complete():
    report = build_chase_report(ChaseInput(name="Vex", cost=4, owned=7, contested=2, level=8, gold=80))

    assert report.needed == 2
    assert report.remaining_target == 1
    assert report.probability == 0
    assert report.risk == "impossible"
    assert "牌库剩余不够" in report.title


def test_chase_report_estimates_high_cost_all_in_probability():
    report = build_chase_report(
        ChaseInput(
            name="千珏",
            cost=4,
            owned=8,
            contested=0,
            level=8,
            gold=30,
            cost_odds_percent=30,
            same_cost_units=13,
        )
    )

    assert report.needed == 1
    assert report.rolls == 13
    assert report.attempts == 65
    assert report.probability > 0.25
    assert "追三概率: 千珏(4费)" in format_chase_report(report)


def test_chase_report_reserves_future_buy_gold():
    report = build_chase_report(ChaseInput(name="五费", cost=5, owned=7, level=9, gold=12, cost_odds_percent=15))

    assert report.needed == 2
    assert report.roll_budget == 2
    assert report.rolls == 1


def test_build_chase_reports_from_state_uses_visible_shop_copy():
    state = CardTrackerState(counts={"千珏": 8}, costs={"千珏": 4})

    reports = build_chase_reports_from_state(state, level=8, gold=30, visible_counts={"千珏": 1})

    assert reports[0].needed == 0
    assert reports[0].risk == "complete"


def test_parse_contested_counts_supports_common_forms():
    assert parse_contested_counts(["千珏=2", "Vexx1"]) == {"千珏": 2, "Vex": 1}
