from __future__ import annotations

from pathlib import Path

from jkcheese.card_tracker import CardTrackerState
from jkcheese.lineups import Lineup
from jkcheese.shop_hits import build_shop_hit_alerts, format_shop_hit_alerts
from jkcheese.shop_recognition import ShopScanReport, ShopSlotReading


def test_shop_hit_alerts_flag_direct_three_star_purchase():
    report = _report(ShopSlotReading(slot=3, occupied=True, name="Vex", cost=4, confidence=0.95, source="template"))
    state = CardTrackerState(counts={"Vex": 8}, costs={"Vex": 4})

    alerts = build_shop_hit_alerts(report, state)

    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert alerts[0].after_buy_count == 9
    assert "买下就是9/9三星" in alerts[0].title
    assert "槽位3 Vex" in format_shop_hit_alerts(alerts)


def test_shop_hit_alerts_include_s_lineup_context():
    report = _report(ShopSlotReading(slot=1, occupied=True, name="娜美", cost=5, confidence=0.8, source="name-ocr"))
    state = CardTrackerState()
    lineups = (Lineup(name="律动娜美", tier="S"),)

    alerts = build_shop_hit_alerts(report, state, lineups=lineups)

    assert alerts[0].severity == "medium"
    assert alerts[0].matched_lineups == ("律动娜美",)


def _report(*slots: ShopSlotReading) -> ShopScanReport:
    return ShopScanReport(
        image_path=Path("screen.png"),
        output_dir=None,
        slots=slots,
        templates_path=Path("templates.json"),
        template_count=0,
        candidate_count=0,
    )
