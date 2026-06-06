"""eBay Trending 数据源 (best-effort, 无 API key).

策略: 抓 eBay 公开的 Daily Deals / Trending 页面, 提取商品信息.
- 优点: 免费, 不需要 OAuth
- 缺点: eBay 偶尔会返回 captcha, 所以本模块做容错处理
"""
from __future__ import annotations

import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .scraper_amazon import Product

logger = logging.getLogger(__name__)

# eBay 公开页面 (无登录, 但有时段性反爬)
EBAY_DEALS = "https://www.ebay.com/deals"
EBAY_TRENDING = "https://www.ebay.com/trending/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _fetch(url: str) -> str | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200 and len(r.text) > 1000:
                # 检测 captcha
                if "captcha" in r.text.lower()[:5000]:
                    logger.warning("eBay returned captcha, skip")
                    return None
                return r.text
            logger.warning("eBay GET %s -> %s", url, r.status_code)
        except requests.RequestException as exc:
            logger.warning("eBay GET %s failed: %s", url, exc)
        time.sleep(2 + attempt)
    return None


def _parse_price(text: str) -> float | None:
    m = re.search(r"\$\s*([\d,]+\.\d{2})", text)
    if not m:
        m = re.search(r"\$\s*([\d,]+)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_deals_page(html: str) -> list[Product]:
    """从 eBay deals 页面提取 trending 商品.

    eBay 页面会内嵌一段 __NEXT_DATA__ / 初始 state JSON,
    如果有, 直接解析; 否则回退到 HTML 选择器.
    """
    products: list[Product] = []

    # 方式 1: 从内嵌 JSON 解析
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            # 递归找包含 "price" 和 "title" 的 dict 列表
            items = _walk(data, target_keys={"title", "price", "url"})
            for rank, it in enumerate(items[:50], start=1):
                title = it.get("title", "").strip()
                price_raw = it.get("price") or it.get("currentPrice") or it.get("amount")
                if isinstance(price_raw, dict):
                    price_raw = price_raw.get("value") or price_raw.get("amount")
                price = _parse_price(str(price_raw)) if price_raw else None
                url = it.get("url") or it.get("itemWebUrl") or ""
                if url and not url.startswith("http"):
                    url = "https://www.ebay.com" + url
                if title and price is not None and price <= 20.0:
                    products.append(
                        Product(
                            source="ebay",
                            category="eBay Deals",
                            rank=rank,
                            title=title[:200],
                            price_usd=price,
                            url=url,
                            image_url=it.get("image", {}).get("url", "")
                            if isinstance(it.get("image"), dict)
                            else it.get("image", ""),
                            asin=f"ebay:{re.sub(r'[^a-z0-9]', '', title.lower())[:32]}",
                        )
                    )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.debug("eBay __NEXT_DATA__ parse failed: %s", exc)

    if products:
        return products

    # 方式 2: 退到 HTML 选择器
    soup = BeautifulSoup(html, "lxml")
    for rank, card in enumerate(soup.select("[class*='dne-itemtile']"), start=1):
        try:
            title_el = card.select_one("[class*='dne-itemtile-title']") or card.select_one("h3")
            price_el = card.select_one("[class*='dne-itemtile-price']")
            link_el = card.select_one("a[href*='/itm/']")
            img_el = card.select_one("img")
            if not title_el or not link_el:
                continue
            title = title_el.get_text(strip=True)
            href = link_el.get("href", "")
            if href and not href.startswith("http"):
                href = "https://www.ebay.com" + href
            price = _parse_price(price_el.get_text() if price_el else "")
            if price is None or price > 20.0:
                continue
            products.append(
                Product(
                    source="ebay",
                    category="eBay Deals",
                    rank=rank,
                    title=title[:200],
                    price_usd=price,
                    url=href,
                    image_url=img_el.get("src", "") if img_el else "",
                    asin=f"ebay:{re.sub(r'[^a-z0-9]', '', title.lower())[:32]}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("parse eBay card failed: %s", exc)
            continue

    return products


def _walk(node, target_keys: set[str], path: list = None) -> list[dict]:
    """递归找含 title+price+url 的 dict."""
    path = path or []
    found: list[dict] = []
    if isinstance(node, dict):
        keys = set(node.keys())
        if target_keys.issubset(keys):
            found.append(node)
        for v in node.values():
            found.extend(_walk(v, target_keys, path + [str(k) for k in node.keys() if isinstance(k, str)]))
    elif isinstance(node, list):
        for v in node:
            found.extend(_walk(v, target_keys, path))
    return found


def scrape_ebay() -> list[Product]:
    """抓 eBay deals 页面, 返回价格 <= 20 的 trending 商品."""
    logger.info("scraping eBay deals ...")
    html = _fetch(EBAY_DEALS)
    if not html:
        return []
    items = _parse_deals_page(html)
    logger.info("eBay: %s items under $20", len(items))
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    items = scrape_ebay()
    for p in items[:5]:
        print(f"  ${p.price_usd:>6.2f}  {p.title[:60]}  ({p.url})")
