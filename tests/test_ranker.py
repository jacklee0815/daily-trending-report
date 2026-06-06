"""单元测试: 价格解析, 去重, 上升排名计算."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.ranker import _key, compute_rising, dedupe_products  # noqa: E402
from src.scraper_amazon import Product, _parse_price  # noqa: E402


# ---------- price parser ----------

class TestParsePrice:
    def test_basic(self):
        assert _parse_price("$12.99") == 12.99

    def test_with_thousands(self):
        assert _parse_price("$1,234.56") == 1234.56

    def test_no_dollar(self):
        assert _parse_price("12.99") == 12.99

    def test_integer(self):
        assert _parse_price("$10") == 10.0

    def test_empty(self):
        assert _parse_price("") is None

    def test_garbage(self):
        assert _parse_price("free shipping") is None


# ---------- dedupe ----------

class TestDedupe:
    def test_unique_kept(self):
        items = [
            Product("amazon", "Earrings", 1, "Ear A", 5.0, "u1", "", "B0A"),
            Product("amazon", "Toys", 2, "Toy B", 9.0, "u2", "", "B0B"),
        ]
        out = dedupe_products(items)
        assert len(out) == 2
        assert {p.asin for p in out} == {"B0A", "B0B"}

    def test_duplicate_keeps_lower_rank(self):
        items = [
            Product("amazon", "Earrings", 7, "Ear A", 5.0, "u", "B0A"),
            Product("amazon", "Bracelets", 3, "Ear A", 5.0, "u", "B0A"),
        ]
        out = dedupe_products(items)
        assert len(out) == 1
        # rank=3 胜出
        assert out[0].rank == 3
        # category 合并: 保留 Bracelets (rank 较小) + 加上 Earrings
        assert "Bracelets" in out[0].category
        assert "Earrings" in out[0].category

    def test_tiktok_dedup_by_url(self):
        items = [
            Product("tiktok", "Jewelry", 1, "X", 5.0, "https://tt/video/123", "tt1"),
            Product("tiktok", "Watches", 2, "X", 5.0, "https://tt/video/123", "tt1"),
        ]
        out = dedupe_products(items)
        assert len(out) == 1

    def test_no_key_dropped(self):
        # asin/url/title 都为空, 唯一 key 没法构造, 应被丢弃
        items = [
            Product("tiktok", "X", 1, "", 5.0, "", "", ""),
        ]
        out = dedupe_products(items)
        assert len(out) == 0  # 没有 key 的被丢弃


# ---------- compute_rising ----------

def _product(asin: str, rank: int, source: str = "amazon", category: str = "Earrings") -> Product:
    # Product 字段: source, category, rank, title, price_usd, url, image_url, asin
    return Product(source, category, rank, f"Title {asin}", 5.0, f"https://x/{asin}", "", asin)


class TestComputeRising:
    def test_first_run_marks_all_new(self):
        history = {}
        today = [
            _product("B0A", 1),
            _product("B0B", 2),
        ]
        top = compute_rising(today, history, "2026-06-05", top_n=10)
        assert all(r.is_new for r in top)
        assert len(top) == 2

    def test_rising_above_falling(self):
        history = {
            "2026-06-04": [
                {"key": "B0A", "asin": "B0A", "title": "A", "price_usd": 5, "url": "", "image_url": "", "source": "amazon", "category": "E", "rank": 1},
                {"key": "B0B", "asin": "B0B", "title": "B", "price_usd": 5, "url": "", "image_url": "", "source": "amazon", "category": "E", "rank": 30},
            ]
        }
        # A 升到 #1 (不变, change=0), B 升到 #2 (change=+28)
        today = [
            _product("B0A", 1),
            _product("B0B", 2),
        ]
        top = compute_rising(today, history, "2026-06-05", top_n=10)
        # B 排第一
        assert top[0].asin == "B0B"
        assert top[0].rank_change == 28
        assert top[1].asin == "B0A"
        assert top[1].rank_change == 0

    def test_new_above_steady(self):
        history = {
            "2026-06-04": [
                {"key": "B0A", "asin": "B0A", "title": "A", "price_usd": 5, "url": "", "image_url": "", "source": "amazon", "category": "E", "rank": 5},
            ]
        }
        # A 不变 (change=0), C 新晋 (change=+50, is_new=True)
        today = [
            _product("B0A", 5),
            _product("B0C", 4),
        ]
        top = compute_rising(today, history, "2026-06-05", top_n=10)
        # C 排第一 (NEW 优先)
        assert top[0].asin == "B0C"
        assert top[0].is_new is True
        assert top[1].asin == "B0A"

    def test_top_n_limits(self):
        history = {}
        today = [_product(f"B{i:03d}", i + 1) for i in range(20)]
        top = compute_rising(today, history, "2026-06-05", top_n=10)
        assert len(top) == 10

    def test_negative_change_recorded(self):
        history = {
            "2026-06-04": [
                {"key": "B0A", "asin": "B0A", "title": "A", "price_usd": 5, "url": "", "image_url": "", "source": "amazon", "category": "E", "rank": 1},
            ]
        }
        # A 从 #1 跌到 #10, change = 1 - 10 = -9
        today = [_product("B0A", 10)]
        top = compute_rising(today, history, "2026-06-05", top_n=10)
        assert top[0].rank_change == -9
        assert top[0].is_new is False


# ---------- _key ----------

class TestKey:
    def test_uses_asin(self):
        p = _product("B0A", 1)
        assert _key(p) == "B0A"

    def test_falls_back_to_url(self):
        p = Product("tiktok", "X", 1, "T", 5.0, "https://tt/abc", "")
        assert _key(p) == "https://tt/abc"

    def test_falls_back_to_title(self):
        p = Product("tiktok", "X", 1, "Unique Title Here", 5.0, "", "")
        assert _key(p) == "Unique Title Here"
