from __future__ import annotations

from zipfile import ZipFile

import pytest

from jkcheese.lineups import (
    DEFAULT_TAB_ID,
    extract_lineups_from_rows,
    extract_s_lineups_from_grid,
    fetch_jcc_s_lineups,
    load_lineups_from_file,
    parse_docs_url,
    parse_lineup_code,
    LineupSourceError,
    recommend_lineups,
)


def test_parse_docs_url_reads_tab_id():
    doc_id, tab_id = parse_docs_url("https://docs.qq.com/sheet/DTmFrR3dDWVBsYmxo?tab=99oz3s")

    assert doc_id == "DTmFrR3dDWVBsYmxo"
    assert tab_id == "99oz3s"


def test_parse_docs_url_defaults_to_realtime_tab():
    doc_id, tab_id = parse_docs_url("https://docs.qq.com/sheet/abc")

    assert doc_id == "abc"
    assert tab_id == DEFAULT_TAB_ID


def test_parse_lineup_code_matches_reference_parser_dictionary():
    code = "0201f02003a000000000000000000000000TFTSet17"

    assert parse_lineup_code(code) == ("千珏", "卡莎", "薇古丝")


def test_extract_lineups_from_rows_reads_excel_style_lineup_codes():
    code = "0201f02003a000000000000000000000000TFTSet17"

    lineups = extract_lineups_from_rows(
        (
            ("评级", "阵容名", "阵容码", "备注"),
            ("S", "千珏卡莎", f"【阵容码】#{code}#", "上限高"),
        )
    )

    assert len(lineups) == 1
    assert lineups[0].tier == "S"
    assert lineups[0].name == "千珏卡莎"
    assert lineups[0].code == code
    assert lineups[0].champions == ("千珏", "卡莎", "薇古丝")


def test_load_lineups_from_csv_file(tmp_path):
    csv_path = tmp_path / "lineups.csv"
    csv_path.write_text(
        "tier,name,code\nS,千珏卡莎,0201f02003a000000000000000000000000TFTSet17\n",
        encoding="utf-8",
    )

    lineups = load_lineups_from_file(csv_path)

    assert lineups[0].name == "千珏卡莎"
    assert lineups[0].champions[:2] == ("千珏", "卡莎")


def test_load_lineups_from_xlsx_file(tmp_path):
    xlsx_path = tmp_path / "lineups.xlsx"
    with ZipFile(xlsx_path, "w") as workbook:
        workbook.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="6" uniqueCount="6">
  <si><t>S</t></si>
  <si><t>千珏卡莎</t></si>
  <si><t>0201f02003a000000000000000000000000TFTSet17</t></si>
</sst>""",
        )
        workbook.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
      <c r="C1" t="s"><v>2</v></c>
    </row>
  </sheetData>
</worksheet>""",
        )

    lineups = load_lineups_from_file(xlsx_path)

    assert lineups[0].name == "千珏卡莎"
    assert lineups[0].champions == ("千珏", "卡莎", "薇古丝")


def test_missing_local_lineup_file_does_not_fall_back_to_network(tmp_path):
    with pytest.raises(LineupSourceError, match="Local lineup file was not found"):
        fetch_jcc_s_lineups(str(tmp_path / "missing.csv"))


def test_extract_s_lineups_includes_s_minus_block_after_marker():
    grid = {
        10: {8: "↑神器"},
        11: {0: "23新星\n薇古丝95", 4: "【阵容码】#23新星薇古丝95-小鱼一图流#abc"},
        12: {0: "暗星机甲", 1: "3幻/远征\n需要偷3", 4: "【阵容码】#暗星机甲-小鱼一图流#def"},
        13: {0: "盗宗5牧羊 / 不刚需转", 4: "【阵容码】#盗宗57牧羊-公众号小鱼一图流#ghi"},
        14: {},
        15: {0: "装唐流 / 得会连胜", 4: "【阵容码】#装唐流-小鱼一图流#jkl"},
        16: {},
        17: {0: "低优先阵容", 4: "【阵容码】#低优先阵容#zzz"},
    }

    lineups = extract_s_lineups_from_grid(grid)

    assert [lineup.name for lineup in lineups] == ["23新星 薇古丝95", "暗星机甲", "盗宗5牧羊", "装唐流"]
    assert lineups[1].notes == ("3幻/远征 需要偷3",)
    assert lineups[2].notes == ("不刚需转",)
    assert [lineup.tier for lineup in lineups] == ["S", "S", "S", "S-"]


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


def test_recommend_lineups_prioritizes_lineup_code_heroes_over_text_notes():
    lineups = extract_lineups_from_rows(
        (
            ("S", "卡莎阵容", "0201f02003a000000000000000000000000TFTSet17"),
            ("S", "备注写卡莎但阵容码无卡莎", "02001d000000000000000000000000000000TFTSet17", "卡莎"),
        )
    )

    recommendations = recommend_lineups(lineups, ("卡莎",), limit=2)

    assert recommendations[0].lineup.name == "卡莎阵容"
    assert recommendations[0].matched_tokens == ("卡莎",)
