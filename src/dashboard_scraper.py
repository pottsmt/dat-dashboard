"""
Selenium-based dashboard scraper for company-owned primary source data.

Scrapes authoritative metrics (market cap, treasury holdings, mNAV) directly
from company dashboards like strategy.com. These override computed values
from SEC filings + yfinance since the company's own numbers are more current.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


@dataclass
class DashboardData:
    """Structured data scraped from a company dashboard."""
    ticker: str
    market_cap: Optional[float] = None        # In USD
    enterprise_value: Optional[float] = None  # In USD
    treasury_units: Optional[float] = None     # e.g. 714,644 BTC
    mnav: Optional[float] = None               # EV/NAV (only set when dashboard reports EV/NAV)
    mcap_nav: Optional[float] = None           # Market Cap / NAV
    shares_outstanding: Optional[float] = None  # If directly available
    total_debt: Optional[float] = None         # In USD
    cash: Optional[float] = None               # In USD
    source_url: str = ""
    scraped_at: Optional[datetime] = None

    def to_dict(self) -> Dict:
        """Serialize to JSON-compatible dict."""
        d = {
            "ticker": self.ticker,
            "market_cap": self.market_cap,
            "enterprise_value": self.enterprise_value,
            "treasury_units": self.treasury_units,
            "mnav": self.mnav,
            "mcap_nav": self.mcap_nav,
            "shares_outstanding": self.shares_outstanding,
            "total_debt": self.total_debt,
            "cash": self.cash,
            "source_url": self.source_url,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "DashboardData":
        """Deserialize from JSON-compatible dict."""
        scraped_at = None
        if d.get("scraped_at"):
            scraped_at = datetime.fromisoformat(d["scraped_at"])
        return cls(
            ticker=d.get("ticker", ""),
            market_cap=d.get("market_cap"),
            enterprise_value=d.get("enterprise_value"),
            treasury_units=d.get("treasury_units"),
            mnav=d.get("mnav"),
            mcap_nav=d.get("mcap_nav"),
            shares_outstanding=d.get("shares_outstanding"),
            total_debt=d.get("total_debt"),
            cash=d.get("cash"),
            source_url=d.get("source_url", ""),
            scraped_at=scraped_at,
        )


# =========================================================================
# Dashboard cache — stale data is far better than bad yfinance fallback
# =========================================================================
CACHE_PATH = Path(__file__).parent.parent / "data" / "dashboard_cache.json"
CACHE_MAX_AGE_HOURS = 72  # 3 days


def _load_cache() -> Dict[str, DashboardData]:
    """Load cached dashboard data from disk."""
    if not CACHE_PATH.exists():
        return {}
    try:
        with open(CACHE_PATH, "r") as f:
            raw = json.load(f)
        return {ticker: DashboardData.from_dict(entry) for ticker, entry in raw.items()}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"   Dashboard cache: Error loading cache: {e}")
        return {}


def _save_cache(cache: Dict[str, DashboardData]):
    """Write cache dict to disk."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = {ticker: data.to_dict() for ticker, data in cache.items()}
    with open(CACHE_PATH, "w") as f:
        json.dump(raw, f, indent=2)


def _is_cache_fresh(data: DashboardData) -> bool:
    """Check if cached entry is within CACHE_MAX_AGE_HOURS."""
    if not data.scraped_at:
        return False
    age = datetime.now() - data.scraped_at
    return age < timedelta(hours=CACHE_MAX_AGE_HOURS)


