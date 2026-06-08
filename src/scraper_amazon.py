"""Amazon Best Sellers 爬虫.

抓取美国站 Amazon 多个细分类目的 Best Sellers 榜单,
筛选出价格 <= 20 USD 的小物品.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

AMAZON_BASE = "https://www.amazon.com"

# 关注的细分类目 (slug -> 中文显示名).
# 这些都是小物品、价格在 20 美金以内的常见类目.
CATEGORIES: dict[str, str] = {
    "fashion-jewelry": "Fashion Jewelry 时尚饰品",
    "watches": "Watches 手表",
    "toys-and-games": "Toys & Games 玩具",
    "kids": "Kids 儿童用品",
    "handmade-jewelry": "Handmade Jewelry 手作饰品",
    "handmade-toys": "Handmade Toys 手作玩具",
    "bracelets": "Bracelets 手环",
    "earrings": "Earrings 耳环",
    "fashion-watches": "Fashion Watches 时尚手表",
    "hair-accessories": "Hair Accessories 发饰",
    "keychains": "Keychains 钥匙扣",
    "cell-phone-mini-accessories": "Phone Mini Accessories 手机小配件",
}

# slug -> Amazon URL 路径 (Best Sellers 分类页 URL 格式变了)
CATEGORY_URLS: dict[str, str] = {
    "fashion-jewelry": "/Best-Sellers-Jewelry/zgbs/fashion-jewelry",
    "watches": "/Best-Sellers-Watches/zgbs/watches",
    "toys-and-games": "/Best-Sellers-Toys-Games/zgbs/toys-and-games",
    "kids": "/Best-Sellers-Baby/kids",
    "handmade-jewelry": "/Best-Sellers-Handmade-Jewelry/zgbs/handmade-jewelry",
    "handmade-toys": "/Best-Sellers-Handmade-Toys/zgbs/handmade-toys",
    "bracelets": "/Best-Sellers-Bracelets/zgbs/bracelets",
    "earrings": "/Best-Sellers-Earrings/zgbs/earrings",
    "fashion-watches": "/Best-Sellers-Fashion-Watches/zgbs/fashion-watches",
    "hair-accessories": "/Best-Sellers-Hair-Accessories/zgbs/hair-accessories",
    "keychains": "/Best-Sellers-Keychains/zgbs/keychains",
    "cell-phone-mini-accessories": "/Best-Sellers-Cell-Phone-Accessories/zgbs/cell-phone-mini-accessories",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class Product:
    """一个商品条目."""

    source: str  # "amazon" / "tiktok"
    category: str
    rank: int
    title: str
    price_usd: float
    url: str
    image_url: str = ""
    asin: str = ""  # Amazon 商品 ID, 用于去重

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_price(text: str) -> float | None:
    """从 '$12.99' / '$1,234.56' 之类的文本里提取价格数字."""
    if not text:
        return None
    m = re.search(r"\$?\s*([\d,]+\.\d{2})", text)
    if not m:
        m = re.search(r"\$?\s*([\d,]+)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _fetch(url: str, session: requests.Session) -> str | None:
    """带重试地抓取一个页面."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
    }
    for attempt in range(3):
        try:
            r = session.get(url, headers=headers, timeout=20)
            if r.status_code == 200:
                return r.text
            logger.warning("Amazon GET %s -> %s (attempt %s)", url, r.status_code, attempt + 1)
        except requests.RequestException as exc:
            logger.warning("Amazon GET %s failed: %s (attempt %s)", url, exc, attempt + 1)
        time.sleep(2 + attempt * 2)
    return None


