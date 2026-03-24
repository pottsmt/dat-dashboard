"""
CoinMarketCap scraper for historical cryptocurrency prices.
Scrapes historical data from CMC website (no API key required).
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import re
import json


class CoinMarketCapScraper:
    """Scrapes historical price data from CoinMarketCap website."""

    BASE_URL = "https://coinmarketcap.com"

    # Mapping from our asset symbols to CMC slugs
    SYMBOL_TO_SLUG = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "DOGE": "dogecoin",
        "AVAX": "avalanche",
        "BNB": "bnb",
        "TON": "toncoin",
        "TRX": "tron",
        "LTC": "litecoin",
        "ZEC": "zcash",
        "NEAR": "near-protocol",
        "SUI": "sui",
        "INJ": "injective",
        "HYPE": "hyperliquid",
        "ENA": "ethena",
        "WLD": "worldcoin-org",  # Also try worldcoin-wld
        "BERA": "berachain",
        "IP": "story-protocol",  # Assuming IP refers to this
        "CC": "cloudcoin",  # May need verification
        "WLFI": "world-liberty-financial-wlfi",  # Trump's World Liberty Financial token
    }

    def __init__(self, rate_limit_delay: float = 1.0):
        """
        Initialize scraper.

        Args:
            rate_limit_delay: Seconds between requests
        """
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._last_request_time = 0
        self._cache = {}  # Cache for today's fetches

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _get_slug(self, symbol: str) -> Optional[str]:
        """Get CMC slug for a symbol."""
        return self.SYMBOL_TO_SLUG.get(symbol.upper())

    def get_historical_prices(self, symbol: str, days: int = 30) -> Optional[List[Dict]]:
        """
        Get historical prices for a cryptocurrency.

        Args:
            symbol: Crypto symbol (BTC, ETH, etc.)
            days: Number of days of history

        Returns:
            List of {date, price} dicts or None
        """
        slug = self._get_slug(symbol)
        if not slug:
            print(f"    Unknown symbol: {symbol}")
            return None

        # Check cache
        cache_key = f"{symbol}_{days}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        self._rate_limit()

        # Try the web scraping approach - CMC embeds data in script tags
        url = f"https://coinmarketcap.com/currencies/{slug}/"

        try:
            response = self.session.get(url, timeout=30)

            if response.status_code != 200:
                print(f"    CMC returned {response.status_code} for {symbol}")
                return None

            # Find the __NEXT_DATA__ script tag which contains price data
            # The tag may have additional attributes like crossorigin
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', response.text, re.DOTALL)

            if not match:
                print(f"    Could not find data script for {symbol}")
                return None

            data = json.loads(match.group(1))

            # Navigate to the price data
            # Structure: props.pageProps.detailRes.detail.statistics
            try:
                page_props = data.get("props", {}).get("pageProps", {})
                detail_res = page_props.get("detailRes", {})
                detail = detail_res.get("detail", {})
                stats = detail.get("statistics", {})

                current_price = stats.get("price")
                price_change_7d = stats.get("priceChangePercentage7d")
                price_change_30d = stats.get("priceChangePercentage30d")

                if current_price:
                    # Calculate historical prices from percentage changes
                    prices = []
                    today = datetime.now().date()

                    # Current price
                    prices.append({"date": today, "price": current_price})

                    # 7 days ago
                    if price_change_7d is not None:
                        price_7d = current_price / (1 + price_change_7d / 100)
                        prices.insert(0, {"date": today - timedelta(days=7), "price": price_7d})

                    # 30 days ago
                    if price_change_30d is not None:
                        price_30d = current_price / (1 + price_change_30d / 100)
                        prices.insert(0, {"date": today - timedelta(days=30), "price": price_30d})

                    # Sort by date
                    prices.sort(key=lambda x: x["date"])

                    # Store the percentage changes directly for efficiency
                    self._cache[f"{symbol}_perf"] = {
                        "7d": price_change_7d,
                        "30d": price_change_30d,
                        "current_price": current_price
                    }

                    self._cache[cache_key] = prices
                    return prices

            except (KeyError, TypeError) as e:
                print(f"    Error parsing CMC data for {symbol}: {e}")
                return None

        except Exception as e:
            print(f"    Error fetching {symbol} from CMC: {e}")
            return None

    def get_performance(self, symbol: str, days: int) -> Optional[float]:
        """
        Calculate performance over N days.

        Args:
            symbol: Crypto symbol
            days: Number of days

        Returns:
            Percentage change or None
        """
        prices = self.get_historical_prices(symbol, days + 5)
        if not prices or len(prices) < 2:
            return None

        current_price = prices[-1]["price"]

        # Find price from N days ago
        target_date = datetime.now().date() - timedelta(days=days)
        old_price = None

        for p in prices:
            if p["date"] <= target_date:
                old_price = p["price"]

        if old_price is None or old_price == 0:
            return None

        return ((current_price - old_price) / old_price) * 100

    def get_all_performance(self, symbol: str) -> Dict[str, Optional[float]]:
        """
        Get 3d, 7d, and 30d performance.

        Args:
            symbol: Crypto symbol

        Returns:
            Dict with '3d', '7d', '30d' keys
        """
        result = {"3d": None, "7d": None, "30d": None}

        # First try to get data (which populates the performance cache)
        self.get_historical_prices(symbol, 35)

        # Check if we have cached performance data from CMC
        perf_cache_key = f"{symbol}_perf"
        if perf_cache_key in self._cache:
            cached = self._cache[perf_cache_key]
            result["7d"] = cached.get("7d")
            result["30d"] = cached.get("30d")
            # CMC doesn't provide 3d directly, but 7d and 30d are the main ones
            return result

        # Fallback: calculate from historical prices
        prices = self._cache.get(f"{symbol}_35")
        if not prices or len(prices) < 2:
            return result

        current_price = prices[-1]["price"]
        if current_price == 0:
            return result

        today = datetime.now().date()

        for days_key, days_back in [("3d", 3), ("7d", 7), ("30d", 30)]:
            target_date = today - timedelta(days=days_back)
            old_price = None

            # Find closest price on or before target date
            for p in prices:
                if p["date"] <= target_date:
                    old_price = p["price"]

            if old_price and old_price > 0:
                result[days_key] = ((current_price - old_price) / old_price) * 100

        return result

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol.

        Args:
            symbol: Crypto symbol

        Returns:
            Current price or None
        """
        prices = self.get_historical_prices(symbol, 1)
        if prices:
            return prices[-1]["price"]
        return None


if __name__ == "__main__":
    # Test the scraper
    scraper = CoinMarketCapScraper()

    test_symbols = ["BTC", "ETH", "SOL"]

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        perf = scraper.get_all_performance(symbol)
        print(f"  3D: {perf['3d']:+.2f}%" if perf['3d'] else "  3D: N/A")
        print(f"  7D: {perf['7d']:+.2f}%" if perf['7d'] else "  7D: N/A")
        print(f"  30D: {perf['30d']:+.2f}%" if perf['30d'] else "  30D: N/A")
