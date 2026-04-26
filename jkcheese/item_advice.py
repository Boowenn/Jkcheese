from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Iterable

from .card_tracker import CardTrackerState, normalize_tokens
from .lineups import LineupRecommendation
from .shop_recognition import DEFAULT_CHAMPION_NAMES


AP_ITEMS = (
    "蓝霸符",
    "朔极之矛",
    "珠光护手",
    "纳什之牙",
    "灭世者的死亡之帽",
    "海克斯科技枪刃",
    "正义之手",
)
AD_ITEMS = (
    "鬼索的狂暴之刃",
    "最后的轻语",
    "无尽之刃",
    "巨人捕手",
    "锐利之刃",
    "红霸符",
)
FIGHTER_ITEMS = (
    "汲取剑",
    "泰坦的坚决",
    "斯特拉克的挑战护手",
    "夜之锋刃",
    "正义之手",
)
TANK_ITEMS = (
    "石像鬼石板甲",
    "狂徒铠甲",
    "巨龙之爪",
    "棘刺背心",
    "救赎",
    "坚定之心",
)
UTILITY_ITEMS = (
    "莫雷洛秘典",
    "斯塔缇克电刃",
    "离子火花",
    "日炎斗篷",
    "救赎",
)

ROLE_ITEMS = {
    "ap_carry": AP_ITEMS,
    "ad_carry": AD_ITEMS,
    "fighter_carry": FIGHTER_ITEMS,
    "tank": TANK_ITEMS,
    "utility": UTILITY_ITEMS,
}

ROLE_LABELS = {
    "ap_carry": "法系主 C",
    "ad_carry": "物理主 C",
    "fighter_carry": "战士/近战主 C",
    "tank": "主坦",
    "utility": "功能位",
}

CHAMPION_ROLES = {
    "薇古丝": "ap_carry",
    "娜美": "ap_carry",
    "安妮": "ap_carry",
    "维克托": "ap_carry",
    "拉克丝": "ap_carry",
    "阿狸": "ap_carry",
    "佐伊": "ap_carry",
    "辛德拉": "ap_carry",
    "乐芙兰": "ap_carry",
    "妖姬": "ap_carry",
    "泽拉斯": "ap_carry",
    "奥莉安娜": "ap_carry",
    "吉格斯": "ap_carry",
    "莫甘娜": "ap_carry",
    "萨勒芬妮": "ap_carry",
    "卡尔玛": "ap_carry",
    "卡莎": "ad_carry",
    "艾希": "ad_carry",
    "卢锡安": "ad_carry",
    "希维尔": "ad_carry",
    "伊泽瑞尔": "ad_carry",
    "凯特琳": "ad_carry",
    "金克丝": "ad_carry",
    "薇恩": "ad_carry",
    "霞": "ad_carry",
    "德莱文": "ad_carry",
    "莎弥拉": "ad_carry",
    "烬": "ad_carry",
    "奎因": "ad_carry",
    "厄斐琉斯": "ad_carry",
    "库奇": "ad_carry",
    "崔丝塔娜": "ad_carry",
    "千珏": "ad_carry",
    "厄加特": "fighter_carry",
    "小鱼人": "fighter_carry",
    "菲兹": "fighter_carry",
    "阿卡丽": "fighter_carry",
    "卡特琳娜": "fighter_carry",
    "艾克": "fighter_carry",
    "亚托克斯": "fighter_carry",
    "锐雯": "fighter_carry",
    "瑟提": "fighter_carry",
    "孙悟空": "fighter_carry",
    "李青": "fighter_carry",
    "赵信": "fighter_carry",
    "贾克斯": "fighter_carry",
    "沃里克": "fighter_carry",
    "德莱厄斯": "fighter_carry",
    "凯隐": "fighter_carry",
    "亚索": "fighter_carry",
    "永恩": "fighter_carry",
    "艾瑞莉娅": "fighter_carry",
    "刀妹": "fighter_carry",
    "佛耶戈": "fighter_carry",
    "卑尔维斯": "fighter_carry",
    "潘森": "tank",
    "俄洛伊": "tank",
    "茂凯": "tank",
    "雷克塞": "tank",
    "波比": "tank",
    "塔姆": "tank",
    "盖伦": "tank",
    "蔚": "tank",
    "布隆": "tank",
    "慎": "tank",
    "墨菲特": "tank",
    "布里茨": "tank",
    "加里奥": "tank",
    "科加斯": "tank",
    "雷克顿": "tank",
    "内瑟斯": "tank",
    "阿木木": "tank",
    "蒙多": "tank",
    "诺提勒斯": "tank",
    "奎桑提": "tank",
    "洛": "tank",
    "妮蔻": "tank",
    "悠米": "utility",
    "婕拉": "utility",
    "索拉卡": "utility",
}

