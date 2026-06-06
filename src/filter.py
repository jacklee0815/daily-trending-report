"""商品关键词过滤器.

屏蔽不相关 / 敏感类目, 让报告内容更聚焦.
可在 config 中按需添加 / 删除关键词.
"""
from __future__ import annotations

import re
from typing import Iterable

from .scraper_amazon import Product

# 默认黑名单: 标题 / 类目命中任一关键词即过滤
# (小写匹配, 自动处理 's / 复数等)
DEFAULT_BLOCK_KEYWORDS: list[str] = [
    # 成人 / 性感
    "adult", "sex", "sexy", "lingerie", "panty", "thong", "bra ", "underwear",
    "erotic", "bondage", "vibrator", "dildo", "masturbat",
    # 武器 / 危险品
    "weapon", "gun", "pistol", "rifle", "ammunition", "ammo", "bullet", "knife",
    "tactical", "self defense spray", "pepper spray",
    # 烟酒 / 毒品相关
    "cigarette", "vape", "vaping", "e-cigarette", "hookah", "bong", "weed",
    "cannabis", "marijuana", "thc", "cbd oil", "drug", "alcohol",
    # 医疗 / 药品
    "medication", "prescription", "pill", "supplement", "vitamin ", "weight loss",
    "diet ",
    # 政治 / 宗教 / 争议
    "political", "trump ", "biden ", " MAGA", "election", "religious", "bible",
    # 大件 / 不符合"小物品"定义的
    "mattress", "sofa", "refrigerator", "treadmill", "generator",
]

# 灰名单: 命中则给标题加 "[!]" 标记, 但不直接过滤
# (用于让你人工 review 一次, 例如 "vintage" 经常是相关但也可能是二手)
DEFAULT_FLAG_KEYWORDS: list[str] = [
    "vintage", "used", "refurbished", "replica", "knockoff",
]

# 价格硬阈值 (USD). 即便关键词放行, 价格过高也不取.
HARD_PRICE_CEILING = 20.0

# 标题最短长度. 防止抓到空标题 / 乱码.
MIN_TITLE_LEN = 6

# 类目名白名单 (来源 CATEGORIES / DISCOVER_CATEGORIES 的中文显示名片段,
# 命中非白名单的类目也过滤, 防止爬到不相关细类)
ALLOWED_CATEGORY_HINTS: list[str] = [
    "jewelry", "earring", "bracelet", "ring", "necklace", "pendant", "anklet",
    "watch", "hair", "keychain", "phone", "earphone", "headphone",
    "toy", "puzzle", "game", "plush", "stuffed", "squishy", "fidget",
    "cute", "kawaii", "stationery", "sticker", "card", "anime",
    "decoration", "ornament", "charm", "trinket", "figurine", "miniature",
    "candle", "incense", "aromatherapy", "essential oil", "soap",
    "bag", "pouch", "wallet", "coin purse", "card holder",
    "pet", "dog ", "cat ",
    "trending", "search",
]


def _contains_any(text: str, keywords: Iterable[str]) -> str | None:
    """返回首个命中的关键词 (小写匹配), 没命中返回 None."""
    if not text:
        return None
    low = text.lower()
    for kw in keywords:
        if kw.lower() in low:
            return kw
    return None


def _title_word_count(title: str) -> int:
    return len([w for w in re.split(r"\s+", title.strip()) if w])


class FilterResult:
    def __init__(self, kept: list[Product], blocked: list[tuple[Product, str]], flagged: list[Product]):
        self.kept = kept
        self.blocked = blocked  # (product, reason)
        self.flagged = flagged  # 命中灰名单, 但保留


def filter_products(
    products: list[Product],
    block_keywords: list[str] | None = None,
    flag_keywords: list[str] | None = None,
    price_ceiling: float = HARD_PRICE_CEILING,
    min_title_len: int = MIN_TITLE_LEN,
) -> FilterResult:
    """过滤商品.

    Args:
        products: 抓回来的原始商品
        block_keywords: 黑名单关键词 (默认用 DEFAULT_BLOCK_KEYWORDS)
        flag_keywords: 灰名单关键词 (默认用 DEFAULT_FLAG_KEYWORDS)
        price_ceiling: 价格上限, 超过即过滤
        min_title_len: 标题最少字符数, 低于即过滤
    """
    block = block_keywords or DEFAULT_BLOCK_KEYWORDS
    flag = flag_keywords or DEFAULT_FLAG_KEYWORDS

    kept: list[Product] = []
    blocked: list[tuple[Product, str]] = []
    flagged: list[Product] = []

    for p in products:
        # 1) 标题过短 -> 过滤
        if not p.title or len(p.title.strip()) < min_title_len:
            blocked.append((p, f"title too short (<{min_title_len} chars)"))
            continue
        # 2) 价格过高 -> 过滤
        if p.price_usd > price_ceiling:
            blocked.append((p, f"price > ${price_ceiling:.2f}"))
            continue
        # 3) 黑名单关键词 -> 过滤
        hit = _contains_any(p.title, block) or _contains_any(p.category, block)
        if hit:
            blocked.append((p, f"keyword '{hit}'"))
            continue
        # 4) 灰名单 -> 标记, 仍保留
        flag_hit = _contains_any(p.title, flag)
        if flag_hit:
            p.title = f"[!{flag_hit}] {p.title}"
            flagged.append(p)
        # 5) 类目提示符不在白名单 -> 过滤 (防止抓到大件或无关类目)
        cat_low = (p.category or "").lower()
        if cat_low and not any(h in cat_low for h in ALLOWED_CATEGORY_HINTS):
            # 类目不匹配白名单 → 过滤
            blocked.append((p, f"category '{p.category}' not in whitelist"))
            continue

        kept.append(p)

    logger_filter(kept, blocked, flagged)
    return FilterResult(kept, blocked, flagged)


def logger_filter(kept, blocked, flagged) -> None:
    import logging

    log = logging.getLogger(__name__)
    log.info(
        "filter: %s kept, %s blocked, %s flagged",
        len(kept), len(blocked), len(flagged),
    )
    if blocked:
        # 最多打 5 个原因示例
        from collections import Counter

        reasons = Counter(r for _, r in blocked)
        log.debug("blocked reasons: %s", dict(reasons.most_common(5)))
