"""Tests for report_generator.py - Company Detail Pages"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from report_generator import ReportGenerator, CompanyMetrics
from holdings_tracker import CompanyHoldings, HoldingsUpdate, SharesUpdate


class TestBuildSecFilingUrl:
    """Tests for _build_sec_filing_url helper method."""

    def setup_method(self):
        self.gen = ReportGenerator()

    def test_valid_cik_and_accession(self):
        """Test URL generation with valid CIK and accession number."""
        url = self.gen._build_sec_filing_url("0001050446", "0001193125-26-032731")
        expected = "https://www.sec.gov/Archives/edgar/data/1050446/000119312526032731/0001193125-26-032731-index.htm"
        assert url == expected

    def test_cik_without_leading_zeros(self):
        """Test URL generation when CIK has no leading zeros."""
        url = self.gen._build_sec_filing_url("1050446", "0001193125-26-032731")
        expected = "https://www.sec.gov/Archives/edgar/data/1050446/000119312526032731/0001193125-26-032731-index.htm"
        assert url == expected

    def test_empty_cik_returns_none(self):
        """Test that empty CIK returns None."""
        url = self.gen._build_sec_filing_url("", "0001193125-26-032731")
        assert url is None

    def test_empty_accession_returns_none(self):
        """Test that empty accession number returns None."""
        url = self.gen._build_sec_filing_url("0001050446", "")
        assert url is None

    def test_none_cik_returns_none(self):
        """Test that None CIK returns None."""
        url = self.gen._build_sec_filing_url(None, "0001193125-26-032731")
        assert url is None

    def test_none_accession_returns_none(self):
        """Test that None accession number returns None."""
        url = self.gen._build_sec_filing_url("0001050446", None)
        assert url is None


class TestCalculateHistoryDeltas:
    """Tests for _calculate_history_deltas helper method."""

    def setup_method(self):
        self.gen = ReportGenerator()

    def test_single_entry_no_delta(self):
        """Test that single entry has no delta."""
        history = [{"date": "2026-01-01", "treasury_units": 100.0}]
        result = self.gen._calculate_history_deltas(history, "treasury_units")

        assert len(result) == 1
        assert "delta" not in result[0]
        assert "delta_percent" not in result[0]

    def test_two_entries_calculates_delta(self):
        """Test delta calculation with two entries."""
        history = [
            {"date": "2026-01-01", "treasury_units": 100.0},
            {"date": "2026-02-01", "treasury_units": 150.0},
        ]
        result = self.gen._calculate_history_deltas(history, "treasury_units")

        assert len(result) == 2
        assert "delta" not in result[0]  # First entry has no delta
        assert result[1]["delta"] == 50.0
        assert result[1]["delta_percent"] == 50.0

    def test_multiple_entries_sorted_by_date(self):
        """Test that entries are sorted by date before delta calculation."""
        history = [
            {"date": "2026-03-01", "treasury_units": 200.0},
            {"date": "2026-01-01", "treasury_units": 100.0},
            {"date": "2026-02-01", "treasury_units": 150.0},
        ]
        result = self.gen._calculate_history_deltas(history, "treasury_units")

        assert result[0]["date"] == "2026-01-01"
        assert result[1]["date"] == "2026-02-01"
        assert result[2]["date"] == "2026-03-01"

        assert result[1]["delta"] == 50.0  # 150 - 100
        assert result[2]["delta"] == 50.0  # 200 - 150

    def test_negative_delta(self):
        """Test negative delta when value decreases."""
        history = [
            {"date": "2026-01-01", "treasury_units": 200.0},
            {"date": "2026-02-01", "treasury_units": 150.0},
        ]
        result = self.gen._calculate_history_deltas(history, "treasury_units")

        assert result[1]["delta"] == -50.0
        assert result[1]["delta_percent"] == -25.0

    def test_empty_history(self):
        """Test empty history returns empty list."""
        result = self.gen._calculate_history_deltas([], "treasury_units")
        assert result == []

    def test_missing_value_key_skips_delta(self):
        """Test that missing value key doesn't cause error."""
        history = [
            {"date": "2026-01-01", "treasury_units": 100.0},
            {"date": "2026-02-01"},  # Missing treasury_units
        ]
        result = self.gen._calculate_history_deltas(history, "treasury_units")

        assert len(result) == 2
        assert "delta" not in result[1]


