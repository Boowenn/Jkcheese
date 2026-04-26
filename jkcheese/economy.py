from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True, order=True)
class Stage:
    major: int
    minor: int

    @property
    def label(self) -> str:
        return f"{self.major}-{self.minor}"

    @property
    def index(self) -> int:
        return self.major * 10 + self.minor


@dataclass(frozen=True, slots=True)
class RhythmAdvice:
    action: str
    title: str
    detail: str
    severity: str = "info"


@dataclass(frozen=True, slots=True)
class EconomyRhythmReport:
    stage: Stage | None
    level: int | None
    gold: int | None
    hp: int | None
    advice: tuple[RhythmAdvice, ...]
    missing: tuple[str, ...]


def parse_stage(value: str | int | None) -> Stage | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    explicit = re.search(r"(?P<major>[1-9])\s*[-:：/]\s*(?P<minor>[1-9])", text)
    if explicit:
        return _stage_or_none(int(explicit.group("major")), int(explicit.group("minor")))

    digits = re.sub(r"\D", "", text)
    if len(digits) >= 2:
        return _stage_or_none(int(digits[0]), int(digits[1]))
    return None


def build_economy_rhythm(
    *,
    stage: str | int | Stage | None = None,
    level: int | None = None,
    gold: int | None = None,
    hp: int | None = None,
) -> EconomyRhythmReport:
    parsed_stage = stage if isinstance(stage, Stage) else parse_stage(stage)
    missing = tuple(
        name
        for name, value in (
            ("stage", parsed_stage),
            ("level", level),
            ("gold", gold),
            ("hp", hp),
        )
        if value is None
    )

    advice: list[RhythmAdvice] = []
    advice.extend(_critical_hp_advice(parsed_stage, level, gold, hp))
    advice.extend(_stage_timing_advice(parsed_stage, level, gold, hp))
    advice.extend(_economy_breakpoint_advice(parsed_stage, level, gold, hp))

    if missing:
        advice.insert(
            0,
            RhythmAdvice(
                action="check_read",
                title="补齐读数",
                detail="阶段/等级/金币/血量有缺失，本次节奏建议会更保守；可用手动参数覆盖 OCR。",
                severity="warning",
            ),
        )

    if not advice:
        advice.append(
            RhythmAdvice(
                action="hold",
                title="稳住节奏",
                detail="当前读数没有触发强烈升人口或 roll down 信号，继续观察商店、对子和同行。",
            )
        )

    return EconomyRhythmReport(
        stage=parsed_stage,
        level=level,
        gold=gold,
        hp=hp,
        advice=_dedupe_advice(advice),
        missing=missing,
    )


def format_economy_rhythm(report: EconomyRhythmReport) -> str:
    lines = ["阶段 / 经济节奏建议:"]
    lines.append(
        "读数: "
        f"阶段={report.stage.label if report.stage else '?'} | "
        f"等级={report.level if report.level is not None else '?'} | "
        f"金币={report.gold if report.gold is not None else '?'} | "
        f"血量={report.hp if report.hp is not None else '?'}"
    )
    for item in report.advice:
        lines.append(f"- [{item.severity}] {item.title}: {item.detail}")
    return "\n".join(lines)


def _critical_hp_advice(
    stage: Stage | None,
    level: int | None,
    gold: int | None,
    hp: int | None,
) -> tuple[RhythmAdvice, ...]:
    if hp is None:
        return ()
    if hp <= 25:
        return (
            RhythmAdvice(
                action="all_in",
                title="该 all in 稳血",
                detail="血量已经进入危险线，优先把钱换成即时战力；先找主 C/主坦两星和关键羁绊，不要继续贪利息。",
                severity="critical",
            ),
        )
    if hp <= 40 and stage is not None and stage.index >= 36:
        return (
            RhythmAdvice(
                action="small_d",
                title="该小 D 或直接补强",
                detail="中后期血量偏低，建议先小 D 找到一到两个关键升级；如果已经到 4-2 后且金币足够，可转为大 D 稳血。",
                severity="warning",
            ),
        )
    return ()


