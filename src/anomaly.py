"""趋势异常检测.

根据商品的历史排名/价格序列, 识别以下异常:
  🔥 HOT_RISE     排名飙升 (单日上升 ≥ 30 名)
  🚀 LAUNCH       新晋爆款 (首次上榜 + 有价格)
  📈 STREAK_UP    连续上升 (连续 3+ 天排名都在上升)
  📉 BIG_DROP     大跌 (排名下降 ≥ 20 名)
  💸 PRICE_DROP   降价 (比历史最低价还低 30%+)
  💰 PRICE_HIKE   涨价 (比历史最高价还高 30%+)
  ⚡ FLASH_RISE   一夜爆款 (从 50+ 名直接升到前 10)

所有规则都基于 history 数据, 没有历史时不会触发.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


# 阈值常量 (集中调参)
HOT_RISE_THRESHOLD = 30          # rank_change >= 30 -> HOT_RISE
BIG_DROP_THRESHOLD = -20         # rank_change <= -20 -> BIG_DROP
STREAK_DAYS = 3                  # 连续 3 天都在上升
PRICE_DROP_PCT = 0.30            # 比历史最低价低 30%+
PRICE_HIKE_PCT = 0.30            # 比历史最高价高 30%+
FLASH_FROM = 50                  # FLASH_RISE: 之前 ≥ 50 名
FLASH_TO = 10                    # FLASH_RISE: 现在 ≤ 10 名


@dataclass
class Anomaly:
    """一个异常标签."""
    code: str            # e.g. "HOT_RISE"
    label: str           # 短文本, e.g. "🔥 HOT"
    severity: int = 1    # 1-3, 越大越重要 (用于排序 / 颜色)

    def __str__(self) -> str:
        return self.label


# 异常定义表 (code -> 默认 Anomaly)
ANOMALY_DEFS: dict[str, Anomaly] = {
    "FLASH_RISE": Anomaly("FLASH_RISE", "⚡ FLASH", 3),
    "HOT_RISE":   Anomaly("HOT_RISE",   "🔥 HOT",   2),
    "LAUNCH":     Anomaly("LAUNCH",     "🚀 LAUNCH", 2),
    "STREAK_UP":  Anomaly("STREAK_UP",  "📈 STREAK", 2),
    "PRICE_HIKE": Anomaly("PRICE_HIKE", "💰 HIKE",  1),
    "PRICE_DROP": Anomaly("PRICE_DROP", "💸 DROP",  1),
    "BIG_DROP":   Anomaly("BIG_DROP",   "📉 DOWN",  1),
}


def _get_history_series(
    history: dict[str, list[dict]],
    asin: str,
) -> tuple[list[tuple[str, int, float]], list[str]]:
    """从 history 抽出 (date, rank, price) 序列, 按日期升序. 返回 (序列, 日期列表)."""
    if not asin or not history:
        return [], []
    series: list[tuple[str, int, float]] = []
    for day in sorted(history.keys()):
        for item in history[day]:
            if item.get("asin") == asin or item.get("key") == asin:
                rank = item.get("rank") or 0
                price = item.get("price_usd") or 0.0
                if rank:
                    series.append((day, int(rank), float(price)))
                break
    return series, [s[0] for s in series]


def detect(
    *,
    asin: str,
    rank_today: int,
    rank_change: int,
    is_new: bool,
    price_today: float,
    history: dict[str, list[dict]],
) -> list[Anomaly]:
    """对一个商品检测异常, 返回匹配的 Anomaly 列表 (按 severity 倒序).

    Args:
        asin: 商品唯一 key
        rank_today: 今日排名
        rank_change: 今日 - 昨日 (正数=上升, 负数=下降)
        is_new: 是否昨日未上榜
        price_today: 今日价格 (0 = 无价格信息, e.g. Google Trends)
        history: data/history.json 内容
    """
    out: list[Anomaly] = []

    # 1) 排名飙升
    if rank_change >= HOT_RISE_THRESHOLD:
        out.append(ANOMALY_DEFS["HOT_RISE"])

    # 2) 大跌
    if rank_change <= BIG_DROP_THRESHOLD:
        out.append(ANOMALY_DEFS["BIG_DROP"])

    # 3) 一夜爆款: 昨日排名 ≥ 50, 今日 ≤ 10
    if (rank_today <= FLASH_TO
            and not is_new
            and (rank_change + rank_today) >= FLASH_FROM):
        # rank_yesterday ≈ rank_change + rank_today
        rank_yesterday = rank_change + rank_today
        if rank_yesterday >= FLASH_FROM:
            out.append(ANOMALY_DEFS["FLASH_RISE"])

    # 4) 新晋爆款
    if is_new and price_today > 0:
        out.append(ANOMALY_DEFS["LAUNCH"])

    # 5) 连续上升 (从 history 拿更长序列)
    series, dates = _get_history_series(history, asin)
    # 把今天也补上
    series.append(("today", int(rank_today), float(price_today)))

    if len(series) >= STREAK_DAYS + 1:
        # 至少 3 个连续上升步
        last_n = [r for _, r, _ in series[-(STREAK_DAYS + 1):]]
        # last_n[i] > last_n[i+1] 意味着排名在上升 (排名数字小=靠前)
        rising_steps = sum(
            1 for i in range(len(last_n) - 1)
            if last_n[i] > last_n[i + 1]  # 数字变小 = 排名靠前 = 上升
        )
        if rising_steps >= STREAK_DAYS:
            out.append(ANOMALY_DEFS["STREAK_UP"])

    # 6) 价格突降 / 突涨
    if price_today > 0 and len(series) >= 2:
        prices = [p for _, _, p in series[:-1] if p > 0]
        if prices:
            min_p = min(prices)
            max_p = max(prices)
            if min_p > 0 and price_today <= min_p * (1 - PRICE_DROP_PCT):
                out.append(ANOMALY_DEFS["PRICE_DROP"])
            elif max_p > 0 and price_today >= max_p * (1 + PRICE_HIKE_PCT):
                out.append(ANOMALY_DEFS["PRICE_HIKE"])

    # 按 severity 倒序排
    out.sort(key=lambda a: -a.severity)
    return out


def detect_batch(
    items: Iterable[dict],
    history: dict[str, list[dict]],
) -> dict[str, list[Anomaly]]:
    """批量检测. items: 每个 dict 含 asin/rank_today/rank_change/is_new/price_usd.
    返回 {asin: [anomalies]}."""
    out: dict[str, list[Anomaly]] = {}
    for it in items:
        asin = it.get("asin", "")
        if not asin:
            continue
        out[asin] = detect(
            asin=asin,
            rank_today=int(it.get("rank_today", 0) or 0),
            rank_change=int(it.get("rank_change", 0) or 0),
            is_new=bool(it.get("is_new", False)),
            price_today=float(it.get("price_usd", 0) or 0),
            history=history,
        )
    return out


if __name__ == "__main__":
    # 演示
    sample_history = {
        "2026-06-01": [
            {"key": "B0A", "asin": "B0A", "rank": 50, "price_usd": 10.0},
        ],
        "2026-06-02": [
            {"key": "B0A", "asin": "B0A", "rank": 35, "price_usd": 10.0},
        ],
        "2026-06-03": [
            {"key": "B0A", "asin": "B0A", "rank": 20, "price_usd": 10.0},
        ],
        "2026-06-04": [
            {"key": "B0A", "asin": "B0A", "rank": 12, "price_usd": 9.5},
        ],
    }
    a = detect(
        asin="B0A",
        rank_today=3,
        rank_change=9,  # 12 -> 3
        is_new=False,
        price_today=6.0,  # 9.5 -> 6.0, 大幅降价
        history=sample_history,
    )
    for x in a:
        print(f"  {x}")