class TestGenerateCompanyDetailPage:
    """Tests for generate_company_detail_page method."""

    def setup_method(self):
        self.gen = ReportGenerator()

    def create_test_holdings(self):
        """Create test CompanyHoldings object."""
        holdings = CompanyHoldings(
            ticker="TEST",
            name="Test Company",
            primary_asset="BTC",
        )
        holdings.holdings_history = [
            HoldingsUpdate(
                date="2026-01-01",
                treasury_units=100.0,
                treasury_asset="BTC",
                source="8-K",
                accession_number="0001193125-26-000001",
            ),
            HoldingsUpdate(
                date="2026-02-01",
                treasury_units=150.0,
                treasury_asset="BTC",
                source="8-K",
                accession_number="0001193125-26-000002",
            ),
        ]
        holdings.shares_history = [
            SharesUpdate(
                date="2026-01-15",
                shares_outstanding=10000000,
                source="10-K",
                method="official",
            ),
        ]
        return holdings

    def create_test_metrics(self):
        """Create test CompanyMetrics object."""
        return CompanyMetrics(
            ticker="TEST",
            name="Test Company",
            primary_asset="BTC",
            treasury_units=150.0,
            shares_outstanding=10000000,
            mnav=1.5,
            nav_per_share=100.0,
        )

    def test_page_contains_ticker_and_name(self):
        """Test that page contains company ticker and name."""
        holdings = self.create_test_holdings()
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "0001234567", 50000.0)

        assert "TEST" in html
        assert "Test Company" in html

    def test_page_contains_back_link(self):
        """Test that page contains back link to dashboard."""
        holdings = self.create_test_holdings()
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "0001234567", 50000.0)

        assert "Back to Dashboard" in html
        assert "../dat_report_" in html

    def test_page_contains_summary_cards(self):
        """Test that page contains summary cards with values."""
        holdings = self.create_test_holdings()
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "0001234567", 50000.0)

        assert "Treasury Holdings" in html
        assert "Treasury Value" in html
        assert "Shares Outstanding" in html
        assert "mNAV" in html
        assert "1.50x" in html  # mNAV value

    def test_page_contains_treasury_history_table(self):
        """Test that page contains treasury history table."""
        holdings = self.create_test_holdings()
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "0001234567", 50000.0)

        assert "Treasury History" in html
        assert "2026-01-01" in html
        assert "2026-02-01" in html
        assert "100.0000" in html
        assert "150.0000" in html

    def test_page_contains_sec_links(self):
        """Test that page contains SEC filing links."""
        holdings = self.create_test_holdings()
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "1234567", 50000.0)

        assert "sec.gov/Archives/edgar/data" in html
        assert 'target="_blank"' in html

    def test_page_contains_shares_history_table(self):
        """Test that page contains shares history table."""
        holdings = self.create_test_holdings()
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "0001234567", 50000.0)

        assert "Shares Outstanding History" in html
        assert "10,000,000" in html
        assert "official" in html

    def test_page_with_empty_shares_history(self):
        """Test page generation when no shares history exists."""
        holdings = self.create_test_holdings()
        holdings.shares_history = []
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "0001234567", 50000.0)

        assert "No shares history available" in html

    def test_page_with_other_holdings(self):
        """Test page generation with other holdings."""
        holdings = self.create_test_holdings()
        holdings.other_holdings = [
            {
                "type": "private_equity",
                "name": "Test Investment",
                "value_usd": 50000000,
                "date": "2026-01-01",
                "notes": "Test notes",
            }
        ]
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "0001234567", 50000.0)

        assert "Other Holdings" in html
        assert "private_equity" in html
        assert "Test Investment" in html
        assert "$50,000,000" in html

    def test_page_without_other_holdings(self):
        """Test that Other Holdings section is omitted when empty."""
        holdings = self.create_test_holdings()
        holdings.other_holdings = []
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "0001234567", 50000.0)

        # Should not contain Other Holdings section
        assert "Other Holdings" not in html

    def test_delta_displayed_correctly(self):
        """Test that delta values are displayed in treasury history."""
        holdings = self.create_test_holdings()
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "0001234567", 50000.0)

        # First entry should have "--" for delta
        assert "--" in html
        # Second entry should have +50 delta
        assert "+50.0000" in html
        assert "+50.00%" in html

    def test_missing_cik_no_sec_links(self):
        """Test that missing CIK results in no SEC links."""
        holdings = self.create_test_holdings()
        metrics = self.create_test_metrics()

        html = self.gen.generate_company_detail_page(holdings, metrics, "", 50000.0)

        # Should have source text but not as a link
        assert "8-K" in html
        assert "sec.gov" not in html


class TestGenerateHtmlClickableTickers:
    """Tests for clickable ticker links in main report."""

    def setup_method(self):
        self.gen = ReportGenerator()

    def test_ticker_links_generated(self):
        """Test that ticker cells contain links to company pages."""
        metrics = [
            CompanyMetrics(
                ticker="MSTR",
                name="Strategy Inc",
                primary_asset="BTC",
                stock_price=200.0,
                treasury_units=500000.0,
                shares_outstanding=180000000,
                crypto_price=50000.0,
                market_cap=36000000000.0,
                mnav=1.5,
            )
        ]

        html = self.gen.generate_html(metrics, {"BTC": 50000.0})

        assert 'href="companies/mstr.html"' in html
        assert ">MSTR</a>" in html

    def test_ticker_link_lowercase(self):
        """Test that ticker links use lowercase filenames."""
        metrics = [
            CompanyMetrics(
                ticker="BTBT",
                name="Bit Digital",
                primary_asset="ETH",
                stock_price=5.0,
                treasury_units=150000.0,
                shares_outstanding=50000000,
                crypto_price=2000.0,
                market_cap=250000000.0,
                mnav=0.8,
            )
        ]

        html = self.gen.generate_html(metrics, {"ETH": 2000.0})

        assert 'href="companies/btbt.html"' in html
        assert 'href="companies/BTBT.html"' not in html
