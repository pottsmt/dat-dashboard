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
    avg_volume_30d: Optional[float] = None
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
    nav: Optional[float] = None  # Treasury value
    nav_per_share: Optional[float] = None
    mnav: Optional[float] = None  # Market cap / NAV
    ev_nav: Optional[float] = None  # EV / NAV

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

    def calculate_derived_metrics(self):
        """Calculate NAV, mNAV, EV/NAV from component data."""
        # NAV = treasury units * crypto price
        if self.treasury_units and self.crypto_price:
            self.nav = self.treasury_units * self.crypto_price

            # NAV per share
            if self.shares_outstanding:
                self.nav_per_share = self.nav / self.shares_outstanding

        # mNAV = market cap / NAV
        if self.market_cap and self.nav:
            self.mnav = self.market_cap / self.nav

        # EV/NAV = enterprise value / NAV
        if self.enterprise_value and self.nav:
            self.ev_nav = self.enterprise_value / self.nav

        # Relative performance = stock perf - crypto perf
        if self.stock_perf_3d is not None and self.crypto_perf_3d is not None:
            self.rel_perf_3d = self.stock_perf_3d - self.crypto_perf_3d
        if self.stock_perf_7d is not None and self.crypto_perf_7d is not None:
            self.rel_perf_7d = self.stock_perf_7d - self.crypto_perf_7d
        if self.stock_perf_30d is not None and self.crypto_perf_30d is not None:
            self.rel_perf_30d = self.stock_perf_30d - self.crypto_perf_30d


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
        return f"{value:,.4f} {asset}"

    def generate_html(self, metrics: List[CompanyMetrics], crypto_prices: Dict[str, float]) -> str:
        """Generate HTML report."""
        # Sort by mNAV descending (highest premium first)
        sorted_metrics = sorted(
            metrics,
            key=lambda x: x.mnav if x.mnav is not None else float('-inf'),
            reverse=True
        )

        rows = []
        for m in sorted_metrics:
            # Determine color classes for performance
            def perf_class(val):
                if val is None:
                    return ""
                return "positive" if val > 0 else "negative" if val < 0 else ""

            def nav_class(val):
                if val is None:
                    return ""
                return "premium" if val > 1 else "discount"

            nav_per_share_str = f"${m.nav_per_share:,.2f}" if m.nav_per_share else "N/A"
            shares_str = f"{m.shares_outstanding/1_000_000:,.1f}M" if m.shares_outstanding else "N/A"
            rows.append(f"""
            <tr>
                <td class="ticker"><strong>{m.ticker}</strong></td>
                <td>{m.name[:20]}...</td>
                <td>{m.primary_asset}</td>
                <td class="number">${m.stock_price:,.2f}</td>
                <td class="number">{self._format_units(m.treasury_units, m.primary_asset)}</td>
                <td class="number">{shares_str}</td>
                <td class="number">{self._format_number(m.nav)}</td>
                <td class="number">{nav_per_share_str}</td>
                <td class="number">{self._format_number(m.market_cap)}</td>
                <td class="number {nav_class(m.mnav)}">{self._format_ratio(m.mnav)}</td>
                <td class="number {nav_class(m.ev_nav)}">{self._format_ratio(m.ev_nav)}</td>
                <td class="number {perf_class(m.rel_perf_7d)}">{self._format_percent(m.rel_perf_7d)}</td>
                <td class="number {perf_class(m.rel_perf_30d)}">{self._format_percent(m.rel_perf_30d)}</td>
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
            text-align: left;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        td {{
            padding: 12px 10px;
            border-bottom: 1px solid #e2e8f0;
            font-size: 13px;
        }}
        tr:hover {{
            background-color: #f7fafc;
        }}
        .ticker {{
            font-weight: 600;
            color: #2b6cb0;
        }}
        .number {{
            text-align: right;
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
        .premium {{
            color: #744210;
            background-color: #fefcbf;
        }}
        .discount {{
            color: #22543d;
            background-color: #c6f6d5;
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

    <table>
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
                <th>mNAV</th>
                <th>EV/NAV</th>
                <th>7D Rel</th>
                <th>30D Rel</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>

    <div class="legend">
        <strong>Legend:</strong>
        mNAV = Market Cap / NAV (>1x = premium, <1x = discount) |
        EV/NAV = Enterprise Value / NAV |
        Rel = Stock performance vs underlying crypto asset
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

        # Sort by mNAV
        sorted_metrics = sorted(
            metrics,
            key=lambda x: x.mnav if x.mnav is not None else float('-inf'),
            reverse=True
        )

        for m in sorted_metrics:
            nav_per_share_str = f"${m.nav_per_share:,.2f}" if m.nav_per_share else "N/A"
            shares_str = f"{m.shares_outstanding:,.0f}" if m.shares_outstanding else "N/A"
            lines.extend([
                f"{m.ticker} - {m.name}",
                f"  Primary Asset: {m.primary_asset}",
                f"  Stock Price: ${m.stock_price:,.2f}" if m.stock_price else "  Stock Price: N/A",
                f"  Treasury: {self._format_units(m.treasury_units, m.primary_asset)}",
                f"  Shares Outstanding: {shares_str}",
                f"  NAV: {self._format_number(m.nav)}",
                f"  NAV/Share: {nav_per_share_str}",
                f"  Market Cap: {self._format_number(m.market_cap)}",
                f"  mNAV: {self._format_ratio(m.mnav)}",
                f"  EV/NAV: {self._format_ratio(m.ev_nav)}",
                f"  7D Relative Perf: {self._format_percent(m.rel_perf_7d)}",
                f"  30D Relative Perf: {self._format_percent(m.rel_perf_30d)}",
                "-" * 40,
            ])

        lines.extend([
            "",
            "Data sources: Bloomberg, CoinGecko, SEC EDGAR",
        ])

        return "\n".join(lines)
