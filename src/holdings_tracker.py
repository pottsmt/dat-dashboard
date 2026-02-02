"""
Tracks treasury holdings and shares outstanding with estimation logic.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date
from dataclasses import dataclass, asdict, field


@dataclass
class HoldingsUpdate:
    """A single holdings update record."""
    date: str  # ISO format date
    treasury_units: float
    treasury_asset: str
    source: str  # "8-K", "10-Q", "10-K", "press_release", "manual"
    accession_number: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class SharesUpdate:
    """A single shares outstanding update record."""
    date: str  # ISO format date
    shares_outstanding: float
    source: str  # "10-Q", "10-K", "estimated", "bloomberg"
    method: Optional[str] = None  # "official", "vwap_estimate"
    accession_number: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class CompanyHoldings:
    """Complete holdings record for a company."""
    ticker: str
    name: str
    primary_asset: str
    holdings_history: List[HoldingsUpdate] = field(default_factory=list)
    shares_history: List[SharesUpdate] = field(default_factory=list)
    last_updated: Optional[str] = None

    @property
    def current_holdings(self) -> Optional[HoldingsUpdate]:
        """Get most recent holdings update."""
        if not self.holdings_history:
            return None
        return self.holdings_history[-1]

    @property
    def current_shares(self) -> Optional[SharesUpdate]:
        """Get most recent shares update."""
        if not self.shares_history:
            return None
        return self.shares_history[-1]

    def add_holdings_update(self, update: HoldingsUpdate):
        """Add a holdings update, maintaining chronological order."""
        self.holdings_history.append(update)
        self.holdings_history.sort(key=lambda x: x.date)
        self.last_updated = datetime.now().isoformat()

    def add_shares_update(self, update: SharesUpdate):
        """Add a shares update, maintaining chronological order."""
        self.shares_history.append(update)
        self.shares_history.sort(key=lambda x: x.date)
        self.last_updated = datetime.now().isoformat()


class HoldingsTracker:
    """
    Tracks treasury holdings and estimates shares outstanding.
    """

    def __init__(self, data_dir: Path):
        """
        Initialize tracker.

        Args:
            data_dir: Directory for storing holdings data
        """
        self.data_dir = Path(data_dir)
        self.holdings_file = self.data_dir / "holdings.json"
        self.holdings: Dict[str, CompanyHoldings] = {}
        self._load()

    def _load(self):
        """Load holdings data from disk."""
        if self.holdings_file.exists():
            with open(self.holdings_file, "r") as f:
                data = json.load(f)
                for ticker, company_data in data.get("companies", {}).items():
                    holdings_history = [
                        HoldingsUpdate(**h) for h in company_data.get("holdings_history", [])
                    ]
                    shares_history = [
                        SharesUpdate(**s) for s in company_data.get("shares_history", [])
                    ]
                    self.holdings[ticker] = CompanyHoldings(
                        ticker=ticker,
                        name=company_data.get("name", ""),
                        primary_asset=company_data.get("primary_asset", "UNKNOWN"),
                        holdings_history=holdings_history,
                        shares_history=shares_history,
                        last_updated=company_data.get("last_updated"),
                    )

    def _save(self):
        """Save holdings data to disk."""
        data = {"companies": {}}
        for ticker, company in self.holdings.items():
            data["companies"][ticker] = {
                "ticker": company.ticker,
                "name": company.name,
                "primary_asset": company.primary_asset,
                "holdings_history": [asdict(h) for h in company.holdings_history],
                "shares_history": [asdict(s) for s in company.shares_history],
                "last_updated": company.last_updated,
            }

        self.holdings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.holdings_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_company(self, ticker: str) -> Optional[CompanyHoldings]:
        """Get holdings for a company."""
        return self.holdings.get(ticker.upper())

    def init_company(self, ticker: str, name: str, primary_asset: str) -> CompanyHoldings:
        """Initialize or update company record."""
        ticker = ticker.upper()
        if ticker in self.holdings:
            company = self.holdings[ticker]
            company.name = name
            company.primary_asset = primary_asset
        else:
            company = CompanyHoldings(
                ticker=ticker,
                name=name,
                primary_asset=primary_asset,
            )
            self.holdings[ticker] = company
        self._save()
        return company

    def update_holdings(
        self,
        ticker: str,
        units: float,
        asset: str,
        update_date: date,
        source: str,
        accession_number: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        """
        Record a treasury holdings update.

        Args:
            ticker: Company ticker
            units: Number of units held (e.g., BTC count)
            asset: Asset type (BTC, ETH, etc.)
            update_date: Date of the update
            source: Source of info (8-K, 10-Q, etc.)
            accession_number: SEC accession number if applicable
            notes: Optional notes
        """
        ticker = ticker.upper()
        if ticker not in self.holdings:
            self.init_company(ticker, "", asset)

        update = HoldingsUpdate(
            date=update_date.isoformat(),
            treasury_units=units,
            treasury_asset=asset,
            source=source,
            accession_number=accession_number,
            notes=notes,
        )
        self.holdings[ticker].add_holdings_update(update)
        self._save()

    def update_shares(
        self,
        ticker: str,
        shares: float,
        update_date: date,
        source: str,
        method: str = "official",
        accession_number: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        """
        Record a shares outstanding update.

        Args:
            ticker: Company ticker
            shares: Number of shares outstanding
            update_date: Date of the update
            source: Source of info (10-Q, 10-K, bloomberg, estimated)
            method: "official" or "vwap_estimate"
            accession_number: SEC accession number if applicable
            notes: Optional notes
        """
        ticker = ticker.upper()
        if ticker not in self.holdings:
            self.init_company(ticker, "", "UNKNOWN")

        update = SharesUpdate(
            date=update_date.isoformat(),
            shares_outstanding=shares,
            source=source,
            method=method,
            accession_number=accession_number,
            notes=notes,
        )
        self.holdings[ticker].add_shares_update(update)
        self._save()

    def estimate_shares_from_treasury_change(
        self,
        ticker: str,
        crypto_vwap: float,
        stock_vwap: float,
    ) -> Optional[Tuple[float, str]]:
        """
        Estimate new shares issued based on treasury change.

        When treasury holdings increase but no shares update is available,
        estimate shares issued using:
        - Delta in treasury units
        - Crypto VWAP over the period
        - Stock VWAP over the period

        Formula: (delta_units * crypto_vwap) / stock_vwap = estimated_new_shares

        Args:
            ticker: Company ticker
            crypto_vwap: VWAP of the crypto asset over the period
            stock_vwap: VWAP of the stock over the period

        Returns:
            Tuple of (estimated_total_shares, notes) or None if can't estimate
        """
        ticker = ticker.upper()
        company = self.holdings.get(ticker)
        if not company:
            return None

        holdings = company.holdings_history
        shares = company.shares_history

        if len(holdings) < 2:
            return None
        if not shares:
            return None

        # Get the two most recent holdings updates
        prev_holdings = holdings[-2]
        curr_holdings = holdings[-1]

        # Calculate delta in units
        delta_units = curr_holdings.treasury_units - prev_holdings.treasury_units

        if delta_units <= 0:
            # No increase in holdings, no dilution estimate needed
            return None

        # Get last known official shares
        last_shares = shares[-1].shares_outstanding

        # Estimate cost of new crypto
        cost_of_new_crypto = delta_units * crypto_vwap

        # Estimate shares issued
        estimated_new_shares = cost_of_new_crypto / stock_vwap

        # Total estimated shares
        estimated_total = last_shares + estimated_new_shares

        notes = (
            f"Estimated: {delta_units:.4f} units added "
            f"@ ${crypto_vwap:,.2f} crypto VWAP = ${cost_of_new_crypto:,.0f}. "
            f"Stock VWAP ${stock_vwap:.2f} -> ~{estimated_new_shares:,.0f} new shares"
        )

        return (estimated_total, notes)

    def get_current_data(self, ticker: str) -> Optional[Dict]:
        """
        Get current holdings and shares for a company.

        Returns:
            Dict with current_holdings, current_shares, or None
        """
        company = self.holdings.get(ticker.upper())
        if not company:
            return None

        result = {
            "ticker": company.ticker,
            "name": company.name,
            "primary_asset": company.primary_asset,
        }

        if company.current_holdings:
            result["treasury_units"] = company.current_holdings.treasury_units
            result["treasury_date"] = company.current_holdings.date
            result["treasury_source"] = company.current_holdings.source

        if company.current_shares:
            result["shares_outstanding"] = company.current_shares.shares_outstanding
            result["shares_date"] = company.current_shares.date
            result["shares_source"] = company.current_shares.source
            result["shares_method"] = company.current_shares.method

        return result
