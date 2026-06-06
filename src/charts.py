"""极简 SVG 图表生成器 (无外部依赖).

支持的图表:
  - sparkline          迷你折线 (单商品价格/排名趋势)
  - bar_chart_svg      水平条形图 (Top N 商品价格对比)
  - pie_chart_svg      饼图 (来源分布)
  - multi_line_svg     多线折线图 (Top N 商品排名历史)
  - price_chart_svg    sparkline 别名
  - rank_chart_svg     sparkline 别名 (排名方向反转)
"""
from __future__ import annotations

import math
from typing import Sequence

WIDTH = 120
HEIGHT = 32
PADDING = 2

# 多线图默认颜色 (与邮件里 sparkline 配色呼应)
DEFAULT_PALETTE = [
    "#16a34a", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
    "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#a855f7",
]


def _normalize(series: Sequence[float], max_val: float, invert: bool = False) -> list[float]:
    """线性归一化到 [0, 1] 区间. invert=True 用于排名 (排名低=位置高)."""
    if not series:
        return []
    lo, hi = min(series), max(series)
    if hi == lo:
        return [0.5] * len(series)
    rng = hi - lo
    out = []
    for v in series:
        n = (v - lo) / rng
        if invert:
            n = 1 - n
        out.append(n)
    return out


def sparkline(
    series: Sequence[float],
    color: str = "#16a34a",
    invert: bool = False,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> str:
    """返回一个 SVG 字符串, 表示一条带末尾点的折线."""
    if not series or len(series) < 2:
        return ""

    normed = _normalize(series, series[0], invert=invert)
    n = len(normed)
    step_x = (width - 2 * PADDING) / max(1, n - 1)

    points = []
    for i, v in enumerate(normed):
        x = PADDING + i * step_x
        y = PADDING + (1 - v) * (height - 2 * PADDING)
        points.append(f"{x:.1f},{y:.1f}")

    polyline = " ".join(points)
    last_x, last_y = points[-1].split(",")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="{last_x}" cy="{last_y}" r="2" fill="{color}" />
</svg>"""


def price_chart_svg(prices: Sequence[float], color: str = "#16a34a") -> str:
    return sparkline(prices, color=color, invert=False)


def rank_chart_svg(ranks: Sequence[float], color: str = "#3b82f6") -> str:
    return sparkline(ranks, color=color, invert=True)


# ====================== 综合图表 ======================

def bar_chart_svg(
    labels: Sequence[str],
    values: Sequence[float],
    width: int = 480,
    bar_height: int = 22,
    gap: int = 6,
    color: str = "#3b82f6",
    max_value: float | None = None,
    value_fmt: str = "${:.2f}",
) -> str:
    """水平条形图, 用在邮件里展示 Top N 商品的价格对比.

    Args:
        labels: 每根条的标签 (e.g. 商品简称)
        values: 每根条对应的数值
        max_value: x 轴最大值, 默认用 values 的最大值
    """
    if not labels or not values or len(labels) != len(values):
        return ""
    n = len(labels)
    label_w = 130   # 左侧标签宽度
    value_w = 50    # 右侧数值文字宽度
    chart_w = width - label_w - value_w
    total_h = n * (bar_height + gap) + 4
    if max_value is None:
        max_value = max(values) if values else 1
    if max_value <= 0:
        max_value = 1

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_h}" viewBox="0 0 {width} {total_h}">'
    ]
    for i, (lab, val) in enumerate(zip(labels, values)):
        y = 2 + i * (bar_height + gap)
        bar_len = max(2, (val / max_value) * chart_w)
        # 标签
        text = (lab or "")[:18]
        parts.append(
            f'<text x="{label_w - 6}" y="{y + bar_height * 0.7}" '
            f'text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#374151">'
            f'{_xml_escape(text)}</text>'
        )
        # 条
        parts.append(
            f'<rect x="{label_w}" y="{y}" width="{bar_len:.1f}" height="{bar_height}" '
            f'rx="3" ry="3" fill="{color}" />'
        )
        # 数值
        parts.append(
            f'<text x="{label_w + bar_len + 6}" y="{y + bar_height * 0.7}" '
            f'font-family="Arial, sans-serif" font-size="11" fill="#111827" font-weight="600">'
            f'{_xml_escape(value_fmt.format(val))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def pie_chart_svg(
    labels: Sequence[str],
    values: Sequence[float],
    width: int = 220,
    colors: Sequence[str] | None = None,
) -> str:
    """饼图 + 右侧图例. 展示来源分布等占比.

    用 SVG <path> 画扇形 (起点 12 点钟方向, 顺时针).
    """
    if not labels or not values or len(labels) != len(values):
        return ""
    total = sum(values)
    if total <= 0:
        return ""

    colors = list(colors or DEFAULT_PALETTE)
    cx, cy, r = width / 2, width / 2, min(width / 2 - 8, 90)
    legend_x = width + 12
    legend_w = 130
    total_h = width + max(0, len(labels) * 18 - width + 20)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width + legend_w}" height="{int(total_h)}" '
        f'viewBox="0 0 {width + legend_w} {int(total_h)}">'
    ]

    # 扇形
    start_angle = -math.pi / 2  # 12 点钟方向
    for i, (lab, val) in enumerate(zip(labels, values)):
        if val <= 0:
            continue
        angle = val / total * 2 * math.pi
        end_angle = start_angle + angle
        x1, y1 = cx + r * math.cos(start_angle), cy + r * math.sin(start_angle)
        x2, y2 = cx + r * math.cos(end_angle), cy + r * math.sin(end_angle)
        large = 1 if angle > math.pi else 0
        d = f"M {cx:.2f},{cy:.2f} L {x1:.2f},{y1:.2f} A {r},{r} 0 {large} 1 {x2:.2f},{y2:.2f} Z"
        parts.append(
            f'<path d="{d}" fill="{colors[i % len(colors)]}" stroke="#fff" stroke-width="1.5" />'
        )
        start_angle = end_angle

    # 中心白圆 (donut 效果, 顺便放总数)
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r * 0.55}" fill="#fff" />'
    )
    parts.append(
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" font-family="Arial, sans-serif" '
        f'font-size="11" fill="#6b7280">Total</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + 12}" text-anchor="middle" font-family="Arial, sans-serif" '
        f'font-size="16" fill="#111827" font-weight="700">{int(total)}</text>'
    )

    # 图例
    for i, (lab, val) in enumerate(zip(labels, values)):
        ly = 18 + i * 18
        if ly > total_h - 8:
            break
        parts.append(
            f'<rect x="{legend_x}" y="{ly - 9}" width="10" height="10" rx="2" fill="{colors[i % len(colors)]}" />'
        )
        pct = val / total * 100
        parts.append(
            f'<text x="{legend_x + 16}" y="{ly}" font-family="Arial, sans-serif" font-size="12" fill="#374151">'
            f'{_xml_escape((lab or "")[:14])} ({pct:.0f}%)</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def multi_line_svg(
    series_list: Sequence[Sequence[float]],
    labels: Sequence[str],
    width: int = 480,
    height: int = 180,
    colors: Sequence[str] | None = None,
    x_labels: Sequence[str] | None = None,
    invert: bool = True,
    y_label: str = "rank",
) -> str:
    """多线折线图. 用于展示 Top N 商品过去若干天的排名变化.

    Args:
        series_list: 多个序列, 每个序列是一个商品的历史值
        labels: 每个序列对应的图例 (商品简称)
        x_labels: x 轴标签 (日期), 与每个序列长度一致
        invert: True=排名方向 (1 在顶部)
    """
    series_list = [s for s in series_list if s and len(s) >= 2]
    if not series_list:
        return ""
    colors = list(colors or DEFAULT_PALETTE)

    pad_l, pad_r, pad_t, pad_b = 44, 12, 14, 30
    chart_w = width - pad_l - pad_r
    chart_h = height - pad_t - pad_b
    max_len = max(len(s) for s in series_list)
    # 全局 min/max 用于归一化
    all_vals = [v for s in series_list for v in s]
    if invert:
        # 排名方向: y 轴翻转, 1 在顶部
        # 我们让最小值在顶部, 最大值在底部
        v_min, v_max = min(all_vals), max(all_vals)
    else:
        v_min, v_max = min(all_vals), max(all_vals)
    if v_min == v_max:
        v_min, v_max = v_min - 1, v_max + 1

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fafafa" />',
    ]

    # 网格 (4 条横线)
    for i in range(5):
        gy = pad_t + chart_h * i / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
            f'stroke="#e5e7eb" stroke-width="1" />'
        )
        # y 轴标签 (从大到小, 因为排名方向)
        if invert:
            val = v_max - (v_max - v_min) * i / 4
        else:
            val = v_min + (v_max - v_min) * i / 4
        parts.append(
            f'<text x="{pad_l - 4}" y="{gy + 3:.1f}" text-anchor="end" '
            f'font-family="Arial, sans-serif" font-size="10" fill="#9ca3af">{val:.0f}</text>'
        )

    # x 轴标签 (最多 6 个, 间隔均匀)
    if x_labels and len(x_labels) == max_len:
        step = max(1, max_len // 6)
        for i in range(0, max_len, step):
            gx = pad_l + (chart_w * i / max(1, max_len - 1))
            parts.append(
                f'<text x="{gx:.1f}" y="{height - pad_b + 14}" text-anchor="middle" '
                f'font-family="Arial, sans-serif" font-size="10" fill="#9ca3af">'
                f'{_xml_escape(x_labels[i][:10])}</text>'
            )

    # y 轴标题
    parts.append(
        f'<text x="{pad_l - 28}" y="{pad_t - 4}" font-family="Arial, sans-serif" '
        f'font-size="10" fill="#6b7280">{_xml_escape(y_label)}</text>'
    )

    # 每条线
    for idx, series in enumerate(series_list):
        color = colors[idx % len(colors)]
        n = len(series)
        step_x = chart_w / max(1, max_len - 1)
        points = []
        for i, v in enumerate(series):
            x = pad_l + i * step_x
            if invert:
                n_v = (v - v_min) / (v_max - v_min)
                n_v = 1 - n_v  # 小值在顶
            else:
                n_v = (v - v_min) / (v_max - v_min)
            y = pad_t + n_v * chart_h
            points.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />'
        )
        # 末尾点
        lx, ly = points[-1].split(",")
        parts.append(
            f'<circle cx="{lx}" cy="{ly}" r="3" fill="{color}" stroke="#fff" stroke-width="1.5" />'
        )

    parts.append("</svg>")

    # 图例 (单独返回字符串, 邮件里加在 SVG 下方)
    legend_lines = []
    for i, (lab, s) in enumerate(zip(labels, series_list)):
        c = colors[i % len(colors)]
        legend_lines.append(
            f'<span style="display:inline-block;margin:2px 8px 2px 0;font-size:11px;color:#374151;">'
            f'<span style="display:inline-block;width:10px;height:10px;background:{c};'
            f'border-radius:2px;margin-right:4px;vertical-align:middle;"></span>'
            f'{_xml_escape((lab or "")[:24])}</span>'
        )
    return "".join(parts) + "".join(legend_lines)


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


if __name__ == "__main__":
    # 演示
    bar = bar_chart_svg(
        labels=["Cat Earphone Case", "Beaded Bracelet", "Kawaii Plush"],
        values=[8.99, 12.50, 6.99],
    )
    print("bar chart length:", len(bar))
    pie = pie_chart_svg(
        labels=["Amazon", "TikTok", "eBay", "Trends"],
        values=[5, 3, 1, 1],
    )
    print("pie chart length:", len(pie))
    multi = multi_line_svg(
        series_list=[
            [50, 30, 15, 8, 3],
            [40, 35, 25, 10, 5],
            [60, 50, 40, 30, 20],
        ],
        labels=["Cat Earphone", "Bracelet Set", "Plush Toy"],
        x_labels=["06-01", "06-02", "06-03", "06-04", "06-05"],
        invert=True,
        y_label="rank",
    )
    print("multi-line chart length:", len(multi))

