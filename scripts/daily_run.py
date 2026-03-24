"""
Daily DAT Dashboard Runner - Complete daily workflow.

This script:
1. Scans SEC filings for new treasury/shares updates
2. Shows findings for review
3. Runs Bloomberg export and generates dashboard

Usage:
    python scripts/daily_run.py              # Full daily run
    python scripts/daily_run.py --scan-only  # Just scan filings
    python scripts/daily_run.py --skip-scan  # Skip filing scan
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from scan_filings import FilingScanner
from run_dashboard_auto import run_bloomberg_export, run_dashboard, open_report


def daily_run(scan_days: int = 1, analyze: bool = True, skip_scan: bool = False,
              scan_only: bool = False, wait_seconds: int = 30):
    """
    Run the complete daily workflow.

    Args:
        scan_days: Days to look back for new filings
        analyze: Analyze filing content
        skip_scan: Skip the SEC filing scan
        scan_only: Only scan filings, don't run dashboard
        wait_seconds: Seconds to wait for Bloomberg data
    """
    print("=" * 70)
    print("DAT DASHBOARD - DAILY RUN")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()

    # Step 1: Scan SEC filings
    if not skip_scan:
        print("STEP 1: Scanning SEC filings for updates...")
        print("-" * 50)

        data_dir = Path(__file__).parent.parent / "data"
        scanner = FilingScanner(data_dir)

        results = scanner.scan_all(days=scan_days, analyze=analyze)
        scanner.print_summary(results)

        # If filings with updates found, prompt for review
        if results["filings_with_updates"]:
            print()
            print("*" * 50)
            print("ACTION REQUIRED: Review filings above for updates")
            print("Update holdings.json if needed before continuing")
            print("*" * 50)
            print()

            if not scan_only:
                response = input("Continue to dashboard generation? [Y/n]: ").strip().lower()
                if response == 'n':
                    print("Exiting. Run again after updating holdings.json")
                    return False
        elif results["new_filings"]:
            print()
            print("New filings found but no obvious treasury/shares updates detected.")
            print("Review manually if needed.")
            print()
    else:
        print("STEP 1: Skipping SEC filing scan (--skip-scan)")
        print()

    if scan_only:
        print("Scan complete (--scan-only mode)")
        return True

    # Step 2: Bloomberg export
    print()
    print("STEP 2: Bloomberg data export...")
    print("-" * 50)

    if not run_bloomberg_export(wait_seconds=wait_seconds, close_excel=True):
        print("ERROR: Bloomberg export failed")
        return False

    # Step 3: Generate dashboard
    print()
    print("STEP 3: Generating dashboard report...")
    print("-" * 50)

    if not run_dashboard():
        print("ERROR: Dashboard generation failed")
        return False

    # Step 4: Open report
    print()
    print("STEP 4: Opening report...")
    print("-" * 50)
    open_report()

    print()
    print("=" * 70)
    print("DAILY RUN COMPLETE")
    print("=" * 70)

    return True


def main():
    parser = argparse.ArgumentParser(description="DAT Dashboard Daily Runner")
    parser.add_argument("--scan-days", type=int, default=1,
                        help="Days to look back for filings (default: 1)")
    parser.add_argument("--no-analyze", action="store_true",
                        help="Don't analyze filing content")
    parser.add_argument("--skip-scan", action="store_true",
                        help="Skip SEC filing scan")
    parser.add_argument("--scan-only", action="store_true",
                        help="Only scan filings, don't run dashboard")
    parser.add_argument("--wait", type=int, default=30,
                        help="Seconds to wait for Bloomberg data (default: 30)")
    args = parser.parse_args()

    success = daily_run(
        scan_days=args.scan_days,
        analyze=not args.no_analyze,
        skip_scan=args.skip_scan,
        scan_only=args.scan_only,
        wait_seconds=args.wait
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
