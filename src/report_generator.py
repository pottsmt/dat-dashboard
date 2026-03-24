"""
Generates DAT Dashboard reports in HTML and plain text formats.
"""

from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class CompanyMetrics:
    """Calculated metrics for a company."""
    ticker: str
    name: str
    primary_asset: str

    # Stock data
    stock_price: Optional[float] = None
    volume: Optional[float] = None
    avg_volume_5d: Optional[float] = None
    shares_outstanding: Optional[float] = None
    shares_source: str = "unknown"  # "official", "estimated", "bloomberg"
    market_cap: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    enterprise_value: Optional[float] = None

    # Treasury data
    treasury_units: Optional[float] = None
    treasury_date: Optional[str] = None
    treasury_source: Optional[str] = None

    # Crypto data
    crypto_price: Optional[float] = None
    crypto_24h_change: Optional[float] = None

    # Calculated metrics
    nav: Optional[float] = None  # Net asset value (crypto + other holdings + cash)
    nav_per_share: Optional[float] = None
    mcap_nav: Optional[float] = None  # Market cap / NAV
    mnav: Optional[float] = None  # EV / NAV (the standard "mNAV")

    # Performance
    stock_perf_3d: Optional[float] = None
    stock_perf_7d: Optional[float] = None
    stock_perf_30d: Optional[float] = None
    crypto_perf_3d: Optional[float] = None
    crypto_perf_7d: Optional[float] = None
    crypto_perf_30d: Optional[float] = None

    # Relative performance (stock vs crypto)
    rel_perf_3d: Optional[float] = None
    rel_perf_7d: Optional[float] = None
    rel_perf_30d: Optional[float] = None

    # Adjusted shares calculation (for ATM dilution estimation)
    official_shares: Optional[float] = None  # From last filing
    official_shares_date: Optional[str] = None  # Date of last shares filing
    treasury_at_shares_date: Optional[float] = None  # Treasury units at shares filing
    treasury_value_at_shares_date: Optional[float] = None  # Or treasury $ if reported
    vwap_since_shares_date: Optional[float] = None  # VWAP from shares date to now
    estimated_shares_sold: Optional[float] = None  # Calculated ATM dilution
    adjusted_shares: Optional[float] = None  # official + estimated

    # Other holdings (private equity, public equity stakes, etc.)
    other_holdings_value: Optional[float] = None  # Total value of other holdings

    # Dashboard source URL (when data comes from a company dashboard)
    dashboard_source_url: Optional[str] = None

    def calculate_derived_metrics(self):
        """Calculate NAV, Mcap/NAV, mNAV from component data."""
        # Calculate adjusted shares first (if we have ATM data)
        self._calculate_adjusted_shares()

        # Use adjusted shares if available, otherwise official
        effective_shares = self.adjusted_shares or self.shares_outstanding

        # NAV = treasury units * crypto price + other holdings + cash
        if self.treasury_units and self.crypto_price:
            self.nav = self.treasury_units * self.crypto_price

            # Add other holdings value (private equity, public equity stakes, etc.)
            if self.other_holdings_value:
                self.nav += self.other_holdings_value

            # Add cash to NAV
            if self.cash:
                self.nav += self.cash

            # NAV per share (using effective shares)
            if effective_shares:
                self.nav_per_share = self.nav / effective_shares

        # Recalculate market cap with adjusted shares if we have them
        if self.adjusted_shares and self.stock_price:
            adjusted_market_cap = self.adjusted_shares * self.stock_price
        else:
            adjusted_market_cap = self.market_cap

        # Mcap/NAV = market cap / NAV
        if adjusted_market_cap and self.nav:
            self.mcap_nav = adjusted_market_cap / self.nav

        # Recalculate EV with adjusted market cap
        if self.adjusted_shares and adjusted_market_cap:
            adjusted_ev = adjusted_market_cap + (self.total_debt or 0) - (self.cash or 0)
        else:
            adjusted_ev = self.enterprise_value

        # If EV is N/A, fall back to market cap
        if adjusted_ev is None:
            adjusted_ev = adjusted_market_cap

        # Store EV for display purposes
        self.enterprise_value = adjusted_ev

        # mNAV = (Mcap + Debt) / NAV
        # Cash is included in NAV, so use (Mcap + Debt) instead of EV
        # to avoid double-counting cash (subtracted in EV, added in NAV)
        if adjusted_market_cap and self.nav:
            self.mnav = (adjusted_market_cap + (self.total_debt or 0)) / self.nav

        # Relative performance = stock perf - crypto perf
        if self.stock_perf_3d is not None and self.crypto_perf_3d is not None:
            self.rel_perf_3d = self.stock_perf_3d - self.crypto_perf_3d
        if self.stock_perf_7d is not None and self.crypto_perf_7d is not None:
            self.rel_perf_7d = self.stock_perf_7d - self.crypto_perf_7d
        if self.stock_perf_30d is not None and self.crypto_perf_30d is not None:
            self.rel_perf_30d = self.stock_perf_30d - self.crypto_perf_30d

    def _calculate_adjusted_shares(self):
        """
        Estimate shares sold via ATM between filings.

        Formula:
        1. Treasury $ change = (current_units - units_at_shares_date) * crypto_price
           OR if treasury_value reported: current_treasury_$ - treasury_$_at_shares_date
        2. Estimated shares sold = Treasury $ change / VWAP
        3. Adjusted shares = official_shares + estimated_shares_sold
        """
        if not self.official_shares:
            return

        # Need VWAP to estimate dilution
        if not self.vwap_since_shares_date:
            self.adjusted_shares = self.official_shares
            return

        treasury_dollar_change = None

        # Method 1: Use reported treasury $ values if available
        if self.treasury_value_at_shares_date is not None and self.nav is not None:
            treasury_dollar_change = self.nav - self.treasury_value_at_shares_date

        # Method 2: Calculate from units * crypto price
        elif (self.treasury_at_shares_date is not None and
              self.treasury_units is not None and
              self.crypto_price is not None):
            current_treasury_value = self.treasury_units * self.crypto_price
            treasury_at_filing_value = self.treasury_at_shares_date * self.crypto_price
            treasury_dollar_change = current_treasury_value - treasury_at_filing_value

        if treasury_dollar_change is not None and treasury_dollar_change > 0:
            # Only estimate if treasury increased (ATM used to buy more crypto)
            self.estimated_shares_sold = treasury_dollar_change / self.vwap_since_shares_date
            self.adjusted_shares = self.official_shares + self.estimated_shares_sold
        else:
            # No dilution or treasury decreased
            self.estimated_shares_sold = 0
            self.adjusted_shares = self.official_shares


