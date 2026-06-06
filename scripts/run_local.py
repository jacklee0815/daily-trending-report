"""本地 dry-run: 跑一遍抓取 + 排名, 渲染邮件 HTML 到本地, 但不发送.

用法:
    python scripts/run_local.py            # 跑抓取 + 渲染到 output/preview.html
    python scripts/run_local.py --no-scrape  # 用 data/history.json 里的数据重新渲染

可以打开 output/preview.html 看邮件长什么样.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date

# 让 `from src.xxx import` 可用
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.email_sender import build_html  # noqa: E402
from src.ranker import (  # noqa: E402
    DEFAULT_HISTORY_PATH,
    _load_history,
    compute_rising,
    dedupe_products,
)
from src.scraper_amazon import scrape_amazon  # noqa: E402
from src.scraper_tiktok import scrape_tiktok  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("dry-run")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-scrape",
        action="store_true",
        help="用 data/history.json 里的数据重新渲染, 不联网",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="返回 top N (默认 10)",
    )
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "output", "preview.html"),
        help="HTML 输出路径",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    today = date.today().isoformat()

    if args.no_scrape:
        history = _load_history(DEFAULT_HISTORY_PATH)
        if not history or today not in history:
            logger.error("no history for %s, run without --no-scrape first", today)
            return 1
        from src.scraper_amazon import Product

        items_dict = history[today]
        products = [
            Product(
                source=d["source"],
                category=d["category"],
                rank=d["rank"],
                title=d["title"],
                price_usd=d["price_usd"],
                url=d["url"],
                image_url=d["image_url"],
                asin=d.get("asin", ""),
            )
            for d in items_dict
        ]
        deduped = dedupe_products(products)
        top = compute_rising(deduped, history, today, top_n=args.top)
    else:
        logger.info("scraping Amazon ...")
        amazon = scrape_amazon()
        logger.info("Amazon: %s items", len(amazon))

        logger.info("scraping TikTok ...")
        tiktok = scrape_tiktok()
        logger.info("TikTok: %s items", len(tiktok))

        all_products = amazon + tiktok
        deduped = dedupe_products(all_products)
        history = _load_history(DEFAULT_HISTORY_PATH)
        top = compute_rising(deduped, history, today, top_n=args.top)

    logger.info("=" * 60)
    logger.info("TOP %s RISING:", args.top)
    logger.info("=" * 60)
    for i, r in enumerate(top, 1):
        sign = "+" if r.rank_change > 0 else ""
        marker = "NEW" if r.is_new else f"{sign}{r.rank_change}"
        logger.info(
            "%2d. [%5s] $%6.2f  %s  %s",
            i, marker, r.price_usd, r.source.upper(), r.title[:60],
        )

    html = build_html(top, today)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("preview written to: %s", args.out)
    logger.info("open it in a browser to see the email layout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