def _parse_category_page(html: str, category_slug: str, category_name: str) -> list[Product]:
    """解析一个 Best Sellers 类目页, 提取价格 <= 20 的商品."""
    soup = BeautifulSoup(html, "lxml")
    products: list[Product] = []

    # 2024+ Amazon Best Sellers 的商品卡片结构:
    # <div id="gridItemRoot" data-asin="B0XXXX">
    #   <a class="a-link-normal" href="/dp/B0XXXX">...</a>
    #   <div class="p13n-sc-truncate-desktop-type2">title</div>
    #   <span class="p13n-sc-price">$12.99</span>
    #   <img alt="..." src="...">
    cards = soup.select("div#gridItemRoot, div.zg-grid-general-faceout, li.zg-item")

    for idx, card in enumerate(cards, start=1):
        try:
            asin = card.get("data-asin") or ""
            # 标题
            title_el = card.select_one(
                "div.p13n-sc-truncate-desktop-type2, "
                "div.p13n-sc-truncate, "
                "a.a-link-normal > span"
            )
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                # 备选: 用 a 标签的 title 属性
                a_el = card.select_one("a.a-link-normal[title]")
                if a_el:
                    title = a_el.get("title", "").strip()

            # 链接
            a_el = card.select_one("a.a-link-normal[href*='/dp/']")
            href = a_el["href"] if a_el else ""
            full_url = urljoin(AMAZON_BASE, href) if href else ""

            if not asin and full_url:
                m = re.search(r"/dp/([A-Z0-9]{10})", full_url)
                asin = m.group(1) if m else ""

            # 价格
            price_el = card.select_one(
                "span.p13n-sc-price, "
                "span.a-color-price, "
                "span._cDEzb_p13n-sc-price"
            )
            price_text = price_el.get_text(strip=True) if price_el else ""
            price = _parse_price(price_text)

            # 图片 (多种属性尝试)
            img_el = card.select_one("img")
            image_url = ""
            if img_el:
                # 按优先级尝试多个属性
                for attr in ("src", "data-old-hd", "data-old-hires", "data-a-dynamic-image", "srcset"):
                    val = img_el.get(attr, "")
                    if val:
                        if attr == "data-a-dynamic-image":
                            # JSON 格式: {"url1": [w, h], "url2": [w, h]}
                            try:
                                import json
                                imgs = json.loads(val)
                                image_url = list(imgs.keys())[0] if imgs else ""
                            except (json.JSONDecodeError, IndexError):
                                image_url = val[:200]  # 截断避免过长
                        elif attr == "srcset":
                            # srcset: "url1 1x, url2 2x" -> 取第一个
                            image_url = val.split(",")[0].strip().split(" ")[0]
                        else:
                            image_url = val
                        if image_url:
                            break

            if not title or not asin:
                continue

            # 排名 (用卡片在页面中的位置, 1-based)
            rank = idx

            if price is not None and price > 20.0:
                # 价格超 20 美金, 跳过
                continue

            products.append(
                Product(
                    source="amazon",
                    category=category_name,
                    rank=rank,
                    title=title,
                    price_usd=price or 0.0,
                    url=full_url,
                    image_url=image_url,
                    asin=asin,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("parse card failed: %s", exc)
            continue

    return products


def scrape_amazon(categories: Iterable[str] | None = None) -> list[Product]:
    """抓取所有目标类目的 Amazon Best Sellers, 返回价格 <= 20 的商品列表."""
    session = requests.Session()
    slugs = list(categories) if categories else list(CATEGORIES.keys())
    all_products: list[Product] = []

    for slug in slugs:
        category_name = CATEGORIES.get(slug, slug)
        url_path = CATEGORY_URLS.get(slug, f"/Best-Sellers/zgbs/{slug}")
        url = f"{AMAZON_BASE}{url_path}"
        logger.info("scraping Amazon %s (%s)", category_name, url)
        html = _fetch(url, session)
        if not html:
            logger.warning("skip %s (no html)", slug)
            continue
        items = _parse_category_page(html, slug, category_name)
        logger.info("  -> %s items under $20", len(items))
        all_products.extend(items)
        time.sleep(1.5)  # 礼貌延时

    return all_products


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    items = scrape_amazon()
    print(f"total: {len(items)}")
    for p in items[:5]:
        print(p)
