"""
CoinGecko API client for cryptocurrency prices.
"""

import time
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class CoinGeckoClient:
    """Client for CoinGecko API to fetch crypto prices."""

    BASE_URL = "https://api.coingecko.com/api/v3"
    RATE_LIMIT_DELAY = 1.5  # seconds between requests (free tier)

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize CoinGecko client.

        Args:
            api_key: Optional API key for pro tier (higher rate limits)
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
        })
        if api_key:
            self.session.headers["x-cg-demo-api-key"] = api_key
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make GET request to CoinGecko API."""
        self._rate_limit()
        url = f"{self.BASE_URL}/{endpoint}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_current_prices(self, coin_ids: List[str], vs_currency: str = "usd") -> Dict[str, float]:
        """
        Get current prices for multiple coins.

        Args:
            coin_ids: List of CoinGecko coin IDs (e.g., ["bitcoin", "ethereum"])
            vs_currency: Currency for price (default: usd)

        Returns:
            Dict mapping coin_id to current price
        """
        params = {
            "ids": ",".join(coin_ids),
            "vs_currencies": vs_currency,
        }
        data = self._get("simple/price", params)
        return {coin_id: data.get(coin_id, {}).get(vs_currency) for coin_id in coin_ids}

    def get_price_with_market_data(self, coin_ids: List[str], vs_currency: str = "usd") -> Dict:
        """
        Get current prices with additional market data.

        Args:
            coin_ids: List of CoinGecko coin IDs
            vs_currency: Currency for price

        Returns:
            Dict with price, market_cap, 24h_vol, 24h_change for each coin
        """
        params = {
            "ids": ",".join(coin_ids),
            "vs_currencies": vs_currency,
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        }
        return self._get("simple/price", params)

    def get_historical_price(self, coin_id: str, date: datetime, vs_currency: str = "usd") -> Optional[float]:
        """
        Get historical price for a specific date.

        Args:
            coin_id: CoinGecko coin ID
            date: Date to get price for
            vs_currency: Currency for price

        Returns:
            Price on that date or None if not found
        """
        date_str = date.strftime("%d-%m-%Y")
        params = {"date": date_str}
        try:
            data = self._get(f"coins/{coin_id}/history", params)
            return data.get("market_data", {}).get("current_price", {}).get(vs_currency)
        except requests.HTTPError:
            return None

    def get_price_history(
        self, coin_id: str, days: int, vs_currency: str = "usd"
    ) -> List[Dict]:
        """
        Get price history for past N days.

        Args:
            coin_id: CoinGecko coin ID
            days: Number of days of history
            vs_currency: Currency for price

        Returns:
            List of {timestamp, price} dicts
        """
        params = {
            "vs_currency": vs_currency,
            "days": days,
            "interval": "daily",
        }
        data = self._get(f"coins/{coin_id}/market_chart", params)
        prices = data.get("prices", [])
        return [
            {"timestamp": datetime.fromtimestamp(p[0] / 1000), "price": p[1]}
            for p in prices
        ]

    def get_performance(self, coin_id: str, days: int, vs_currency: str = "usd") -> Optional[float]:
        """
        Calculate percentage performance over N days.

        Args:
            coin_id: CoinGecko coin ID
            days: Number of days to look back
            vs_currency: Currency for price

        Returns:
            Percentage change (e.g., 5.2 for +5.2%) or None
        """
        history = self.get_price_history(coin_id, days, vs_currency)
        if len(history) < 2:
            return None

        old_price = history[0]["price"]
        current_price = history[-1]["price"]

        if old_price == 0:
            return None

        return ((current_price - old_price) / old_price) * 100

    def get_vwap(self, coin_id: str, days: int, vs_currency: str = "usd") -> Optional[float]:
        """
        Calculate approximate VWAP over N days.

        Note: CoinGecko doesn't provide true VWAP, so this uses
        volume-weighted average of daily prices.

        Args:
            coin_id: CoinGecko coin ID
            days: Number of days
            vs_currency: Currency

        Returns:
            Approximate VWAP or None
        """
        params = {
            "vs_currency": vs_currency,
            "days": days,
            "interval": "daily",
        }
        data = self._get(f"coins/{coin_id}/market_chart", params)

        prices = data.get("prices", [])
        volumes = data.get("total_volumes", [])

        if len(prices) != len(volumes) or len(prices) == 0:
            return None

        total_volume = sum(v[1] for v in volumes)
        if total_volume == 0:
            return None

        vwap = sum(p[1] * v[1] for p, v in zip(prices, volumes)) / total_volume
        return vwap
