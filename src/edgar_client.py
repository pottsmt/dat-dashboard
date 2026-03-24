"""SEC EDGAR API client for fetching company filings."""

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


class EdgarClient:
    """Client for interacting with SEC EDGAR API."""

    BASE_URL = "https://data.sec.gov"
    SUBMISSIONS_URL = f"{BASE_URL}/submissions"
    ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
    TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"

    # Rate limiting: SEC allows max 10 requests/second
    MIN_REQUEST_INTERVAL = 0.1  # 100ms between requests

    def __init__(self, user_agent: str, data_dir: Path):
        """Initialize EDGAR client.

        Args:
            user_agent: User-Agent header required by SEC (format: "Name email@example.com")
            data_dir: Directory for storing downloaded filings
        """
        self.user_agent = user_agent
        self.data_dir = data_dir
        self.filings_dir = data_dir / "filings"
        self.filings_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })

        self._last_request_time = 0.0
        self._ticker_cik_map: Optional[dict] = None

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str) -> requests.Response:
        """Make a rate-limited GET request."""
        self._rate_limit()
        response = self.session.get(url)
        response.raise_for_status()
        return response

    def get_ticker_cik_map(self) -> dict:
        """Fetch and cache ticker-to-CIK mapping from SEC."""
        if self._ticker_cik_map is not None:
            return self._ticker_cik_map

        response = self._get(self.TICKER_CIK_URL)
        data = response.json()

        # Build mapping: ticker -> CIK (padded to 10 digits)
        self._ticker_cik_map = {}
        for entry in data.values():
            ticker = entry["ticker"].upper()
            cik = str(entry["cik_str"]).zfill(10)
            self._ticker_cik_map[ticker] = cik

        return self._ticker_cik_map

    def ticker_to_cik(self, ticker: str) -> Optional[str]:
        """Convert ticker symbol to CIK."""
        mapping = self.get_ticker_cik_map()
        return mapping.get(ticker.upper())

    def validate_ticker(self, ticker: str) -> bool:
        """Check if ticker exists in SEC database."""
        return self.ticker_to_cik(ticker) is not None

    def get_company_info(self, ticker: str) -> Optional[Dict]:
        """Get company information from SEC."""
        cik = self.ticker_to_cik(ticker)
        if not cik:
            return None

        url = f"{self.SUBMISSIONS_URL}/CIK{cik}.json"
        response = self._get(url)
        data = response.json()

        return {
            "ticker": ticker,
            "cik": cik,
            "name": data.get("name", ""),
            "sic": data.get("sic", ""),
            "sic_description": data.get("sicDescription", ""),
        }

    def get_company_filings(
        self,
        ticker: str,
        filing_types: List[str],
        lookback_days: int = 365,
    ) -> List[Dict]:
        """Get recent filings for a company."""
        cik = self.ticker_to_cik(ticker)
        if not cik:
            raise ValueError(f"Unknown ticker: {ticker}")

        url = f"{self.SUBMISSIONS_URL}/CIK{cik}.json"
        response = self._get(url)
        data = response.json()

        company_name = data.get("name", ticker)
        recent = data.get("filings", {}).get("recent", {})

        if not recent:
            return []

        cutoff_date = datetime.now() - timedelta(days=lookback_days)

        filings = []
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_documents = recent.get("primaryDocument", [])

        for form, date_str, accession, primary_doc in zip(
            forms, dates, accession_numbers, primary_documents
        ):
            if form not in filing_types:
                continue

            filing_date = datetime.strptime(date_str, "%Y-%m-%d")
            if filing_date < cutoff_date:
                continue

            accession_clean = accession.replace("-", "")
            filing_url = f"{self.ARCHIVES_URL}/{cik.lstrip('0')}/{accession_clean}/{primary_doc}"

            filings.append({
                "ticker": ticker,
                "company_name": company_name,
                "cik": cik,
                "form_type": form,
                "filing_date": date_str,
                "accession_number": accession,
                "primary_document": primary_doc,
                "filing_url": filing_url,
                "filing_id": f"{ticker}_{accession}",
            })

        return filings

    def download_filing(self, filing: dict) -> str:
        """Download filing document and extract text content.

        For 8-K filings, also downloads EX-99.x exhibits (press releases,
        presentations) which often contain treasury updates.
        """
        url = filing["filing_url"]
        response = self._get(url)

        content_type = response.headers.get("Content-Type", "")

        if "html" in content_type or url.endswith(".htm") or url.endswith(".html"):
            text = self._extract_html_text(response.text)
        else:
            text = response.text

        # For 8-K/6-K filings, also fetch EX-99.x exhibits (press releases, presentations)
        if filing.get("form_type") in ("8-K", "6-K"):
            exhibits_text = self._download_8k_exhibits(filing)
            if exhibits_text:
                text = text + "\n\n" + exhibits_text

        filing_path = self.filings_dir / f"{filing['filing_id']}.txt"
        filing_path.write_text(text, encoding="utf-8")

        return text

    def _download_8k_exhibits(self, filing: dict) -> str:
        """Download EX-99.x exhibits from an 8-K filing index page."""
        cik = filing["cik"].lstrip("0")
        accession = filing["accession_number"]
        accession_clean = accession.replace("-", "")
        index_url = f"{self.ARCHIVES_URL}/{cik}/{accession_clean}/{accession}-index.htm"

        try:
            response = self._get(index_url)
            soup = BeautifulSoup(response.text, "lxml")
            table = soup.find("table", class_="tableFile")
            if not table:
                return ""

            exhibit_texts = []
            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) < 4:
                    continue
                doc_type = cols[3].text.strip()
                # Only grab EX-99.x exhibits (press releases, presentations, transcripts)
                if not doc_type.startswith("EX-99"):
                    continue
                link = cols[2].find("a")
                if not link or not link.get("href"):
                    continue
                href = link["href"]
                # Skip non-document files (images, etc.)
                if any(href.endswith(ext) for ext in (".jpg", ".png", ".gif", ".pdf")):
                    continue
                exhibit_url = f"https://www.sec.gov{href}"
                try:
                    ex_response = self._get(exhibit_url)
                    ex_content_type = ex_response.headers.get("Content-Type", "")
                    if "html" in ex_content_type or exhibit_url.endswith((".htm", ".html")):
                        ex_text = self._extract_html_text(ex_response.text)
                    else:
                        ex_text = ex_response.text
                    if ex_text.strip():
                        exhibit_texts.append(f"--- {doc_type} ---\n{ex_text}")
                except Exception:
                    continue

            return "\n\n".join(exhibit_texts)
        except Exception:
            return ""

    def _extract_html_text(self, html: str) -> str:
        """Extract readable text from HTML filing."""
        import warnings
        from bs4 import XMLParsedAsHTMLWarning
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

        soup = BeautifulSoup(html, "lxml")

        for element in soup(["script", "style", "meta", "link"]):
            element.decompose()

        text = soup.get_text(separator="\n")

        lines = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines.append(line)

        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text

    def get_all_recent_filings(
        self,
        tickers: List[str],
        filing_types: List[str],
        lookback_days: int = 365,
    ) -> List[Dict]:
        """Get recent filings for multiple tickers."""
        all_filings = []

        for ticker in tickers:
            try:
                filings = self.get_company_filings(ticker, filing_types, lookback_days)
                all_filings.extend(filings)
            except Exception as e:
                print(f"Error fetching filings for {ticker}: {e}")

        return all_filings
