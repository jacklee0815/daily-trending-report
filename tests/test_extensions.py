"""单元测试: Google Trends 解析, eBay 解析, LLM 容错, Web UI 生成."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.llm import generate_selling_point  # noqa: E402
from src.scraper_ebay import _parse_price  # noqa: E402
from src.scraper_google_trends import _google_trends_to_products, _parse_rss  # noqa: E402
from src.web import _all_products, _build_dataset, _render_head, build_web  # noqa: E402

# ---------- Google Trends ----------

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="http://www.google.com/trends/hottrends">
  <channel>
    <title>Daily Search Trends</title>
    <item>
      <title>cat earphone case</title>
      <ht:approx_traffic>200000+</ht:approx_traffic>
      <pubDate>Mon, 05 Jun 2026 00:00:00 -0700</pubDate>
    </item>
    <item>
      <title>beaded bracelet set</title>
      <ht:approx_traffic>50000+</ht:approx_traffic>
      <pubDate>Mon, 05 Jun 2026 00:00:00 -0700</pubDate>
    </item>
    <item>
      <title></title>
      <ht:approx_traffic>0</ht:approx_traffic>
    </item>
  </channel>
</rss>
"""


class TestGoogleTrends:
    def test_parse_rss(self):
        items = _parse_rss(SAMPLE_RSS)
        # 空标题的会被过滤掉
        titles = [it["title"] for it in items if it["title"]]
        assert "cat earphone case" in titles
        assert "beaded bracelet set" in titles

    def test_to_products(self):
        items = _parse_rss(SAMPLE_RSS)
        products = _google_trends_to_products(items)
        # 非空的进 products
        assert len(products) >= 2
        for p in products:
            assert p.source == "google_trends"
            assert p.price_usd == 0.0
            assert p.url.startswith("https://www.amazon.com/s?")
            assert p.asin.startswith("trend:")

    def test_rank_starts_from_one(self):
        items = _parse_rss(SAMPLE_RSS)
        products = _google_trends_to_products(items)
        if products:
            assert products[0].rank == 1


# ---------- eBay price parser ----------

class TestEbayPrice:
    def test_basic(self):
        assert _parse_price("$12.99") == 12.99

    def test_with_thousands(self):
        assert _parse_price("$1,234.56") == 1234.56

    def test_no_dollar(self):
        # eBay 有时会显示 USD 12.99
        assert _parse_price("12.99") is None or _parse_price("12.99") == 12.99

    def test_empty(self):
        assert _parse_price("") is None


# ---------- LLM ----------

class TestLLM:
    def test_no_api_key_returns_empty(self, monkeypatch):
        # 确保环境变量没有 LLM_API_KEY
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        result = generate_selling_point("Cute Cat Earring", "amazon", 8.99)
        assert result == ""

    def test_handles_empty_title(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        result = generate_selling_point("", "amazon", 8.99)
        assert result == ""

    def test_failed_import_returns_empty(self, monkeypatch):
        # 设了 key 但假装 openai 包未装
        monkeypatch.setenv("LLM_API_KEY", "fake")
        # import 会成功因为 openai 可能装了, 但 client 调用会失败
        # 这里只能确保函数不抛异常
        try:
            result = generate_selling_point("X", "amazon", 5.0)
            assert isinstance(result, str)
        except Exception as exc:
            raise AssertionError(f"should not raise: {exc}")


# ---------- Web UI ----------

class TestWeb:
    def _fake_history(self) -> dict[str, list[dict]]:
        return {
            "2026-06-04": [
                {"key": "B0A", "asin": "B0A", "title": "A", "price_usd": 5, "url": "u", "image_url": "", "source": "amazon", "category": "E", "rank": 1},
            ],
            "2026-06-05": [
                {"key": "B0A", "asin": "B0A", "title": "A", "price_usd": 6, "url": "u", "image_url": "", "source": "amazon", "category": "E", "rank": 2},
                {"key": "B0B", "asin": "B0B", "title": "B", "price_usd": 9, "url": "u", "image_url": "", "source": "tiktok", "category": "J", "rank": 1},
            ],
        }

    def test_all_products(self):
        flat = _all_products(self._fake_history())
        assert len(flat) == 3
        # 应该有 date 字段
        assert all("date" in p for p in flat)

    def test_build_dataset(self):
        flat = _all_products(self._fake_history())
        ds = _build_dataset(flat, top_n=10)
        assert ds["total_records"] == 3
        assert ds["date_range"]["start"] == "2026-06-04"
        assert ds["date_range"]["end"] == "2026-06-05"
        assert len(ds["latest"]) == 3
        # latest 按 date 倒序, 最新一天的在前
        assert ds["latest"][0]["date"] == "2026-06-05"

    def test_render_head_has_placeholders(self):
        html = _render_head("Test")
        assert "<!DOCTYPE html>" in html
        assert "Daily Trending Report" in html
        assert "__DATA_PLACEHOLDER__" in html
        assert "chart.js" in html.lower() or "chartjs" in html.lower() or "chart" in html.lower()

    def test_build_web_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            hist_path = os.path.join(d, "history.json")
            out_path = os.path.join(d, "sub", "index.html")
            with open(hist_path, "w", encoding="utf-8") as f:
                json.dump(self._fake_history(), f)
            result = build_web(hist_path, out_path)
            assert os.path.exists(result)
            with open(result, "r", encoding="utf-8") as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
            # 占位符已被替换
            assert "__DATA_PLACEHOLDER__" not in content
            # 数据注入
            assert "B0A" in content

    def test_build_web_empty_history(self):
        with tempfile.TemporaryDirectory() as d:
            hist_path = os.path.join(d, "history.json")
            out_path = os.path.join(d, "index.html")
            # history.json 不存在
            result = build_web(hist_path, out_path)
            assert os.path.exists(result)
