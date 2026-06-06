"""TikTok 趋势爬虫 (免费方案的折中实现).

注意: TikTok Shop 的"上升最快商品"数据基本只通过付费 API (EchoTik 等) 提供.
本模块采用以下折中策略:
  1. 抓取 TikTok 公开的 trending hashtags / discover 页面, 提取热门话题.
  2. 从话题相关视频的描述中匹配 "商品关键词 + 价格" 模式, 合成轻量商品条目.
  3. 抓取失败时返回空列表, 不影响 Amazon 数据源.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from .scraper_amazon import Product

logger = logging.getLogger(__name__)

TIKTOK_BASE = "https://www.tiktok.com"

# 关注的 discover 类目 (slug -> 中文显示名).
DISCOVER_CATEGORIES: dict[str, str] = {
    "jewelry": "Jewelry 首饰",
    "earrings": "Earrings 耳环",
    "bracelet": "Bracelet 手环",
    "fidget-toys": "Fidget Toys 解压玩具",
    "kawaii": "Kawaii Cute 萌物",
    "phone-accessories": "Phone Accessories 手机配件",
    "hair-clips": "Hair Clips 发夹",
    "keychain": "Keychain 钥匙扣",
    "rings": "Rings 戒指",
    "cute-stationery": "Cute Stationery 文具",
}

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

# 从视频描述/标题中提取价格 ($5.99 / $10 / under $15)
PRICE_RE = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)", re.IGNORECASE)
UNDER_PRICE_RE = re.compile(
    r"under\s*\$\s*(\d+(?:\.\d{1,2})?)|less\s*than\s*\$\s*(\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# 购物引导关键词, 命中后认为是商品类内容
BUY_KEYWORDS = re.compile(
    r"\b(buy|shop|sale|deal|amazon|etsy|tiktok made me buy it|"
    r"haul|favorite|must[- ]?have|trending|viral|recommend)\b",
    re.IGNORECASE,
)


def _fetch(url: str, session: requests.Session) -> str | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for attempt in range(2):
        try:
            r = session.get(url, headers=headers, timeout=20, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 1000:
                return r.text
            logger.warning("TikTok GET %s -> %s", url, r.status_code)
        except requests.RequestException as exc:
            logger.warning("TikTok GET %s failed: %s", url, exc)
        time.sleep(2)
    return None


def _extract_price(text: str) -> float | None:
    if not text:
        return None
    # "under $15" 这种优先
    m = UNDER_PRICE_RE.search(text)
    if m:
        try:
            return float(m.group(1) or m.group(2))
        except (ValueError, TypeError):
            pass
    # 抓 $数字
    matches = PRICE_RE.findall(text)
    if not matches:
        return None
    prices = [float(p) for p in matches if float(p) < 50]
    if not prices:
        return None
    # 取最小值, 倾向于单价
    return min(prices)


def _parse_discover(html: str, category_name: str) -> list[Product]:
    """从 discover 页面提取 trending 视频的描述/标题, 合成商品."""
    soup = BeautifulSoup(html, "lxml")
    products: list[Product] = []

    # TikTok 把 trending 视频的元信息序列化在 <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">
    for script in soup.select("script#__UNIVERSAL_DATA_FOR_REHYDRATION__"):
        try:
            data = json.loads(script.string or "{}")
        except json.JSONDecodeError:
            continue
        items = _walk_trending_items(data)
        for rank, item in enumerate(items, start=1):
            desc = item.get("desc") or item.get("title") or ""
            if not desc or len(desc) < 5:
                continue
            if not BUY_KEYWORDS.search(desc):
                continue
            price = _extract_price(desc)
            if price is None or price > 20.0:
                continue
            url = item.get("webUrl") or item.get("url") or ""
            if url and not url.startswith("http"):
                url = TIKTOK_BASE + url
            products.append(
                Product(
                    source="tiktok",
                    category=category_name,
                    rank=rank,
                    title=desc[:140],
                    price_usd=price,
                    url=url,
                    image_url=item.get("coverUrl", "") or item.get("image", ""),
                    asin=item.get("id", ""),
                )
            )

    # 备选: 直接抓 meta og:title / description
    if not products:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and BUY_KEYWORDS.search(meta_desc.get("content", "")):
            price = _extract_price(meta_desc.get("content", ""))
            if price is not None and price <= 20.0:
                products.append(
                    Product(
                        source="tiktok",
                        category=category_name,
                        rank=1,
                        title=meta_desc.get("content", "")[:140],
                        price_usd=price,
                        url="",
                        image_url="",
                        asin="",
                    )
                )

    return products


def _walk_trending_items(node) -> list[dict]:
    """递归遍历 __UNIVERSAL_DATA__ JSON, 找出所有可能含 desc/url 的视频项."""
    results: list[dict] = []
    if isinstance(node, dict):
        if "desc" in node and ("webUrl" in node or "url" in node):
            results.append(node)
        for v in node.values():
            results.extend(_walk_trending_items(v))
    elif isinstance(node, list):
        for v in node:
            results.extend(_walk_trending_items(v))
    return results


def scrape_tiktok(categories: dict[str, str] | None = None) -> list[Product]:
    """抓取所有目标 discover 类目, 返回带价格的 trending 商品."""
    cats = categories or DISCOVER_CATEGORIES
    session = requests.Session()
    all_products: list[Product] = []

    for slug, name in cats.items():
        url = f"{TIKTOK_BASE}/discover/{slug}"
        logger.info("scraping TikTok %s (%s)", name, url)
        html = _fetch(url, session)
        if not html:
            logger.warning("skip %s (no html)", slug)
            continue
        items = _parse_discover(html, name)
        logger.info("  -> %s candidate items", len(items))
        all_products.extend(items)
        time.sleep(2)

    return all_products


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    items = scrape_tiktok()
    print(f"total: {len(items)}")
    for p in items[:5]:
        print(p)
