"""
Reader for Bloomberg Excel CSV exports.
"""

import csv
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class StockData:
    """Stock data from Bloomberg export."""
    ticker: str
    price: Optional[float] = None
    volume: Optional[float] = None
    avg_volume_30d: Optional[float] = None
    shares_outstanding: Optional[float] = None  # in millions from Bloomberg
    market_cap: Optional[float] = None  # in millions from Bloomberg
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    enterprise_value: Optional[float] = None
    vwap: Optional[float] = None
    price_3d_ago: Optional[float] = None
    price_7d_ago: Optional[float] = None
    price_30d_ago: Optional[float] = None
    export_timestamp: Optional[datetime] = None

    @property
    def shares_outstanding_actual(self) -> Optional[float]:
        """Get actual shares outstanding (Bloomberg reports in millions)."""
        if self.shares_outstanding is not None:
            return self.shares_outstanding * 1_000_000
        return None

    @property
    def market_cap_actual(self) -> Optional[float]:
        """Get actual market cap (Bloomberg reports in millions)."""
        if self.market_cap is not None:
            return self.market_cap * 1_000_000
        return None

    @property
    def enterprise_value_actual(self) -> Optional[float]:
        """Get actual enterprise value (Bloomberg reports in millions)."""
        if self.enterprise_value is not None:
            return self.enterprise_value * 1_000_000
        return None

    def get_performance(self, days: int) -> Optional[float]:
        """
        Calculate stock performance over N days.

        Args:
            days: 3, 7, or 30

        Returns:
            Percentage change or None
        """
        price_map = {
            3: self.price_3d_ago,
            7: self.price_7d_ago,
            30: self.price_30d_ago,
        }
        old_price = price_map.get(days)
        if old_price is None or self.price is None or old_price == 0:
            return None
        return ((self.price - old_price) / old_price) * 100


class BloombergReader:
    """Reads and parses Bloomberg CSV exports."""

    # Expected column headers - order matters for matching
    # More specific patterns should come before general ones
    COLUMN_MAP = [
        ("price_30d_ago", "price_30d_ago"),
        ("price_7d_ago", "price_7d_ago"),
        ("price_3d_ago", "price_3d_ago"),
        ("avg_vol_30d", "avg_volume_30d"),
        ("enterprise_value", "enterprise_value"),
        ("shares_out", "shares_outstanding"),
        ("market_cap", "market_cap"),
        ("total_debt", "total_debt"),
        ("ticker", "ticker"),
        ("price", "price"),
        ("volume", "volume"),
        ("cash", "cash"),
        ("vwap", "vwap"),
    ]

    def __init__(self, export_path: Path):
        """
        Initialize reader.

        Args:
            export_path: Path to Bloomberg CSV export file
        """
        self.export_path = Path(export_path)

    def _parse_float(self, value: str) -> Optional[float]:
        """Parse string to float, handling Bloomberg error values."""
        if not value or value.strip() == "":
            return None
        value = value.strip()
        # Bloomberg error values
        if value in ["#N/A", "#N/A N/A", "N/A", "#VALUE!", "#REF!", "-"]:
            return None
        try:
            # Remove commas from numbers
            value = value.replace(",", "")
            return float(value)
        except ValueError:
            return None

    def _normalize_header(self, header: str) -> str:
        """Normalize column header for matching."""
        return header.lower().strip().replace(" ", "_")

    def read(self) -> List[StockData]:
        """
        Read and parse Bloomberg CSV export.

        Returns:
            List of StockData objects

        Raises:
            FileNotFoundError: If export file doesn't exist
        """
        if not self.export_path.exists():
            raise FileNotFoundError(f"Bloomberg export not found: {self.export_path}")

        export_time = datetime.fromtimestamp(self.export_path.stat().st_mtime)
        results = []

        with open(self.export_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            # Build column name mapping
            col_mapping = {}
            for csv_col in reader.fieldnames or []:
                normalized = self._normalize_header(csv_col)
                for key, attr in self.COLUMN_MAP:
                    # Use exact match or check if normalized equals key
                    if normalized == key or normalized.replace("_", "") == key.replace("_", ""):
                        col_mapping[csv_col] = attr
                        break

            for row in reader:
                # Skip empty rows
                ticker_col = next((c for c in row.keys() if "ticker" in c.lower()), None)
                if not ticker_col or not row.get(ticker_col):
                    continue

                data = StockData(
                    ticker=row[ticker_col].strip().upper(),
                    export_timestamp=export_time,
                )

                # Map columns to StockData attributes
                for csv_col, attr in col_mapping.items():
                    if attr == "ticker":
                        continue
                    value = self._parse_float(row.get(csv_col, ""))
                    setattr(data, attr, value)

                results.append(data)

        return results

    def read_as_dict(self) -> Dict[str, StockData]:
        """
        Read Bloomberg export and return as dict keyed by ticker.

        Returns:
            Dict mapping ticker to StockData
        """
        data_list = self.read()
        return {d.ticker: d for d in data_list}

    def get_stock(self, ticker: str) -> Optional[StockData]:
        """
        Get data for a specific ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            StockData or None if not found
        """
        data_dict = self.read_as_dict()
        return data_dict.get(ticker.upper())
