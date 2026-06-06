"""测试 exporters 模块 (CSV / PDF 导出)."""
from __future__ import annotations

import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import pytest

from src.exporters import export_csv, csv_bytes, export_pdf, CSV_FIELDS, _has_fpdf
from src.ranker import RankedItem


# ================= Fixtures =================

def _make_item(**overrides) -> RankedItem:
    defaults = dict(
        title="Cute Cat Earphone Case", price_usd=8.99,
        url="https://amazon.com/dp/B0A", image_url="",
        source="amazon", category="Phone Accessories",
        rank_today=1, rank_yesterday=50, rank_change=49,
        is_new=False, asin="B0A",
        selling_point="925 silver needle, hypoallergenic",
        badges=["🔥 HOT", "⚡ FLASH"],
    )
    defaults.update(overrides)
    return RankedItem(**defaults)


@pytest.fixture
def sample_items():
    return [
        _make_item(),
        _make_item(
            title="Beaded Bracelet Set", price_usd=12.50,
            source="tiktok", category="Jewelry",
            rank_today=2, rank_yesterday=None, rank_change=50,
            is_new=True, asin="B0B",
            selling_point="natural stone, multi-layer",
            badges=["🚀 LAUNCH"],
        ),
    ]


@pytest.fixture
def empty_items():
    return []


# ================= CSV Tests =================

class TestCSVExport:

    def test_csv_has_bom(self, sample_items):
        """CSV starts with UTF-8 BOM (Excel-friendly)."""
        data = csv_bytes(sample_items, "2026-06-05")
        assert data[:3] == b'\xef\xbb\xbf'

    def test_csv_fields_match_header(self, sample_items):
        """CSV header row matches CSV_FIELDS constant."""
        text = export_csv(sample_items, "2026-06-05")
        # strip BOM
        lines = text.lstrip('\ufeff').splitlines()
        header = [h.strip() for h in lines[0].split(",")]
        assert header == CSV_FIELDS

    def test_csv_row_count(self, sample_items):
        """CSV has header + N data rows."""
        text = export_csv(sample_items, "2026-06-05")
        lines = text.lstrip('\ufeff').splitlines()
        assert len(lines) == 3  # header + 2 items

    def test_csv_rank_change_positive(self, sample_items):
        """Rank change is prefixed with + when positive."""
        text = export_csv(sample_items, "2026-06-05")
        assert "+49" in text
        assert "+50" in text

    def test_csv_new_item_flag(self, sample_items):
        """New items show YES in is_new column."""
        text = export_csv(sample_items, "2026-06-05")
        lines = text.lstrip('\ufeff').splitlines()
        # second data row is the new item
        row2 = lines[2]
        assert "YES" in row2

    def test_csv_price_format(self, sample_items):
        """Prices are formatted as X.XX."""
        text = export_csv(sample_items, "2026-06-05")
        assert "8.99" in text
        assert "12.50" in text

    def test_csv_badges_joined(self, sample_items):
        """Badges joined with ' | '."""
        text = export_csv(sample_items, "2026-06-05")
        assert "🔥 HOT | ⚡ FLASH" in text

    def test_csv_bytes_encoding(self, sample_items):
        """csv_bytes returns UTF-8 encoded bytes."""
        data = csv_bytes(sample_items, "2026-06-05")
        assert isinstance(data, bytes)
        decoded = data.decode("utf-8")
        assert "Cute Cat" in decoded

    def test_csv_empty_items(self, empty_items):
        """Empty list produces header-only CSV."""
        text = export_csv(empty_items, "2026-06-05")
        lines = text.lstrip('\ufeff').splitlines()
        assert len(lines) == 1

    def test_csv_parser_roundtrip(self, sample_items):
        """Can parse CSV back with stdlib csv reader."""
        data = csv_bytes(sample_items, "2026-06-05")
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["title"] == "Cute Cat Earphone Case"
        assert rows[1]["is_new"] == "YES"
        assert rows[1]["badges"] == "🚀 LAUNCH"

    def test_csv_date_in_filename(self, sample_items):
        """Date string is available for filename construction."""
        date = "2026-06-05"
        data = csv_bytes(sample_items, date)
        assert len(data) > 0
        # caller would use: f"trending_{date}.csv"


# ================= PDF Tests =================

class TestPDFExport:

    def test_has_fpdf_returns_bool(self):
        """_has_fpdf returns a boolean."""
        assert isinstance(_has_fpdf(), bool)

    def test_pdf_none_when_no_fpdf(self, sample_items):
        """If fpdf2 not installed, returns None (not an error)."""
        result = export_pdf(sample_items, "2026-06-05")
        if not _has_fpdf():
            assert result is None
        else:
            assert isinstance(result, bytes)

    def test_pdf_bytes_when_fpdf_installed(self, sample_items):
        """If fpdf2 installed, returns valid PDF bytes."""
        if not _has_fpdf():
            pytest.skip("fpdf2 not installed")
        result = export_pdf(sample_items, "2026-06-05")
        assert result is not None
        assert result[:4] == b'%PDF'

    def test_pdf_contains_title(self, sample_items):
        """PDF contains the report title."""
        if not _has_fpdf():
            pytest.skip("fpdf2 not installed")
        result = export_pdf(sample_items, "2026-06-05", title="My Report")
        assert b'My Report' in result

    def test_pdf_contains_date(self, sample_items):
        """PDF contains the date string."""
        if not _has_fpdf():
            pytest.skip("fpdf2 not installed")
        result = export_pdf(sample_items, "2026-06-05")
        assert b'2026-06-05' in result

    def test_pdf_contains_product_title(self, sample_items):
        """PDF contains at least one product title."""
        if not _has_fpdf():
            pytest.skip("fpdf2 not installed")
        result = export_pdf(sample_items, "2026-06-05")
        assert b'Cute Cat' in result

    def test_pdf_contains_badges(self, sample_items):
        """PDF contains badge text."""
        if not _has_fpdf():
            pytest.skip("fpdf2 not installed")
        result = export_pdf(sample_items, "2026-06-05")
        assert b'HOT' in result or b'FLASH' in result

    def test_pdf_contains_legend(self, sample_items):
        """PDF contains badge legend section."""
        if not _has_fpdf():
            pytest.skip("fpdf2 not installed")
        result = export_pdf(sample_items, "2026-06-05")
        assert b'Badge Legend' in result

    def test_pdf_empty_items(self, empty_items):
        """Empty list still produces a valid PDF."""
        if not _has_fpdf():
            pytest.skip("fpdf2 not installed")
        result = export_pdf(empty_items, "2026-06-05")
        assert result is not None
        assert result[:4] == b'%PDF'

    def test_pdf_filesize_sane(self, sample_items):
        """PDF is between 1KB and 500KB (sanity check)."""
        if not _has_fpdf():
            pytest.skip("fpdf2 not installed")
        result = export_pdf(sample_items, "2026-06-05")
        assert 1000 < len(result) < 500_000
