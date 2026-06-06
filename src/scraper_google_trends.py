"""Google Trends RSS 数据源 (免费, 无 API key).

每天抓美国前 20 热门搜索词, 反映"大家在搜什么", 即潜在的上升趋势信号.
每个搜索词会被构造成一个"轻量商品条目" (Product), 搜索链接跳到 Amazon 搜索结果.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from .scraper_amazon import Product

logger = logging.getLogger(__name__)

# Google Trends 公开的 RSS feed (无 key, 不限速)
TRENDS_RSS = "https://trends.google.com/trending/rss?geo=US"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _fetch(url: str) -> str | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200 and len(r.text) > 200:
                return r.text
            logger.warning("Google Trends GET %s -> %s", url, r.status_code)
        except requests.RequestException as exc:
            logger.warning("Google Trends GET %s failed: %s", url, exc)
        time.sleep(1 + attempt)
    return None


def _parse_rss(xml: str) -> list[dict]:
    """解析 RSS, 返回 [{title, traffic, pubDate, picture, news_item}, ...]"""
    soup = BeautifulSoup(xml, features="xml")
    items: list[dict] = []
    for item_el in soup.select("item"):
        title_el = item_el.select_one("title")
        traffic_el = item_el.select_one("ht\\:approx_traffic, approx_traffic")
        pub_el = item_el.select_one("pubDate")
        items.append({
            "title": title_el.get_text(strip=True) if title_el else "",
            "traffic": traffic_el.get_text(strip=True) if traffic_el else "",
            "pubDate": pub_el.get_text(strip=True) if pub_el else "",
        })
    return items


def _google_trends_to_products(items: Iterable[dict]) -> list[Product]:
    """把 trending 搜索词转成 Product, 链接跳到 Amazon 搜索结果."""
    products: list[Product] = []
    for rank, item in enumerate(items, start=1):
        title = item.get("title", "").strip()
        if not title:
            continue
        traffic_raw = item.get("traffic", "")
        # "200,000+" / "10000+"
        m = re.search(r"([\d,]+)\+?", traffic_raw)
        traffic = int(m.group(1).replace(",", "")) if m else 0
        # 用 Amazon 搜索结果链接, 让用户点开看具体商品
        search_url = (
            f"https://www.amazon.com/s?k={requests.utils.quote(title)}&i=fashion"
        )
        products.append(
            Product(
                source="google_trends",
                category="Trending Search 热门搜索",
                rank=rank,
                title=title,
                price_usd=0.0,  # 趋势词没有价格
                url=search_url,
                image_url="",
                asin=f"trend:{title.lower()}",
            )
        )
        # 把搜索量当作"价格"用来排序也没意义, 但可加到 rank_change 逻辑里
        # 实际我们让 rank 越小=越热门, 由 ranker 处理
        _ = traffic  # 暂未直接使用
    return products


def scrape_google_trends() -> list[Product]:
    """抓 Google Trends 美国每日 top 20 热门搜索词."""
    logger.info("scraping Google Trends RSS ...")
    xml = _fetch(TRENDS_RSS)
    if not xml:
        logger.warning("Google Trends RSS empty, skip")
        return []
    items = _parse_rss(xml)
    products = _google_trends_to_products(items)
    logger.info("Google Trends: %s trending queries", len(products))
    return products


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    items = scrape_google_trends()
    for p in items[:5]:
        print(f"  #{p.rank}  {p.title}  ({p.url})")
