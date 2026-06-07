"""主入口: 抓取 -> 过滤 -> 计算上升 -> LLM 卖点 -> 发邮件 -> 生成 Web UI.

环境变量 (通过 GitHub Actions Secrets 或 .env):
  GMAIL_ADDRESS, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL
  LLM_API_KEY, LLM_BASE_URL (可选, 默认 OpenAI), LLM_MODEL (可选)
"""
from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv()

from .email_sender import send_alert, send_report
from .exporters import csv_bytes, export_pdf
from .filter import filter_products
from .llm import generate_selling_point
from .ranker import run_ranking
from .scraper_amazon import scrape_amazon
from .scraper_ebay import scrape_ebay
from .scraper_google_trends import scrape_google_trends
from .scraper_tiktok import scrape_tiktok
from .web import build_web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("daily-trending")


def _scrape_all() -> tuple[list, list[str]]:
    """抓取所有数据源, 返回 (products, errors)."""
    all_products: list = []
    errors: list[str] = []

    scrapers = [
        ("Amazon", scrape_amazon),
        ("TikTok", scrape_tiktok),
        ("eBay", scrape_ebay),
        ("Google Trends", scrape_google_trends),
    ]
    for name, fn in scrapers:
        logger.info("=" * 60)
        logger.info("scraping %s ...", name)
        logger.info("=" * 60)
        try:
            items = fn()
            logger.info("%s: %s items", name, len(items))
            all_products.extend(items)
        except Exception as exc:  # noqa: BLE001
            msg = f"{name} scrape failed: {exc}"
            logger.exception(msg)
            errors.append(msg)
    return all_products, errors


def _enrich_with_selling_points(items: list) -> list:
    """给 top 商品加 LLM 生成的中文卖点. 失败静默回退."""
    if not os.environ.get("LLM_API_KEY"):
        logger.info("LLM_API_KEY not set, skip selling point generation")
        return items
    logger.info("generating LLM selling points ...")
    for r in items:
        if not r.selling_point:
            r.selling_point = generate_selling_point(
                title=r.title, source=r.source, price=r.price_usd,
            )
    n = sum(1 for r in items if r.selling_point)
    logger.info("LLM selling points generated: %s / %s", n, len(items))
    return items


def main() -> int:
    report_date = date.today().isoformat()
    all_products, scrape_errors = _scrape_all()

    if not all_products:
        logger.error("no data from any source")
        send_alert(
            subject="抓取全部失败",
            body=(
                f"Daily Trending 报告生成失败 ({report_date}).\n\n"
                f"所有数据源均未返回商品:\n"
                + "\n".join(f"  - {e}" for e in scrape_errors)
                + "\n\n请检查 GitHub Actions 日志确认网络 / 爬虫状态."
            ),
        )
        return 1

    logger.info("=" * 60)
    logger.info("filtering ...")
    logger.info("=" * 60)
    fr = filter_products(all_products)
    if fr.blocked:
        from collections import Counter
        reasons = Counter(r for _, r in fr.blocked)
        top_reasons = ", ".join(f"{k}({v})" for k, v in reasons.most_common(3))
        logger.info("filtered out %s: %s", len(fr.blocked), top_reasons)
    products = fr.kept
    if not products:
        logger.error("all products filtered out")
        send_alert(
            subject="过滤后无商品",
            body=(
                f"Daily Trending 抓取到 {len(all_products)} 个商品, "
                f"但全部被过滤器拦截 ({report_date}).\n"
                f"原因示例: " + "; ".join(r for _, r in fr.blocked[:5])
            ),
        )
        return 1

    logger.info("=" * 60)
    logger.info("computing top 10 rising ...")
    logger.info("=" * 60)
    top = run_ranking(products, report_date, top_n=10)
    for i, r in enumerate(top, 1):
        sign = "+" if r.rank_change > 0 else ""
        marker = "NEW" if r.is_new else f"{sign}{r.rank_change}"
        logger.info(
            "%2d. [%5s] $%6.2f  %s/%s  %s",
            i, marker, r.price_usd, r.source.upper(), r.category, r.title[:60],
        )

    # LLM 卖点增强
    top = _enrich_with_selling_points(top)

    # 导出 CSV + PDF (PDF 需要 fpdf2, 没装时返回 None)
    logger.info("=" * 60)
    logger.info("exporting CSV/PDF ...")
    logger.info("=" * 60)
    csv_attachment = csv_bytes(top, report_date)
    pdf_attachment = export_pdf(top, report_date)
    logger.info("CSV: %s bytes, PDF: %s bytes", len(csv_attachment),
                len(pdf_attachment) if pdf_attachment else "skipped")

    logger.info("=" * 60)
    logger.info("sending email ...")
    logger.info("=" * 60)
    email_ok = send_report(top, report_date,
                           csv_data=csv_attachment,
                           pdf_data=pdf_attachment)

    logger.info("=" * 60)
    logger.info("generating web UI ...")
    logger.info("=" * 60)
    try:
        build_web()
    except Exception as exc:  # noqa: BLE001
        logger.exception("web UI build failed: %s", exc)

    if not email_ok:
        send_alert(
            subject="邮件发送失败",
            body=f"数据已抓取并排名, 但发送邮件时失败 ({report_date}).",
        )
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        err = traceback.format_exc()
        logging.exception("unhandled exception in main")
        send_alert(
            subject="主流程崩溃",
            body=f"Daily Trending 主入口未捕获异常:\n\n{err}",
        )
        sys.exit(99)
