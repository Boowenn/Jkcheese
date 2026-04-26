from __future__ import annotations

from jkcheese.lineups import DEFAULT_TAB_ID, extract_s_lineups_from_grid, parse_docs_url, recommend_lineups


def test_parse_docs_url_reads_tab_id():
    doc_id, tab_id = parse_docs_url("https://docs.qq.com/sheet/DTmFrR3dDWVBsYmxo?tab=99oz3s")

    assert doc_id == "DTmFrR3dDWVBsYmxo"
    assert tab_id == "99oz3s"


def test_parse_docs_url_defaults_to_realtime_tab():
    doc_id, tab_id = parse_docs_url("https://docs.qq.com/sheet/abc")

    assert doc_id == "abc"
    assert tab_id == DEFAULT_TAB_ID


def test_extract_s_lineups_uses_first_block_after_marker():
    grid = {
        10: {8: "↑神器"},
        11: {0: "23新星\n薇古丝95", 4: "【阵容码】#23新星薇古丝95-小鱼一图流#abc"},
        12: {0: "暗星机甲", 1: "3幻/远征\n需要偷3", 4: "【阵容码】#暗星机甲-小鱼一图流#def"},
        13: {0: "盗宗5牧羊 / 不刚需转", 4: "【阵容码】#盗宗57牧羊-公众号小鱼一图流#ghi"},
        14: {},
        15: {0: "装唐流 / 得会连胜", 4: "【阵容码】#装唐流-小鱼一图流#jkl"},
    }

    lineups = extract_s_lineups_from_grid(grid)

    assert [lineup.name for lineup in lineups] == ["23新星 薇古丝95", "暗星机甲", "盗宗5牧羊"]
    assert lineups[1].notes == ("3幻/远征 需要偷3",)
    assert lineups[2].notes == ("不刚需转",)


def test_recommend_lineups_prioritizes_seen_tokens():
    grid = {
        1: {8: "↑神器"},
        2: {0: "23新星\n薇古丝95", 4: "【阵容码】#23新星薇古丝95-小鱼一图流#abc"},
        3: {0: "暗星机甲", 1: "3幻/远征\n需要偷3", 4: "【阵容码】#暗星机甲-小鱼一图流#def"},
    }
    lineups = extract_s_lineups_from_grid(grid)

    recommendations = recommend_lineups(lineups, "机甲 远征", limit=1)

    assert recommendations[0].lineup.name == "暗星机甲"
    assert recommendations[0].matched_tokens == ("机甲", "远征")
