"""
DAT Dashboard - Main orchestrator for daily report generation.
"""

import argparse
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from dotenv import load_dotenv

from .bloomberg_reader import BloombergReader, StockData
from .coingecko_client import CoinGeckoClient
from .edgar_client import EdgarClient
from .filing_analyzer import FilingAnalyzer
from .holdings_tracker import HoldingsTracker
from .report_generator import ReportGenerator, CompanyMetrics
from .email_sender import EmailSender


class DATDashboard:
    """Main orchestrator for DAT Dashboard."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize dashboard.

        Args:
            config_path: Path to config.yaml (default: config/config.yaml)
        """
        load_dotenv()

        self.base_dir = Path(__file__).parent.parent
        self.config_path = config_path or self.base_dir / "config" / "config.yaml"
        self.config = self._load_config()
        self.companies = self._load_companies()

        # Initialize components
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(exist_ok=True)

        # Bloomberg reader
        bloomberg_path = self._resolve_path(self.config["bloomberg"]["export_path"])
        self.bloomberg = BloombergReader(bloomberg_path)

        # CoinGecko client
        self.coingecko = CoinGeckoClient(
            api_key=self.config["coingecko"].get("api_key") or None
        )

        # EDGAR client
        self.edgar = EdgarClient(
            user_agent=self.config["edgar"]["user_agent"],
            data_dir=self.data_dir,
        )

        # Filing analyzer (only if Anthropic key available)
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key and self.config.get("anthropic", {}).get("enabled"):
            self.analyzer = FilingAnalyzer(
                api_key=anthropic_key,
                model=self.config["anthropic"].get("model", "claude-sonnet-4-20250514"),
                output_dir=self.data_dir / "analysis",
            )
        else:
            self.analyzer = None

        # Holdings tracker
        self.tracker = HoldingsTracker(self.data_dir / "history")

        # Report generator
        self.report_gen = ReportGenerator()

        # Email sender (only if configured)
        if self.config["email"]["enabled"]:
            self.email = EmailSender(
                smtp_server=self.config["email"]["smtp_server"],
                smtp_port=self.config["email"]["smtp_port"],
                sender_email=self._resolve_env(self.config["email"]["sender_email"]),
                sender_password=self._resolve_env(self.config["email"]["sender_password"]),
                recipient_email=self._resolve_env(self.config["email"]["recipient_email"]),
            )
        else:
            self.email = None

    def _load_config(self) -> Dict:
        """Load configuration from YAML."""
        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)

    def _load_companies(self) -> Dict:
        """Load companies configuration."""
        companies_path = self.base_dir / "config" / "companies.json"
        with open(companies_path, "r") as f:
            return json.load(f)

    def _resolve_env(self, value: str) -> str:
        """Resolve environment variable references."""
        if value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            return os.getenv(env_var, "")
        return value

    def _resolve_path(self, path: str) -> Path:
        """Resolve path with environment variables."""
        resolved = os.path.expandvars(path)
        resolved = os.path.expanduser(resolved)
        if not os.path.isabs(resolved):
            resolved = self.base_dir / resolved
        return Path(resolved)

    def _get_asset_coingecko_id(self, asset: str) -> Optional[str]:
        """Get CoinGecko ID for an asset."""
        assets = self.companies.get("assets", {})
        return assets.get(asset, {}).get("coingecko_id")

    def run_daily_report(self) -> bool:
        """Run daily report generation.

        Returns:
            True if report generated and sent successfully
        """
        print(f"Starting DAT Dashboard report generation at {datetime.now()}")

        # Step 1: Load Bloomberg data
        print("\n1. Loading Bloomberg data...")
        try:
            stock_data = self.bloomberg.read_as_dict()
            print(f"   Loaded data for {len(stock_data)} tickers")
        except FileNotFoundError as e:
            print(f"   ERROR: Bloomberg export not found: {e}")
            print("   Please ensure Bloomberg Excel has exported data.")
            return False

        # Step 2: Get unique assets and fetch crypto prices
        print("\n2. Fetching crypto prices...")
        unique_assets = set()
        for company in self.companies["companies"]:
            asset = company.get("primary_asset")
            if asset and asset != "UNKNOWN":
                unique_assets.add(asset)

        coingecko_ids = []
        asset_to_id = {}
        for asset in unique_assets:
            cg_id = self._get_asset_coingecko_id(asset)
            if cg_id:
                coingecko_ids.append(cg_id)
                asset_to_id[asset] = cg_id

        crypto_prices = {}
        if coingecko_ids:
            prices = self.coingecko.get_current_prices(coingecko_ids)
            for asset, cg_id in asset_to_id.items():
                if cg_id in prices:
                    crypto_prices[asset] = prices[cg_id]
                    print(f"   {asset}: ${prices[cg_id]:,.2f}")

        # Step 3: Get crypto performance data
        print("\n3. Fetching crypto performance...")
        crypto_perf = {}
        for asset, cg_id in asset_to_id.items():
            try:
                perf_3d = self.coingecko.get_performance(cg_id, 3)
                perf_7d = self.coingecko.get_performance(cg_id, 7)
                perf_30d = self.coingecko.get_performance(cg_id, 30)
                crypto_perf[asset] = {
                    "3d": perf_3d,
                    "7d": perf_7d,
                    "30d": perf_30d,
                }
                print(f"   {asset}: 7D {perf_7d:+.2f}%, 30D {perf_30d:+.2f}%")
            except Exception as e:
                print(f"   Error getting {asset} performance: {e}")

        # Step 4: Build metrics for each company
        print("\n4. Building company metrics...")
        metrics_list = []

        for company in self.companies["companies"]:
            ticker = company["ticker"]
            stock = stock_data.get(ticker)

            if not stock:
                print(f"   {ticker}: No Bloomberg data, skipping")
                continue

            # Get holdings from tracker
            holdings = self.tracker.get_current_data(ticker)

            # Build metrics
            m = CompanyMetrics(
                ticker=ticker,
                name=company.get("name", "Unknown"),
                primary_asset=company.get("primary_asset", "UNKNOWN"),
            )

            # Stock data from Bloomberg
            m.stock_price = stock.price
            m.volume = stock.volume
            m.avg_volume_30d = stock.avg_volume_30d
            m.market_cap = stock.market_cap_actual
            m.total_debt = stock.total_debt
            m.cash = stock.cash
            m.enterprise_value = stock.enterprise_value_actual

            # Shares - prefer tracker data if available, else Bloomberg
            if holdings and holdings.get("shares_outstanding"):
                m.shares_outstanding = holdings["shares_outstanding"]
                m.shares_source = holdings.get("shares_method", "official")
            elif stock.shares_outstanding_actual:
                m.shares_outstanding = stock.shares_outstanding_actual
                m.shares_source = "bloomberg"

            # Treasury data from tracker
            if holdings and holdings.get("treasury_units"):
                m.treasury_units = holdings["treasury_units"]
                m.treasury_date = holdings.get("treasury_date")
                m.treasury_source = holdings.get("treasury_source")

            # Crypto price
            asset = m.primary_asset
            if asset in crypto_prices:
                m.crypto_price = crypto_prices[asset]

            # Performance
            m.stock_perf_3d = stock.get_performance(3)
            m.stock_perf_7d = stock.get_performance(7)
            m.stock_perf_30d = stock.get_performance(30)

            if asset in crypto_perf:
                m.crypto_perf_3d = crypto_perf[asset].get("3d")
                m.crypto_perf_7d = crypto_perf[asset].get("7d")
                m.crypto_perf_30d = crypto_perf[asset].get("30d")

            # Calculate derived metrics
            m.calculate_derived_metrics()

            metrics_list.append(m)
            print(f"   {ticker}: mNAV={m.mnav:.2f}x" if m.mnav else f"   {ticker}: No NAV data")

        # Step 5: Generate report
        print("\n5. Generating report...")
        html_report = self.report_gen.generate_html(metrics_list, crypto_prices)
        text_report = self.report_gen.generate_plain_text(metrics_list, crypto_prices)

        # Save reports
        reports_dir = self.data_dir / "reports"
        reports_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")

        html_path = reports_dir / f"dat_report_{date_str}.html"
        text_path = reports_dir / f"dat_report_{date_str}.txt"

        html_path.write_text(html_report)
        text_path.write_text(text_report)
        print(f"   Saved: {html_path}")
        print(f"   Saved: {text_path}")

        # Step 6: Send email
        if self.email:
            print("\n6. Sending email report...")
            success = self.email.send_report(html_report, text_report)
            if success:
                print("   Email sent successfully!")
            else:
                print("   Email sending failed")
                return False
        else:
            print("\n6. Email not configured, skipping")

        print("\nReport generation complete!")
        return True

    def scan_filings(self, ticker: str, lookback_days: int = 365) -> List[Dict]:
        """Scan SEC filings for a company and extract treasury info.

        Args:
            ticker: Company ticker
            lookback_days: Days to look back for filings

        Returns:
            List of analysis results
        """
        if not self.analyzer:
            print("Filing analyzer not available (no Anthropic API key)")
            return []

        print(f"\nScanning SEC filings for {ticker}...")

        # Get company info
        company_info = self.edgar.get_company_info(ticker)
        if not company_info:
            print(f"  Ticker {ticker} not found in SEC database")
            return []

        print(f"  Company: {company_info['name']}")

        # Get filings
        filings = self.edgar.get_company_filings(
            ticker,
            self.config["edgar"]["filing_types"],
            lookback_days,
        )
        print(f"  Found {len(filings)} filings")

        # Download and analyze each filing
        results = []
        for filing in filings:
            print(f"  Analyzing {filing['form_type']} from {filing['filing_date']}...")
            try:
                content = self.edgar.download_filing(filing)
                analysis = self.analyzer.analyze_filing(filing, content)

                if analysis:
                    results.append(analysis)

                    # Update tracker with holdings if found
                    holdings_update = self.analyzer.extract_holdings_update(analysis)
                    if holdings_update:
                        self.tracker.update_holdings(
                            ticker=ticker,
                            units=holdings_update["units"],
                            asset=holdings_update["asset"],
                            update_date=date.fromisoformat(holdings_update["date"]),
                            source=holdings_update["source"],
                            accession_number=holdings_update["accession_number"],
                        )
                        print(f"    Found holdings: {holdings_update['units']:.4f} {holdings_update['asset']}")

                    # Update tracker with shares if found
                    shares_update = self.analyzer.extract_shares_update(analysis)
                    if shares_update:
                        self.tracker.update_shares(
                            ticker=ticker,
                            shares=shares_update["shares"],
                            update_date=date.fromisoformat(shares_update["date"]),
                            source=shares_update["source"],
                            accession_number=shares_update["accession_number"],
                        )
                        print(f"    Found shares: {shares_update['shares']:,.0f}")

            except Exception as e:
                print(f"    Error: {e}")

        # Update company info
        if company_info:
            self.tracker.init_company(
                ticker=ticker,
                name=company_info["name"],
                primary_asset=results[0].get("primary_asset", "UNKNOWN") if results else "UNKNOWN",
            )

        return results

    def init_company(self, ticker: str) -> bool:
        """Initialize a company by scanning its filings.

        Args:
            ticker: Company ticker

        Returns:
            True if company initialized successfully
        """
        results = self.scan_filings(ticker, lookback_days=365)
        return len(results) > 0


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="DAT Dashboard - Digital Asset Treasury Monitor"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run daily report
    run_parser = subparsers.add_parser("run", help="Run daily report generation")

    # Scan filings
    scan_parser = subparsers.add_parser("scan", help="Scan SEC filings for a company")
    scan_parser.add_argument("ticker", help="Company ticker symbol")
    scan_parser.add_argument(
        "--lookback", type=int, default=365, help="Days to look back (default: 365)"
    )

    # Initialize company
    init_parser = subparsers.add_parser("init", help="Initialize a company")
    init_parser.add_argument("ticker", help="Company ticker symbol")

    # Show current data
    show_parser = subparsers.add_parser("show", help="Show current data for a company")
    show_parser.add_argument("ticker", help="Company ticker symbol")

    args = parser.parse_args()

    dashboard = DATDashboard()

    if args.command == "run":
        success = dashboard.run_daily_report()
        sys.exit(0 if success else 1)

    elif args.command == "scan":
        results = dashboard.scan_filings(args.ticker, args.lookback)
        print(f"\nFound {len(results)} filings with treasury data")

    elif args.command == "init":
        success = dashboard.init_company(args.ticker)
        if success:
            print(f"\n{args.ticker} initialized successfully")
        else:
            print(f"\nFailed to initialize {args.ticker}")

    elif args.command == "show":
        data = dashboard.tracker.get_current_data(args.ticker)
        if data:
            print(json.dumps(data, indent=2))
        else:
            print(f"No data for {args.ticker}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
