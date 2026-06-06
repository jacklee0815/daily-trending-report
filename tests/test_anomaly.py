"""单元测试: 趋势异常检测."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.anomaly import (  # noqa: E402
    FLASH_FROM,
    FLASH_TO,
    HOT_RISE_THRESHOLD,
    PRICE_DROP_PCT,
    PRICE_HIKE_PCT,
    STREAK_DAYS,
    Anomaly,
    detect,
    detect_batch,
)


def _hist(days_data: list[tuple[str, int, float]]) -> dict[str, list[dict]]:
    """days_data: [(date, rank, price), ...]  -> history dict"""
    out: dict[str, list[dict]] = {}
    for day, rk, pr in days_data:
        out[day] = [{
            "key": "B0A", "asin": "B0A", "title": "X",
            "price_usd": pr, "url": "", "image_url": "",
            "source": "amazon", "category": "E", "rank": rk,
        }]
    return out


def _codes(anomalies: list[Anomaly]) -> list[str]:
    return [a.code for a in anomalies]


# ---------- 单商品检测 ----------

class TestDetect:
    def test_no_history_no_anomaly(self):
        a = detect(
            asin="X", rank_today=5, rank_change=10, is_new=True,
            price_today=8.0, history={},
        )
        # is_new=True 触发 LAUNCH
        assert "LAUNCH" in _codes(a)

    def test_no_history_old_item(self):
        a = detect(
            asin="X", rank_today=5, rank_change=10, is_new=False,
            price_today=8.0, history={},
        )
        # 没历史 + 非新晋 -> 没有任何标签
        assert a == []

    def test_hot_rise(self):
        a = detect(
            asin="X", rank_today=5, rank_change=HOT_RISE_THRESHOLD, is_new=False,
            price_today=8.0, history={},
        )
        assert "HOT_RISE" in _codes(a)

    def test_not_hot_rise_below_threshold(self):
        a = detect(
            asin="X", rank_today=5, rank_change=HOT_RISE_THRESHOLD - 1, is_new=False,
            price_today=8.0, history={},
        )
        assert "HOT_RISE" not in _codes(a)

    def test_big_drop(self):
        a = detect(
            asin="X", rank_today=80, rank_change=-25, is_new=False,
            price_today=8.0, history={},
        )
        assert "BIG_DROP" in _codes(a)

    def test_launch(self):
        a = detect(
            asin="X", rank_today=1, rank_change=0, is_new=True,
            price_today=8.0, history={},
        )
        assert "LAUNCH" in _codes(a)

    def test_launch_requires_price(self):
        # Google Trends 没价格, 不应触发 LAUNCH
        a = detect(
            asin="X", rank_today=1, rank_change=0, is_new=True,
            price_today=0.0, history={},
        )
        assert "LAUNCH" not in _codes(a)

    def test_flash_rise(self):
        # 昨天 #60, 今天 #5
        a = detect(
            asin="X", rank_today=5, rank_change=55, is_new=False,
            price_today=8.0, history={},
        )
        assert "FLASH_RISE" in _codes(a)

    def test_flash_rise_not_triggered_when_from_too_low(self):
        # 昨天 #20, 今天 #5 - 不是从底部爆发
        a = detect(
            asin="X", rank_today=5, rank_change=15, is_new=False,
            price_today=8.0, history={},
        )
        assert "FLASH_RISE" not in _codes(a)

    def test_streak_up(self):
        # 连续 3+ 天排名都在上升
        # 50 -> 30 -> 20 -> 10 -> 5
        hist = _hist([
            ("2026-06-01", 50, 10.0),
            ("2026-06-02", 30, 10.0),
            ("2026-06-03", 20, 10.0),
            ("2026-06-04", 10, 10.0),
        ])
        a = detect(
            asin="B0A", rank_today=5, rank_change=5, is_new=False,
            price_today=10.0, history=hist,
        )
        assert "STREAK_UP" in _codes(a)

    def test_streak_broken_by_drop(self):
        # 后 3 步不全是上升 (最后 1 步持平或下降) -> streak 断了
        hist = _hist([
            ("2026-06-01", 50, 10.0),
            ("2026-06-02", 40, 10.0),
            ("2026-06-03", 30, 10.0),
            ("2026-06-04", 20, 10.0),  # 上升
        ])
        # 今天保持 20 (持平, 不是上升)
        a = detect(
            asin="B0A", rank_today=20, rank_change=0, is_new=False,
            price_today=10.0, history=hist,
        )
        # last_n = [30, 20, 20], 步: 30>20 (升), 20>20 (平) -> 仅 1 步升, < 3
        assert "STREAK_UP" not in _codes(a)

    def test_streak_requires_3_steps(self):
        # 只有 2 天数据
        hist = _hist([
            ("2026-06-03", 30, 10.0),
            ("2026-06-04", 20, 10.0),
        ])
        a = detect(
            asin="B0A", rank_today=10, rank_change=10, is_new=False,
            price_today=10.0, history=hist,
        )
        assert "STREAK_UP" not in _codes(a)

    def test_price_drop(self):
        hist = _hist([
            ("2026-06-02", 10, 10.0),
            ("2026-06-03", 10, 12.0),
            ("2026-06-04", 10, 11.5),
        ])
        a = detect(
            asin="B0A", rank_today=10, rank_change=0, is_new=False,
            price_today=6.0,  # 跌了 40%+
            history=hist,
        )
        assert "PRICE_DROP" in _codes(a)

    def test_price_hike(self):
        hist = _hist([
            ("2026-06-02", 10, 5.0),
            ("2026-06-03", 10, 6.0),
            ("2026-06-04", 10, 5.5),
        ])
        a = detect(
            asin="B0A", rank_today=10, rank_change=0, is_new=False,
            price_today=9.0,  # 涨了 50%+
            history=hist,
        )
        assert "PRICE_HIKE" in _codes(a)

    def test_no_price_anomaly_when_zero(self):
        a = detect(
            asin="X", rank_today=10, rank_change=0, is_new=False,
            price_today=0.0, history=_hist([("d", 10, 0)]),
        )
        assert "PRICE_DROP" not in _codes(a)
        assert "PRICE_HIKE" not in _codes(a)

    def test_combined(self):
        # 飙升 + 连续上升 + 大幅降价 + flash -> 多个标签
        hist = _hist([
            ("2026-06-01", 100, 15.0),
            ("2026-06-02", 70, 14.0),
            ("2026-06-03", 50, 14.0),
            ("2026-06-04", 30, 14.0),
        ])
        a = detect(
            asin="B0A", rank_today=5, rank_change=35, is_new=False,
            price_today=5.0,  # 降价 64%
            history=hist,
        )
        codes = _codes(a)
        assert "HOT_RISE" in codes
        assert "STREAK_UP" in codes
        assert "PRICE_DROP" in codes
        # severity 倒序: FLASH (3) > HOT/STREAK (2) > DROP (1)
        assert a[0].severity >= a[-1].severity

    def test_sorted_by_severity(self):
        a = detect(
            asin="X", rank_today=5, rank_change=40, is_new=False,
            price_today=5.0, history=_hist([("d", 50, 20.0)]),
        )
        # FLASH / HOT / DROP 都可能触发, 验证按 severity 排
        for i in range(len(a) - 1):
            assert a[i].severity >= a[i + 1].severity


# ---------- 批量 ----------

class TestBatch:
    def test_batch_returns_dict_by_asin(self):
        items = [
            {"asin": "B0A", "rank_today": 5, "rank_change": 40, "is_new": False, "price_usd": 8.0},
            {"asin": "B0B", "rank_today": 1, "rank_change": 0, "is_new": True, "price_usd": 5.0},
            {"asin": "", "rank_today": 5, "rank_change": 0, "is_new": False, "price_usd": 5.0},
        ]
        result = detect_batch(items, history={})
        assert "B0A" in result
        assert "B0B" in result
        assert "" not in result  # 空 asin 跳过

    def test_empty(self):
        assert detect_batch([], {}) == {}


# ---------- 阈值常量 ----------

class TestThresholds:
    def test_thresholds_sensible(self):
        # sanity: 阈值要合理
        assert HOT_RISE_THRESHOLD >= 10
        assert STREAK_DAYS >= 2
        assert 0 < PRICE_DROP_PCT < 0.5
        assert 0 < PRICE_HIKE_PCT < 0.5
        assert FLASH_FROM > FLASH_TO
