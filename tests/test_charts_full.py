"""单元测试: 综合图表 (bar / pie / multi-line)."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.charts import bar_chart_svg, multi_line_svg, pie_chart_svg  # noqa: E402


class TestBarChart:
    def test_basic(self):
        svg = bar_chart_svg(
            labels=["A", "B", "C"],
            values=[10.0, 5.0, 7.5],
        )
        assert "<svg" in svg
        assert "<rect" in svg
        assert "</svg>" in svg
        # 3 根条 -> 3 个 rect
        assert svg.count("<rect") == 3

    def test_label_escaped(self):
        svg = bar_chart_svg(
            labels=['<script>alert(1)</script>'],
            values=[1.0],
        )
        assert "<script>" not in svg
        assert "&lt;script&gt;" in svg

    def test_value_format(self):
        svg = bar_chart_svg(["A"], [12.5], value_fmt="${:.2f}")
        assert "$12.50" in svg

    def test_empty(self):
        assert bar_chart_svg([], []) == ""
        assert bar_chart_svg(["A"], []) == ""

    def test_mismatched_length(self):
        assert bar_chart_svg(["A", "B"], [1.0]) == ""

    def test_max_value_overrides(self):
        svg = bar_chart_svg(["A"], [50.0], max_value=100.0)
        # 50/100 = 0.5 比例, 仍然会画
        assert "<rect" in svg


class TestPieChart:
    def test_basic(self):
        svg = pie_chart_svg(
            labels=["A", "B", "C"],
            values=[3, 2, 1],
        )
        assert "<svg" in svg
        assert "<path" in svg
        assert "</svg>" in svg
        # 3 段扇形
        assert svg.count("<path") == 3
        # 中心白圆
        assert "<circle" in svg
        # 图例
        assert "A" in svg or "A &amp;" in svg or "33%" in svg

    def test_label_pct_in_legend(self):
        svg = pie_chart_svg(["Only"], [10])
        assert "100%" in svg

    def test_empty(self):
        assert pie_chart_svg([], []) == ""
        assert pie_chart_svg(["A"], [0]) == ""
        # 0 总和
        assert pie_chart_svg(["A", "B"], [0, 0]) == ""

    def test_mismatched_length(self):
        assert pie_chart_svg(["A", "B"], [1]) == ""

    def test_skip_zero_slices(self):
        svg = pie_chart_svg(["A", "B", "C"], [1, 0, 2])
        # B 是 0, 不应被画成 path
        assert svg.count("<path") == 2

    def test_donut_center_text(self):
        svg = pie_chart_svg(["A", "B"], [3, 2])
        assert "Total" in svg
        assert "5" in svg  # 总数


class TestMultiLine:
    def test_basic(self):
        svg = multi_line_svg(
            series_list=[[1, 2, 3], [3, 2, 1]],
            labels=["A", "B"],
            x_labels=["d1", "d2", "d3"],
        )
        assert "<svg" in svg
        # 2 条折线
        assert svg.count("<polyline") == 2
        # 末尾点 (2 个)
        assert svg.count("<circle") >= 2
        # 图例
        assert "A" in svg or "A &" in svg

    def test_invert(self):
        # invert=True 时, 排名 1 在顶部
        s1 = multi_line_svg([[1, 2, 3]], ["A"], invert=True)
        s2 = multi_line_svg([[1, 2, 3]], ["A"], invert=False)
        # 两种情况下 y 坐标不同, SVG 字符串不同
        assert s1 != s2

    def test_x_labels(self):
        svg = multi_line_svg(
            series_list=[[1, 2, 3]],
            labels=["A"],
            x_labels=["Jan", "Feb", "Mar"],
        )
        # 至少有一个 x 轴标签
        assert "Jan" in svg or "Feb" in svg or "Mar" in svg

    def test_empty(self):
        assert multi_line_svg([], []) == ""
        assert multi_line_svg([[]], ["A"]) == ""  # 单点
        assert multi_line_svg([[1]], ["A"]) == ""  # 单点

    def test_filter_flat_series(self):
        # 序列没变化 (所有值一样) 仍然能画, 因为 sparkline 允许
        svg = multi_line_svg(
            series_list=[[1, 1, 1], [1, 2, 3]],
            labels=["Flat", "Rising"],
        )
        assert "<polyline" in svg

    def test_y_label(self):
        svg = multi_line_svg(
            series_list=[[1, 2]],
            labels=["A"],
            y_label="price",
        )
        assert "price" in svg

    def test_label_escaped(self):
        svg = multi_line_svg(
            series_list=[[1, 2, 3]],
            labels=['<bad>&"x'],
        )
        assert "<bad>" not in svg
        assert "&lt;bad&gt;" in svg
