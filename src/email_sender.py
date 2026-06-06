"""Gmail 邮件发送器.

使用 Gmail SMTP + App Password 发送 HTML 邮件.
配置 (在 GitHub Actions Secrets 或 .env 中):
  GMAIL_ADDRESS       发件 Gmail 地址
  GMAIL_APP_PASSWORD  16 位 App Password (https://myaccount.google.com/apppasswords)
  RECIPIENT_EMAIL     收件人邮箱 (可多个, 逗号分隔)
"""
from __future__ import annotations

import html
import logging
import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

from .charts import bar_chart_svg, multi_line_svg, pie_chart_svg, price_chart_svg, rank_chart_svg
from .ranker import RankedItem, _load_history

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _badge(rank_change: int, is_new: bool) -> str:
    if is_new:
        return '<span style="background:#16a34a;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px;">NEW</span>'
    color = "#16a34a" if rank_change > 0 else ("#dc2626" if rank_change < 0 else "#6b7280")
    sign = "+" if rank_change > 0 else ""
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:10px;font-size:12px;">{sign}{rank_change}</span>'
    )


def _img_tag(url: str) -> str:
    if not url:
        return """<div style="width:120px;height:120px;background:#f3f4f6;border-radius:8px;
display:flex;align-items:center;justify-content:center;color:#9ca3af;font-size:12px;">No image</div>"""
    return (
        f'<img src="{html.escape(url)}" alt="" width="120" height="120" '
        f'style="width:120px;height:120px;object-fit:contain;background:#fff;'
        f'border:1px solid #e5e7eb;border-radius:8px;" />'
    )


def _badges_html(badges: list[str]) -> str:
    """把异常标签渲染成彩色徽章. 颜色按 emoji 自动匹配."""
    if not badges:
        return ""
    palette = {
        "🔥": ("#fee2e2", "#991b1b"),  # 红色
        "🚀": ("#dcfce7", "#166534"),  # 绿色
        "📈": ("#dbeafe", "#1e40af"),  # 蓝色
        "📉": ("#f3e8ff", "#6b21a8"),  # 紫色
        "💸": ("#fef3c7", "#92400e"),  # 黄色
        "💰": ("#fef3c7", "#92400e"),  # 黄色
        "⚡": ("#fce7f3", "#9d174d"),  # 粉色
    }
    parts = []
    for b in badges:
        emoji = b[0] if b else ""
        bg, fg = palette.get(emoji, ("#e5e7eb", "#374151"))
        parts.append(
            f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'padding:2px 7px;border-radius:10px;font-size:11px;font-weight:600;'
            f'margin-right:4px;margin-top:2px;">{html.escape(b)}</span>'
        )
    return f'<div style="margin-top:4px;">{"".join(parts)}</div>'


def _item_row(idx: int, r: RankedItem) -> str:
    yesterday_text = f"yesterday #{r.rank_yesterday}" if r.rank_yesterday else "new entry"
    sp_html = ""
    if r.selling_point:
        sp_html = (
            f'<div style="margin-top:6px;padding:6px 10px;background:#f0f9ff;'
            f'border-left:3px solid #0ea5e9;border-radius:4px;font-size:12px;'
            f'color:#0c4a6e;line-height:1.4;">'
            f'💡 {html.escape(r.selling_point)}</div>'
        )
    badges_html = _badges_html(r.badges)
    return f"""
<tr>
  <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;width:36px;">
    <div style="font-size:22px;font-weight:700;color:#6b7280;">{idx}</div>
  </td>
  <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;width:140px;">
    {_img_tag(r.image_url)}
  </td>
  <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;">
    <div style="font-size:15px;font-weight:600;color:#111827;margin-bottom:4px;">
      <a href="{html.escape(r.url)}" style="color:#111827;text-decoration:none;">
        {html.escape(r.title)}
      </a>
    </div>
    <div style="font-size:13px;color:#6b7280;margin-bottom:6px;">
      <span style="color:#111827;font-weight:600;">${r.price_usd:.2f}</span>
      &nbsp;·&nbsp;
      <span style="background:#eef2ff;color:#4338ca;padding:1px 6px;border-radius:6px;font-size:11px;">
        {html.escape(r.source.upper())}
      </span>
      &nbsp;·&nbsp;
      <span style="color:#6b7280;">{html.escape(r.category)}</span>
    </div>
    <div style="font-size:12px;color:#6b7280;">
      {yesterday_text} &nbsp; { _badge(r.rank_change, r.is_new) }
    </div>
    {badges_html}
    {sp_html}
  </td>
  <td style="padding:12px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;width:140px;">
    {_trend_cell(r)}
  </td>
</tr>
"""