def _stage_timing_advice(
    stage: Stage | None,
    level: int | None,
    gold: int | None,
    hp: int | None,
) -> tuple[RhythmAdvice, ...]:
    if stage is None or level is None or gold is None:
        return ()

    advice: list[RhythmAdvice] = []
    pressure = hp is not None and hp <= 55
    safe_hp = hp is not None and hp > 55

    if stage.index <= 23:
        if level < 4 and gold >= 4:
            advice.append(
                RhythmAdvice(
                    action="level",
                    title="可升 4 打连胜",
                    detail="2阶段前半如果阵容强，可以升人口保血/保连胜；阵容弱则允许不升，先吃经济。",
                )
            )
        elif gold >= 20 and not pressure:
            advice.append(
                RhythmAdvice(
                    action="save",
                    title="该存钱吃利息",
                    detail="前期血量压力不大，优先凑 20/30 金币利息，不要为低质量对子乱 D。",
                )
            )

    if 25 <= stage.index <= 31:
        if level < 5 and gold >= 10:
            advice.append(
                RhythmAdvice(
                    action="level",
                    title="该升 5 补战力",
                    detail="2-5 到 3-1 是常见补人口窗口；如果场面弱，升人口通常比硬 D 更稳定。",
                    severity="warning" if pressure else "info",
                )
            )
        elif gold >= 30 and not pressure:
            advice.append(
                RhythmAdvice(
                    action="save",
                    title="继续存钱",
                    detail="金币健康且未到 3-2 节点，优先保经济进 3-2 再统一决定升 6 或小 D。",
                )
            )

    if 32 <= stage.index <= 35:
        if level < 6 and gold >= 20:
            advice.append(
                RhythmAdvice(
                    action="level",
                    title="该升 6",
                    detail="3-2 附近通常要升 6 补羁绊和质量；如果血量低，升完可以小 D 到核心一星/二星。",
                    severity="warning" if pressure else "info",
                )
            )
        elif pressure and gold >= 20:
            advice.append(
                RhythmAdvice(
                    action="small_d",
                    title="该小 D 稳血",
                    detail="3阶段血量压力已经明显，建议小 D 找前排两星、主 C 一星和关键羁绊，别一次 D 光。",
                    severity="warning",
                )
            )

    if 36 <= stage.index <= 41:
        if level < 7 and gold >= 30:
            advice.append(
                RhythmAdvice(
                    action="level",
                    title="该升 7",
                    detail="3-6 到 4-1 是转中期阵容的重要窗口；升 7 后根据血量决定小 D 还是继续存。",
                    severity="warning" if pressure else "info",
                )
            )
        elif pressure and gold >= 20:
            advice.append(
                RhythmAdvice(
                    action="small_d",
                    title="该小 D 找中期质量",
                    detail="4阶段前后不能再只贪经济，优先补前排、主 C 和关键高费卡。",
                    severity="warning",
                )
            )

    if 42 <= stage.index <= 47:
        if level < 8 and gold >= 40:
            advice.append(
                RhythmAdvice(
                    action="level",
                    title="该升 8",
                    detail="4-2 后金币够时优先升 8 找四费核心；血量越低，升完越应该把钱转成战力。",
                    severity="warning" if pressure else "info",
                )
            )
        elif level >= 8 and gold >= 30 and pressure:
            advice.append(
                RhythmAdvice(
                    action="all_in",
                    title="该 all in 找四费两星",
                    detail="已经到 8 级且血量有压力，优先 D 出主 C/主坦两星，再考虑上 9。",
                    severity="critical",
                )
            )
        elif level >= 8 and gold >= 50 and safe_hp:
            advice.append(
                RhythmAdvice(
                    action="save",
                    title="可存钱上 9",
                    detail="8级、血量和金币都舒服时，不急着 D 光；可以存钱等 5阶段上 9 提上限。",
                )
            )

    if stage.index >= 51:
        if level < 9 and gold >= 50 and safe_hp:
            advice.append(
                RhythmAdvice(
                    action="level",
                    title="该考虑升 9",
                    detail="5阶段后经济健康且血量安全，可以上 9 补五费或高级羁绊提高上限。",
                )
            )
        elif pressure and gold >= 20:
            advice.append(
                RhythmAdvice(
                    action="all_in",
                    title="该 all in 提质量",
                    detail="5阶段以后每波掉血都很贵，优先把关键两星、装备承载位和前排质量补满。",
                    severity="critical",
                )
            )

    return tuple(advice)


def _economy_breakpoint_advice(
    stage: Stage | None,
    level: int | None,
    gold: int | None,
    hp: int | None,
) -> tuple[RhythmAdvice, ...]:
    if gold is None:
        return ()

    late_stage = stage is not None and stage.index >= 42
    if hp is None and late_stage:
        return ()
    pressure_line = 55 if late_stage else 45
    pressure = hp is not None and hp <= pressure_line
    if gold >= 50 and not pressure:
        return (
            RhythmAdvice(
                action="save",
                title="该存钱吃满利息",
                detail="金币已经到 50，除非当前阶段正好要升人口或血量突然危险，否则优先用利息做节奏。",
            ),
        )
    if 30 <= gold < 50 and not pressure and not late_stage:
        return (
            RhythmAdvice(
                action="save",
                title="经济健康，别乱 D",
                detail="金币在 30-49，适合卡利息过渡；只为关键对子或强势羁绊做少量调整。",
            ),
        )
    if gold < 10:
        return (
            RhythmAdvice(
                action="hold",
                title="金币偏低",
                detail="钱很少时不要无计划刷新；除非快出局，否则先用自然商店和装备提升即时战力。",
                severity="warning",
            ),
        )
    return ()


def _stage_or_none(major: int, minor: int) -> Stage | None:
    if 1 <= major <= 9 and 1 <= minor <= 7:
        return Stage(major, minor)
    return None


def _dedupe_advice(advice: list[RhythmAdvice]) -> tuple[RhythmAdvice, ...]:
    seen: set[tuple[str, str]] = set()
    output: list[RhythmAdvice] = []
    for item in advice:
        key = (item.action, item.title)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return tuple(output[:5])
