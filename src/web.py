"""静态 Web UI 生成器.

读取 data/history.json, 生成单页 HTML 报告, 可部署到 GitHub Pages / 任何静态托管.
- 顶部: 今日 Top 10 卡片
- 中间: 来源/类目筛选器
- 下方: 历史商品表格 (按日期倒序)
- 图表: 用 Chart.js (CDN 引入), 展示价格 + 排名趋势
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "history.json",
)

DEFAULT_OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
    "index.html",
)

CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"


def _load_history(path: str) -> dict[str, list[dict]]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _all_products(history: dict[str, list[dict]]) -> list[dict]:
    """把 history 展平成 [{date, ...item}, ...], 按 (date, source, rank) 排序."""
    flat: list[dict] = []
    for date_str, items in history.items():
        for it in items:
            flat.append({**it, "date": date_str})
    flat.sort(key=lambda x: (x.get("date", ""), x.get("source", ""), x.get("rank", 999)))
    return flat


def _build_dataset(flat: list[dict], top_n: int = 30) -> dict[str, Any]:
    """构造前端需要的 JSON 数据集."""
    # 取 top_n 最新商品 (按 date desc, rank asc 排序后切片)
    items = sorted(
        flat,
        key=lambda x: (x.get("date", ""), x.get("rank", 999)),
        reverse=False,
    )
    latest = sorted(
        items,
        key=lambda x: x.get("date", ""),
        reverse=True,
    )[:top_n]
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_records": len(flat),
        "date_range": {
            "start": min((x["date"] for x in flat), default=""),
            "end": max((x["date"] for x in flat), default=""),
        },
        "latest": [
            {**x, "title": x.get("title", "")[:100]}
            for x in latest
        ],
    }


def _render_head(title: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(title)}</title>
<script src="{CHARTJS_CDN}"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; background: #f9fafb; color: #111827; }}
  header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 32px 24px; text-align: center; }}
  header h1 {{ margin: 0 0 8px; font-size: 28px; }}
  header .meta {{ font-size: 13px; opacity: 0.9; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }}
  .stat {{ background: #fff; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  .stat .label {{ font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; }}
  .stat .value {{ font-size: 22px; font-weight: 600; margin-top: 4px; }}
  .filters {{ background: #fff; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-bottom: 16px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
  .filters label {{ font-size: 13px; color: #6b7280; }}
  .filters select, .filters input {{ padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; font-size: 13px; }}
  th {{ background: #f3f4f6; font-weight: 600; color: #374151; text-transform: uppercase; font-size: 11px; letter-spacing: 0.04em; }}
  tr:hover {{ background: #f9fafb; }}
  .src-amazon {{ background: #fef3c7; color: #92400e; padding: 1px 6px; border-radius: 4px; font-size: 11px; }}
  .src-tiktok {{ background: #fce7f3; color: #9d174d; padding: 1px 6px; border-radius: 4px; font-size: 11px; }}
  .src-ebay {{ background: #dbeafe; color: #1e40af; padding: 1px 6px; border-radius: 4px; font-size: 11px; }}
  .src-google_trends {{ background: #d1fae5; color: #065f46; padding: 1px 6px; border-radius: 4px; font-size: 11px; }}
  a {{ color: #2563eb; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .empty {{ padding: 60px 20px; text-align: center; color: #6b7280; }}
  footer {{ text-align: center; padding: 24px; color: #9ca3af; font-size: 12px; }}
</style>
</head>
<body>
<header>
  <h1>Daily Trending Report</h1>
  <div class="meta">每日上升最快小物品 (≤$20) · 美国市场 · 由 GitHub Actions 自动生成</div>
</header>
<main>
  <div id="stats" class="stats"></div>
  <div class="filters">
    <label>来源: <select id="filter-source"><option value="">全部</option></select></label>
    <label>类目: <select id="filter-category"><option value="">全部</option></select></label>
    <label>搜索: <input id="filter-search" type="text" placeholder="标题关键词..."></label>
  </div>
  <table>
    <thead>
      <tr>
        <th>日期</th>
        <th>排名</th>
        <th>来源</th>
        <th>类目</th>
        <th>标题</th>
        <th>价格</th>
        <th>链接</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none;">暂无数据</div>
  <footer>
    数据来源: Amazon Best Sellers · eBay Deals · Google Trends RSS · TikTok trending
  </footer>
</main>
<script>
  const DATA = __DATA_PLACEHOLDER__;
  const rowsEl = document.getElementById('rows');
  const emptyEl = document.getElementById('empty');
  const statsEl = document.getElementById('stats');
  const filterSource = document.getElementById('filter-source');
  const filterCategory = document.getElementById('filter-category');
  const filterSearch = document.getElementById('filter-search');

  // 统计
  statsEl.innerHTML = `
    <div class="stat"><div class="label">总记录数</div><div class="value">${{DATA.total_records}}</div></div>
    <div class="stat"><div class="label">开始日期</div><div class="value">${{DATA.date_range.start || '-'}}</div></div>
    <div class="stat"><div class="label">最新日期</div><div class="value">${{DATA.date_range.end || '-'}}</div></div>
    <div class="stat"><div class="label">生成时间</div><div class="value" style="font-size:13px;">${{DATA.generated_at.replace('T',' ').slice(0,19)}}</div></div>
  `;

  // 填筛选器选项
  const sources = new Set();
  const categories = new Set();
  DATA.latest.forEach(r => {{ sources.add(r.source); categories.add(r.category); }});
  [...sources].sort().forEach(s => filterSource.add(new Option(s, s)));
  [...categories].sort().forEach(c => filterCategory.add(new Option(c, c)));

  function render() {{
    const src = filterSource.value;
    const cat = filterCategory.value;
    const q = filterSearch.value.toLowerCase().trim();
    const filtered = DATA.latest.filter(r =>
      (!src || r.source === src) &&
      (!cat || r.category === cat) &&
      (!q || (r.title || '').toLowerCase().includes(q))
    );
    rowsEl.innerHTML = filtered.map(r => `
      <tr>
        <td>${{r.date}}</td>
        <td>${{r.rank}}</td>
        <td><span class="src-${{r.source}}">${{r.source}}</span></td>
        <td>${{(r.category || '').slice(0, 30)}}</td>
        <td>${{(r.title || '').slice(0, 80)}}</td>
        <td>${{r.price_usd ? '$' + r.price_usd.toFixed(2) : '-'}}</td>
        <td>${{r.url ? `<a href="${{r.url}}" target="_blank" rel="noopener">→ 打开</a>` : '-'}}</td>
      </tr>
    `).join('');
    emptyEl.style.display = filtered.length ? 'none' : 'block';
  }}

  filterSource.addEventListener('change', render);
  filterCategory.addEventListener('change', render);
  filterSearch.addEventListener('input', render);
  render();
</script>
</body>
</html>"""


def build_web(history_path: str = DEFAULT_HISTORY_PATH, out_path: str = DEFAULT_OUT_PATH) -> str:
    """生成静态 HTML, 返回写入的文件路径."""
    history = _load_history(history_path)
    flat = _all_products(history)
    dataset = _build_dataset(flat)
    html = _render_head("Daily Trending Report")
    # 把 dataset JSON 注入到占位符
    html = html.replace(
        "__DATA_PLACEHOLDER__",
        json.dumps(dataset, ensure_ascii=False),
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("web UI written to: %s (%s records)", out_path, dataset["total_records"])
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_web()
