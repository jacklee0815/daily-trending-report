"""历史数据存储 + "上升最快" 排名计算.

每天的抓取结果按日期存到 data/history.json, 通过对比今天 vs 昨天的
排名变化来近似"上升最快"商品.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Iterable

from .scraper_amazon import Product

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "history.json",
)


@dataclass
class RankedItem:
    """带上升排名的最终条目."""

    title: str
    price_usd: float
    url: str
    image_url: str
    source: str  # "amazon" / "tiktok" / "ebay" / "google_trends"
    category: str
    rank_today: int
    rank_yesterday: int | None  # None 表示昨天没上榜
    rank_change: int  # 正数=上升名次, 负数=下降
    is_new: bool  # 昨天没出现过
    asin: str = ""
    selling_point: str = ""  # LLM 生成的中文卖点 (可空)
    badges: list[str] = field(default_factory=list)  # 异常标签, e.g. ["🔥 HOT", "💸 DROP"]

    def to_dict(self) -> dict:
        return asdict(self)


def _load_history(path: str) -> dict[str, list[dict]]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("history load failed: %s, starting fresh", exc)
        return {}


def _save_history(path: str, data: dict[str, list[dict]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _key(p: Product) -> str:
    """商品唯一 key: Amazon 用 asin, TikTok 用 asin(其 id) 或 url."""
    if p.asin:
        return p.asin
    return p.url or p.title


def dedupe_products(products: list[Product]) -> list[Product]:
    """同一商品在多个类目里出现时, 只保留 rank 最小(最热门)的那条.

    重复的 category 信息会合并到主条目, 例如 "Bracelets · Earrings".
    """
    best: dict[str, Product] = {}
    extras: dict[str, list[str]] = {}

    for p in products:
        k = _key(p)
        if not k:
            continue
        if k in best:
            extras.setdefault(k, []).append(p.category)
            if p.rank < best[k].rank:
                extras[k].append(best[k].category)
                best[k] = p
        else:
            best[k] = p

    out: list[Product] = []
    for k, p in best.items():
        cats = [p.category] + extras.get(k, [])
        seen: set[str] = set()
        merged = []
        for c in cats:
            if c and c not in seen:
                seen.add(c)
                merged.append(c)
        p.category = " · ".join(merged)
        out.append(p)
    return out


def save_today(history_path: str, today: str, products: Iterable[Product]) -> None:
    """把今天的商品快照保存到历史文件."""
    data = _load_history(history_path)
    data[today] = [
        {
            "key": _key(p),
            "asin": p.asin,
            "title": p.title,
            "price_usd": p.price_usd,
            "url": p.url,
            "image_url": p.image_url,
            "source": p.source,
            "category": p.category,
            "rank": p.rank,
        }
        for p in products
    ]
    # 只保留最近 14 天的数据, 防止文件无限增长
    keys = sorted(data.keys())
    if len(keys) > 14:
        for k in keys[:-14]:
            data.pop(k, None)
    _save_history(history_path, data)
    logger.info("history saved: %s entries on %s, kept %s days", len(data[today]), today, len(data))


def _find_yesterday(history: dict[str, list[dict]], today: str) -> str | None:
    """找最近一次有数据的日期 (排除今天)."""
    keys = sorted([k for k in history.keys() if k < today], reverse=True)
    return keys[0] if keys else None


def compute_rising(
    today_products: list[Product],
    history: dict[str, list[dict]],
    today: str,
    top_n: int = 10,
) -> list[RankedItem]:
    """计算 top N 上升最快商品.

    排序评分:
      1.  rank_change 大的 (上升名次多)
      2.  is_new 的 (新晋)
      3.  同分时 rank 小的 (当前排名靠前)
    """
    yesterday_key = _find_yesterday(history, today)
    yesterday_map: dict[str, dict] = {}
    if yesterday_key:
        for item in history.get(yesterday_key, []):
            yesterday_map[item.get("key") or item.get("asin") or ""] = item

    ranked: list[RankedItem] = []
    for p in today_products:
        key = _key(p)
        y = yesterday_map.get(key)
        if y:
            rank_y = int(y.get("rank", 999))
            rank_t = p.rank
            change = rank_y - rank_t  # 正数=上升
            is_new = False
        else:
            rank_y = None
            change = 50  # 新晋商品默认 +50, 让它排前面
            is_new = True

        ranked.append(
            RankedItem(
                title=p.title,
                price_usd=p.price_usd,
                url=p.url,
                image_url=p.image_url,
                source=p.source,
                category=p.category,
                rank_today=p.rank,
                rank_yesterday=rank_y,
                rank_change=change,
                is_new=is_new,
                asin=p.asin,
            )
        )

    # 异常检测: 给每个商品打 labels
    try:
        from .anomaly import detect as _detect_anomaly

        for r in ranked:
            anomalies = _detect_anomaly(
                asin=r.asin,
                rank_today=r.rank_today,
                rank_change=r.rank_change,
                is_new=r.is_new,
                price_today=r.price_usd,
                history=history,
            )
            r.badges = [a.label for a in anomalies]
    except Exception as exc:  # noqa: BLE001
        logger.warning("anomaly detection skipped: %s", exc)

    ranked.sort(
        key=lambda r: (
            -r.rank_change,
            0 if r.is_new else 1,
            r.rank_today,
        )
    )
    return ranked[:top_n]


def run_ranking(
    today_products: list[Product],
    today: str,
    history_path: str = DEFAULT_HISTORY_PATH,
    top_n: int = 10,
) -> list[RankedItem]:
    """加载历史 -> 计算上升 -> 保存今天快照 -> 返回 top N."""
    history = _load_history(history_path)
    # 先去重再算上升, 防止同一商品 (asin/id) 在多个类目里被重复算
    deduped = dedupe_products(today_products)
    top = compute_rising(deduped, history, today, top_n=top_n)
    save_today(history_path, today, deduped)
    return top


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from .scraper_amazon import scrape_amazon

    today = date.today().isoformat()
    items = scrape_amazon()
    top = run_ranking(items, today)
    for r in top:
        print(f"+{r.rank_change:>3}  ${r.price_usd:>5.2f}  [{r.source}/{r.category}]  {r.title[:60]}")
