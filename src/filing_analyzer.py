"""
Analyzes SEC filings to extract treasury holdings information using Claude.
"""

import json
import re
from typing import Dict, List, Optional
from pathlib import Path

import anthropic


class FilingAnalyzer:
    """Analyzes SEC filings to extract digital asset treasury information."""

    EXTRACTION_PROMPT = """Analyze this SEC filing and extract information about digital asset (cryptocurrency) holdings.

Look for:
1. **Treasury Holdings**: Bitcoin (BTC), Ethereum (ETH), Solana (SOL), or other cryptocurrency holdings
   - Look for specific quantities (number of coins/tokens held)
   - Look for USD values of holdings
   - Look for acquisition announcements

2. **Shares Outstanding**: Total shares outstanding, fully diluted shares

3. **ATM Programs**: At-the-market equity offering programs
   - Total authorized amount
   - Amount utilized/remaining

4. **Debt Information**: Convertible notes, loans related to crypto purchases

5. **Company Strategy**: Any stated bitcoin/crypto acquisition strategy

Return your findings as JSON in this exact format:
```json
{
  "treasury_holdings": [
    {
      "asset": "BTC",
      "quantity": 15000,
      "quantity_unit": "coins",
      "usd_value": 1500000000,
      "as_of_date": "2025-12-31",
      "source_text": "excerpt from filing"
    }
  ],
  "shares_outstanding": {
    "basic": 20000000,
    "fully_diluted": 25000000,
    "as_of_date": "2025-12-31"
  },
  "atm_program": {
    "authorized_amount": 500000000,
    "utilized_amount": 300000000,
    "remaining_amount": 200000000
  },
  "debt": {
    "convertible_notes": 1000000000,
    "other_debt": 0
  },
  "primary_asset": "BTC",
  "company_name": "Company Name",
  "filing_summary": "Brief 2-3 sentence summary of key treasury-related information"
}
```

If any field is not found or mentioned, set it to null. Only include information explicitly stated in the filing.

SEC Filing Content:
"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        output_dir: Optional[Path] = None,
    ):
        """
        Initialize filing analyzer.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
            output_dir: Directory to save analysis results
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.output_dir = Path(output_dir) if output_dir else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def _truncate_content(self, content: str, max_chars: int = 400000) -> str:
        """Truncate content to fit within context limits."""
        if len(content) <= max_chars:
            return content

        # Keep beginning and end, which often have key info
        half = max_chars // 2
        return content[:half] + "\n\n[... content truncated ...]\n\n" + content[-half:]

    def analyze_filing(self, filing: Dict, content: str) -> Optional[Dict]:
        """
        Analyze a filing to extract treasury information.

        Args:
            filing: Filing metadata dict
            content: Filing text content

        Returns:
            Extracted treasury information or None on error
        """
        truncated_content = self._truncate_content(content)
        prompt = self.EXTRACTION_PROMPT + truncated_content

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # Extract JSON from response
            json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON
                json_str = response_text

            result = json.loads(json_str)
            result["filing_metadata"] = {
                "ticker": filing["ticker"],
                "form_type": filing["form_type"],
                "filing_date": filing["filing_date"],
                "accession_number": filing["accession_number"],
                "filing_url": filing["filing_url"],
            }

            # Save analysis if output dir configured
            if self.output_dir:
                output_file = self.output_dir / f"{filing['filing_id']}_analysis.json"
                with open(output_file, "w") as f:
                    json.dump(result, f, indent=2)

            return result

        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response for {filing['filing_id']}: {e}")
            return None
        except Exception as e:
            print(f"Error analyzing {filing['filing_id']}: {e}")
            return None

    def extract_holdings_update(self, analysis: Dict) -> Optional[Dict]:
        """
        Extract holdings update from analysis for tracker.

        Args:
            analysis: Filing analysis result

        Returns:
            Dict with holdings info suitable for HoldingsTracker
        """
        if not analysis:
            return None

        holdings = analysis.get("treasury_holdings", [])
        if not holdings:
            return None

        # Get primary holding (largest by quantity or first)
        primary = holdings[0]
        for h in holdings:
            if h.get("quantity") and (
                not primary.get("quantity") or h["quantity"] > primary["quantity"]
            ):
                primary = h

        if not primary.get("quantity"):
            return None

        return {
            "asset": primary.get("asset", "UNKNOWN"),
            "units": primary["quantity"],
            "date": primary.get("as_of_date") or analysis["filing_metadata"]["filing_date"],
            "source": analysis["filing_metadata"]["form_type"],
            "accession_number": analysis["filing_metadata"]["accession_number"],
        }

    def extract_shares_update(self, analysis: Dict) -> Optional[Dict]:
        """
        Extract shares outstanding update from analysis.

        Args:
            analysis: Filing analysis result

        Returns:
            Dict with shares info suitable for HoldingsTracker
        """
        if not analysis:
            return None

        shares_info = analysis.get("shares_outstanding")
        if not shares_info:
            return None

        shares = shares_info.get("basic") or shares_info.get("fully_diluted")
        if not shares:
            return None

        return {
            "shares": shares,
            "date": shares_info.get("as_of_date") or analysis["filing_metadata"]["filing_date"],
            "source": analysis["filing_metadata"]["form_type"],
            "accession_number": analysis["filing_metadata"]["accession_number"],
        }

    def batch_analyze(self, filings: List[Dict], contents: Dict[str, str]) -> List[Dict]:
        """
        Analyze multiple filings.

        Args:
            filings: List of filing metadata dicts
            contents: Dict mapping filing_id to content

        Returns:
            List of analysis results
        """
        results = []
        for filing in filings:
            content = contents.get(filing["filing_id"])
            if not content:
                continue

            print(f"Analyzing {filing['ticker']} {filing['form_type']} ({filing['filing_date']})...")
            analysis = self.analyze_filing(filing, content)
            if analysis:
                results.append(analysis)

        return results