def _trend_cell(r: RankedItem) -> str:
    """根据历史数据画一条 sparkline, 展示排名/价格趋势."""
    history = _load_history(DEFAULT_HISTORY_PATH)
    if r.asin and history:
        # 跨日遍历 history, 找这个 asin 的排名和价格序列
        rank_series: list[float] = []
        price_series: list[float] = []
        for day in sorted(history.keys()):
            for item in history[day]:
                if item.get("asin") == r.asin or item.get("key") == r.asin:
                    rk = item.get("rank")
                    pr = item.get("price_usd", 0)
                    if rk:
                        rank_series.append(float(rk))
                    if pr:
                        price_series.append(float(pr))
                    break
        # 补上今天
        if r.rank_today:
            rank_series.append(float(r.rank_today))
        if r.price_usd:
            price_series.append(float(r.price_usd))
        # 至少 2 个点才画
        rank_svg = rank_chart_svg(rank_series) if len(rank_series) >= 2 else ""
        price_svg = price_chart_svg(price_series) if len(price_series) >= 2 else ""
        if not (rank_svg or price_svg):
            return ""
        parts = []
        if rank_svg:
            parts.append(
                f'<div style="font-size:10px;color:#6b7280;margin-top:2px;">rank&nbsp;{rank_svg}</div>'
            )
        if price_svg:
            parts.append(
                f'<div style="font-size:10px;color:#6b7280;">price&nbsp;{price_svg}</div>'
            )
        return "".join(parts)
    return ""


# 解决循环引用: 把历史文件路径绑到这里
from .ranker import DEFAULT_HISTORY_PATH  # noqa: E402


def _stats_panel(items: list[RankedItem]) -> str:
    """顶部统计小卡片: 价格区间 / 来源分布 / 新晋数量."""
    if not items:
        return ""
    prices = [r.price_usd for r in items if r.price_usd > 0]
    new_count = sum(1 for r in items if r.is_new)
    amazon_count = sum(1 for r in items if r.source == "amazon")
    tiktok_count = sum(1 for r in items if r.source == "tiktok")
    avg_price = sum(prices) / len(prices) if prices else 0
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0

    def cell(label: str, value: str, bg: str = "#f3f4f7") -> str:
        return (
            f'<td style="padding:10px 12px;background:{bg};border-radius:8px;'
            f'vertical-align:top;width:25%;">'
            f'<div style="font-size:11px;color:#6b7280;text-transform:uppercase;'
            f'letter-spacing:0.04em;">{label}</div>'
            f'<div style="font-size:16px;font-weight:600;color:#111827;margin-top:2px;">{value}</div>'
            f"</td>"
        )

    return (
        '<table style="width:100%;border-collapse:separate;border-spacing:6px;margin-bottom:18px;">'
        "<tr>"
        + cell("Price avg", f"${avg_price:.2f}")
        + cell("Price range", f"${min_price:.2f} – ${max_price:.2f}")
        + cell("New entries", f"{new_count} / {len(items)}", bg="#ecfdf5" if new_count else "#f3f4f7")
        + cell("Sources", f"A:{amazon_count} · T:{tiktok_count}")
        + "</tr></table>"
    )


def _bar_panel(items: list[RankedItem]) -> str:
    """价格对比条形图: Top 10 商品价格可视化."""
    priced = [(r.title, r.price_usd) for r in items if r.price_usd > 0]
    if len(priced) < 2:
        return ""
    # 按价格降序
    priced.sort(key=lambda x: x[1], reverse=True)
    labels = [t[:24] for t, _ in priced]
    values = [v for _, v in priced]
    svg = bar_chart_svg(labels, values, width=620, value_fmt="${:.2f}")
    if not svg:
        return ""
    return f"""
    <div style="margin:20px 0 8px;padding:14px 16px;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;">
      <div style="font-size:13px;font-weight:600;color:#92400e;margin-bottom:8px;">💰 Top {len(priced)} 价格对比</div>
      {svg}
    </div>
    """


