"""Name and predicate normalisation for the extraction pipeline.

Two different jobs live here. `normalize_name` is a *key*: it decides when two
extracted mentions are the same wiki entry, and its formula is fixed by
`Entity.normalized_name` in ARCHITECTURE 3.2. `normalize_predicate` is
*convergence*: models reach for a different verb every time they describe the
same relation ("发布"/"推出"/"上线"), and a graph whose edges are labelled six
ways for one kind of fact is a graph nobody can read.
"""

import re
from collections.abc import Iterable

# Characters that differ between surface forms of one name without changing it:
# any whitespace, hyphen/underscore, the ASCII dot in `Node.js`, and the CJK
# interpuncts used when transliterating western names.
_NAME_SEPARATORS = re.compile(r"[\s\-_.·・‧∙]+")

# The canonical predicates offered to the model in `wiki.extract_linkages`.
# Anything the model invents outside this list survives normalisation unchanged —
# an unrecognised but meaningful predicate beats a wrong one.
CANONICAL_PREDICATES: tuple[str, ...] = (
    "发布",
    "收购",
    "投资",
    "合作",
    "竞争",
    "采用",
    "支持",
    "基于",
    "属于",
    "隶属",
    "任职",
    "离职",
    "开源",
    "集成",
    "超越",
    "替代",
    "依赖",
    "涉及",
    "应用于",
    "反对",
)

# Synonym -> canonical. The bar for adding a row: the two words would draw the
# *same edge* in the graph. Words that merely feel related stay out — mapping
# "质疑" onto "反对" would turn a hedge into a stance, and the wiki would be
# asserting something no source said.
#
# Deliberately absent, and why:
#   宣布 — attaches to anything ("宣布收购"), so it carries no relation of its own
#   退出 — "退出市场" is not "离职"
#   融合 — too vague to pin to 集成
#   关注 — weaker than 涉及, and the difference is the interesting part
PREDICATE_ALIASES: dict[str, str] = {
    # 发布
    "推出": "发布",
    "发行": "发布",
    "上线": "发布",
    "发表": "发布",
    "公布": "发布",
    "首发": "发布",
    "放出": "发布",
    "面世": "发布",
    "问世": "发布",
    "亮相": "发布",
    "正式发布": "发布",
    "对外发布": "发布",
    "宣布推出": "发布",
    # 收购
    "并购": "收购",
    "兼并": "收购",
    "买下": "收购",
    "购入": "收购",
    "全资收购": "收购",
    # 投资
    "注资": "投资",
    "领投": "投资",
    "跟投": "投资",
    "参投": "投资",
    "入股": "投资",
    "出资": "投资",
    # 合作
    "携手": "合作",
    "联手": "合作",
    "联合": "合作",
    "共建": "合作",
    "结盟": "合作",
    "协作": "合作",
    "达成合作": "合作",
    # 竞争
    "对标": "竞争",
    "抗衡": "竞争",
    "角逐": "竞争",
    "竞逐": "竞争",
    "对垒": "竞争",
    "叫板": "竞争",
    # 采用
    "使用": "采用",
    "采纳": "采用",
    "启用": "采用",
    "选用": "采用",
    "引入": "采用",
    # 支持
    "兼容": "支持",
    "支撑": "支持",
    # 基于
    "构建于": "基于",
    "建立于": "基于",
    "建立在": "基于",
    "源于": "基于",
    "脱胎于": "基于",
    # 属于 / 隶属
    "归属": "属于",
    "归于": "属于",
    "隶属于": "隶属",
    "归属于": "隶属",
    "从属于": "隶属",
    "旗下": "隶属",
    # 任职 / 离职
    "加入": "任职",
    "入职": "任职",
    "就职": "任职",
    "出任": "任职",
    "担任": "任职",
    "履新": "任职",
    "离开": "离职",
    "卸任": "离职",
    "辞职": "离职",
    "出走": "离职",
    # 开源
    "开放源代码": "开源",
    "开放源码": "开源",
    "开源发布": "开源",
    # 集成
    "接入": "集成",
    "整合": "集成",
    "内置": "集成",
    "嵌入": "集成",
    "对接": "集成",
    # 超越
    "领先": "超越",
    "优于": "超越",
    "胜过": "超越",
    "超过": "超越",
    "击败": "超越",
    "战胜": "超越",
    # 替代
    "取代": "替代",
    "代替": "替代",
    "顶替": "替代",
    # 依赖
    "依靠": "依赖",
    "仰赖": "依赖",
    "倚重": "依赖",
    # 涉及
    "涉足": "涉及",
    "瞄准": "涉及",
    "布局": "涉及",
    # 应用于
    "用于": "应用于",
    "应用在": "应用于",
    "落地于": "应用于",
    "服务于": "应用于",
    # 反对
    "抵制": "反对",
    "反制": "反对",
    "抗议": "反对",
}


def normalize_name(name: str) -> str:
    """The match key for an entity or concept name.

    Contract: `Entity.normalized_name` in ARCHITECTURE 3.2. Case is folded and
    every separator is dropped, so "Open AI" and "OpenAI" are one wiki entry.

    Dropping separators rather than merely collapsing them is what the live data
    asked for: `小米 18 Fold` / `小米18 Fold`, `约翰 · 特努斯` / `约翰·特努斯`,
    `DeepSeek V4 Flash` / `DeepSeek-V4-Flash` and `U-Net` / `Unet` were all
    sitting as separate rows, each splitting one subject's relations across two
    nodes. What varies between those pairs is spacing and hyphenation; the
    characters on either side never do. See ADR-019.
    """
    stripped = _NAME_SEPARATORS.sub("", name.lower())
    # A name made only of separators would otherwise key on "" and collide with
    # every other such name. Rare, but a silent cross-entity merge is the worst
    # failure this function has.
    return stripped or " ".join(name.lower().split())


def normalize_predicate(predicate: str) -> str:
    """Fold a predicate onto its canonical form, or return it unchanged."""
    collapsed = " ".join(predicate.split())
    return PREDICATE_ALIASES.get(collapsed, collapsed)


def merge_aliases(old: Iterable[str], new: Iterable[str]) -> list[str]:
    """Union of two alias lists: deduplicated, sorted, blanks dropped.

    Sorted rather than append-ordered so that re-running extraction over the same
    articles produces byte-identical JSON and does not show up as a change.
    """
    return sorted({alias.strip() for alias in (*old, *new) if isinstance(alias, str) and alias.strip()})
