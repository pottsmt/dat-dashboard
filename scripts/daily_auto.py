"""
Fully Automated Daily DAT Dashboard Runner.

Runs without any user prompts - designed for scheduled execution.

This script:
1. Scans SEC filings for new treasury/shares updates
2. Logs findings to file
3. Runs Bloomberg export and generates dashboard
4. Saves report

Usage:
    python scripts/daily_auto.py
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from scan_filings import FilingScanner
from run_dashboard_auto import run_bloomberg_export, run_dashboard, open_report
from email_notify import send_scan_notification


def setup_logging():
    """Setup logging to file and console."""
    log_dir = Path(__file__).parent.parent / "data" / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"daily_run_{datetime.now().strftime('%Y-%m-%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def daily_auto():
    """Run the complete daily workflow automatically."""
    logger = setup_logging()

    logger.info("=" * 70)
    logger.info("DAT DASHBOARD - AUTOMATED DAILY RUN")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    success = True

    # Step 1: Scan SEC filings
    logger.info("STEP 1: Scanning SEC filings...")
    try:
        data_dir = Path(__file__).parent.parent / "data"
        scanner = FilingScanner(data_dir)
        results = scanner.scan_all(days=1, analyze=True)

        logger.info(f"Companies scanned: {results['companies_scanned']}")
        logger.info(f"New filings found: {results['total_new_filings']}")

        if results["filings_with_updates"]:
            logger.warning("FILINGS WITH POTENTIAL UPDATES:")
            for f in results["filings_with_updates"]:
                logger.warning(f"  {f['ticker']} - {f['form_type']} ({f['filing_date']})")
                logger.warning(f"    {f['filing_url']}")

        # Send email notification
        logger.info("Sending email notification...")
        if send_scan_notification(results):
            logger.info("Email sent successfully")
        else:
            logger.warning("Email notification skipped or failed")

    except Exception as e:
        logger.error(f"SEC scan failed: {e}")
        # Continue anyway - filing scan failure shouldn't stop dashboard

    # Step 2: Bloomberg export
    logger.info("")
    logger.info("STEP 2: Bloomberg data export...")
    try:
        if not run_bloomberg_export(wait_seconds=30, close_excel=True):
            logger.error("Bloomberg export failed")
            success = False
    except Exception as e:
        logger.error(f"Bloomberg export error: {e}")
        success = False

    if not success:
        logger.error("Stopping due to Bloomberg export failure")
        return False

    # Step 3: Generate dashboard
    logger.info("")
    logger.info("STEP 3: Generating dashboard report...")
    try:
        if not run_dashboard():
            logger.error("Dashboard generation failed")
            success = False
    except Exception as e:
        logger.error(f"Dashboard generation error: {e}")
        success = False

    # Step 4: Open report (optional for automated runs)
    if success:
        logger.info("")
        logger.info("STEP 4: Opening report...")
        try:
            open_report()
        except Exception as e:
            logger.warning(f"Could not open report: {e}")

    logger.info("")
    logger.info("=" * 70)
    if success:
        logger.info("DAILY RUN COMPLETE - SUCCESS")
    else:
        logger.error("DAILY RUN COMPLETE - WITH ERRORS")
    logger.info("=" * 70)

    return success


def main():
    success = daily_auto()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
