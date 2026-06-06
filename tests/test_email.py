"""单元测试: 邮件 HTML 渲染."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.email_sender import _badge, _img_tag, build_html, build_text  # noqa: E402
from src.ranker import RankedItem  # noqa: E402


def _item(idx: int = 0, **kw) -> RankedItem:
    base = dict(
        title="Sample Title",
        price_usd=8.99,
        url="https://example.com/p/1",
        image_url="https://example.com/i/1.jpg",
        source="amazon",
        category="Earrings",
        rank_today=idx + 1,
        rank_yesterday=10,
        rank_change=9,
        is_new=False,
        asin="B0TEST",
    )
    base.update(kw)
    return RankedItem(**base)


class TestBadge:
    def test_positive(self):
        html = _badge(15, False)
        assert "+15" in html
        assert "16a34a" in html  # green

    def test_negative(self):
        html = _badge(-5, False)
        assert "-5" in html
        assert "dc2626" in html  # red

    def test_new(self):
        html = _badge(0, True)
        assert "NEW" in html
        assert "16a34a" in html


class TestImgTag:
    def test_with_url(self):
        out = _img_tag("https://x.com/i.jpg")
        assert "<img" in out
        assert "https://x.com/i.jpg" in out

    def test_no_url_placeholder(self):
        out = _img_tag("")
        # 占位 div 里要明确显示 "No image" 文本
        assert "No image" in out
        assert out.endswith("</div>")


class TestBuildHtml:
    def test_contains_items(self):
        items = [_item(0), _item(1, title="Second", is_new=True)]
        html = build_html(items, "2026-06-05")
        assert "Sample Title" in html
        assert "Second" in html
        assert "$8.99" in html
        assert "2026-06-05" in html

    def test_contains_stats_panel(self):
        items = [_item(0), _item(1), _item(2, is_new=True)]
        html = build_html(items, "2026-06-05")
        # 统计面板的关键 label
        assert "Price avg" in html
        assert "Price range" in html
        assert "New entries" in html
        assert "Sources" in html

    def test_empty_items_renders_minimal(self):
        html = build_html([], "2026-06-05")
        # stats panel 是空字符串, 但 head/body/footer 仍要存在
        assert "Daily Trending" in html
        assert "排名变化" in html

    def test_special_chars_escaped(self):
        items = [_item(0, title='<script>alert("xss")</script>')]
        html = build_html(items, "2026-06-05")
        # 不能有原始 <script> (会被执行)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_sources_listed(self):
        items = [
            _item(0, source="amazon"),
            _item(1, source="tiktok"),
        ]
        html = build_html(items, "2026-06-05")
        assert "AMAZON" in html
        assert "TIKTOK" in html


class TestBuildText:
    def test_basic(self):
        items = [_item(0), _item(1, is_new=True)]
        text = build_text(items, "2026-06-05")
        assert "2026-06-05" in text
        assert "Sample Title" in text
        assert "$8.99" in text
        assert "NEW" in text

    def test_contains_url(self):
        items = [_item(0)]
        text = build_text(items, "2026-06-05")
        assert "https://example.com/p/1" in text