class ReportGenerator:
    """Generates DAT Dashboard reports."""

    def __init__(self):
        self.report_date = datetime.now()

    def _format_number(self, value: Optional[float], decimals: int = 2) -> str:
        """Format number with commas and decimals."""
        if value is None:
            return "N/A"
        if abs(value) >= 1_000_000_000:
            return f"${value / 1_000_000_000:,.{decimals}f}B"
        if abs(value) >= 1_000_000:
            return f"${value / 1_000_000:,.{decimals}f}M"
        if abs(value) >= 1_000:
            return f"${value / 1_000:,.{decimals}f}K"
        return f"${value:,.{decimals}f}"

    def _format_percent(self, value: Optional[float]) -> str:
        """Format percentage with color indicator."""
        if value is None:
            return "N/A"
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.2f}%"

    def _format_ratio(self, value: Optional[float]) -> str:
        """Format ratio."""
        if value is None:
            return "N/A"
        return f"{value:.2f}x"

    def _format_units(self, value: Optional[float], asset: str) -> str:
        """Format treasury units."""
        if value is None:
            return "N/A"
        return f"{value:,.0f} {asset}"

    def _filing_type_badge(self, filing_type: str) -> str:
        """Return an HTML badge for the filing type."""
        colors = {
            "10-K": "#2b6cb0",   # Blue
            "10-Q": "#2f855a",   # Green
            "8-K": "#c05621",    # Orange
        }
        color = colors.get(filing_type, "#718096")
        return (
            f'<span style="display:inline-block;background:{color};color:white;'
            f'padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">'
            f'{filing_type}</span>'
        )

    def _build_sec_filing_url(self, cik: str, accession_number: str) -> Optional[str]:
        """Build SEC filing URL from CIK and accession number."""
        if not cik or not accession_number:
            return None
        cik_clean = cik.lstrip('0')
        accession_clean = accession_number.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{accession_clean}/{accession_number}-index.htm"

    def _calculate_history_deltas(self, history: List[Dict], value_key: str) -> List[Dict]:
        """Add delta and delta_percent to each history entry."""
        result = []
        sorted_history = sorted(history, key=lambda x: x.get('date', ''))
        for i, entry in enumerate(sorted_history):
            entry_copy = dict(entry)
            if i > 0:
                prev_value = sorted_history[i-1].get(value_key)
                curr_value = entry.get(value_key)
                if prev_value and curr_value:
                    entry_copy['delta'] = curr_value - prev_value
                    entry_copy['delta_percent'] = ((curr_value - prev_value) / prev_value) * 100
            result.append(entry_copy)
        return result

    def generate_company_detail_page(
        self,
        company_holdings,
        current_metrics: CompanyMetrics,
        cik: str,
        crypto_price: float,
        all_crypto_prices: Optional[Dict[str, float]] = None,
        all_stock_data: Optional[Dict] = None,
    ) -> str:
        """Generate HTML detail page for a company.

        Args:
            company_holdings: CompanyHoldings object with full history
            current_metrics: Calculated metrics for the company
            cik: SEC CIK number
            crypto_price: Current price of the primary asset
            all_crypto_prices: Dict of all crypto prices (for valuing other digital assets)
            all_stock_data: Dict of ticker->StockData (for valuing public equity holdings)
        """
        ticker = current_metrics.ticker
        name = current_metrics.name
        asset = current_metrics.primary_asset

        # Build treasury history rows with deltas
        treasury_rows = []
        if company_holdings.holdings_history:
            holdings_dicts = [
                {
                    'date': h.date,
                    'treasury_units': h.treasury_units,
                    'treasury_asset': h.treasury_asset,
                    'source': h.source,
                    'accession_number': h.accession_number,
                    'notes': h.notes
                }
                for h in company_holdings.holdings_history
            ]
            holdings_with_deltas = self._calculate_history_deltas(holdings_dicts, 'treasury_units')

            for entry in reversed(holdings_with_deltas):  # Most recent first
                date_str = entry.get('date', 'N/A')
                units = entry.get('treasury_units', 0)
                source = entry.get('source', 'N/A')
                accession = entry.get('accession_number')
                notes = entry.get('notes') or ''
                delta = entry.get('delta')
                delta_pct = entry.get('delta_percent')

                delta_str = "--" if delta is None else f"{delta:+,.0f}"
                delta_pct_str = "--" if delta_pct is None else f"{delta_pct:+.2f}%"

                # Filing type badge
                filing_badge = self._filing_type_badge(source)

                # Build source with SEC link if available
                sec_url = self._build_sec_filing_url(cik, accession) if accession else None
                if sec_url:
                    source_html = f'<a href="{sec_url}" target="_blank">{filing_badge}</a>'
                else:
                    source_html = filing_badge

                # Truncate notes for display
                notes_display = (notes[:120] + '...') if len(notes) > 120 else notes

                treasury_rows.append(f"""
                <tr>
                    <td>{date_str}</td>
                    <td class="number">{units:,.0f}</td>
                    <td class="number">{delta_str}</td>
                    <td class="number">{delta_pct_str}</td>
                    <td>{source_html}</td>
                    <td class="notes">{notes_display}</td>
                </tr>
                """)
        else:
            treasury_rows.append('<tr><td colspan="6">No treasury history available</td></tr>')

        # Build shares history rows with deltas
        shares_rows = []
        if company_holdings.shares_history:
            shares_dicts = [
                {
                    'date': s.date,
                    'shares_outstanding': s.shares_outstanding,
                    'source': s.source,
                    'method': s.method,
                    'accession_number': s.accession_number,
                    'notes': s.notes
                }
                for s in company_holdings.shares_history
            ]
            shares_with_deltas = self._calculate_history_deltas(shares_dicts, 'shares_outstanding')

            for entry in reversed(shares_with_deltas):  # Most recent first
                date_str = entry.get('date', 'N/A')
                shares = entry.get('shares_outstanding', 0)
                source = entry.get('source', 'N/A')
                method = entry.get('method') or 'N/A'
                accession = entry.get('accession_number')
                notes = entry.get('notes') or ''
                delta = entry.get('delta')
                delta_pct = entry.get('delta_percent')

                is_estimate = method == "vwap_estimate"
                row_class = ' class="estimated"' if is_estimate else ''

                delta_str = "--" if delta is None else f"{delta:+,.0f}"
                delta_pct_str = "--" if delta_pct is None else f"{delta_pct:+.2f}%"

                # Method display
                if is_estimate:
                    method_html = '<span class="method-estimated">estimated</span>'
                else:
                    method_html = method

                # Filing type badge — no badge for estimates (no accession number)
                if is_estimate:
                    source_html = '<span style="color:#9f7aea;font-style:normal;">ATM dilution</span>'
                else:
                    filing_badge = self._filing_type_badge(source)
                    sec_url = self._build_sec_filing_url(cik, accession) if accession else None
                    if sec_url:
                        source_html = f'<a href="{sec_url}" target="_blank">{filing_badge}</a>'
                    else:
                        source_html = filing_badge

                # Truncate notes for display
                notes_display = (notes[:120] + '...') if len(notes) > 120 else notes

                shares_rows.append(f"""
                <tr{row_class}>
                    <td>{date_str}</td>
                    <td class="number">{shares:,.0f}</td>
                    <td class="number">{delta_str}</td>
                    <td class="number">{delta_pct_str}</td>
                    <td>{method_html}</td>
                    <td>{source_html}</td>
                    <td class="notes">{notes_display}</td>
                </tr>
                """)
        else:
            shares_rows.append('<tr><td colspan="7">No shares history available</td></tr>')

        # Build other holdings section
        other_holdings_html = ""
        if hasattr(company_holdings, 'other_holdings') and company_holdings.other_holdings:
            other_rows = []
            for holding in company_holdings.other_holdings:
                h_type = holding.get('type', 'N/A')
                h_name = holding.get('name') or holding.get('ticker', 'N/A')
                h_value = holding.get('value_usd')
                # For digital assets, compute live value from units * current price
                if holding.get('type') == 'digital_asset' and holding.get('units') and holding.get('ticker'):
                    h_ticker = holding['ticker']
                    prices = all_crypto_prices or {}
                    if h_ticker in prices:
                        h_value = holding['units'] * prices[h_ticker]
                # For public equity, compute live value from shares * stock price
                if holding.get('type') == 'public_equity' and holding.get('shares') and holding.get('ticker'):
                    stocks = all_stock_data or {}
                    eq_stock = stocks.get(holding['ticker'])
                    if eq_stock and eq_stock.price:
                        h_value = holding['shares'] * eq_stock.price
                h_date = holding.get('date', 'N/A')
                h_notes = holding.get('notes', '')
                h_source = holding.get('source', '')
                h_accession = holding.get('accession_number')

                value_str = f"${h_value:,.0f}" if h_value else "N/A"

                # Filing type badge with SEC link
                filing_badge = self._filing_type_badge(h_source) if h_source else ''
                sec_url = self._build_sec_filing_url(cik, h_accession) if h_accession else None
                if sec_url:
                    filing_html = f'<a href="{sec_url}" target="_blank">{filing_badge}</a>'
                else:
                    filing_html = filing_badge

                other_rows.append(f"""
                <tr>
                    <td>{h_type}</td>
                    <td>{h_name}</td>
                    <td class="number">{value_str}</td>
                    <td>{h_date}</td>
                    <td>{filing_html}</td>
                    <td class="notes">{h_notes}</td>
                </tr>
                """)

            other_holdings_html = f"""
            <h2>Other Holdings</h2>
            <table>
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>Name</th>
                        <th>Value</th>
                        <th>Date</th>
                        <th>Filing</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(other_rows)}
                </tbody>
            </table>
            """

        # Calculate summary values
        treasury_value = (current_metrics.treasury_units or 0) * crypto_price if crypto_price else None
        nav_value_str = self._format_number(current_metrics.nav) if current_metrics.nav else "N/A"
        # Digital assets + other holdings (NAV minus cash)
        digital_holdings_value = None
        if current_metrics.nav is not None:
            digital_holdings_value = current_metrics.nav - (current_metrics.cash or 0)
        digital_holdings_str = self._format_number(digital_holdings_value) if digital_holdings_value else "N/A"
        treasury_units_str = f"{current_metrics.treasury_units:,.0f} {asset}" if current_metrics.treasury_units else "N/A"
        shares_str = f"{current_metrics.shares_outstanding:,.0f}" if current_metrics.shares_outstanding else "N/A"
        mnav_str = self._format_ratio(current_metrics.mnav)
        mcap_nav_str = self._format_ratio(current_metrics.mcap_nav)
        nav_per_share_str = f"${current_metrics.nav_per_share:,.2f}" if current_metrics.nav_per_share else "N/A"
        market_cap_str = self._format_number(current_metrics.market_cap) if current_metrics.market_cap else "N/A"
        ev_str = self._format_number(current_metrics.enterprise_value) if current_metrics.enterprise_value else "N/A"
        debt_str = self._format_number(current_metrics.total_debt) if current_metrics.total_debt else "N/A"
        cash_str = self._format_number(current_metrics.cash) if current_metrics.cash else "N/A"

        # Dashboard source badge
        is_dashboard = current_metrics.shares_source == "dashboard"
        dashboard_badge = ""
        if is_dashboard and current_metrics.treasury_source == "dashboard":
            source_url = current_metrics.dashboard_source_url or ''
            source_display = source_url.replace("https://", "").replace("http://", "").rstrip("/") if source_url else "company dashboard"
            dashboard_badge = (
                f'<div style="background:#f0fff4;border:1px solid #c6f6d5;border-radius:8px;'
                f'padding:10px 15px;margin-bottom:20px;font-size:13px;color:#22543d;">'
                f'<strong>Primary Source:</strong> Key metrics (treasury, market cap, mNAV) sourced from '
                f'<a href="{source_url}" target="_blank" style="color:#2b6cb0;">{source_display}</a>'
                f'</div>'
            )

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{ticker} - {name} | DAT Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.5;
            color: #1a202c;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f7fafc;
        }}
        .header {{
            background: linear-gradient(135deg, #1a365d 0%, #2d3748 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0 0 5px 0;
            font-size: 28px;
        }}
        .header .subtitle {{
            opacity: 0.9;
            font-size: 14px;
        }}
        .back-link {{
            color: white;
            text-decoration: none;
            opacity: 0.8;
            font-size: 14px;
        }}
        .back-link:hover {{
            opacity: 1;
            text-decoration: underline;
        }}
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .card .label {{
            font-size: 12px;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .card .value {{
            font-size: 24px;
            font-weight: 600;
            color: #2d3748;
            margin-top: 5px;
        }}
        h2 {{
            color: #2d3748;
            font-size: 18px;
            margin-top: 30px;
            margin-bottom: 15px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        th {{
            background: #2d3748;
            color: white;
            padding: 12px 10px;
            text-align: left;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #e2e8f0;
            font-size: 13px;
        }}
        tr:hover {{
            background-color: #f7fafc;
        }}
        th {{
            text-align: center;
        }}
        .number {{
            text-align: center;
            font-family: 'SF Mono', Monaco, monospace;
        }}
        .notes {{
            font-size: 12px;
            color: #4a5568;
            max-width: 300px;
        }}
        tr.estimated {{
            background-color: #f0f4ff;
            font-style: italic;
        }}
        tr.estimated td {{
            color: #5a6577;
        }}
        .method-estimated {{
            display: inline-block;
            background: #9f7aea;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            font-style: normal;
        }}
        a {{
            color: #2b6cb0;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .footer {{
            text-align: center;
            color: #718096;
            font-size: 12px;
            margin-top: 30px;
            padding: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <a href="../dat_report_{self.report_date.strftime('%Y-%m-%d')}.html" class="back-link">&larr; Back to Dashboard</a>
        <h1>{ticker} - {name}</h1>
        <div class="subtitle">Primary Asset: {asset} | Generated: {self.report_date.strftime('%Y-%m-%d %H:%M:%S')} ET</div>
    </div>

    {dashboard_badge}

    <div class="summary-cards">
        <div class="card">
            <div class="label">Stock Price</div>
            <div class="value">${current_metrics.stock_price:,.2f}</div>
        </div>
        <div class="card">
            <div class="label">{asset} Price</div>
            <div class="value">${crypto_price:,.2f}</div>
        </div>
        <div class="card">
            <div class="label">Treasury ({treasury_units_str})</div>
            <div class="value">{digital_holdings_str}</div>
        </div>
        <div class="card">
            <div class="label">Cash</div>
            <div class="value">{cash_str}</div>
        </div>
        <div class="card">
            <div class="label">NAV</div>
            <div class="value">{nav_value_str}</div>
        </div>
        <div class="card">
            <div class="label">Shares Outstanding</div>
            <div class="value">{shares_str}</div>
            <div style="font-size:11px;color:#718096;margin-top:3px;">Source: {current_metrics.shares_source}</div>
        </div>
        <div class="card">
            <div class="label">NAV per Share</div>
            <div class="value">{nav_per_share_str}</div>
        </div>
        <div class="card">
            <div class="label">Market Cap</div>
            <div class="value">{market_cap_str}</div>
        </div>
        <div class="card">
            <div class="label">Enterprise Value</div>
            <div class="value">{ev_str}</div>
        </div>
        <div class="card">
            <div class="label">Total Debt</div>
            <div class="value">{debt_str}</div>
        </div>
        <div class="card">
            <div class="label">Mcap/NAV</div>
            <div class="value">{mcap_nav_str}</div>
        </div>
        <div class="card">
            <div class="label">mNAV</div>
            <div class="value">{mnav_str}</div>
        </div>
    </div>

    <h2>Treasury History</h2>
    <table>
        <thead>
            <tr>
                <th>Date</th>
                <th>Units</th>
                <th>Change</th>
                <th>Change %</th>
                <th>Filing</th>
                <th>Notes</th>
            </tr>
        </thead>
        <tbody>
            {''.join(treasury_rows)}
        </tbody>
    </table>

    <h2>Shares Outstanding History</h2>
    <table>
        <thead>
            <tr>
                <th>Date</th>
                <th>Shares</th>
                <th>Change</th>
                <th>Change %</th>
                <th>Method</th>
                <th>Filing</th>
                <th>Notes</th>
            </tr>
        </thead>
        <tbody>
            {''.join(shares_rows)}
        </tbody>
    </table>

    {other_holdings_html}

    <div class="footer">
        Generated by DAT Dashboard | Data sources: {'Company Dashboard, ' if is_dashboard else ''}Bloomberg, CoinGecko, SEC EDGAR
    </div>
</body>
</html>
"""
        return html

    def generate_html(self, metrics: List[CompanyMetrics], crypto_prices: Dict[str, float]) -> str:
        """Generate HTML report."""
        # Sort by market cap descending (largest first)
        sorted_metrics = sorted(
            metrics,
            key=lambda x: x.market_cap if x.market_cap is not None else float('-inf'),
            reverse=True
        )

        rows = []
        for m in sorted_metrics:
            # Determine color classes for performance
            def perf_class(val):
                if val is None:
                    return ""
                return "positive" if val > 0 else "negative" if val < 0 else ""

            nav_per_share_str = f"${m.nav_per_share:,.2f}" if m.nav_per_share else "N/A"
            shares_str = f"{m.shares_outstanding/1_000_000:,.1f}M" if m.shares_outstanding else "N/A"
            updated_str = m.treasury_date if m.treasury_date else "N/A"
            if m.avg_volume_5d and m.stock_price:
                dollar_vol = m.avg_volume_5d * m.stock_price
                avg_vol_str = self._format_number(dollar_vol)
            else:
                avg_vol_str = "N/A"
            rows.append(f"""
            <tr>
                <td class="ticker"><strong><a href="companies/{m.ticker.lower()}.html">{m.ticker}</a></strong></td>
                <td>{m.name[:20]}...</td>
                <td>{m.primary_asset}</td>
                <td class="number">${m.stock_price:,.2f}</td>
                <td class="number">{self._format_units(m.treasury_units, m.primary_asset)}</td>
                <td class="number">{shares_str}</td>
                <td class="number">{self._format_number(m.nav)}</td>
                <td class="number">{nav_per_share_str}</td>
                <td class="number">{self._format_number(m.market_cap)}</td>
                <td class="number">{self._format_ratio(m.mcap_nav)}</td>
                <td class="number">{self._format_ratio(m.mnav)}</td>
                <td class="number">{avg_vol_str}</td>
                <td class="number {perf_class(m.rel_perf_7d)}">{self._format_percent(m.rel_perf_7d)}</td>
                <td class="number {perf_class(m.rel_perf_30d)}">{self._format_percent(m.rel_perf_30d)}</td>
                <td class="number">{updated_str}</td>
            </tr>
            """)

        # Crypto prices summary
        crypto_rows = []
        for asset, price in crypto_prices.items():
            crypto_rows.append(f"<span class='crypto-badge'>{asset}: ${price:,.2f}</span>")

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.5;
            color: #1a202c;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f7fafc;
        }}
        .header {{
            background: linear-gradient(135deg, #1a365d 0%, #2d3748 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .header .subtitle {{
            opacity: 0.9;
            font-size: 14px;
        }}
        .crypto-prices {{
            background: white;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .crypto-badge {{
            display: inline-block;
            background: #edf2f7;
            padding: 5px 12px;
            border-radius: 20px;
            margin-right: 10px;
            font-weight: 500;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th {{
            background: #2d3748;
            color: white;
            padding: 15px 10px;
            text-align: center;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            cursor: pointer;
            user-select: none;
        }}
        th:hover {{
            background: #4a5568;
        }}
        th .sort-arrow {{
            font-size: 10px;
            margin-left: 4px;
            opacity: 0.5;
        }}
        th.sort-active .sort-arrow {{
            opacity: 1;
        }}
        td {{
            padding: 12px 10px;
            border-bottom: 1px solid #e2e8f0;
            font-size: 13px;
            text-align: center;
        }}
        tr:hover {{
            background-color: #f7fafc;
        }}
        .ticker {{
            font-weight: 600;
            color: #2b6cb0;
        }}
        .ticker a {{
            color: #2b6cb0;
            text-decoration: none;
        }}
        .ticker a:hover {{
            text-decoration: underline;
        }}
        .number {{
            text-align: center;
            font-family: 'SF Mono', Monaco, monospace;
        }}
        .positive {{
            color: #22543d;
            background-color: #c6f6d5;
        }}
        .negative {{
            color: #742a2a;
            background-color: #fed7d7;
        }}
        .footer {{
            text-align: center;
            color: #718096;
            font-size: 12px;
            margin-top: 30px;
            padding: 20px;
        }}
        .legend {{
            background: white;
            padding: 15px 20px;
            border-radius: 8px;
            margin-top: 20px;
            font-size: 12px;
            color: #4a5568;
        }}
        .legend strong {{
            color: #2d3748;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Digital Asset Treasury Dashboard</h1>
        <div class="subtitle">
            Generated: {self.report_date.strftime('%Y-%m-%d %H:%M:%S')} ET
        </div>
    </div>

    <div class="crypto-prices">
        <strong>Crypto Prices:</strong> {' '.join(crypto_rows)}
    </div>

    <table id="dashboard-table">
        <thead>
            <tr>
                <th>Ticker</th>
                <th>Company</th>
                <th>Asset</th>
                <th>Price</th>
                <th>Treasury</th>
                <th>Shares</th>
                <th>NAV</th>
                <th>NAV/Shr</th>
                <th>Mkt Cap</th>
                <th>Mcap/NAV</th>
                <th>mNAV</th>
                <th>Avg Vol ($)</th>
                <th>7D Rel</th>
                <th>30D Rel</th>
                <th>Last Updated</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>

    <script>
    (function() {{
        const table = document.getElementById('dashboard-table');
        const headers = table.querySelectorAll('th');
        let sortCol = -1, sortAsc = true;

        function parseVal(text) {{
            text = text.trim().replace(/,/g, '');
            if (text === 'N/A' || text === '--') return null;
            // Strip $, %, x, +, and suffix multipliers
            let m = text.replace(/[$%x+]/gi, '').trim();
            // Handle B/M/K suffixes
            let mult = 1;
            if (/B$/i.test(m)) {{ mult = 1e9; m = m.slice(0, -1); }}
            else if (/M$/i.test(m)) {{ mult = 1e6; m = m.slice(0, -1); }}
            else if (/K$/i.test(m)) {{ mult = 1e3; m = m.slice(0, -1); }}
            let num = parseFloat(m);
            return isNaN(num) ? null : num * mult;
        }}

        headers.forEach((th, idx) => {{
            th.innerHTML += ' <span class="sort-arrow">&#x25B2;</span>';
            th.addEventListener('click', () => {{
                if (sortCol === idx) {{ sortAsc = !sortAsc; }}
                else {{ sortCol = idx; sortAsc = true; }}

                headers.forEach(h => h.classList.remove('sort-active'));
                th.classList.add('sort-active');
                th.querySelector('.sort-arrow').innerHTML = sortAsc ? '&#x25B2;' : '&#x25BC;';

                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                rows.sort((a, b) => {{
                    let aText = a.cells[idx].textContent;
                    let bText = b.cells[idx].textContent;
                    let aVal = parseVal(aText);
                    let bVal = parseVal(bText);
                    // Nulls last
                    if (aVal === null && bVal === null) return 0;
                    if (aVal === null) return 1;
                    if (bVal === null) return -1;
                    if (aVal !== null && bVal !== null) {{
                        return sortAsc ? aVal - bVal : bVal - aVal;
                    }}
                    // Text sort fallback
                    return sortAsc ? aText.localeCompare(bText) : bText.localeCompare(aText);
                }});
                rows.forEach(r => tbody.appendChild(r));
            }});
        }});
    }})();
    </script>

    <div class="legend">
        <strong>Legend:</strong>
        Mcap/NAV = Market Cap / NAV |
        mNAV = Enterprise Value / NAV (>1x = premium, <1x = discount) |
        Rel = Stock performance vs underlying crypto asset |
        Last Updated = Date of last holdings update
    </div>

    <div class="footer">
        Generated by DAT Dashboard | Data sources: Bloomberg, CoinGecko, SEC EDGAR
    </div>
</body>
</html>
"""
        return html

    def generate_plain_text(self, metrics: List[CompanyMetrics], crypto_prices: Dict[str, float]) -> str:
        """Generate plain text report."""
        lines = [
            "=" * 80,
            "DIGITAL ASSET TREASURY DASHBOARD",
            f"Generated: {self.report_date.strftime('%Y-%m-%d %H:%M:%S')} ET",
            "=" * 80,
            "",
            "CRYPTO PRICES:",
        ]

        for asset, price in crypto_prices.items():
            lines.append(f"  {asset}: ${price:,.2f}")

        lines.extend(["", "-" * 80, ""])

        # Sort by market cap descending
        sorted_metrics = sorted(
            metrics,
            key=lambda x: x.market_cap if x.market_cap is not None else float('-inf'),
            reverse=True
        )

        for m in sorted_metrics:
            nav_per_share_str = f"${m.nav_per_share:,.2f}" if m.nav_per_share else "N/A"
            shares_str = f"{m.shares_outstanding:,.0f}" if m.shares_outstanding else "N/A"
            updated_str = m.treasury_date if m.treasury_date else "N/A"
            lines.extend([
                f"{m.ticker} - {m.name}",
                f"  Primary Asset: {m.primary_asset}",
                f"  Stock Price: ${m.stock_price:,.2f}" if m.stock_price else "  Stock Price: N/A",
                f"  Treasury: {self._format_units(m.treasury_units, m.primary_asset)}",
                f"  Shares Outstanding: {shares_str}",
                f"  NAV: {self._format_number(m.nav)}",
                f"  NAV/Share: {nav_per_share_str}",
                f"  Market Cap: {self._format_number(m.market_cap)}",
                f"  Mcap/NAV: {self._format_ratio(m.mcap_nav)}",
                f"  mNAV: {self._format_ratio(m.mnav)}",
                f"  7D Relative Perf: {self._format_percent(m.rel_perf_7d)}",
                f"  30D Relative Perf: {self._format_percent(m.rel_perf_30d)}",
                f"  Holdings Updated: {updated_str}",
                "-" * 40,
            ])

        lines.extend([
            "",
            "Data sources: Bloomberg, CoinGecko, SEC EDGAR",
        ])

        return "\n".join(lines)
