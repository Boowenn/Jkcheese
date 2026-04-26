from __future__ import annotations

import json

from jkcheese.card_tracker import (
    CardTrackerState,
    apply_owned_counts,
    build_core_advice,
    build_upgrade_warnings,
    load_card_state,
    normalize_tokens,
    parse_owned_counts,
    reset_card_state,
)
from jkcheese.lineups import Lineup


def test_normalize_tokens_splits_common_separators():
    assert normalize_tokens("Vex, Mecha/Vanguard，Nami") == ("Vex", "Mecha", "Vanguard", "Nami")


def test_parse_owned_counts_supports_suffix_and_repeated_tokens():
    parsed = parse_owned_counts(["4费Vexx2", "Vex", "五费", "Nami=7", "Nami"])

    assert [(item.token, item.count, item.cost) for item in parsed] == [("Vex", 3, 4), ("Nami", 8, 5)]


def test_parse_owned_counts_supports_at_cost_form():
    parsed = parse_owned_counts("Vex@4x7")

    assert [(item.token, item.count, item.cost) for item in parsed] == [("Vex", 7, 4)]


def test_apply_owned_counts_add_and_replace_modes():
    state = CardTrackerState(counts={"Vex": 2})

    apply_owned_counts(state, ["4费Vexx2", "Nami"], mode="add")
    assert state.counts == {"Vex": 4, "Nami": 1}
    assert state.costs == {"Vex": 4}

    apply_owned_counts(state, ["五费Nami=8"], mode="replace")
    assert state.counts == {"Nami": 8}
    assert state.costs == {"Nami": 5}


def test_upgrade_warnings_include_s_lineup_context():
    lineups = (Lineup(name="Mecha Vex", tier="S", notes=("reroll",)),)
    warnings = build_upgrade_warnings(CardTrackerState(counts={"Vex": 8}, costs={"Vex": 4}), lineups)

    assert warnings[0].severity == "critical"
    assert warnings[0].cost == 4
    assert warnings[0].pool_size == 10
    assert warnings[0].matched_lineups == ("Mecha Vex",)


def test_pool_sizes_can_be_overridden_for_season_variants():
    warnings = build_upgrade_warnings(
        CardTrackerState(counts={"Vex": 7}, costs={"Vex": 4}),
        pool_sizes={4: 12},
    )

    assert warnings[0].pool_size == 12
    assert "about 12" in warnings[0].detail


def test_low_cost_warnings_are_suppressed_before_completion_by_default():
    warnings = build_upgrade_warnings(CardTrackerState(counts={"Cheap": 8}, costs={"Cheap": 1}))

    assert warnings == ()


def test_build_core_advice_persists_state_and_ranks_lineups(tmp_path):
    state_path = tmp_path / "cards.json"
    lineups = (
        Lineup(name="Default Nami", tier="S"),
        Lineup(name="Mecha Vex", tier="S", notes=("Vanguard",)),
    )

    report = build_core_advice(
        state_path=state_path,
        lineups=lineups,
        seen="Vanguard",
        owned="4费Vexx7",
        reset=True,
    )

    assert report.state.counts == {"Vex": 7}
    assert report.state.costs == {"Vex": 4}
    assert report.pool_sizes == {1: 30, 2: 25, 3: 18, 4: 10, 5: 9}
    assert report.recommendations[0].lineup.name == "Mecha Vex"
    assert report.warnings[0].severity == "critical"
    assert json.loads(state_path.read_text(encoding="utf-8"))["counts"] == {"Vex": 7}
    assert json.loads(state_path.read_text(encoding="utf-8"))["costs"] == {"Vex": 4}


def test_reset_card_state_writes_empty_state(tmp_path):
    state_path = tmp_path / "cards.json"

    reset_card_state(state_path)

    assert load_card_state(state_path).counts == {}
    assert load_card_state(state_path).costs == {}