def _pie_panel(items: list[RankedItem]) -> str:
    """来源分布饼图."""
    from collections import Counter
    counts = Counter(r.source for r in items)
    if not counts:
        return ""
    # 稳定的顺序
    order = ["amazon", "tiktok", "ebay", "google_trends"]
    labels = []
    values = []
    for src in order:
        if counts.get(src):
            labels.append(src)
            values.append(counts[src])
    # 任何未识别的来源
    for src, n in counts.items():
        if src not in order:
            labels.append(src)
            values.append(n)
    if sum(values) == 0:
        return ""
    svg = pie_chart_svg(labels, values, width=160)
    if not svg:
        return ""
    return f"""
    <div style="margin:20px 0 8px;padding:14px 16px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;">
      <div style="font-size:13px;font-weight:600;color:#1e40af;margin-bottom:8px;">📊 来源分布</div>
      {svg}
    </div>
    """


def _multi_line_panel(items: list[RankedItem]) -> str:
    """Top 商品的跨日排名趋势多线图 (有历史数据时才画)."""
    history = _load_history(DEFAULT_HISTORY_PATH)
    if not history or len(history) < 2:
        return ""
    # 收集每个 asin 跨日的 rank 序列
    series_list: list[list[float]] = []
    labels: list[str] = []
    dates = sorted(history.keys())
    for r in items[:8]:  # 最多画 8 条线, 太多会糊
        if not r.asin:
            continue
        ranks: list[float] = []
        for day in dates:
            day_ranks = [
                float(it.get("rank", 0))
                for it in history[day]
                if (it.get("asin") == r.asin or it.get("key") == r.asin)
                and it.get("rank")
            ]
            ranks.append(day_ranks[0] if day_ranks else float(r.rank_today))
        # 补上今天
        ranks.append(float(r.rank_today))
        if len(set(ranks)) > 1:  # 有变化才画
            series_list.append(ranks)
            labels.append(r.title)
    if not series_list:
        return ""
    all_dates = dates + [dates[-1]]  # 简化: 用最后一个日期当今天
    svg = multi_line_svg(
        series_list, labels,
        width=620, height=200,
        x_labels=all_dates[-len(series_list[0]):],
        invert=True,
        y_label="rank",
    )
    if not svg:
        return ""
    return f"""
    <div style="margin:20px 0 8px;padding:14px 16px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;">
      <div style="font-size:13px;font-weight:600;color:#166534;margin-bottom:8px;">📈 排名趋势 (过去 {len(all_dates)} 天)</div>
      <div style="font-size:10px;color:#6b7280;margin-bottom:4px;">越靠上 = 排名越靠前 (1 = 第一名)</div>
      {svg}
    </div>
    """


def build_html(items: list[RankedItem], date_str: str) -> str:
    """构造邮件 HTML 内容."""
    rows = "".join(_item_row(i + 1, r) for i, r in enumerate(items))
    sources = sorted({r.source for r in items})
    stats = _stats_panel(items)
    bar = _bar_panel(items)
    pie = _pie_panel(items)
    multi = _multi_line_panel(items)
    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;">
  <div style="max-width:680px;margin:0 auto;padding:24px;">
    <div style="background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
      <h1 style="margin:0 0 4px;font-size:22px;color:#111827;">
        Daily Trending — 上升最快小物品
      </h1>
      <div style="color:#6b7280;font-size:13px;margin-bottom:14px;">
        {html.escape(date_str)} · 美国市场 · 价格 ≤ $20 · 数据源: {", ".join(s.upper() for s in sources) or "无"}
      </div>
      {stats}
      {bar}
      {pie}
      {multi}
      <h2 style="margin:20px 0 8px;font-size:16px;color:#111827;">🏆 Top 10 详细列表</h2>
      <table style="width:100%;border-collapse:collapse;">
        {rows}
      </table>
      <div style="margin-top:20px;padding-top:16px;border-top:1px solid #e5e7eb;color:#9ca3af;font-size:11px;">
        本报告由 GitHub Actions 每日自动生成 · 数据来源 Amazon · eBay · Google Trends · TikTok<br>
        排名变化 = 昨日排名 - 今日排名 (正数=上升) · "NEW" = 昨日未上榜
      </div>
    </div>
  </div>