def _parse_number(text: str) -> Optional[float]:
    """Parse a formatted number string into a float.

    Handles formats like:
        "714,644"      -> 714644.0
        "$98.5B"       -> 98_500_000_000.0
        "$1.2T"        -> 1_200_000_000_000.0
        "$450.3M"      -> 450_300_000.0
        "1.84x"        -> 1.84
        "1.84"         -> 1.84
        "$97,234.50"   -> 97234.50
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Remove currency symbols and whitespace
    text = text.replace("$", "").replace("€", "").replace("£", "").strip()

    # Remove trailing 'x' or '×' (for ratios like "1.84x" or "0.59×")
    if text.lower().endswith("x") or text.endswith("\u00d7"):
        text = text[:-1].strip()

    # Handle suffix multipliers (B, T, M, K)
    multiplier = 1
    if text.upper().endswith("T"):
        multiplier = 1_000_000_000_000
        text = text[:-1].strip()
    elif text.upper().endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1].strip()
    elif text.upper().endswith("M"):
        multiplier = 1_000_000
        text = text[:-1].strip()
    elif text.upper().endswith("K"):
        multiplier = 1_000
        text = text[:-1].strip()

    # Remove commas
    text = text.replace(",", "")

    # Remove any remaining non-numeric characters except '.' and '-'
    text = re.sub(r"[^\d.\-]", "", text)

    if not text:
        return None

    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _get_page_lines(driver, wait_time=6) -> Tuple[List[str], Dict[str, str], str]:
    """Get page text and build label->value dict from adjacent lines.

    Pre-processes lines to merge bare "$" with the following line (handles
    dashboards that render "$ \\n 62.227M" as separate lines).

    Returns:
        (lines, label_values, raw_page_text)
    """
    time.sleep(wait_time)
    page_text = driver.find_element(By.TAG_NAME, "body").text
    raw_lines = [line.strip() for line in page_text.splitlines() if line.strip()]

    # Merge bare "$" lines with the next line
    lines = []
    i = 0
    while i < len(raw_lines):
        if raw_lines[i] == "$" and i + 1 < len(raw_lines):
            lines.append("$" + raw_lines[i + 1])
            i += 2
        else:
            lines.append(raw_lines[i])
            i += 1

    label_values = {}
    for i, line in enumerate(lines):
        if i + 1 < len(lines):
            label_values[line] = lines[i + 1]

    return lines, label_values, page_text


class DashboardScraper:
    """Scrapes company-owned dashboards for authoritative metrics."""

    SUPPORTED_TICKERS = {
        "MSTR", "SBET", "BNC", "DFDV", "NAKA", "LITS", "PAPL",
        "PURR", "FGNX", "EMPD", "ASST", "AVX", "IPST",
    }

    def __init__(self, chrome_path: Optional[str] = None):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self._driver = None

    def _get_driver(self):
        """Create and return a headless Chrome driver."""
        if self._driver is not None:
            return self._driver

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        options.binary_location = self.chrome_path

        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=options)
        self._driver.set_page_load_timeout(30)
        return self._driver

    def scrape(self, ticker: str, dashboard_url: str) -> Optional[DashboardData]:
        """Scrape a company dashboard and return structured data."""
        ticker = ticker.upper()

        scraper_map = {
            "MSTR": self._scrape_strategy,
            "SBET": self._scrape_sharplink,
            "BNC": self._scrape_bnc,
            "DFDV": self._scrape_dfdv,
            "NAKA": self._scrape_naka,
            "LITS": self._scrape_lits,
            "PAPL": self._scrape_papl,
            "PURR": self._scrape_purr,
            "FGNX": self._scrape_fgnx,
            "EMPD": self._scrape_empd,
            "ASST": self._scrape_asst,
            "AVX": self._scrape_avx,
            "IPST": self._scrape_ipst,
        }

        scraper_fn = scraper_map.get(ticker)
        if not scraper_fn:
            print(f"   Dashboard scraper: No scraper implemented for {ticker}")
            return None

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                driver = self._get_driver()
                driver.get(dashboard_url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                data = scraper_fn(driver)
                if data:
                    data.ticker = ticker
                    data.source_url = dashboard_url
                    data.scraped_at = datetime.now()
                    return data
                # Scraper returned None — retry if first attempt
                if attempt < max_attempts:
                    print(f"   Dashboard scraper: {ticker} returned no data, retrying in 3s...")
                    time.sleep(3)
                    continue
                return None
            except Exception as e:
                if attempt < max_attempts:
                    print(f"   Dashboard scraper: {ticker} error (attempt {attempt}), retrying in 3s: {e}")
                    time.sleep(3)
                else:
                    print(f"   Dashboard scraper: Error scraping {ticker} from {dashboard_url}: {e}")
                    return None
        return None

    # =========================================================================
    # MSTR — strategy.com
    # =========================================================================
    def _scrape_strategy(self, driver) -> Optional[DashboardData]:
        """Parse strategy.com for MSTR data.

        Labels have ($M) suffix meaning values are in millions.
        mNAV on strategy.com = EV/NAV.
        """
        data = DashboardData(ticker="MSTR")
        lines, lv, page_text = _get_page_lines(driver, wait_time=5)

        # BTC Holdings — "BTC" label, value has ₿ prefix
        for label, value in lv.items():
            if label == "BTC" and "\u20bf" in value:
                val = _parse_number(value.replace("\u20bf", ""))
                if val and val > 1000:
                    data.treasury_units = val
                    break
        if not data.treasury_units:
            match = re.search(r"\u20bf([\d,]+)", page_text)
            if match:
                val = _parse_number(match.group(1))
                if val and val > 1000:
                    data.treasury_units = val

        # Market Cap, Enterprise Value, Debt, Cash — all ($M) labels
        for label, value in lv.items():
            ll = label.lower()
            is_millions = "($M)" in label or "(M)" in label
            is_billions = "($B)" in label or "(B)" in label

            if "market cap" in ll and not data.market_cap:
                val = _parse_number(value)
                if val:
                    if is_millions: val *= 1_000_000
                    elif is_billions: val *= 1_000_000_000
                    if val > 1_000_000_000:
                        data.market_cap = val

            elif "enterprise value" in ll and not data.enterprise_value:
                val = _parse_number(value)
                if val:
                    if is_millions: val *= 1_000_000
                    elif is_billions: val *= 1_000_000_000
                    if val > 1_000_000_000:
                        data.enterprise_value = val

            elif ll.startswith("debt") and not data.total_debt:
                val = _parse_number(value)
                if val:
                    if is_millions: val *= 1_000_000
                    elif is_billions: val *= 1_000_000_000
                    data.total_debt = val

            elif ("usd reserve" in ll or "cash" in ll) and not data.cash:
                val = _parse_number(value)
                if val:
                    if is_millions: val *= 1_000_000
                    elif is_billions: val *= 1_000_000_000
                    data.cash = val

        # mNAV — EV/NAV on strategy.com
        for label, value in lv.items():
            if label.lower() == "mnav":
                val = _parse_number(value)
                if val and 0.1 < val < 50:
                    data.mnav = val
                    break

        if data.treasury_units or data.market_cap or data.mnav:
            return data
        print("   Dashboard scraper: Could not extract metrics from strategy.com")
        return None

    # =========================================================================
    # SBET — sharplink.com/eth-dashboard (iframe)
    # =========================================================================
    def _scrape_sharplink(self, driver) -> Optional[DashboardData]:
        """Parse sharplink.com/eth-dashboard for SBET data.

        Dashboard is in an iframe at sharplink-dashboard.vercel.app.
        Fully Diluted mNAV = EV/NAV.
        """
        data = DashboardData(ticker="SBET")
        time.sleep(5)

        page_text = driver.find_element(By.TAG_NAME, "body").text.strip()
        has_dashboard_content = page_text and "TOTAL ETH HOLDINGS" in page_text.upper()
        if not has_dashboard_content:
            page_text = ""
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    src = iframe.get_attribute("src") or ""
                    if "sharplink" in src or "dashboard" in src:
                        driver.switch_to.frame(iframe)
                        time.sleep(5)
                        page_text = driver.find_element(By.TAG_NAME, "body").text.strip()
                        break
                if not page_text:
                    driver.switch_to.default_content()
                    driver.get("https://sharplink-dashboard.vercel.app/")
                    time.sleep(8)
                    page_text = driver.find_element(By.TAG_NAME, "body").text.strip()
            except Exception as e:
                print(f"   Dashboard scraper: Error accessing sharplink iframe: {e}")

        if not page_text:
            print("   Dashboard scraper: No text content from sharplink dashboard")
            return None

        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        lv = {}
        for i, line in enumerate(lines):
            if i + 1 < len(lines):
                lv[line.upper()] = lines[i + 1]

        for label, value in lv.items():
            if "TOTAL ETH HOLDINGS" in label:
                val = _parse_number(value)
                if val and val > 100:
                    data.treasury_units = val
                    break

        for label, value in lv.items():
            if label == "MARKET CAP":
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.market_cap = val
                    break

        for label, value in lv.items():
            if "ENTERPRISE VALUE" in label:
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.enterprise_value = val
                    break

        # Fully Diluted mNAV = EV/NAV
        for label, value in lv.items():
            if "FULLY DILUTED MNAV" in label:
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mnav = val
                    break
        if not data.mnav:
            for label, value in lv.items():
                if "BASIC MNAV" in label or label == "MNAV":
                    val = _parse_number(value)
                    if val and 0.01 < val < 50:
                        data.mnav = val
                        break

        if data.treasury_units or data.market_cap or data.mnav:
            return data
        print("   Dashboard scraper: Could not extract metrics from sharplink")
        return None

    # =========================================================================
    # BNC — ceaindustries.com/dashboard.html
    # =========================================================================
    def _scrape_bnc(self, driver) -> Optional[DashboardData]:
        """Parse CEA Industries dashboard for BNC data.

        Labels: "Total BNB Holdings" → "515,544 BNB", "mNAV" → "0.74x"
        BNC's mNAV = Market Cap / Holdings Value (Mcap/NAV per footnote 8).
        """
        data = DashboardData(ticker="BNC")
        lines, lv, _ = _get_page_lines(driver)

        for label, value in lv.items():
            if "total bnb holdings" in label.lower():
                val = _parse_number(value.split("BNB")[0].strip())
                if val and val > 100:
                    data.treasury_units = val
                    break

        for label, value in lv.items():
            if label.lower() == "mnav":
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mcap_nav = val  # BNC mNAV = Mcap/NAV
                    break

        if data.treasury_units or data.mcap_nav:
            return data
        print("   Dashboard scraper: Could not extract metrics from CEA Industries")
        return None

    # =========================================================================
    # DFDV — defidevcorp.com/dashboard
    # =========================================================================
    def _scrape_dfdv(self, driver) -> Optional[DashboardData]:
        """Parse DeFi Development Corp dashboard for DFDV data.

        Labels: "SOL Count" → "2,221,329", "Market Cap" → "$119.0M",
        "Enterprise Value" → "$276.2M", "Shares Outstanding" → "29,892,800",
        "mNAV" → "0.64" (Mcap/NAV).
        """
        data = DashboardData(ticker="DFDV")
        lines, lv, _ = _get_page_lines(driver)

        for label, value in lv.items():
            if label.lower() == "sol count":
                val = _parse_number(value)
                if val and val > 100:
                    data.treasury_units = val
                    break

        for label, value in lv.items():
            if label.lower() == "market cap":
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.market_cap = val
                    break

        for label, value in lv.items():
            if label.lower() == "enterprise value":
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.enterprise_value = val
                    break

        for label, value in lv.items():
            if label.lower() == "shares outstanding":
                val = _parse_number(value)
                if val and val > 1000:
                    data.shares_outstanding = val
                    break

        for label, value in lv.items():
            if label.lower() == "mnav":
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mcap_nav = val  # DFDV mNAV = Mcap/NAV
                    break

        if data.treasury_units or data.market_cap:
            return data
        print("   Dashboard scraper: Could not extract metrics from DeFi Dev Corp")
        return None

    # =========================================================================
    # NAKA — nakamoto.com/dashboard
    # =========================================================================
    def _scrape_naka(self, driver) -> Optional[DashboardData]:
        """Parse Nakamoto Holdings dashboard for NAKA data.

        This dashboard is heavily JS-rendered and may need extra wait time.
        """
        data = DashboardData(ticker="NAKA")

        # Try longer wait for JS rendering
        time.sleep(10)
        page_text = driver.find_element(By.TAG_NAME, "body").text.strip()

        if not page_text or len(page_text) < 50:
            print("   Dashboard scraper: nakamoto.com page did not render content")
            return None

        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        lv = {}
        for i, line in enumerate(lines):
            if i + 1 < len(lines):
                lv[line] = lines[i + 1]

        # Look for common BTC treasury labels
        for label, value in lv.items():
            ll = label.lower()
            if "btc" in ll and ("holdings" in ll or "held" in ll or "treasury" in ll):
                cleaned = value.replace("\u20bf", "").replace("BTC", "").strip()
                val = _parse_number(cleaned)
                if val and val > 10:
                    data.treasury_units = val
                    break

        # Fallback: regex for ₿ prefix
        if not data.treasury_units:
            match = re.search(r"\u20bf([\d,.]+)", page_text)
            if match:
                val = _parse_number(match.group(1))
                if val and val > 10:
                    data.treasury_units = val

        for label, value in lv.items():
            ll = label.lower()
            if "market cap" in ll:
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.market_cap = val
                    break

        for label, value in lv.items():
            ll = label.lower()
            if "enterprise value" in ll:
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.enterprise_value = val
                    break

        for label, value in lv.items():
            ll = label.lower()
            if ll == "mnav" or "ev mnav" in ll:
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mnav = val
                    break

        if data.treasury_units or data.market_cap or data.mnav:
            return data
        print("   Dashboard scraper: Could not extract metrics from nakamoto.com")
        return None

    # =========================================================================
    # LITS — litestrategy.com/dashboard/
    # =========================================================================
    def _scrape_lits(self, driver) -> Optional[DashboardData]:
        """Parse Lite Strategy dashboard for LITS data.

        Labels: "LTC Holdings" → "929,548.46", "Market Cap" → "$38,808,594",
        "Enterprise Value" → "$28,695,594", "Basic mNAV" → "0.59×".
        LITS Basic mNAV = EV/NAV (verified: $28.7M/$48.5M = 0.59).
        """
        data = DashboardData(ticker="LITS")
        lines, lv, _ = _get_page_lines(driver)

        for label, value in lv.items():
            if label.lower() == "ltc holdings":
                val = _parse_number(value)
                if val and val > 100:
                    data.treasury_units = val
                    break

        for label, value in lv.items():
            if label.lower() == "market cap":
                val = _parse_number(value)
                if val and val > 100_000:
                    data.market_cap = val
                    break

        for label, value in lv.items():
            if label.lower() == "enterprise value":
                val = _parse_number(value)
                if val:  # EV can be small or negative
                    data.enterprise_value = val
                    break

        # Basic mNAV = EV/NAV on Lite Strategy
        for label, value in lv.items():
            if "basic mnav" in label.lower():
                val = _parse_number(value)
                if val and -5 < val < 50:
                    data.mnav = val  # EV/NAV
                    break

        if data.treasury_units or data.market_cap:
            return data
        print("   Dashboard scraper: Could not extract metrics from Lite Strategy")
        return None

    # =========================================================================
    # PAPL — pineappledigitalassets.com/dat-dashboard
    # =========================================================================
    def _scrape_papl(self, driver) -> Optional[DashboardData]:
        """Parse Pineapple Financial dashboard for PAPL data.

        Labels: "TOTAL INJ HOLDINGS" → "7.02M", "USD RESERVE" → "$20.79M",
        "TREASURY VALUE" → "$42.54M", "MNAV" → "0.817".
        PAPL MNAV = Mcap/NAV.
        Market cap is embedded in "INJ PRICE / MARKET CAP" section as "$311.8M".
        """
        data = DashboardData(ticker="PAPL")
        lines, lv, page_text = _get_page_lines(driver)

        for label, value in lv.items():
            if "total inj holdings" in label.lower():
                val = _parse_number(value)
                if val and val > 100:
                    data.treasury_units = val
                    break

        for label, value in lv.items():
            if "usd reserve" in label.lower():
                val = _parse_number(value)
                if val and val > 1000:
                    data.cash = val
                    break

        for label, value in lv.items():
            if label.lower() == "mnav":
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mcap_nav = val  # PAPL MNAV = Mcap/NAV
                    break

        if data.treasury_units or data.mcap_nav:
            return data
        print("   Dashboard scraper: Could not extract metrics from Pineapple Financial")
        return None

    # =========================================================================
    # PURR — hypestrat.xyz/dashboard
    # =========================================================================
    def _scrape_purr(self, driver) -> Optional[DashboardData]:
        """Parse Hyperliquid Strategies dashboard for PURR data.

        Layout has some values on the same line as labels:
        "HYPE Tokens Held (M) 17.6", "Fully Diluted Market Cap ($ in M)" → "$693.7",
        "Fully Diluted Shares (M)" → "150.6",
        "Multiple to Adjusted Net Asset Value" → "1.03x" (Mcap/Adjusted NAV).
        """
        data = DashboardData(ticker="PURR")
        lines, lv, page_text = _get_page_lines(driver)

        # HYPE tokens — value may be on same line: "HYPE Tokens Held (M) 17.6"
        for line in lines:
            match = re.search(r"HYPE Tokens Held \(M\)\s*([\d,.]+)", line)
            if match:
                val = _parse_number(match.group(1))
                if val:
                    data.treasury_units = val * 1_000_000  # (M) suffix
                    break
        # Fallback: label/value
        if not data.treasury_units:
            for label, value in lv.items():
                if "hype tokens held" in label.lower():
                    val = _parse_number(value)
                    if val:
                        if "(m)" in label.lower():
                            val *= 1_000_000
                        data.treasury_units = val
                        break

        # Market cap
        for label, value in lv.items():
            if "fully diluted market cap" in label.lower():
                val = _parse_number(value)
                if val:
                    if "($ in m)" in label.lower() or "(m)" in label.lower():
                        val *= 1_000_000
                    data.market_cap = val
                    break

        # Shares
        for label, value in lv.items():
            if "fully diluted shares" in label.lower():
                val = _parse_number(value)
                if val:
                    if "(m)" in label.lower():
                        val *= 1_000_000
                    data.shares_outstanding = val
                    break

        # Multiple to Adjusted NAV = Mcap/Adjusted NAV
        for label, value in lv.items():
            if "multiple to adjusted net asset value" in label.lower():
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mcap_nav = val
                    break

        if data.treasury_units or data.market_cap or data.mcap_nav:
            return data
        print("   Dashboard scraper: Could not extract metrics from Hyperliquid Strategies")
        return None

    # =========================================================================
    # FGNX — fgnexus.io/nav-tracker
    # =========================================================================
    def _scrape_fgnx(self, driver) -> Optional[DashboardData]:
        """Parse FG Nexus NAV Tracker for FGNX data.

        Labels: "ETH BALANCE" → "37,594 ETH", "MNAV" → "0.74",
        "SHARES OUTSTANDING" → "6.6M", "TOTAL DEBT" → "$1.9M",
        "TOTAL NAV" → "$98.1M".
        FGNX MNAV = Share Price / NAV per Share = Mcap/NAV.
        """
        data = DashboardData(ticker="FGNX")
        lines, lv, _ = _get_page_lines(driver)

        for label, value in lv.items():
            if "eth balance" in label.lower():
                val = _parse_number(value.split("ETH")[0].strip())
                if val and val > 10:
                    data.treasury_units = val
                    break

        for label, value in lv.items():
            if label.lower() == "shares outstanding":
                val = _parse_number(value)
                if val and val > 1000:
                    data.shares_outstanding = val
                    break

        for label, value in lv.items():
            if label.lower() == "total debt":
                val = _parse_number(value)
                if val:
                    data.total_debt = val
                    break

        for label, value in lv.items():
            if label.lower() == "mnav":
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mcap_nav = val  # FGNX MNAV = Mcap/NAV
                    break

        if data.treasury_units or data.mcap_nav:
            return data
        print("   Dashboard scraper: Could not extract metrics from FG Nexus")
        return None

    # =========================================================================
    # EMPD — emperydigital.com/treasury-dashboard
    # =========================================================================
    def _scrape_empd(self, driver) -> Optional[DashboardData]:
        """Parse Empery Digital treasury dashboard for EMPD data.

        Dashboard is behind a cookie consent banner — need to accept it first.
        """
        data = DashboardData(ticker="EMPD")

        # Try to accept the cookie banner
        try:
            accept_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//button[contains(text(), 'Accept all') or contains(text(), 'Accept All')]"))
            )
            accept_btn.click()
            time.sleep(3)
        except Exception:
            pass  # No cookie banner or already accepted

        time.sleep(8)
        page_text = driver.find_element(By.TAG_NAME, "body").text.strip()

        if not page_text or len(page_text) < 100:
            print("   Dashboard scraper: emperydigital.com did not render dashboard content")
            return None

        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        lv = {}
        for i, line in enumerate(lines):
            if i + 1 < len(lines):
                lv[line] = lines[i + 1]

        # Look for BTC holdings
        for label, value in lv.items():
            ll = label.lower()
            if "btc" in ll and ("holdings" in ll or "held" in ll or "treasury" in ll):
                cleaned = value.replace("\u20bf", "").replace("BTC", "").strip()
                val = _parse_number(cleaned)
                if val and val > 10:
                    data.treasury_units = val
                    break

        # Fallback: ₿ regex
        if not data.treasury_units:
            match = re.search(r"\u20bf([\d,.]+)", page_text)
            if match:
                val = _parse_number(match.group(1))
                if val and val > 10:
                    data.treasury_units = val

        for label, value in lv.items():
            ll = label.lower()
            if "market cap" in ll:
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.market_cap = val
                    break

        for label, value in lv.items():
            ll = label.lower()
            if "enterprise value" in ll:
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.enterprise_value = val
                    break

        for label, value in lv.items():
            ll = label.lower()
            if "mnav" in ll:
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    if "ev" in ll:
                        data.mnav = val  # EV/NAV
                    else:
                        data.mcap_nav = val  # Assume Mcap/NAV
                    break

        if data.treasury_units or data.market_cap or data.mnav or data.mcap_nav:
            return data
        print("   Dashboard scraper: Could not extract metrics from Empery Digital")
        return None

    # =========================================================================
    # ASST — treasury.strive.com
    # =========================================================================
    def _scrape_asst(self, driver) -> Optional[DashboardData]:
        """Parse Strive Inc Bitcoin Strategy Tracker for ASST data.

        Labels: "BTC Holdings" → "₿13,131.8", "Total Market Cap" → "$550.41M",
        "Enterprise Value" → "$857.56M", "EV mNAV" → "0.95x" (EV/NAV),
        "Total Debt Outstanding" → "$10.00M".
        Also has "Market Cap vs. BTC NAV" → "0.61x" (Mcap/NAV).
        """
        data = DashboardData(ticker="ASST")
        lines, lv, page_text = _get_page_lines(driver)

        # BTC Holdings — may have ₿ prefix
        for label, value in lv.items():
            if label.lower() == "btc holdings":
                cleaned = value.replace("\u20bf", "").replace("BTC", "").strip()
                val = _parse_number(cleaned)
                if val and val > 10:
                    data.treasury_units = val
                    break
        if not data.treasury_units:
            match = re.search(r"\u20bf([\d,.]+)", page_text)
            if match:
                val = _parse_number(match.group(1))
                if val and val > 10:
                    data.treasury_units = val

        for label, value in lv.items():
            if label.lower() == "total market cap":
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.market_cap = val
                    break

        for label, value in lv.items():
            if label.lower() == "enterprise value":
                val = _parse_number(value)
                if val and val > 1_000_000:
                    data.enterprise_value = val
                    break

        for label, value in lv.items():
            if label.lower() == "total debt outstanding":
                val = _parse_number(value)
                if val:
                    data.total_debt = val
                    break

        # EV mNAV = EV/NAV (explicitly labeled)
        for label, value in lv.items():
            if "ev mnav" in label.lower():
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mnav = val
                    break

        # Market Cap vs. BTC NAV = Mcap/NAV
        for label, value in lv.items():
            if "market cap vs" in label.lower() and "nav" in label.lower():
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mcap_nav = val
                    break

        if data.treasury_units or data.market_cap or data.mnav:
            return data
        print("   Dashboard scraper: Could not extract metrics from Strive")
        return None

    # =========================================================================
    # AVX — analytics-avaxone.theblueprint.xyz
    # =========================================================================
    def _scrape_avx(self, driver) -> Optional[DashboardData]:
        """Parse AVAX One Treasury Analytics for AVX data.

        Labels: "AVAX Held" → "13.889M" (next line "AVAX"),
        "Market Capitalization" → "$62.227M", "mNAV" → "0.46" (Mcap/NAV),
        "Total Shares Issued and Outstanding" → "92.672M".
        Note: some values have "$" on a separate line (handled by _get_page_lines).
        """
        data = DashboardData(ticker="AVX")
        lines, lv, _ = _get_page_lines(driver)

        for label, value in lv.items():
            if label.lower() == "avax held":
                val = _parse_number(value)
                if val:
                    data.treasury_units = val
                    break

        for label, value in lv.items():
            if label.lower() == "market capitalization":
                val = _parse_number(value)
                if val and val > 100_000:
                    data.market_cap = val
                    break

        for label, value in lv.items():
            if "total shares" in label.lower() and "outstanding" in label.lower():
                val = _parse_number(value)
                if val and val > 1000:
                    data.shares_outstanding = val
                    break

        for label, value in lv.items():
            if label.lower() == "mnav":
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mcap_nav = val  # AVX mNAV = Mcap/NAV
                    break

        if data.treasury_units or data.market_cap or data.mcap_nav:
            return data
        print("   Dashboard scraper: Could not extract metrics from AVAX One")
        return None

    # =========================================================================
    # IPST — ipstrategy.co/treasury-dashboard
    # =========================================================================
    def _scrape_ipst(self, driver) -> Optional[DashboardData]:
        """Parse IP Strategy treasury dashboard for IPST data.

        Labels: "$IP Held in Treasury" → "53,270,716",
        "Market Cap" → "$12,237,762", "Headline mNAV" → "0.20" (Mcap/NAV),
        "Number of Shares" → "19,786,196".
        """
        data = DashboardData(ticker="IPST")
        lines, lv, _ = _get_page_lines(driver)

        for label, value in lv.items():
            if "held in treasury" in label.lower() or "ip held" in label.lower():
                val = _parse_number(value)
                if val and val > 100:
                    data.treasury_units = val
                    break

        for label, value in lv.items():
            if label.lower() == "market cap":
                val = _parse_number(value)
                if val and val > 100_000:
                    data.market_cap = val
                    break

        for label, value in lv.items():
            if label.lower() == "number of shares":
                val = _parse_number(value)
                if val and val > 1000:
                    data.shares_outstanding = val
                    break

        # Headline mNAV = Mcap/NAV
        for label, value in lv.items():
            if "headline mnav" in label.lower():
                val = _parse_number(value)
                if val and 0.01 < val < 50:
                    data.mcap_nav = val
                    break

        if data.treasury_units or data.market_cap or data.mcap_nav:
            return data
        print("   Dashboard scraper: Could not extract metrics from IP Strategy")
        return None

    # =========================================================================
    def close(self):
        """Clean up Selenium driver."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def __del__(self):
        self.close()
