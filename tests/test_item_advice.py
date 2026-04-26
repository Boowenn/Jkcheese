from __future__ import annotations

from jkcheese.card_tracker import CardTrackerState
from jkcheese.item_advice import build_item_advice, format_item_advice
from jkcheese.lineups import Lineup, recommend_lineups


def test_item_advice_picks_named_ap_carry_and_craftable_items():
    lineups = (
        Lineup(
            name="23新星 薇古丝95",
            tier="S",
            code="【阵容码】#23新星薇古丝95-小鱼一图流#abc",
        ),
    )
    recommendations = recommend_lineups(lineups, ("薇古丝",), limit=1)
    state = CardTrackerState(counts={"薇古丝": 2}, costs={"薇古丝": 4})

    report = build_item_advice(
        recommendations,
        state=state,
        shop_names=("薇古丝", "盖伦"),
        item_components=("眼泪", "眼泪", "大棒", "拳套"),
    )

    plan = report.plans[0]
    assert plan.main_carry == "薇古丝"
    assert plan.carry_role == "ap_carry"
    assert plan.main_tank == "盖伦"
    assert "蓝霸符" in plan.carry_items
    assert any(status.item == "蓝霸符" and status.can_build for status in plan.recipe_statuses)
    assert any(status.item == "珠光护手" and status.can_build for status in plan.recipe_statuses)


def test_item_advice_uses_keyword_fallback_when_lineup_has_no_champion_name():
    lineups = (Lineup(name="暗星机甲", tier="S", notes=("3幻/远征 需要偷3",)),)
    recommendations = recommend_lineups(lineups, (), limit=1)

    report = build_item_advice(recommendations)

    plan = report.plans[0]
    assert plan.carry_role == "fighter_carry"
    assert plan.carry_confidence == "低置信"
    assert "机甲" in plan.main_carry
    assert "泰坦的坚决" in plan.carry_items


def test_format_item_advice_includes_shop_components_and_next_step():
    lineups = (Lineup(name="律动娜美", tier="S"),)
    recommendations = recommend_lineups(lineups, ("娜美",), limit=1)
    report = build_item_advice(
        recommendations,
        shop_names="娜美",
        item_components="眼泪 大剑",
    )

    output = format_item_advice(report)

    assert "装备 / 主 C 提醒" in output
    assert "当前来牌: 娜美" in output
    assert "已输入散件" in output
    assert "主 C: 娜美" in output
    assert "现在能合: 朔极之矛" in output
