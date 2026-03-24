"""
SEC Filing Scanner - Checks for new filings and extracts treasury/shares data.

Usage:
    python scripts/scan_filings.py              # Scan for new filings since last run
    python scripts/scan_filings.py --days 7     # Scan filings from last 7 days
    python scripts/scan_filings.py --analyze    # Use AI to analyze filing content
"""

import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from edgar_client import EdgarClient


class FilingScanner:
    """Scans SEC filings for treasury and shares updates."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.config_dir = data_dir.parent / "config"
        self.scan_state_file = data_dir / "scan_state.json"

        # Load companies
        with open(self.config_dir / "companies.json") as f:
            self.config = json.load(f)

        # Load holdings
        self.holdings_file = data_dir / "history" / "holdings.json"
        with open(self.holdings_file) as f:
            self.holdings = json.load(f)

        # Initialize EDGAR client
        self.edgar = EdgarClient(
            user_agent="DAT Dashboard scanner@example.com",
            data_dir=data_dir / "edgar"
        )

        # Keywords to search for in filings
        self.treasury_keywords = [
            "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
            "digital asset", "cryptocurrency", "crypto",
            "treasury", "holdings", "acquired", "purchased",
            "aggregate", "total holdings"
        ]

        self.shares_keywords = [
            "shares outstanding", "common stock outstanding",
            "shares issued", "total shares", "diluted shares",
            "atm", "at-the-market", "equity offering"
        ]

    def load_scan_state(self) -> Dict:
        """Load the last scan state."""
        if self.scan_state_file.exists():
            with open(self.scan_state_file) as f:
                return json.load(f)
        return {"last_scan": None, "processed_filings": []}

    def save_scan_state(self, state: Dict):
        """Save scan state."""
        with open(self.scan_state_file, "w") as f:
            json.dump(state, f, indent=2)

    def get_filing_content(self, filing_url: str) -> str:
        """Fetch filing content from SEC."""
        headers = {"User-Agent": "DAT Dashboard scanner@example.com"}
        try:
            resp = requests.get(filing_url, headers=headers, timeout=30)
            resp.raise_for_status()
            # Clean HTML
            text = re.sub(r'<[^>]+>', ' ', resp.text)
            text = re.sub(r'\s+', ' ', text)
            return text
        except Exception as e:
            print(f"    Error fetching {filing_url}: {e}")
            return ""

    def extract_numbers(self, text: str, context_words: List[str]) -> List[Tuple[str, str]]:
        """Extract numbers near context words."""
        results = []
        text_lower = text.lower()

        for word in context_words:
            # Find all occurrences of the word
            idx = 0
            while True:
                idx = text_lower.find(word.lower(), idx)
                if idx == -1:
                    break

                # Get surrounding context (500 chars)
                start = max(0, idx - 100)
                end = min(len(text), idx + 400)
                context = text[start:end]

                # Look for numbers in context
                numbers = re.findall(r'[\$]?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s*(?:million|billion|M|B|K))?', context)
                if numbers:
                    results.append((word, context.strip()))

                idx += len(word)

        return results

    def analyze_filing(self, filing: Dict) -> Dict:
        """Analyze a filing for treasury/shares updates."""
        result = {
            "ticker": filing["ticker"],
            "form_type": filing["form_type"],
            "filing_date": filing["filing_date"],
            "filing_url": filing["filing_url"],
            "treasury_mentions": [],
            "shares_mentions": [],
            "summary": ""
        }

        content = self.get_filing_content(filing["filing_url"])
        if not content:
            return result

        # Search for treasury-related content
        treasury_hits = self.extract_numbers(content, self.treasury_keywords)
        if treasury_hits:
            result["treasury_mentions"] = treasury_hits[:5]  # Top 5

        # Search for shares-related content
        shares_hits = self.extract_numbers(content, self.shares_keywords)
        if shares_hits:
            result["shares_mentions"] = shares_hits[:5]

        # Generate summary
        if treasury_hits or shares_hits:
            result["summary"] = f"Found {len(treasury_hits)} treasury mentions, {len(shares_hits)} shares mentions"

        return result

    def scan_company(self, ticker: str, since_date: str) -> List[Dict]:
        """Scan a company for new filings."""
        filings = []

        try:
            # Get recent filings
            all_filings = self.edgar.get_company_filings(
                ticker,
                filing_types=["8-K", "10-Q", "10-K", "8-K/A", "10-Q/A", "10-K/A"]
            )

            # Filter by date
            for f in all_filings:
                if f["filing_date"] >= since_date:
                    filings.append(f)
        except Exception as e:
            print(f"  Error scanning {ticker}: {e}")

        return filings

    def scan_all(self, days: int = 1, analyze: bool = False) -> Dict:
        """
        Scan all companies for new filings.

        Args:
            days: Number of days to look back
            analyze: Whether to analyze filing content

        Returns:
            Summary of findings
        """
        state = self.load_scan_state()

        # Determine start date
        if days:
            since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        elif state.get("last_scan"):
            since_date = state["last_scan"]
        else:
            since_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"Scanning for filings since {since_date}...")
        print(f"Checking {len(self.config['companies'])} companies...")
        print()

        results = {
            "scan_date": datetime.now().isoformat(),
            "since_date": since_date,
            "new_filings": [],
            "filings_with_updates": [],
            "companies_scanned": 0,
            "total_new_filings": 0
        }

        processed = set(state.get("processed_filings", []))

        for company in self.config["companies"]:
            ticker = company["ticker"]
            results["companies_scanned"] += 1

            filings = self.scan_company(ticker, since_date)

            # Filter already processed
            new_filings = [f for f in filings if f["filing_id"] not in processed]

            if new_filings:
                print(f"{ticker}: {len(new_filings)} new filing(s)")

                for filing in new_filings:
                    print(f"  - {filing['filing_date']} {filing['form_type']}")

                    filing_info = {
                        "ticker": ticker,
                        "company": company["name"],
                        "form_type": filing["form_type"],
                        "filing_date": filing["filing_date"],
                        "filing_url": filing["filing_url"],
                        "filing_id": filing["filing_id"]
                    }

                    if analyze:
                        print(f"    Analyzing content...")
                        analysis = self.analyze_filing(filing)
                        filing_info["analysis"] = analysis

                        if analysis["treasury_mentions"] or analysis["shares_mentions"]:
                            results["filings_with_updates"].append(filing_info)
                            print(f"    {analysis['summary']}")

                    results["new_filings"].append(filing_info)
                    results["total_new_filings"] += 1
                    processed.add(filing["filing_id"])

        # Save state
        state["last_scan"] = datetime.now().strftime("%Y-%m-%d")
        state["processed_filings"] = list(processed)[-1000:]  # Keep last 1000
        self.save_scan_state(state)

        return results

    def print_summary(self, results: Dict):
        """Print scan summary."""
        print()
        print("=" * 60)
        print("SCAN SUMMARY")
        print("=" * 60)
        print(f"Companies scanned: {results['companies_scanned']}")
        print(f"New filings found: {results['total_new_filings']}")

        if results["filings_with_updates"]:
            print()
            print("FILINGS WITH POTENTIAL UPDATES:")
            print("-" * 40)
            for f in results["filings_with_updates"]:
                print(f"  {f['ticker']} - {f['form_type']} ({f['filing_date']})")
                print(f"    URL: {f['filing_url']}")
                if f.get("analysis"):
                    for mention in f["analysis"].get("treasury_mentions", [])[:2]:
                        print(f"    Treasury: ...{mention[1][:100]}...")
                    for mention in f["analysis"].get("shares_mentions", [])[:2]:
                        print(f"    Shares: ...{mention[1][:100]}...")
                print()

        if results["new_filings"] and not results["filings_with_updates"]:
            print()
            print("NEW FILINGS (not analyzed):")
            print("-" * 40)
            for f in results["new_filings"][:10]:
                print(f"  {f['ticker']} - {f['form_type']} ({f['filing_date']})")
                print(f"    {f['filing_url']}")


def main():
    parser = argparse.ArgumentParser(description="SEC Filing Scanner")
    parser.add_argument("--days", type=int, default=1, help="Days to look back (default: 1)")
    parser.add_argument("--analyze", action="store_true", help="Analyze filing content for treasury/shares")
    parser.add_argument("--ticker", type=str, help="Scan specific ticker only")
    args = parser.parse_args()

    data_dir = Path(__file__).parent.parent / "data"
    scanner = FilingScanner(data_dir)

    print("=" * 60)
    print("SEC Filing Scanner")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    results = scanner.scan_all(days=args.days, analyze=args.analyze)
    scanner.print_summary(results)

    # Save results
    results_file = data_dir / "scan_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    main()
