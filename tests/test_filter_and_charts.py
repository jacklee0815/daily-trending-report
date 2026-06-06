"""单元测试: 关键词过滤器, SVG 图表, 失败告警."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.charts import price_chart_svg, rank_chart_svg, sparkline  # noqa: E402
from src.email_sender import _stats_panel  # noqa: E402
from src.filter import (  # noqa: E402
    DEFAULT_BLOCK_KEYWORDS,
    DEFAULT_FLAG_KEYWORDS,
    filter_products,
)
from src.ranker import RankedItem  # noqa: E402
from src.scraper_amazon import Product  # noqa: E402


def _p(**kw) -> Product:
    base = dict(
        source="amazon",
        category="Earrings",
        rank=1,
        title="Cute Cat Stud Earrings",
        price_usd=8.99,
        url="https://amazon.com/dp/B0A",
        image_url="",
        asin="B0A",
    )
    base.update(kw)
    return Product(**base)


# ---------- filter ----------

class TestFilter:
    def test_kept_normal(self):
        result = filter_products([_p()])
        assert len(result.kept) == 1
        assert result.kept[0].title == "Cute Cat Stud Earrings"

    def test_blocked_by_keyword(self):
        result = filter_products([_p(title="Sexy Lingerie Set")])
        assert len(result.kept) == 0
        assert len(result.blocked) == 1
        # "Sexy" 包含 "sex", 会被黑名单先命中
        assert "keyword" in result.blocked[0][1].lower()

    def test_blocked_by_price(self):
        result = filter_products([_p(price_usd=25.0)])
        assert len(result.kept) == 0
        assert "price" in result.blocked[0][1].lower()

    def test_blocked_by_short_title(self):
        result = filter_products([_p(title="abc")])
        assert len(result.kept) == 0
        assert "title too short" in result.blocked[0][1]

    def test_blocked_by_category(self):
        # "Refrigerators" 既在黑名单又不在类目白名单, 会被先命中黑名单
        result = filter_products([_p(category="Refrigerators Small")])
        assert len(result.kept) == 0
        assert "keyword" in result.blocked[0][1].lower()

    def test_blocked_by_category_whitelist(self):
        # 类目不在黑名单但也不在白名单, 触发白名单检查
        result = filter_products([_p(category="Industrial Plumbing Parts")])
        assert len(result.kept) == 0
        assert "whitelist" in result.blocked[0][1]

    def test_flagged_kept(self):
        result = filter_products([_p(title="Vintage Cute Earrings")])
        assert len(result.kept) == 1
        assert len(result.flagged) == 1
        # 标题被加 [!vintage] 前缀
        assert "[!vintage]" in result.kept[0].title

    def test_mixed(self):
        items = [
            _p(asin="B1", title="Cute Cat Earring"),  # keep
            _p(asin="B2", title="Sexy Toy"),  # block (keyword)
            _p(asin="B3", price_usd=30.0),  # block (price)
            _p(asin="B4", title="abc"),  # block (short)
            _p(asin="B5", title="Vintage Earring"),  # flag
        ]
        result = filter_products(items)
        assert len(result.kept) == 2
        assert len(result.blocked) == 3
        assert len(result.flagged) == 1

    def test_custom_keywords(self):
        result = filter_products(
            [_p(title="Toy Plastic")],
            block_keywords=["plastic"],
        )
        assert len(result.kept) == 0
        assert "plastic" in result.blocked[0][1].lower()

    def test_default_block_list_not_empty(self):
        assert len(DEFAULT_BLOCK_KEYWORDS) > 10
        assert len(DEFAULT_FLAG_KEYWORDS) > 0


# ---------- charts ----------

class TestSparkline:
    def test_basic(self):
        s = sparkline([1.0, 2.0, 3.0, 4.0])
        assert "<svg" in s
        assert "</svg>" in s
        assert "<polyline" in s
        assert "<circle" in s

    def test_invert(self):
        # invert=True: 排名 1 在最上, 即数值小的归一化后大
        s1 = sparkline([1, 2, 3], invert=True)
        s2 = sparkline([1, 2, 3], invert=False)
        assert s1 != s2  # 至少坐标点不同

    def test_empty(self):
        assert sparkline([]) == ""
        assert sparkline([1.0]) == ""

    def test_price_chart(self):
        s = price_chart_svg([10, 9, 8, 7])
        assert "<svg" in s

    def test_rank_chart(self):
        s = rank_chart_svg([50, 30, 10, 1])
        assert "<svg" in s

    def test_color_propagates(self):
        s = sparkline([1, 2, 3], color="#ff0000")
        assert "#ff0000" in s


# ---------- stats panel ----------

class TestStatsPanel:
    def test_with_items(self):
        items = [
            RankedItem(
                title="A", price_usd=10.0, url="u", image_url="",
                source="amazon", category="E", rank_today=1, rank_yesterday=None,
                rank_change=50, is_new=True, asin="",
            ),
            RankedItem(
                title="B", price_usd=15.0, url="u", image_url="",
                source="tiktok", category="J", rank_today=2, rank_yesterday=5,
                rank_change=3, is_new=False, asin="",
            ),
        ]
        html = _stats_panel(items)
        assert "Price avg" in html
        assert "Price range" in html
        assert "New entries" in html
        assert "Sources" in html
        # avg = 12.5
        assert "12.50" in html or "$12.50" in html
        # sources: A:1, T:1
        assert "1" in html

    def test_empty(self):
        assert _stats_panel([]) == ""
