"""
Yahoo Finance client for fetching stock data.
Provides automated alternative to Bloomberg CSV exports.
"""

import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

try:
    from .bloomberg_reader import StockData
except ImportError:
    from bloomberg_reader import StockData

logger = logging.getLogger(__name__)


class YFinanceClient:
    """Fetches stock data from Yahoo Finance."""

    def __init__(self, rate_limit_delay: float = 0.1):
        """
        Initialize client.

        Args:
            rate_limit_delay: Seconds to wait between requests (not used with batch)
        """
        self.rate_limit_delay = rate_limit_delay

    def get_stock_data(self, ticker: str) -> Optional[StockData]:
        """
        Fetch stock data for a single ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            StockData object or None if fetch fails
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Get historical data for performance calculations
            end_date = datetime.now()
            start_date = end_date - timedelta(days=35)
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning(f"{ticker}: No historical data available")
                return None

            # Current price
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if current_price is None and not hist.empty:
                current_price = hist["Close"].iloc[-1]

            # Shares outstanding
            shares = info.get("sharesOutstanding")

            # Market cap
            market_cap = info.get("marketCap")

            # Enterprise value
            enterprise_value = info.get("enterpriseValue")

            # Total debt and cash
            total_debt = info.get("totalDebt")
            cash = info.get("totalCash")

            # Volume
            volume = info.get("volume") or info.get("regularMarketVolume")
            avg_volume = info.get("averageVolume")

            # Historical prices for performance
            price_3d_ago = None
            price_7d_ago = None
            price_30d_ago = None

            if len(hist) >= 3:
                price_3d_ago = hist["Close"].iloc[-4] if len(hist) >= 4 else hist["Close"].iloc[0]
            if len(hist) >= 7:
                price_7d_ago = hist["Close"].iloc[-8] if len(hist) >= 8 else hist["Close"].iloc[0]
            if len(hist) >= 30:
                price_30d_ago = hist["Close"].iloc[0]

            return StockData(
                ticker=ticker.upper(),
                price=current_price,
                volume=volume,
                avg_volume_5d=avg_volume,
                shares_outstanding=shares / 1_000_000 if shares else None,  # Convert to millions for Bloomberg compat
                market_cap=market_cap / 1_000_000 if market_cap else None,  # Convert to millions
                total_debt=total_debt,
                cash=cash,
                enterprise_value=enterprise_value / 1_000_000 if enterprise_value else None,  # Convert to millions
                price_3d_ago=price_3d_ago,
                price_7d_ago=price_7d_ago,
                price_30d_ago=price_30d_ago,
                export_timestamp=datetime.now(),
            )

        except Exception as e:
            logger.error(f"{ticker}: Failed to fetch data - {e}")
            return None

    def get_multiple_stocks(self, tickers: List[str]) -> Dict[str, StockData]:
        """
        Fetch stock data for multiple tickers efficiently.

        Args:
            tickers: List of stock ticker symbols

        Returns:
            Dict mapping ticker to StockData
        """
        results = {}

        # Use yfinance's batch download for historical data
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=35)

            # Download all historical data in one batch
            hist_data = yf.download(
                tickers,
                start=start_date,
                end=end_date,
                group_by="ticker",
                progress=False,
                threads=True,
            )
        except Exception as e:
            logger.error(f"Batch download failed: {e}")
            hist_data = None

        # Fetch individual ticker info (yfinance doesn't batch this well)
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info

                # Skip if no valid data
                if not info or info.get("regularMarketPrice") is None:
                    logger.warning(f"{ticker}: No market data available")
                    continue

                # Current price
                current_price = info.get("currentPrice") or info.get("regularMarketPrice")

                # Get historical prices from batch data
                price_3d_ago = None
                price_7d_ago = None
                price_30d_ago = None

                if hist_data is not None and not hist_data.empty:
                    try:
                        # With group_by='ticker', data is always multi-level: (ticker, field)
                        if ticker in hist_data.columns.get_level_values(0):
                            ticker_hist = hist_data[ticker]
                        else:
                            ticker_hist = None

                        if ticker_hist is not None and not ticker_hist.empty:
                            closes = ticker_hist["Close"].dropna()
                            if len(closes) >= 4:
                                price_3d_ago = closes.iloc[-4]
                            if len(closes) >= 8:
                                price_7d_ago = closes.iloc[-8]
                            if len(closes) >= 1:
                                price_30d_ago = closes.iloc[0]
                    except Exception as e:
                        logger.debug(f"{ticker}: Could not extract historical prices - {e}")

                # Shares outstanding
                shares = info.get("sharesOutstanding")

                # Market cap
                market_cap = info.get("marketCap")

                # Enterprise value
                enterprise_value = info.get("enterpriseValue")

                # Total debt and cash
                total_debt = info.get("totalDebt")
                cash = info.get("totalCash")

                # Volume
                volume = info.get("volume") or info.get("regularMarketVolume")
                avg_volume = info.get("averageVolume")

                results[ticker.upper()] = StockData(
                    ticker=ticker.upper(),
                    price=current_price,
                    volume=volume,
                    avg_volume_5d=avg_volume,
                    shares_outstanding=shares / 1_000_000 if shares else None,
                    market_cap=market_cap / 1_000_000 if market_cap else None,
                    total_debt=total_debt,
                    cash=cash,
                    enterprise_value=enterprise_value / 1_000_000 if enterprise_value else None,
                    price_3d_ago=price_3d_ago,
                    price_7d_ago=price_7d_ago,
                    price_30d_ago=price_30d_ago,
                    export_timestamp=datetime.now(),
                )

            except Exception as e:
                logger.error(f"{ticker}: Failed to fetch data - {e}")
                continue

        return results

    def get_vwap(self, ticker: str, start_date: str, end_date: str) -> Optional[float]:
        """
        Compute VWAP for a stock between two dates.

        VWAP = sum(Close * Volume) / sum(Volume) over daily bars.

        Args:
            ticker: Stock ticker symbol
            start_date: ISO date string (YYYY-MM-DD)
            end_date: ISO date string (YYYY-MM-DD)

        Returns:
            VWAP as float, or None if no data available
        """
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty or len(hist) < 1:
                logger.warning(f"{ticker}: No historical data for VWAP ({start_date} to {end_date})")
                return None

            # Filter out zero-volume days
            hist = hist[hist["Volume"] > 0]
            if hist.empty:
                logger.warning(f"{ticker}: No trading volume for VWAP ({start_date} to {end_date})")
                return None

            total_dollar_volume = (hist["Close"] * hist["Volume"]).sum()
            total_volume = hist["Volume"].sum()

            if total_volume == 0:
                return None

            vwap = total_dollar_volume / total_volume
            logger.info(f"{ticker}: VWAP ${vwap:.2f} ({start_date} to {end_date}, {len(hist)} days)")
            return float(vwap)

        except Exception as e:
            logger.error(f"{ticker}: Failed to compute VWAP - {e}")
            return None

    def read_as_dict(self, tickers: List[str]) -> Dict[str, StockData]:
        """
        Fetch stock data matching Bloomberg reader interface.

        Args:
            tickers: List of ticker symbols

        Returns:
            Dict mapping ticker to StockData
        """
        return self.get_multiple_stocks(tickers)
