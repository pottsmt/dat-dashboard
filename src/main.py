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

try:
    from .bloomberg_reader import BloombergReader, StockData
    from .yfinance_client import YFinanceClient
    from .coingecko_client import CoinGeckoClient
    from .coinmarketcap_scraper import CoinMarketCapScraper
    from .edgar_client import EdgarClient
    from .filing_analyzer import FilingAnalyzer
    from .holdings_tracker import HoldingsTracker
    from .report_generator import ReportGenerator, CompanyMetrics
    from .email_sender import EmailSender
    from .pdf_generator import PDFGenerator
    from .dashboard_scraper import DashboardScraper, DashboardData, _load_cache, _save_cache, _is_cache_fresh
except ImportError:
    from bloomberg_reader import BloombergReader, StockData
    from yfinance_client import YFinanceClient
    from coingecko_client import CoinGeckoClient
    from coinmarketcap_scraper import CoinMarketCapScraper
    from edgar_client import EdgarClient
    from filing_analyzer import FilingAnalyzer
    from holdings_tracker import HoldingsTracker
    from report_generator import ReportGenerator, CompanyMetrics
    from email_sender import EmailSender
    from pdf_generator import PDFGenerator
    from dashboard_scraper import DashboardScraper, DashboardData, _load_cache, _save_cache, _is_cache_fresh


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

        # Bloomberg reader (optional, for manual overrides)
        bloomberg_path = self._resolve_path(self.config["bloomberg"]["export_path"])
        self.bloomberg = BloombergReader(bloomberg_path)

        # YFinance client (primary source for stock data)
        self.yfinance = YFinanceClient()

        # CoinGecko client (for current prices)
        self.coingecko = CoinGeckoClient(
            api_key=self.config["coingecko"].get("api_key") or None
        )

        # CoinMarketCap scraper (for performance data - no rate limits)
        self.cmc_scraper = CoinMarketCapScraper()

        # EDGAR client
        self.edgar = EdgarClient(
            user_agent=self.config["edgar"]["user_agent"],
            data_dir=self.data_dir,
        )

        # Filing analyzer (only if OpenAI key available)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key and self.config.get("openai", {}).get("enabled"):
            self.analyzer = FilingAnalyzer(
                api_key=openai_key,
                model=self.config["openai"].get("model", "gpt-4o-mini"),
                output_dir=self.data_dir / "analysis",
            )
        else:
            self.analyzer = None

        # Holdings tracker
        self.tracker = HoldingsTracker(self.data_dir / "history")

        # Dashboard scraper (Selenium-based, for company-owned dashboards)
        self.dashboard_scraper = DashboardScraper()

        # Report generator
        self.report_gen = ReportGenerator()

        # PDF generator (reuses Chrome/Selenium)
        self.pdf_gen = PDFGenerator()

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

    def scan_new_filings(self) -> List[Dict]:
        """Scan for new SEC filings since each company's last update.

        For each company in companies.json, checks EDGAR for filings filed
        after the company's last holdings update. Only processes filings
        whose accession_number hasn't been seen before. Runs sequentially
        to avoid holdings.json race conditions.

        Returns:
            List of filing summary dicts with keys: ticker, name, form_type,
            filing_date, summary, impacts (list of Treasury/Shares/Financials/Corporate/None)
        """
        filing_summaries = []

        if not self.analyzer:
            print("   Filing analyzer not available (no OpenAI API key), skipping")
            return filing_summaries

        # Companies with no usable SEC treasury data or pre-merger SPACs
        skip_tickers = {"BTOG", "NA", "SLMT", "CEPO", "TLGYF", "ETHM"}

        for company_cfg in self.companies["companies"]:
            ticker = company_cfg["ticker"]
            if ticker in skip_tickers:
                continue

            company = self.tracker.get_company(ticker)
            if not company or not company.holdings_history:
                continue

            # Calculate days since last holdings update
            last_date = max(h.date for h in company.holdings_history)
            days_since = (date.today() - date.fromisoformat(last_date)).days
            if days_since < 1:
                print(f"   {ticker}: up to date")
                continue

            # Collect all accession numbers already processed
            known_accessions = set()
            for h in company.holdings_history:
                if h.accession_number:
                    known_accessions.add(h.accession_number)
            for s in company.shares_history:
                if s.accession_number:
                    known_accessions.add(s.accession_number)

            # Fetch filings from EDGAR for the lookback period
            try:
                filings = self.edgar.get_company_filings(
                    ticker,
                    self.config["edgar"]["filing_types"],
                    days_since + 1,  # +1 to include the last update date
                )
            except Exception as e:
                print(f"   {ticker}: EDGAR error: {e}")
                continue

            # Filter to only new filings
            new_filings = [f for f in filings if f["accession_number"] not in known_accessions]

            if not new_filings:
                print(f"   {ticker}: up to date")
                continue

            print(f"   {ticker}: {len(new_filings)} new filing(s) since {last_date}")

            # Process oldest first
            new_filings.sort(key=lambda f: f.get("filing_date", ""))

            for filing in new_filings:
                form_type = filing["form_type"]
                filing_date = filing["filing_date"]
                print(f"   {ticker}: Analyzing {form_type} from {filing_date}...")

                try:
                    content = self.edgar.download_filing(filing)
                    analysis = self.analyzer.analyze_filing(filing, content)

                    if not analysis:
                        print(f"   {ticker}: No data extracted")
                        continue

                    # Build filing summary entry
                    impacts = []

                    # Get last known values for validation
                    company = self.tracker.get_company(ticker)
                    last_units = company.current_holdings.treasury_units if company and company.current_holdings else None
                    last_shares = company.current_shares.shares_outstanding if company and company.current_shares else None

                    # Extract and store holdings
                    holdings_update = self.analyzer.extract_holdings_update(analysis, last_known_units=last_units)
                    if holdings_update:
                        impacts.append("Treasury")
                        self.tracker.update_holdings(
                            ticker=ticker,
                            units=holdings_update["units"],
                            asset=holdings_update["asset"],
                            update_date=date.fromisoformat(holdings_update["date"]),
                            source=holdings_update["source"],
                            accession_number=holdings_update["accession_number"],
                            notes=holdings_update.get("filing_summary"),
                            treasury_value_usd=holdings_update.get("value_usd"),
                        )
                        value_str = f" (${holdings_update['value_usd']:,.0f})" if holdings_update.get("value_usd") else ""
                        print(f"     Treasury: {holdings_update['units']:,.4f} {holdings_update['asset']}{value_str}")

                    # Extract and store shares
                    shares_update = self.analyzer.extract_shares_update(analysis, last_known_shares=last_shares)
                    if shares_update:
                        impacts.append("Shares")
                        self.tracker.update_shares(
                            ticker=ticker,
                            shares=shares_update["shares"],
                            update_date=date.fromisoformat(shares_update["date"]),
                            source=shares_update["source"],
                            accession_number=shares_update["accession_number"],
                            notes=shares_update.get("filing_summary"),
                        )
                        print(f"     Shares: {shares_update['shares']:,.0f}")

                    # Extract other holdings
                    company = self.tracker.get_company(ticker)
                    p_asset = company.primary_asset if company else None
                    other_holdings = self.analyzer.extract_other_holdings(analysis, primary_asset=p_asset)
                    if other_holdings and company:
                        self._merge_other_holdings(company, other_holdings)
                        self.tracker._save()
                        print(f"     Other holdings: {len(other_holdings)}")

                    # Collect summary for email
                    company_name = company_cfg.get("name", ticker)
                    summary_text = analysis.get("filing_summary", "No summary available.")
                    if not impacts:
                        impacts.append("None")
                    filing_summaries.append({
                        "ticker": ticker,
                        "name": company_name,
                        "form_type": form_type,
                        "filing_date": filing_date,
                        "summary": summary_text,
                        "impacts": impacts,
                    })

                except Exception as e:
                    print(f"     Error: {e}")

        return filing_summaries

    def _build_filing_summary_html(self, filing_summaries: List[Dict]) -> str:
        """Build HTML section summarizing new filings for the email."""
        if not filing_summaries:
            return ""

        date_str = datetime.now().strftime("%B %d, %Y")
        rows = ""
        for f in filing_summaries:
            impact_badges = ""
            for impact in f["impacts"]:
                colors = {
                    "Treasury": "#dc2626", "Shares": "#2563eb",
                    "Financials": "#059669", "Corporate": "#7c3aed", "None": "#6b7280",
                }
                color = colors.get(impact, "#6b7280")
                impact_badges += (
                    f'<span style="background:{color};color:#fff;padding:2px 8px;'
                    f'border-radius:4px;font-size:12px;margin-right:4px;">{impact}</span>'
                )
            rows += f"""
            <tr>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;font-weight:bold;">{f['ticker']}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;">{f['form_type']}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;">{f['filing_date']}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;">{impact_badges}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;">{f['summary']}</td>
            </tr>"""

        return f"""
        <div style="font-family:Arial,sans-serif;max-width:1200px;margin:0 auto 30px auto;
                    padding:20px;background:#fffbeb;border:1px solid #f59e0b;border-radius:8px;">
            <h2 style="margin:0 0 15px 0;color:#92400e;">New SEC Filings — {date_str}</h2>
            <p style="margin:0 0 15px 0;color:#78716c;">{len(filing_summaries)} new filing(s) found today</p>
            <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:6px;">
                <thead>
                    <tr style="background:#fef3c7;">
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #f59e0b;">Ticker</th>
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #f59e0b;">Form</th>
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #f59e0b;">Filed</th>
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #f59e0b;">Impact</th>
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #f59e0b;">Summary</th>
                    </tr>
                </thead>
                <tbody>{rows}
                </tbody>
            </table>
        </div>
        """

    def _build_filing_summary_text(self, filing_summaries: List[Dict]) -> str:
        """Build plain text section summarizing new filings for the email."""
        if not filing_summaries:
            return ""

        date_str = datetime.now().strftime("%B %d, %Y")
        lines = [
            f"NEW SEC FILINGS — {date_str}",
            f"{len(filing_summaries)} new filing(s) found today",
            "=" * 60,
        ]
        for f in filing_summaries:
            impacts = ", ".join(f["impacts"])
            lines.append(f"\n{f['ticker']} — {f['form_type']} (filed {f['filing_date']}) [{impacts}]")
            lines.append(f"  {f['summary']}")
        lines.append("\n" + "=" * 60 + "\n")
        return "\n".join(lines)

    def run_daily_report(self, use_yfinance: bool = True) -> bool:
        """Run daily report generation.

        Args:
            use_yfinance: If True, use Yahoo Finance for stock data (default).
                         If False, require Bloomberg CSV export.

        Returns:
            True if report generated and sent successfully
        """
        print(f"Starting DAT Dashboard report generation at {datetime.now()}")

        # Step 0.5: Scan for new SEC filings
        print("\n0.5. Scanning for new SEC filings...")
        filing_summaries = self.scan_new_filings()

        # Get list of tickers to fetch (only those with known holdings)
        tickers_to_fetch = []
        for company in self.companies["companies"]:
            ticker = company["ticker"]
            # Only include companies with holdings data
            holdings = self.tracker.get_current_data(ticker)
            if holdings and holdings.get("treasury_units"):
                tickers_to_fetch.append(ticker)

        print(f"\nTracking {len(tickers_to_fetch)} companies with holdings data")

        # Step 1: Load stock data
        print("\n1. Loading stock data...")
        stock_data = {}

        if use_yfinance:
            print("   Using Yahoo Finance...")
            stock_data = self.yfinance.get_multiple_stocks(tickers_to_fetch)
            print(f"   Loaded data for {len(stock_data)} tickers via yfinance")

            # Try Bloomberg as fallback for missing tickers
            missing_tickers = [t for t in tickers_to_fetch if t not in stock_data]
            if missing_tickers:
                print(f"   Missing from yfinance: {missing_tickers}")
                try:
                    bloomberg_data = self.bloomberg.read_as_dict()
                    for ticker in missing_tickers:
                        if ticker in bloomberg_data:
                            stock_data[ticker] = bloomberg_data[ticker]
                            print(f"   {ticker}: Found in Bloomberg export")
                except FileNotFoundError:
                    pass
        else:
            # Bloomberg only mode
            try:
                stock_data = self.bloomberg.read_as_dict()
                print(f"   Loaded data for {len(stock_data)} tickers from Bloomberg")
            except FileNotFoundError as e:
                print(f"   ERROR: Bloomberg export not found: {e}")
                print("   Please ensure Bloomberg Excel has exported data.")
                return False

        # Step 1.5: Scrape company dashboards for authoritative data
        print("\n1.5. Scraping company dashboards...")
        dashboard_cache = _load_cache()
        dashboard_data = {}
        for company in self.companies["companies"]:
            dashboard_url = company.get("dashboard_url")
            if not dashboard_url:
                continue
            ticker = company["ticker"]
            print(f"   {ticker}: Scraping {dashboard_url}...")
            try:
                result = self.dashboard_scraper.scrape(ticker, dashboard_url)
                if result:
                    dashboard_data[ticker] = result
                    dashboard_cache[ticker] = result  # Update cache
                    parts = []
                    if result.treasury_units:
                        parts.append(f"treasury={result.treasury_units:,.0f}")
                    if result.market_cap:
                        parts.append(f"mktcap=${result.market_cap:,.0f}")
                    if result.enterprise_value:
                        parts.append(f"EV=${result.enterprise_value:,.0f}")
                    if result.total_debt:
                        parts.append(f"debt=${result.total_debt:,.0f}")
                    if result.cash:
                        parts.append(f"cash=${result.cash:,.0f}")
                    if result.mnav:
                        parts.append(f"mNAV={result.mnav:.2f}x")
                    if result.mcap_nav:
                        parts.append(f"Mcap/NAV={result.mcap_nav:.2f}x")
                    if result.shares_outstanding:
                        parts.append(f"shares={result.shares_outstanding:,.0f}")
                    print(f"   {ticker}: Dashboard data: {', '.join(parts) if parts else 'partial'}")
                else:
                    # Scrape failed — try cache fallback
                    cached = dashboard_cache.get(ticker)
                    if cached and _is_cache_fresh(cached):
                        age_hours = (datetime.now() - cached.scraped_at).total_seconds() / 3600
                        dashboard_data[ticker] = cached
                        print(f"   {ticker}: Using CACHED dashboard data (scraped {age_hours:.0f}h ago)")
                    else:
                        print(f"   {ticker}: No data returned from dashboard (no fresh cache)")
            except Exception as e:
                # Scrape exception — try cache fallback
                cached = dashboard_cache.get(ticker)
                if cached and _is_cache_fresh(cached):
                    age_hours = (datetime.now() - cached.scraped_at).total_seconds() / 3600
                    dashboard_data[ticker] = cached
                    print(f"   {ticker}: Dashboard scrape failed, using CACHED data (scraped {age_hours:.0f}h ago): {e}")
                else:
                    print(f"   {ticker}: Dashboard scrape failed: {e}")

        # Save cache after all scrapes
        _save_cache(dashboard_cache)

        if dashboard_data:
            print(f"   Got dashboard data for {len(dashboard_data)} companies")
        else:
            print("   No dashboard data available (will use SEC/yfinance pipeline)")

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
                if cg_id in prices and prices[cg_id] is not None:
                    crypto_prices[asset] = prices[cg_id]
                    print(f"   {asset}: ${prices[cg_id]:,.2f}")
                else:
                    print(f"   {asset}: Price not available")

        # Step 3: Get crypto performance data (using CoinMarketCap scraper)
        print("\n3. Fetching crypto performance from CoinMarketCap...")
        crypto_perf = {}
        for asset in unique_assets:
            try:
                perf = self.cmc_scraper.get_all_performance(asset)
                crypto_perf[asset] = perf
                perf_7d = perf.get("7d")
                perf_30d = perf.get("30d")
                if perf_7d is not None and perf_30d is not None:
                    print(f"   {asset}: 7D {perf_7d:+.2f}%, 30D {perf_30d:+.2f}%")
                elif perf_7d is not None or perf_30d is not None:
                    print(f"   {asset}: 7D {perf_7d:+.2f}%" if perf_7d else f"   {asset}: 30D {perf_30d:+.2f}%")
                else:
                    print(f"   {asset}: Performance data not available")
            except Exception as e:
                print(f"   Error getting {asset} performance: {e}")

        # Step 3.5: Refresh ATM dilution estimates for companies without dashboards
        # Companies with dashboards get shares from market_cap / stock_price instead
        print("\n3.5. Refreshing ATM share estimates...")
        dashboard_tickers = {c["ticker"] for c in self.companies["companies"] if c.get("dashboard_url")}
        for company_cfg in self.companies["companies"]:
            t = company_cfg["ticker"]
            if t in dashboard_tickers:
                continue
            company = self.tracker.get_company(t)
            if company and company.holdings_history and company.shares_history:
                asset = company.primary_asset
                if asset in crypto_prices:
                    self._estimate_shares_from_treasury(t, crypto_prices[asset])

        # Step 4: Build metrics for each company
        print("\n4. Building company metrics...")
        metrics_list = []

        for company in self.companies["companies"]:
            ticker = company["ticker"]
            stock = stock_data.get(ticker)

            # Get holdings from tracker
            holdings = self.tracker.get_current_data(ticker)

            # Skip companies without holdings data
            if not holdings or not holdings.get("treasury_units"):
                continue

            if not stock:
                print(f"   {ticker}: No stock data available, skipping")
                continue

            # Build metrics
            m = CompanyMetrics(
                ticker=ticker,
                name=company.get("name", "Unknown"),
                primary_asset=company.get("primary_asset", "UNKNOWN"),
            )

            # Stock data from Bloomberg
            m.stock_price = stock.price
            m.volume = stock.volume
            m.avg_volume_5d = stock.avg_volume_5d
            m.market_cap = stock.market_cap_actual
            m.total_debt = stock.total_debt
            m.cash = stock.cash
            m.enterprise_value = stock.enterprise_value_actual

            # Shares - prefer tracker data if available, else stock data source
            if holdings and holdings.get("shares_outstanding"):
                m.shares_outstanding = holdings["shares_outstanding"]
                m.shares_source = holdings.get("shares_method", "official")
                # Recalculate market cap from SEC shares * price when SEC shares
                # differ from yfinance (yfinance often lags dilution events)
                if m.stock_price:
                    m.market_cap = m.shares_outstanding * m.stock_price
                    m.enterprise_value = m.market_cap + (m.total_debt or 0) - (m.cash or 0)
            elif stock.shares_outstanding_actual:
                m.shares_outstanding = stock.shares_outstanding_actual
                m.shares_source = "yfinance"

            # Treasury data from tracker
            if holdings and holdings.get("treasury_units"):
                m.treasury_units = holdings["treasury_units"]
                m.treasury_date = holdings.get("treasury_date")
                m.treasury_source = holdings.get("treasury_source")

            # Crypto price
            asset = m.primary_asset
            if asset in crypto_prices:
                m.crypto_price = crypto_prices[asset]

            # Prefer SEC filing cash/debt over yfinance (filing data is more reliable)
            if holdings and holdings.get("other_holdings"):
                has_filing_financials = False
                for holding in holdings["other_holdings"]:
                    if holding.get("type") in ("cash", "cash_override"):
                        m.cash = holding.get("value_usd", 0)
                        has_filing_financials = True
                    elif holding.get("type") == "debt_override":
                        m.total_debt = holding.get("value_usd", 0)
                        has_filing_financials = True
                if has_filing_financials and m.market_cap is not None:
                    m.enterprise_value = m.market_cap + (m.total_debt or 0) - (m.cash or 0)

            # Other holdings (digital assets, private/public equity, venture, other)
            if holdings and holdings.get("other_holdings"):
                other_value = 0
                for holding in holdings["other_holdings"]:
                    if holding.get("type") == "digital_asset":
                        # Look up live crypto price for the asset
                        h_ticker = holding.get("ticker")
                        h_units = holding.get("units")
                        if h_ticker and h_units and h_ticker in crypto_prices:
                            other_value += h_units * crypto_prices[h_ticker]
                    elif holding.get("type") == "public_equity":
                        # Prefer live stock price over static value_usd
                        if holding.get("shares") and holding.get("ticker"):
                            other_ticker = holding["ticker"]
                            other_stock = stock_data.get(other_ticker)
                            if other_stock and other_stock.price:
                                other_value += holding["shares"] * other_stock.price
                                continue
                        if holding.get("value_usd"):
                            other_value += holding["value_usd"]
                    elif holding.get("type") in ("private_equity", "venture", "other"):
                        if holding.get("value_usd"):
                            other_value += holding["value_usd"]
                if other_value > 0:
                    m.other_holdings_value = other_value

            # Dashboard overrides — authoritative data from company-owned sources
            dash = dashboard_data.get(ticker)
            if dash:
                if dash.market_cap:
                    m.market_cap = dash.market_cap
                if dash.enterprise_value:
                    m.enterprise_value = dash.enterprise_value
                if dash.total_debt:
                    m.total_debt = dash.total_debt
                if dash.cash:
                    m.cash = dash.cash
                if dash.treasury_units:
                    m.treasury_units = dash.treasury_units
                    m.treasury_source = "dashboard"
                if dash.shares_outstanding:
                    m.shares_outstanding = dash.shares_outstanding
                    m.shares_source = "dashboard"
                elif dash.market_cap and m.stock_price:
                    # Derive shares from dashboard market cap / stock price
                    m.shares_outstanding = dash.market_cap / m.stock_price
                    m.shares_source = "dashboard"
                m.dashboard_source_url = dash.source_url

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

            # Post-calculation dashboard override: mNAV/mcap_nav from dashboard
            if dash:
                if dash.mnav:
                    m.mnav = dash.mnav
                if dash.mcap_nav:
                    m.mcap_nav = dash.mcap_nav

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

        html_path.write_text(html_report, encoding="utf-8")
        text_path.write_text(text_report)
        print(f"   Saved: {html_path}")
        print(f"   Saved: {text_path}")

        # Generate PDF from HTML report
        pdf_path = reports_dir / f"dat_report_{date_str}.pdf"
        print(f"   Generating PDF...")
        if self.pdf_gen.html_to_pdf(html_path, pdf_path):
            print(f"   Saved: {pdf_path}")
        else:
            print(f"   PDF generation failed, email will send without attachment")
            pdf_path = None
        self.pdf_gen.close()

        # Generate company detail pages
        print("\n   Generating company detail pages...")
        companies_dir = reports_dir / "companies"
        companies_dir.mkdir(exist_ok=True)

        for m in metrics_list:
            company_data = self.tracker.get_company(m.ticker)
            if company_data:
                cik = self.edgar.ticker_to_cik(m.ticker) or ""
                crypto_price = crypto_prices.get(m.primary_asset, 0)
                detail_html = self.report_gen.generate_company_detail_page(
                    company_data, m, cik, crypto_price, crypto_prices, stock_data
                )
                detail_path = companies_dir / f"{m.ticker.lower()}.html"
                detail_path.write_text(detail_html, encoding="utf-8")
        print(f"   Saved {len(metrics_list)} company detail pages to {companies_dir}")

        # Step 6: Send email
        if self.email:
            print("\n6. Sending email report...")

            # Build filing summary section for email body
            filing_html = self._build_filing_summary_html(filing_summaries)
            filing_text = self._build_filing_summary_text(filing_summaries)

            # Prepend filing summary to the email body
            email_html = filing_html + html_report if filing_html else html_report
            email_text = filing_text + "\n" + text_report if filing_text else text_report

            success = self.email.send_report(email_html, email_text, pdf_path=pdf_path)
            if success:
                print("   Email sent successfully!")
            else:
                print("   Email sending failed")
                return False
        else:
            print("\n6. Email not configured, skipping")

        # Clean up Selenium driver
        if dashboard_data:
            self.dashboard_scraper.close()

        # Deploy to GitHub Pages
        print("\n7. Deploying to GitHub Pages...")
        try:
            from .deploy_pages import deploy
            if deploy():
                print("   Deployed to https://pottsmt.github.io/dat-dashboard/")
            else:
                print("   Deploy failed (non-critical)")
        except Exception as e:
            print(f"   Deploy error (non-critical): {e}")

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
            print("Filing analyzer not available (no OpenAI API key)")
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

                    # Get last known values for cross-filing validation
                    company = self.tracker.get_company(ticker)
                    last_units = company.current_holdings.treasury_units if company and company.current_holdings else None
                    last_shares = company.current_shares.shares_outstanding if company and company.current_shares else None

                    # Update tracker with holdings if found
                    holdings_update = self.analyzer.extract_holdings_update(analysis, last_known_units=last_units)
                    if holdings_update:
                        self.tracker.update_holdings(
                            ticker=ticker,
                            units=holdings_update["units"],
                            asset=holdings_update["asset"],
                            update_date=date.fromisoformat(holdings_update["date"]),
                            source=holdings_update["source"],
                            accession_number=holdings_update["accession_number"],
                            notes=holdings_update.get("filing_summary"),
                            treasury_value_usd=holdings_update.get("value_usd"),
                        )
                        value_str = f" (${holdings_update['value_usd']:,.0f})" if holdings_update.get("value_usd") else ""
                        print(f"    Found holdings: {holdings_update['units']:.4f} {holdings_update['asset']}{value_str}")

                    # Update tracker with shares if found
                    shares_update = self.analyzer.extract_shares_update(analysis, last_known_shares=last_shares)
                    if shares_update:
                        self.tracker.update_shares(
                            ticker=ticker,
                            shares=shares_update["shares"],
                            update_date=date.fromisoformat(shares_update["date"]),
                            source=shares_update["source"],
                            accession_number=shares_update["accession_number"],
                            notes=shares_update.get("filing_summary"),
                        )
                        print(f"    Found shares: {shares_update['shares']:,.0f}")

                    # Update tracker with other holdings (secondary assets, cash, investments)
                    company = self.tracker.get_company(ticker)
                    p_asset = company.primary_asset if company else None
                    other_holdings = self.analyzer.extract_other_holdings(analysis, primary_asset=p_asset)
                    if other_holdings and company:
                        self._merge_other_holdings(company, other_holdings)
                        self.tracker._save()
                        print(f"    Found {len(other_holdings)} other holding(s)")

            except Exception as e:
                print(f"    Error: {e}")

        # Update company info
        if company_info:
            self.tracker.init_company(
                ticker=ticker,
                name=company_info["name"],
                primary_asset=results[0].get("primary_asset", "UNKNOWN") if results else "UNKNOWN",
            )

        # Estimate shares from treasury dilution after scan
        company = self.tracker.get_company(ticker)
        if company and company.holdings_history and company.shares_history:
            cg_id = self._get_asset_coingecko_id(company.primary_asset)
            if cg_id:
                prices = self.coingecko.get_current_prices([cg_id])
                crypto_price = prices.get(cg_id)
                if crypto_price:
                    print(f"\n  Estimating ATM dilution...")
                    self._estimate_shares_from_treasury(ticker, crypto_price)

        return results

    def _get_crypto_price_at_date(self, asset: str, target_date: str) -> Optional[float]:
        """Get historical crypto price for a specific date via CoinGecko.

        Args:
            asset: Asset ticker (e.g., "WLD")
            target_date: ISO date string (YYYY-MM-DD)

        Returns:
            Price in USD or None
        """
        cg_id = self._get_asset_coingecko_id(asset)
        if not cg_id:
            return None
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d")
            price = self.coingecko.get_historical_price(cg_id, dt)
            if price:
                print(f"    {asset} price on {target_date}: ${price:,.4f}")
            return price
        except Exception as e:
            print(f"    Could not fetch {asset} price for {target_date}: {e}")
            return None

    def _estimate_shares_from_treasury(self, ticker: str, crypto_price: float):
        """Estimate shares sold via ATM between the last official shares filing
        and subsequent treasury updates.

        For each consecutive pair of treasury dates after the last official
        shares entry, computes:
            delta_units * avg_crypto_price / stock_VWAP = estimated shares sold

        Always uses unit changes (not USD value changes) because the treasury
        value can decline even when units increase due to price drops.

        Crypto price priority:
        1. Average of historical prices at each endpoint date
        2. Current crypto price as last resort

        Results are saved as SharesUpdate entries with method="vwap_estimate".
        Previous estimates are cleared first so they refresh each run.

        Args:
            ticker: Company ticker symbol
            crypto_price: Current price of the company's primary crypto asset
        """
        ticker = ticker.upper()
        company = self.tracker.get_company(ticker)
        if not company:
            return

        holdings_history = company.holdings_history
        shares_history = company.shares_history

        if not holdings_history or not shares_history:
            return

        # Find last official shares entry (method != "vwap_estimate")
        official_entries = [
            s for s in shares_history if s.method != "vwap_estimate"
        ]
        if not official_entries:
            return

        official_entries.sort(key=lambda x: x.date)
        last_official = official_entries[-1]
        last_official_date = last_official.date
        last_official_shares = last_official.shares_outstanding

        # Find all treasury updates strictly after the last official shares date
        treasury_after = [
            h for h in holdings_history if h.date > last_official_date
        ]
        if not treasury_after:
            return

        treasury_after.sort(key=lambda x: x.date)

        # Build the list of consecutive pairs: start from the treasury entry
        # at or just before the official shares date, then each subsequent one
        anchor_entries = [h for h in holdings_history if h.date <= last_official_date]
        if anchor_entries:
            anchor = max(anchor_entries, key=lambda x: x.date)
        else:
            # No treasury at or before the shares date — can't compute delta
            return

        # Clear previous estimates before recomputing
        self.tracker.clear_estimated_shares(ticker)

        # Pre-fetch historical crypto prices for all dates in the sequence
        sequence = [anchor] + treasury_after
        asset = company.primary_asset
        historical_prices = {}
        for entry in sequence:
            if entry.date not in historical_prices:
                hp = self._get_crypto_price_at_date(asset, entry.date)
                historical_prices[entry.date] = hp

        cumulative_shares = last_official_shares

        # Pre-load cash values from analysis files for cash-based dilution estimation
        analysis_dir = self.data_dir / "analysis"
        cash_by_accession = {}
        if analysis_dir.exists():
            for entry in sequence:
                acc = entry.accession_number
                if acc:
                    analysis_file = analysis_dir / f"{ticker}_{acc}_analysis.json"
                    if analysis_file.exists():
                        try:
                            analysis = json.load(open(analysis_file))
                            cash_info = analysis.get("cash_and_equivalents")
                            if cash_info and cash_info.get("amount_usd"):
                                cash_by_accession[acc] = cash_info["amount_usd"]
                        except Exception:
                            pass

        for i in range(1, len(sequence)):
            prev = sequence[i - 1]
            curr = sequence[i]

            delta_units = curr.treasury_units - prev.treasury_units
            if delta_units <= 0:
                # No treasury increase — check if cash increased (ATM for cash reserves)
                prev_cash = cash_by_accession.get(prev.accession_number)
                curr_cash = cash_by_accession.get(curr.accession_number)
                if prev_cash and curr_cash and curr_cash > prev_cash:
                    cash_delta = curr_cash - prev_cash
                    vwap = self.yfinance.get_vwap(ticker, prev.date, curr.date)
                    if vwap:
                        est_shares_sold = cash_delta / vwap
                        cumulative_shares += est_shares_sold
                        notes = (
                            f"VWAP: ${vwap:,.2f} | "
                            f"Cash increase: ${cash_delta:,.0f} (${prev_cash:,.0f} -> ${curr_cash:,.0f}) | "
                            f"+{est_shares_sold:,.0f} shares est."
                        )
                        self.tracker.update_shares(
                            ticker=ticker,
                            shares=cumulative_shares,
                            update_date=date.fromisoformat(curr.date),
                            source="estimated",
                            method="vwap_estimate",
                            notes=notes,
                        )
                        print(f"    {ticker}: Est. shares at {curr.date}: {cumulative_shares:,.0f} "
                              f"(+{est_shares_sold:,.0f} via cash increase ${cash_delta:,.0f} / VWAP ${vwap:.2f})")
                        continue

                # No treasury or cash increase — still record cumulative entry
                self.tracker.update_shares(
                    ticker=ticker,
                    shares=cumulative_shares,
                    update_date=date.fromisoformat(curr.date),
                    source="estimated",
                    method="vwap_estimate",
                    notes=f"No treasury increase ({prev.date} to {curr.date})",
                )
                continue

            # Estimate cost of new units using avg historical price between dates
            if historical_prices.get(curr.date) or historical_prices.get(prev.date):
                prices_available = [
                    p for p in [historical_prices.get(prev.date), historical_prices.get(curr.date)]
                    if p is not None
                ]
                avg_crypto_price = sum(prices_available) / len(prices_available)
                price_note = f"{delta_units:,.0f} units @ ${avg_crypto_price:,.4f} (historical avg)"
            else:
                # Fallback to current price
                avg_crypto_price = crypto_price
                price_note = f"{delta_units:,.0f} units @ ${crypto_price:,.2f} (current)"

            treasury_diff = delta_units * avg_crypto_price

            # Compute stock VWAP between the two dates
            vwap = self.yfinance.get_vwap(ticker, prev.date, curr.date)
            if not vwap:
                print(f"    {ticker}: Could not compute VWAP for {prev.date} to {curr.date}")
                continue

            est_shares_sold = treasury_diff / vwap
            cumulative_shares += est_shares_sold

            notes = (
                f"VWAP: ${vwap:,.2f} | "
                f"Treasury delta: ${treasury_diff:,.0f} ({price_note}) | "
                f"+{est_shares_sold:,.0f} shares est."
            )

            self.tracker.update_shares(
                ticker=ticker,
                shares=cumulative_shares,
                update_date=date.fromisoformat(curr.date),
                source="estimated",
                method="vwap_estimate",
                notes=notes,
            )
            print(f"    {ticker}: Est. shares at {curr.date}: {cumulative_shares:,.0f} "
                  f"(+{est_shares_sold:,.0f} via VWAP ${vwap:.2f})")

    def _merge_other_holdings(self, company, new_holdings: List[Dict]):
        """Merge new other holdings into existing, keyed by ticker (digital assets), type (cash), or name."""
        def _merge_key(h):
            if h.get("type") == "digital_asset" and h.get("ticker"):
                return f"digital_asset:{h['ticker']}"
            if h.get("type") == "cash":
                return "cash"
            # For public/private equity with a ticker, use the ticker to avoid
            # name-variation duplicates (e.g. "WhiteFiber" vs "WhiteFiber Inc.")
            if h.get("type") in ("public_equity", "private_equity") and h.get("ticker"):
                return f"{h['type']}:{h['ticker']}"
            return h.get("name", "")

        existing_by_key = {_merge_key(h): i for i, h in enumerate(company.other_holdings)}
        for h in new_holdings:
            key = _merge_key(h)
            if key in existing_by_key:
                company.other_holdings[existing_by_key[key]] = h
            else:
                company.other_holdings.append(h)
                existing_by_key[key] = len(company.other_holdings) - 1

    def audit_filings(self, ticker: str, lookback_days: int = 730) -> List[Dict]:
        """Build full audit trail from SEC filings for a company.

        Scans all filings within lookback period, extracts treasury units,
        shares outstanding, and other investments. Deduplicates automatically.

        Args:
            ticker: Company ticker
            lookback_days: Days to look back (default: 730 = ~2 years)

        Returns:
            List of analysis results
        """
        if not self.analyzer:
            print("Filing analyzer not available (no OPENAI_API_KEY)")
            return []

        print(f"\n{'='*60}")
        print(f"AUDIT: Building filing history for {ticker}")
        print(f"{'='*60}")

        # Get company info
        company_info = self.edgar.get_company_info(ticker)
        if not company_info:
            print(f"  Ticker {ticker} not found in SEC database")
            return []

        print(f"  Company: {company_info['name']}")

        # Look up primary asset from companies.json
        primary_asset = "UNKNOWN"
        for company in self.companies.get("companies", []):
            if company["ticker"].upper() == ticker.upper():
                primary_asset = company.get("primary_asset", "UNKNOWN")
                break

        # Initialize company in tracker
        self.tracker.init_company(
            ticker=ticker,
            name=company_info["name"],
            primary_asset=primary_asset,
        )

        # Get all filings
        filings = self.edgar.get_company_filings(
            ticker,
            self.config["edgar"]["filing_types"],
            lookback_days,
        )
        print(f"  Found {len(filings)} filings in last {lookback_days} days")

        # Process oldest first so history builds chronologically
        filings_sorted = sorted(filings, key=lambda f: f.get("filing_date", ""))

        results = []
        for i, filing in enumerate(filings_sorted, 1):
            form_type = filing['form_type']
            filing_date = filing['filing_date']
            print(f"\n  [{i}/{len(filings_sorted)}] {form_type} from {filing_date}...")

            try:
                content = self.edgar.download_filing(filing)
                analysis = self.analyzer.analyze_filing(filing, content)

                if not analysis:
                    print(f"    No data extracted")
                    continue

                results.append(analysis)

                # Get last known values for cross-filing validation
                company = self.tracker.get_company(ticker)
                has_treasury = bool(company and company.holdings_history)
                last_units = company.current_holdings.treasury_units if company and company.current_holdings else None
                # Only validate shares against previous if treasury strategy has started
                last_shares = (company.current_shares.shares_outstanding
                               if has_treasury and company and company.current_shares else None)

                # Update tracker with holdings
                holdings_update = self.analyzer.extract_holdings_update(analysis, last_known_units=last_units)
                if holdings_update:
                    self.tracker.update_holdings(
                        ticker=ticker,
                        units=holdings_update["units"],
                        asset=holdings_update["asset"],
                        update_date=date.fromisoformat(holdings_update["date"]),
                        source=holdings_update["source"],
                        accession_number=holdings_update["accession_number"],
                        notes=holdings_update.get("filing_summary"),
                        treasury_value_usd=holdings_update.get("value_usd"),
                    )
                    value_str = f" (${holdings_update['value_usd']:,.0f})" if holdings_update.get("value_usd") else ""
                    print(f"    Treasury: {holdings_update['units']:,.4f} {holdings_update['asset']}{value_str}")

                # Skip shares from pre-strategy filings
                if not has_treasury and not holdings_update:
                    shares_update = None
                else:
                    shares_update = self.analyzer.extract_shares_update(analysis, last_known_shares=last_shares)
                if shares_update:
                    self.tracker.update_shares(
                        ticker=ticker,
                        shares=shares_update["shares"],
                        update_date=date.fromisoformat(shares_update["date"]),
                        source=shares_update["source"],
                        accession_number=shares_update["accession_number"],
                        notes=shares_update.get("filing_summary"),
                    )
                    print(f"    Shares: {shares_update['shares']:,.0f}")

                # Update other holdings (secondary assets, cash, investments)
                company = self.tracker.get_company(ticker)
                p_asset = company.primary_asset if company else primary_asset
                other_holdings = self.analyzer.extract_other_holdings(analysis, primary_asset=p_asset)
                if other_holdings and company:
                    self._merge_other_holdings(company, other_holdings)
                    self.tracker._save()
                    print(f"    Other holdings: {len(other_holdings)}")

                summary = analysis.get("filing_summary", "")
                if summary:
                    print(f"    Summary: {summary[:100]}...")

            except Exception as e:
                print(f"    Error: {e}")

        # Estimate shares from treasury dilution
        print(f"\n  Estimating ATM dilution from treasury changes...")
        company = self.tracker.get_company(ticker)
        if company and company.holdings_history and company.shares_history:
            # Get current crypto price for the primary asset
            cg_id = self._get_asset_coingecko_id(company.primary_asset)
            if cg_id:
                prices = self.coingecko.get_current_prices([cg_id])
                crypto_price = prices.get(cg_id)
                if crypto_price:
                    self._estimate_shares_from_treasury(ticker, crypto_price)
                else:
                    print(f"    Could not fetch {company.primary_asset} price for estimation")
            else:
                print(f"    No CoinGecko ID for {company.primary_asset}")

        # Print final summary
        company = self.tracker.get_company(ticker)
        print(f"\n{'='*60}")
        print(f"AUDIT COMPLETE: {ticker}")
        if company:
            print(f"  Treasury entries: {len(company.holdings_history)}")
            print(f"  Shares entries: {len(company.shares_history)}")
            print(f"  Other holdings: {len(company.other_holdings)}")
            if company.current_holdings:
                print(f"  Latest treasury: {company.current_holdings.treasury_units:,.4f} {company.current_holdings.treasury_asset} ({company.current_holdings.date})")
            if company.current_shares:
                print(f"  Latest shares: {company.current_shares.shares_outstanding:,.0f} ({company.current_shares.date})")
        print(f"{'='*60}")

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
    run_parser.add_argument(
        "--bloomberg", action="store_true",
        help="Use Bloomberg CSV export instead of Yahoo Finance"
    )

    # Scan filings
    scan_parser = subparsers.add_parser("scan", help="Scan SEC filings for a company")
    scan_parser.add_argument("ticker", help="Company ticker symbol")
    scan_parser.add_argument(
        "--lookback", type=int, default=365, help="Days to look back (default: 365)"
    )

    # Initialize company
    init_parser = subparsers.add_parser("init", help="Initialize a company")
    init_parser.add_argument("ticker", help="Company ticker symbol")

    # Audit filings (full history build)
    audit_parser = subparsers.add_parser("audit", help="Build full audit trail from SEC filings")
    audit_parser.add_argument("ticker", help="Company ticker symbol")
    audit_parser.add_argument(
        "--lookback", type=int, default=730, help="Days to look back (default: 730)"
    )

    # Show current data
    show_parser = subparsers.add_parser("show", help="Show current data for a company")
    show_parser.add_argument("ticker", help="Company ticker symbol")

    args = parser.parse_args()

    dashboard = DATDashboard()

    if args.command == "run":
        use_yfinance = not getattr(args, "bloomberg", False)
        success = dashboard.run_daily_report(use_yfinance=use_yfinance)
        sys.exit(0 if success else 1)

    elif args.command == "scan":
        results = dashboard.scan_filings(args.ticker, args.lookback)
        print(f"\nFound {len(results)} filings with treasury data")

    elif args.command == "audit":
        results = dashboard.audit_filings(args.ticker, args.lookback)
        print(f"\nProcessed {len(results)} filings for audit trail")

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