KEYWORD_ROLE_HINTS = (
    ("法", "ap_carry"),
    ("灵能", "ap_carry"),
    ("律动", "ap_carry"),
    ("暗星", "fighter_carry"),
    ("机甲", "fighter_carry"),
    ("战士", "fighter_carry"),
    ("决斗", "fighter_carry"),
    ("射手", "ad_carry"),
    ("狙", "ad_carry"),
    ("枪", "ad_carry"),
    ("牧羊", "ad_carry"),
)

COMPONENT_ALIASES = {
    "大剑": "大剑",
    "暴风大剑": "大剑",
    "剑": "大剑",
    "反曲弓": "反曲弓",
    "弓": "反曲弓",
    "攻速": "反曲弓",
    "大棒": "大棒",
    "无用大棒": "大棒",
    "棒": "大棒",
    "眼泪": "眼泪",
    "女神之泪": "眼泪",
    "泪": "眼泪",
    "锁子甲": "锁子甲",
    "护甲": "锁子甲",
    "甲": "锁子甲",
    "魔抗": "魔抗",
    "负极斗篷": "魔抗",
    "斗篷": "魔抗",
    "腰带": "腰带",
    "巨人腰带": "腰带",
    "拳套": "拳套",
    "拳": "拳套",
    "铲子": "铲子",
    "金铲铲": "铲子",
}

ITEM_RECIPES = {
    "蓝霸符": ("眼泪", "眼泪"),
    "朔极之矛": ("大剑", "眼泪"),
    "珠光护手": ("大棒", "拳套"),
    "纳什之牙": ("反曲弓", "腰带"),
    "灭世者的死亡之帽": ("大棒", "大棒"),
    "海克斯科技枪刃": ("大剑", "大棒"),
    "正义之手": ("眼泪", "拳套"),
    "鬼索的狂暴之刃": ("反曲弓", "大棒"),
    "最后的轻语": ("反曲弓", "拳套"),
    "无尽之刃": ("大剑", "拳套"),
    "巨人捕手": ("大剑", "反曲弓"),
    "锐利之刃": ("大剑", "大剑"),
    "红霸符": ("反曲弓", "反曲弓"),
    "汲取剑": ("大剑", "魔抗"),
    "泰坦的坚决": ("反曲弓", "锁子甲"),
    "斯特拉克的挑战护手": ("大剑", "腰带"),
    "夜之锋刃": ("大剑", "锁子甲"),
    "石像鬼石板甲": ("锁子甲", "魔抗"),
    "狂徒铠甲": ("腰带", "腰带"),
    "巨龙之爪": ("魔抗", "魔抗"),
    "棘刺背心": ("锁子甲", "锁子甲"),
    "救赎": ("眼泪", "腰带"),
    "坚定之心": ("锁子甲", "拳套"),
    "莫雷洛秘典": ("大棒", "腰带"),
    "斯塔缇克电刃": ("反曲弓", "眼泪"),
    "离子火花": ("大棒", "魔抗"),
    "日炎斗篷": ("锁子甲", "腰带"),
}


@dataclass(frozen=True, slots=True)
class RecipeStatus:
    item: str
    components: tuple[str, ...]
    can_build: bool
    missing: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LineupItemAdvice:
    lineup_name: str
    tier: str
    score: int
    matched_tokens: tuple[str, ...]
    main_carry: str
    carry_role: str
    carry_confidence: str
    main_tank: str
    tank_confidence: str
    carry_items: tuple[str, ...]
    tank_items: tuple[str, ...]
    utility_items: tuple[str, ...]
    shop_hits: tuple[str, ...]
    owned_hits: tuple[str, ...]
    recipe_statuses: tuple[RecipeStatus, ...]
    next_step: str


