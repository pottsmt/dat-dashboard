"""
Analyzes SEC filings to extract treasury holdings information using OpenAI.

Three layers of data quality:
1. Confidence scoring — GPT self-rates each extraction (1-10), low confidence rejected
2. Filing-type-aware prompts — stricter instructions for 8-K press releases
3. Cross-filing validation — reject values that swing wildly from last known good entry
"""

import json
import re
from typing import Dict, List, Optional
from pathlib import Path

from openai import OpenAI


# Minimum confidence to accept an extracted value
MIN_CONFIDENCE = 7

# Max swing from last known value before flagging (e.g., 5.0 = 5x / 0.2x)
MAX_SWING_FACTOR = 5.0


class FilingAnalyzer:
    """Analyzes SEC filings to extract digital asset treasury information."""

    BASE_PROMPT = """Analyze this SEC filing and extract digital asset treasury information.

Focus on:
1. **Treasury Holdings**: Cryptocurrency ACTUALLY HELD (BTC, ETH, SOL, WLD, etc.)
   - Specific quantities (number of coins/tokens) that are CURRENTLY HELD
   - If the filing states a USD value for the holdings (e.g., "valued at $X", "fair value of $X", "carrying value of $X"), include it as value_usd
   - IMPORTANT: Do NOT report target/goal amounts. "Targeting 800 million tokens" or "plans to acquire" is NOT a holding.
   - Only report quantities the company explicitly states it HOLDS or HAS ACQUIRED as of a specific date.

2. **Shares Outstanding**: Basic and fully diluted shares actually ISSUED and OUTSTANDING
   - IMPORTANT: Do NOT confuse these with shares outstanding:
     * "Authorized shares" = max a company CAN issue (e.g., "500,000,000 shares authorized") — IGNORE
     * "Quorum" or "shares represented at meeting" = shares that voted, NOT total outstanding — IGNORE
     * "Shares offered" or "shares registered for sale" = potential future shares — IGNORE
   - Look for language like "shares issued and outstanding", "shares outstanding as of", cover page share counts
   - Only report the actual total shares issued and outstanding
   - If shares outstanding DECREASED vs prior periods, set "decrease_reason" to the cause (e.g., "share buyback", "reverse split", "share cancellation"). If no reason is stated, set it to null.

3. **Cash and Cash Equivalents**: The company's cash balance
   - Look for "cash and cash equivalents" on the balance sheet or in financial statements
   - Report the USD amount as of the most recent date in the filing

4. **Other Investments**: Investments MADE BY the company (not investors in the company)
   - Only include companies/assets that THIS company has invested in or acquired stakes in
   - IMPORTANT: Do NOT list the company's own investors, shareholders, or capital providers. We want the company's OUTBOUND investments.
   - Type (private_equity, public_equity, venture, other)
   - USD value if disclosed
   - Number of shares if public equity

For EACH extracted value, rate your confidence from 1-10:
  10 = exact number clearly stated (e.g., "the Company holds 207,123,794 WLD tokens")
  7-9 = number stated but some ambiguity in context
  4-6 = inferred or approximate
  1-3 = uncertain / guessing

Return JSON in this exact format:
```json
{
  "treasury_holdings": [
    {
      "asset": "WLD",
      "quantity": 15000,
      "quantity_unit": "tokens",
      "value_usd": 25000000,
      "as_of_date": "2025-12-31",
      "source_text": "exact quote from filing",
      "confidence": 10
    }
  ],
  "shares_outstanding": {
    "basic": 20000000,
    "fully_diluted": 25000000,
    "as_of_date": "2025-12-31",
    "confidence": 10,
    "decrease_reason": null
  },
  "cash_and_equivalents": {
    "amount_usd": 23000000,
    "as_of_date": "2025-12-31",
    "confidence": 10
  },
  "other_investments": [
    {
      "name": "Investment Name",
      "type": "private_equity",
      "value_usd": 5000000,
      "shares": null,
      "ticker": null,
      "notes": "Brief description",
      "confidence": 8
    }
  ],
  "primary_asset": "WLD",
  "company_name": "Company Name",
  "filing_summary": "Brief 2-3 sentence summary of key treasury-related information"
}
```

If any field is not found, set it to null. Only include information explicitly stated in the filing.
"""

    # Extra instructions prepended for 8-K filings (press releases are noisier)
    EIGHT_K_INSTRUCTIONS = """IMPORTANT — This is an 8-K filing which may contain press releases, presentations, or transcripts.
Be EXTRA CAREFUL with 8-K filings:
- Press releases often contain ASPIRATIONAL language ("we aim to hold", "targeting X tokens") — these are NOT actual holdings.
- Only extract holdings if there is a SPECIFIC number with a SPECIFIC as-of date indicating current ownership.
- Phrases like "holds over 10% of supply" are too vague — do NOT try to calculate a number from this. Set confidence below 5.
- Investor names (e.g., "backed by Pantera, Coinfund") are the company's OWN INVESTORS, not their investments. Do NOT list them.
- If a press release mentions a treasury amount without a clear as-of date, set confidence to 5 or lower.
- If the filing is about corporate governance, board changes, or compliance — there are probably no treasury holdings to extract.

"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        output_dir: Optional[Path] = None,
    ):
        """
        Initialize filing analyzer.

        Args:
            api_key: OpenAI API key
            model: OpenAI model to use
            output_dir: Directory to save analysis results
        """
        self.client = OpenAI(api_key=api_key)
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

    def _build_prompt(self, filing: Dict, content: str) -> str:
        """Build the extraction prompt, with extra guardrails for 8-K filings."""
        truncated = self._truncate_content(content)
        form_type = filing.get("form_type", "")

        if form_type in ("8-K", "6-K"):
            return self.EIGHT_K_INSTRUCTIONS + self.BASE_PROMPT + "\nSEC Filing Content:\n" + truncated
        else:
            return self.BASE_PROMPT + "\nSEC Filing Content:\n" + truncated

    def analyze_filing(self, filing: Dict, content: str) -> Optional[Dict]:
        """
        Analyze a filing to extract treasury information.

        Args:
            filing: Filing metadata dict
            content: Filing text content

        Returns:
            Extracted treasury information or None on error
        """
        prompt = self._build_prompt(filing, content)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.choices[0].message.content

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

    def extract_holdings_update(
        self,
        analysis: Dict,
        last_known_units: Optional[float] = None,
    ) -> Optional[Dict]:
        """
        Extract holdings update from analysis for tracker.

        Args:
            analysis: Filing analysis result
            last_known_units: Previous treasury units for cross-filing validation

        Returns:
            Dict with holdings info suitable for HoldingsTracker
        """
        if not analysis:
            return None

        holdings = analysis.get("treasury_holdings") or []
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

        quantity = primary["quantity"]
        confidence = primary.get("confidence", 5)
        form_type = analysis.get("filing_metadata", {}).get("form_type", "")
        accession = analysis.get("filing_metadata", {}).get("accession_number", "?")

        # Layer 1: Confidence check
        if confidence < MIN_CONFIDENCE:
            print(f"    SKIP treasury: {quantity:,.0f} — low confidence ({confidence}/10)")
            return None

        # Layer 3: Cross-filing validation
        # 10-Q and 10-K are audited/official filings — trust them even with large swings
        # (reverse splits, pivots, etc. cause legitimate huge swings)
        if last_known_units and last_known_units > 0:
            ratio = quantity / last_known_units
            if ratio > MAX_SWING_FACTOR or ratio < (1 / MAX_SWING_FACTOR):
                if form_type in ("10-Q", "10-K", "20-F"):
                    print(f"    Treasury: {quantity:,.4f} — large swing ({ratio:.1f}x) but accepting {form_type} as authoritative")
                else:
                    print(f"    SKIP treasury: {quantity:,.0f} — {ratio:.1f}x swing from last known {last_known_units:,.0f} ({accession})")
                    return None

        return {
            "asset": primary.get("asset", "UNKNOWN"),
            "units": quantity,
            "value_usd": primary.get("value_usd"),
            "date": primary.get("as_of_date") or analysis["filing_metadata"]["filing_date"],
            "source": form_type,
            "accession_number": accession,
            "filing_summary": analysis.get("filing_summary"),
            "confidence": confidence,
        }

    def extract_shares_update(
        self,
        analysis: Dict,
        last_known_shares: Optional[float] = None,
    ) -> Optional[Dict]:
        """
        Extract shares outstanding update from analysis.

        Args:
            analysis: Filing analysis result
            last_known_shares: Previous shares outstanding for cross-filing validation

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

        confidence = shares_info.get("confidence", 5)
        form_type = analysis.get("filing_metadata", {}).get("form_type", "")
        accession = analysis.get("filing_metadata", {}).get("accession_number", "?")

        # Layer 1: Confidence check
        if confidence < MIN_CONFIDENCE:
            print(f"    SKIP shares: {shares:,.0f} — low confidence ({confidence}/10)")
            return None

        # Layer 2: Authorized shares filter
        common_authorized = {
            100_000_000, 200_000_000, 250_000_000, 300_000_000, 500_000_000,
            750_000_000, 1_000_000_000, 2_000_000_000, 5_000_000_000, 10_000_000_000,
        }
        if shares in common_authorized:
            print(f"    SKIP shares: {shares:,.0f} — looks like authorized shares ({accession})")
            return None

        # Layer 3: Cross-filing validation
        # 10-Q and 10-K are audited/official filings — trust them even with large swings
        # (reverse splits, massive ATM dilution, PIPE deals cause legitimate huge swings)
        if last_known_shares and last_known_shares > 0:
            ratio = shares / last_known_shares
            if ratio > MAX_SWING_FACTOR or ratio < (1 / MAX_SWING_FACTOR):
                if form_type in ("10-Q", "10-K", "20-F"):
                    print(f"    Shares: {shares:,.0f} — large swing ({ratio:.1f}x) but accepting {form_type} as authoritative")
                else:
                    print(f"    SKIP shares: {shares:,.0f} — {ratio:.1f}x swing from last known {last_known_shares:,.0f} ({accession})")
                    return None
            # Share decreases on 8-K require an explicit reason (buyback, reverse split, etc.)
            # Quorum/meeting vote counts look like decreases but aren't real
            elif form_type in ("8-K", "6-K") and shares < last_known_shares * 0.9:
                decrease_reason = shares_info.get("decrease_reason")
                if not decrease_reason:
                    print(f"    SKIP shares: {shares:,.0f} — decrease on 8-K with no buyback/split reason ({accession})")
                    return None
                else:
                    print(f"    Shares decreased: {decrease_reason}")

        return {
            "shares": shares,
            "date": shares_info.get("as_of_date") or analysis["filing_metadata"]["filing_date"],
            "source": form_type,
            "accession_number": accession,
            "filing_summary": analysis.get("filing_summary"),
            "confidence": confidence,
        }

    def extract_other_holdings(self, analysis: Dict, primary_asset: str = None) -> Optional[List[Dict]]:
        """
        Extract other holdings from analysis: secondary treasury assets, cash, and investments.

        Args:
            analysis: Filing analysis result
            primary_asset: Primary treasury asset ticker (e.g. "WLD") to exclude from other holdings

        Returns:
            List of holding dicts or None
        """
        if not analysis:
            return None

        filing_date = analysis.get("filing_metadata", {}).get("filing_date", "")
        source = analysis.get("filing_metadata", {}).get("form_type", "")
        accession = analysis.get("filing_metadata", {}).get("accession_number")
        result = []

        # 1. Secondary treasury assets (non-primary crypto holdings)
        holdings = analysis.get("treasury_holdings") or []
        for h in holdings:
            asset = h.get("asset")
            qty = h.get("quantity")
            confidence = h.get("confidence", 5)
            if not asset or not qty or qty < 10:
                continue
            # Skip the primary asset (handled by extract_holdings_update)
            # Normalize: strip $, common suffixes like "Tokens", "Token"
            if primary_asset:
                norm_asset = asset.upper().strip("$").replace(" TOKENS", "").replace(" TOKEN", "").strip()
                norm_primary = primary_asset.upper().strip("$").replace(" TOKENS", "").replace(" TOKEN", "").strip()
                if norm_asset == norm_primary:
                    continue
            # Confidence check
            if confidence < MIN_CONFIDENCE:
                continue
            as_of = h.get("as_of_date") or filing_date
            result.append({
                "name": f"{qty:,.0f} {asset}",
                "type": "digital_asset",
                "value_usd": None,
                "units": qty,
                "ticker": asset,
                "shares": None,
                "notes": f"Per {source} as of {as_of}",
                "source": source,
                "date": as_of,
                "accession_number": accession,
            })

        # 2. Cash and cash equivalents
        cash_info = analysis.get("cash_and_equivalents")
        if cash_info and cash_info.get("amount_usd"):
            cash_confidence = cash_info.get("confidence", 5)
            if cash_confidence >= MIN_CONFIDENCE:
                as_of = cash_info.get("as_of_date") or filing_date
                result.append({
                    "name": "Cash and cash equivalents",
                    "type": "cash",
                    "value_usd": cash_info["amount_usd"],
                    "units": None,
                    "ticker": None,
                    "shares": None,
                    "notes": f"Per {source} as of {as_of}",
                    "source": source,
                    "date": as_of,
                    "accession_number": accession,
                })

        # 3. Other investments (venture, PE, public equity)
        investments = analysis.get("other_investments") or []
        for inv in investments:
            confidence = inv.get("confidence", 5)
            # Skip investments that duplicate the primary treasury asset
            if primary_asset and inv.get("ticker"):
                norm_inv = inv["ticker"].upper().strip("$").replace(" TOKENS", "").replace(" TOKEN", "").strip()
                norm_primary = primary_asset.upper().strip("$").replace(" TOKENS", "").replace(" TOKEN", "").strip()
                if norm_inv == norm_primary:
                    continue
            if inv.get("name") and confidence >= MIN_CONFIDENCE:
                result.append({
                    "name": inv["name"],
                    "type": inv.get("type", "other"),
                    "value_usd": inv.get("value_usd"),
                    "units": None,
                    "shares": inv.get("shares"),
                    "ticker": inv.get("ticker"),
                    "notes": inv.get("notes", ""),
                    "source": source,
                    "date": filing_date,
                    "accession_number": accession,
                })

        return result if result else None

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
