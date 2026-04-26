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
    parsed = parse_owned_counts(["Vexx2", "Vex", "Nami=7", "Nami"])

    assert [(item.token, item.count) for item in parsed] == [("Vex", 3), ("Nami", 8)]


def test_apply_owned_counts_add_and_replace_modes():
    state = CardTrackerState(counts={"Vex": 2})

    apply_owned_counts(state, ["Vexx2", "Nami"], mode="add")
    assert state.counts == {"Vex": 4, "Nami": 1}

    apply_owned_counts(state, ["Nami=8"], mode="replace")
    assert state.counts == {"Nami": 8}


def test_upgrade_warnings_include_s_lineup_context():
    lineups = (Lineup(name="Mecha Vex", tier="S", notes=("reroll",)),)
    warnings = build_upgrade_warnings(CardTrackerState(counts={"Vex": 8}), lineups)

    assert warnings[0].severity == "critical"
    assert warnings[0].matched_lineups == ("Mecha Vex",)


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
        owned="Vexx7",
        reset=True,
    )

    assert report.state.counts == {"Vex": 7}
    assert report.recommendations[0].lineup.name == "Mecha Vex"
    assert report.warnings[0].severity == "high"
    assert json.loads(state_path.read_text(encoding="utf-8"))["counts"] == {"Vex": 7}


def test_reset_card_state_writes_empty_state(tmp_path):
    state_path = tmp_path / "cards.json"

    reset_card_state(state_path)

    assert load_card_state(state_path).counts == {}