@dataclass(frozen=True, slots=True)
class ItemAdviceReport:
    plans: tuple[LineupItemAdvice, ...]
    shop_names: tuple[str, ...]
    item_components: tuple[str, ...]
    component_counts: dict[str, int]


def build_item_advice(
    recommendations: tuple[LineupRecommendation, ...],
    *,
    state: CardTrackerState | None = None,
    shop_names: str | Iterable[str] = (),
    seen_tokens: str | Iterable[str] = (),
    item_components: str | Iterable[str] = (),
    limit: int = 3,
) -> ItemAdviceReport:
    """Build carry, tank, and item reminders for the current S-lineup candidates."""

    resolved_state = state or CardTrackerState()
    normalized_shop_names = _unique(normalize_tokens(shop_names))
    normalized_seen_tokens = _unique(normalize_tokens(seen_tokens))
    normalized_components = _normalize_components(item_components)
    component_counts = dict(Counter(normalized_components))
    plans = [
        _plan_for_recommendation(
            recommendation,
            state=resolved_state,
            shop_names=normalized_shop_names,
            seen_tokens=normalized_seen_tokens,
            component_counts=component_counts,
        )
        for recommendation in recommendations[: max(0, limit)]
    ]
    return ItemAdviceReport(
        plans=tuple(plans),
        shop_names=normalized_shop_names,
        item_components=normalized_components,
        component_counts=component_counts,
    )


def format_item_advice(report: ItemAdviceReport) -> str:
    lines = ["装备 / 主 C 提醒:"]
    if report.shop_names:
        lines.append("当前来牌: " + ", ".join(report.shop_names))
    if report.component_counts:
        lines.append("已输入散件: " + _format_component_counts(report.component_counts))
    else:
        lines.append("已输入散件: 未提供，先按推荐成装优先级提示。")

    if not report.plans:
        lines.append("- 暂无 S 阵容推荐，先运行 lineups/core-advice 或扫描商店。")
        return "\n".join(lines)

    for index, plan in enumerate(report.plans, start=1):
        matched = f" | 命中: {', '.join(plan.matched_tokens)}" if plan.matched_tokens else ""
        lines.append(f"- #{index} [{plan.tier}] {plan.lineup_name} (score {plan.score}){matched}")
        lines.append(
            f"  主 C: {plan.main_carry}（{ROLE_LABELS.get(plan.carry_role, plan.carry_role)}，{plan.carry_confidence}）"
        )
        lines.append(f"  主坦: {plan.main_tank}（{plan.tank_confidence}）")
        lines.append("  主 C 装备: " + ", ".join(plan.carry_items))
        lines.append("  主坦装备: " + ", ".join(plan.tank_items))
        if plan.utility_items:
            lines.append("  功能装备: " + ", ".join(plan.utility_items))
        if plan.shop_hits:
            lines.append("  商店/来牌命中: " + ", ".join(plan.shop_hits))
        if plan.owned_hits:
            lines.append("  已追踪关键牌: " + ", ".join(plan.owned_hits))
        if plan.recipe_statuses:
            craft_now = [status.item for status in plan.recipe_statuses if status.can_build]
            missing = [
                f"{status.item}缺{'+'.join(status.missing)}"
                for status in plan.recipe_statuses
                if not status.can_build and status.missing
            ]
            lines.append("  现在能合: " + (", ".join(craft_now) if craft_now else "暂无核心成装"))
            lines.append("  优先补散件: " + (", ".join(missing[:5]) if missing else "核心装散件已齐"))
        lines.append(f"  建议: {plan.next_step}")
    return "\n".join(lines)