</body>
</html>
"""


def build_text(items: list[RankedItem], date_str: str) -> str:
    """纯文本版本 (邮件客户端不支持 HTML 时的 fallback)."""
    lines = [f"Daily Trending — 上升最快小物品 ({date_str})", "=" * 50, ""]
    for i, r in enumerate(items, 1):
        sign = "+" if r.rank_change > 0 else ""
        marker = "NEW" if r.is_new else f"{sign}{r.rank_change}"
        lines.append(
            f"{i:>2}. [{marker:>5}] ${r.price_usd:.2f}  {r.source.upper()}/{r.category}\n"
            f"     {r.title}\n"
            f"     {r.url}"
        )
    lines.append("")
    lines.append("排名变化 = 昨日排名 - 今日排名 (正数=上升). NEW = 昨日未上榜.")
    return "\n".join(lines)


def send_report(
    items: list[RankedItem],
    date_str: str,
    gmail_address: str | None = None,
    app_password: str | None = None,
    recipient: str | None = None,
    csv_data: bytes | None = None,
    pdf_data: bytes | None = None,
) -> bool:
    """发送邮件, 支持 CSV/PDF 附件. 成功返回 True, 失败返回 False."""
    gmail_address = gmail_address or os.environ.get("GMAIL_ADDRESS", "")
    app_password = app_password or os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient = recipient or os.environ.get("RECIPIENT_EMAIL", "")

    if not (gmail_address and app_password and recipient):
        logger.error("missing email config (GMAIL_ADDRESS / GMAIL_APP_PASSWORD / RECIPIENT_EMAIL)")
        return False

    if not items:
        logger.warning("no items to send, skip email")
        return False

    subject = f"🔥 Daily Trending {date_str} — Top {len(items)} 上升最快小物品 (≤$20)"

    # 有附件时用 multipart/mixed, 否则用 multipart/alternative
    has_attachments = csv_data or pdf_data
    outer = MIMEMultipart("mixed" if has_attachments else "alternative")
    outer["Subject"] = subject
    outer["From"] = formataddr(("Daily Trending Bot", gmail_address))
    outer["To"] = recipient
    outer["Date"] = formatdate(localtime=True)
    outer["X-Mailer"] = "DailyTrendingBot/1.0"
    outer["Precedence"] = "bulk"
    outer["List-Unsubscribe"] = f"<mailto:{gmail_address}?subject=unsubscribe>"
    outer["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    outer["X-Entity-ID"] = f"daily-trending-{date_str}"

    # 正文部分 (multipart/alternative)
    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(build_text(items, date_str), "plain", "utf-8"))
    alt_part.attach(MIMEText(build_html(items, date_str), "html", "utf-8"))
    outer.attach(alt_part)

    # 附件
    if csv_data:
        csv_part = MIMEText(csv_data.decode("utf-8"), "csv", "utf-8")
        csv_part.add_header("Content-Disposition", "attachment",
                            filename=f"trending_{date_str}.csv")
        outer.attach(csv_part)

    if pdf_data:
        from email.mime.base import MIMEBase
        from email import encoders
        pdf_part = MIMEBase("application", "pdf")
        pdf_part.set_payload(pdf_data)
        encoders.encode_base64(pdf_part)
        pdf_part.add_header("Content-Disposition", "attachment",
                            filename=f"trending_{date_str}.pdf")
        outer.attach(pdf_part)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, [a.strip() for a in recipient.split(",")], outer.as_string())
        logger.info("email sent to %s (subject=%s, csv=%s, pdf=%s)",
                     recipient, subject, bool(csv_data), bool(pdf_data))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("send email failed: %s", exc)
        return False


def send_alert(
    subject: str,
    body: str,
    gmail_address: str | None = None,
    app_password: str | None = None,
    recipient: str | None = None,
) -> bool:
    """发送告警邮件 (例如抓取全部失败时). 纯文本, 不带 HTML."""
    gmail_address = gmail_address or os.environ.get("GMAIL_ADDRESS", "")
    app_password = app_password or os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient = recipient or os.environ.get("RECIPIENT_EMAIL", "")

    if not (gmail_address and app_password and recipient):
        logger.error("alert skipped: missing email config")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[ALERT] {subject}"
    msg["From"] = formataddr(("Daily Trending Bot", gmail_address))
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["X-Mailer"] = "DailyTrendingBot/1.0"
    msg["X-Priority"] = "1"  # 高优先级

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, [a.strip() for a in recipient.split(",")], msg.as_string())
        logger.warning("alert email sent: %s", subject)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("send alert failed: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from .ranker import RankedItem

    fake = [
        RankedItem(
            title="Cute Cat Earphone Case for AirPods",
            price_usd=8.99,
            url="https://amazon.com/dp/B0TEST1",
            image_url="",
            source="amazon",
            category="Phone Mini Accessories",
            rank_today=3,
            rank_yesterday=42,
            rank_change=39,
            is_new=False,
        )
    ]
    send_report(fake, "2026-06-05")