def _plan_for_recommendation(
    recommendation: LineupRecommendation,
    *,
    state: CardTrackerState,
    shop_names: tuple[str, ...],
    seen_tokens: tuple[str, ...],
    component_counts: dict[str, int],
) -> LineupItemAdvice:
    lineup = recommendation.lineup
    haystack = _lineup_text(recommendation)
    carry_name, carry_role, carry_confidence = _pick_main_carry(haystack, lineup.name, state, shop_names, seen_tokens)
    main_tank, tank_confidence = _pick_main_tank(haystack, state, shop_names, seen_tokens)
    carry_items = ROLE_ITEMS.get(carry_role, AP_ITEMS)
    if carry_role == "tank":
        carry_items = FIGHTER_ITEMS
    tank_items = TANK_ITEMS
    utility_items = _utility_items_for_text(haystack)
    key_items = _unique((*carry_items[:5], *tank_items[:3], *utility_items[:2]))
    recipe_statuses = _recipe_statuses(key_items, component_counts) if component_counts else ()
    shop_hits = _matching_names(shop_names, haystack)
    owned_hits = _owned_hits(state, haystack)
    next_step = _next_step(
        carry_name,
        carry_confidence,
        shop_hits,
        owned_hits,
        recipe_statuses,
        component_counts,
    )
    return LineupItemAdvice(
        lineup_name=lineup.name,
        tier=lineup.tier,
        score=recommendation.score,
        matched_tokens=recommendation.matched_tokens,
        main_carry=carry_name,
        carry_role=carry_role,
        carry_confidence=carry_confidence,
        main_tank=main_tank,
        tank_confidence=tank_confidence,
        carry_items=carry_items,
        tank_items=tank_items,
        utility_items=utility_items,
        shop_hits=shop_hits,
        owned_hits=owned_hits,
        recipe_statuses=recipe_statuses,
        next_step=next_step,
    )


def _pick_main_carry(
    haystack: str,
    lineup_name: str,
    state: CardTrackerState,
    shop_names: tuple[str, ...],
    seen_tokens: tuple[str, ...],
) -> tuple[str, str, str]:
    candidates = _champion_candidates(haystack, state, shop_names, seen_tokens, include_unmatched=False)
    non_tanks = [(name, score) for name, score in candidates if CHAMPION_ROLES.get(name) != "tank"]
    if non_tanks:
        name, score = max(non_tanks, key=lambda item: (item[1], len(item[0])))
        confidence = "高置信" if name in lineup_name or score >= 80 else "中置信"
        return name, CHAMPION_ROLES.get(name, _role_from_keywords(haystack)), confidence

    role = _role_from_keywords(haystack)
    label = {
        "ap_carry": "阵容名未写明具体棋子，优先看法系最高星/最高费输出",
        "ad_carry": "阵容名未写明具体棋子，优先看物理后排最高星输出",
        "fighter_carry": "阵容名未写明具体棋子，优先看机甲/近战最高星主 C",
    }.get(role, "阵容名未写明具体棋子，优先看当前最高星核心输出")
    return label, role, "低置信"


def _pick_main_tank(
    haystack: str,
    state: CardTrackerState,
    shop_names: tuple[str, ...],
    seen_tokens: tuple[str, ...],
) -> tuple[str, str]:
    tank_candidates = [
        (name, score)
        for name, score in _champion_candidates(haystack, state, shop_names, seen_tokens, include_unmatched=True)
        if CHAMPION_ROLES.get(name) == "tank"
    ]
    if tank_candidates:
        name, score = max(tank_candidates, key=lambda item: (item[1], len(item[0])))
        confidence = "高置信" if name in haystack and score >= 60 else "中置信"
        return name, confidence
    return "当前前排最高星/最高费坦克", "低置信"


def _champion_candidates(
    haystack: str,
    state: CardTrackerState,
    shop_names: tuple[str, ...],
    seen_tokens: tuple[str, ...],
    *,
    include_unmatched: bool,
) -> tuple[tuple[str, int], ...]:
    scores: dict[str, int] = {}
    for name in _champions_in_text(haystack):
        scores[name] = max(scores.get(name, 0), 70)

    evidence_tokens = _unique((*shop_names, *seen_tokens, *state.counts.keys()))
    for token in evidence_tokens:
        matched_names = _champions_in_text(token) or ((token,) if token in CHAMPION_ROLES else ())
        for name in matched_names:
            if name not in haystack and not include_unmatched:
                continue
            score = 30
            if name in haystack:
                score += 35
            else:
                score -= 12
            if name in shop_names:
                score += 15
            if name in state.counts:
                score += min(24, state.counts[name] * 3)
                if state.costs.get(name, 0) >= 4:
                    score += 8
            scores[name] = max(scores.get(name, 0), score)

    return tuple(sorted(scores.items(), key=lambda item: (-item[1], item[0])))


def _champions_in_text(text: str) -> tuple[str, ...]:
    matches: list[tuple[int, str]] = []
    for name in sorted(DEFAULT_CHAMPION_NAMES, key=len, reverse=True):
        index = text.find(name)
        if index >= 0:
            matches.append((index, name))
    seen: list[str] = []
    for _, name in sorted(matches, key=lambda item: (item[0], -len(item[1]))):
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def _role_from_keywords(text: str) -> str:
    for keyword, role in KEYWORD_ROLE_HINTS:
        if keyword in text:
            return role
    return "ap_carry"


def _utility_items_for_text(text: str) -> tuple[str, ...]:
    if any(keyword in text for keyword in ("法", "灵能", "娜美", "薇古丝")):
        return ("离子火花", "莫雷洛秘典")
    if any(keyword in text for keyword in ("射手", "枪", "霞", "卡莎", "烬")):
        return ("斯塔缇克电刃", "日炎斗篷")
    return ("莫雷洛秘典", "日炎斗篷")


def _matching_names(names: tuple[str, ...], haystack: str) -> tuple[str, ...]:
    hits: list[str] = []
    for name in names:
        if name in haystack:
            hits.append(name)
    return _unique(hits)


def _owned_hits(state: CardTrackerState, haystack: str) -> tuple[str, ...]:
    hits: list[str] = []
    for name, count in sorted(state.counts.items(), key=lambda item: (-item[1], item[0])):
        if name in haystack:
            cost = f"{state.costs[name]}费" if name in state.costs else "费用未知"
            hits.append(f"{name}={count}张({cost})")
    return tuple(hits[:5])


def _recipe_statuses(items: Iterable[str], component_counts: dict[str, int]) -> tuple[RecipeStatus, ...]:
    statuses: list[RecipeStatus] = []
    for item in items:
        components = ITEM_RECIPES.get(item)
        if not components:
            continue
        available = Counter(component_counts)
        missing: list[str] = []
        for component in components:
            if available[component] > 0:
                available[component] -= 1
            else:
                missing.append(component)
        statuses.append(
            RecipeStatus(
                item=item,
                components=components,
                can_build=not missing,
                missing=tuple(missing),
            )
        )
    statuses.sort(key=lambda status: (not status.can_build, len(status.missing), status.item))
    return tuple(statuses)


def _next_step(
    carry_name: str,
    carry_confidence: str,
    shop_hits: tuple[str, ...],
    owned_hits: tuple[str, ...],
    recipe_statuses: tuple[RecipeStatus, ...],
    component_counts: dict[str, int],
) -> str:
    if shop_hits:
        return f"商店出现 {', '.join(shop_hits[:3])}，优先买/留与当前 S 阵容重合的核心牌。"
    if owned_hits:
        return f"已追踪到 {owned_hits[0]}，先围绕它保留装备方向，再等商店确认最终阵容。"
    if carry_confidence == "低置信":
        if component_counts and any(status.can_build for status in recipe_statuses):
            craftable = next(status.item for status in recipe_statuses if status.can_build)
            return f"主 C 还没确认，{craftable} 可以先给打工位，但别急着硬锁最终阵容。"
        return "先别硬合专属装，继续用商店来牌/已拥有数量确认主 C。"
    if component_counts and any(status.can_build for status in recipe_statuses):
        craftable = next(status.item for status in recipe_statuses if status.can_build)
        return f"散件已经能做 {craftable}，可以先给 {carry_name} 或临时打工位过渡。"
    return "优先补主 C 两件核心输出装，再给前排补一件抗性或血量装。"


def _lineup_text(recommendation: LineupRecommendation) -> str:
    lineup = recommendation.lineup
    return " ".join(
        token
        for token in (
            lineup.name,
            lineup.code_title,
            lineup.code,
            *lineup.notes,
            *recommendation.matched_tokens,
        )
        if token
    )


def _normalize_components(values: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, str):
        raw_values = re.split(r"[\s,，、/|;；+]+", values)
    else:
        raw_values = []
        for value in values:
            raw_values.extend(re.split(r"[\s,，、/|;；+]+", str(value)))

    components: list[str] = []
    for value in raw_values:
        cleaned = value.strip()
        if not cleaned:
            continue
        component = COMPONENT_ALIASES.get(cleaned, cleaned)
        if component in COMPONENT_ALIASES.values():
            components.append(component)
    return tuple(components)


def _format_component_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{name}x{count}" for name, count in sorted(counts.items()))


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    unique_values: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in unique_values:
            unique_values.append(cleaned)
    return tuple(unique_values)
