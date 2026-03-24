"""
Fully automated DAT Dashboard runner.

Opens Bloomberg Excel template, refreshes data, exports to CSV, runs dashboard.

Usage:
    python scripts/run_dashboard_auto.py

Options:
    --wait SECONDS   Time to wait for Bloomberg data to load (default: 30)
    --no-close       Keep Excel open after export
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def run_bloomberg_export(wait_seconds=30, close_excel=True):
    """
    Open Bloomberg Excel, refresh data, export to CSV.

    Args:
        wait_seconds: Time to wait for Bloomberg data to populate
        close_excel: Whether to close Excel after export

    Returns:
        True if successful
    """
    import win32com.client
    import pythoncom
    import subprocess
    import os

    template_path = str(Path(__file__).parent.parent / "data" / "exports" / "bloomberg_template_v2.xlsx")
    csv_path = str(Path(__file__).parent.parent / "data" / "exports" / "bloomberg_data.csv")

    # Initialize COM
    pythoncom.CoInitialize()

    excel = None
    wb = None

    try:
        # Method: Open file via shell (like double-click) to ensure Bloomberg Add-in loads
        print(f"Opening Bloomberg template via shell (ensures Add-in loads)...")
        print(f"File: {template_path}")

        # Use os.startfile to open like a double-click
        os.startfile(template_path)

        # Wait for Excel to open and Bloomberg to connect
        print("Waiting 10 seconds for Excel and Bloomberg Add-in to initialize...")
        time.sleep(10)

        # Now connect to the Excel instance
        try:
            excel = win32com.client.GetActiveObject("Excel.Application")
            print("Connected to Excel instance")
        except Exception as e:
            print(f"ERROR: Could not connect to Excel: {e}")
            return False

        excel.DisplayAlerts = False

        # Find the workbook we just opened
        wb = None
        for w in excel.Workbooks:
            if "bloomberg_template" in w.Name.lower() or "template_v2" in w.Name.lower():
                wb = w
                break

        if not wb:
            print("ERROR: Could not find bloomberg_template workbook")
            return False

        print(f"Found workbook: {wb.Name}")

        # Wait for Bloomberg data to populate
        print(f"Waiting {wait_seconds} seconds for Bloomberg data to load...")
        for i in range(wait_seconds):
            time.sleep(1)
            remaining = wait_seconds - i - 1
            if remaining > 0 and remaining % 10 == 0:
                print(f"  {remaining} seconds remaining...")

        print("Saving workbook to cache values...")
        wb.Save()

        # Export the Export sheet to CSV
        print(f"Exporting to CSV: {csv_path}")

        # Delete old CSV if exists to avoid overwrite prompt
        csv_file = Path(csv_path)
        if csv_file.exists():
            csv_file.unlink()

        # Get the Export sheet
        try:
            export_sheet = wb.Sheets("Export")
        except:
            export_sheet = wb.ActiveSheet
            print(f"'Export' sheet not found, using: {export_sheet.Name}")

        # Copy the Export sheet to a new workbook and save as CSV
        export_sheet.Copy()  # Creates new workbook with just this sheet
        new_wb = excel.ActiveWorkbook
        new_wb.SaveAs(csv_path, 6)  # 6 = xlCSV
        new_wb.Close(False)

        print("CSV export complete!")

        if close_excel:
            print("Closing Excel...")
            wb.Close(False)
            excel.Quit()
        else:
            print("Keeping Excel open (--no-close)")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        pythoncom.CoUninitialize()


def run_dashboard():
    """Run the main dashboard report generator."""

    print("\n" + "="*60)
    print("Running DAT Dashboard...")
    print("="*60 + "\n")

    import subprocess
    main_path = Path(__file__).parent.parent / "src" / "main.py"

    result = subprocess.run(
        [sys.executable, str(main_path), "run"],  # Pass "run" command
        cwd=str(Path(__file__).parent.parent)
    )
    return result.returncode == 0


def open_report():
    """Open the generated HTML report in browser."""
    import subprocess

    report_path = Path(__file__).parent.parent / "data" / "reports" / f"dat_report_{datetime.now().strftime('%Y-%m-%d')}.html"

    if report_path.exists():
        print(f"Opening report: {report_path}")
        subprocess.run(["start", "", str(report_path)], shell=True)
    else:
        print(f"Report not found: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="DAT Dashboard - Automated Bloomberg Export & Run")
    parser.add_argument("--wait", type=int, default=30, help="Seconds to wait for Bloomberg data (default: 30)")
    parser.add_argument("--no-close", action="store_true", help="Keep Excel open after export")
    parser.add_argument("--no-report", action="store_true", help="Don't open the HTML report after")
    args = parser.parse_args()

    print("="*60)
    print("DAT Dashboard - Automated Bloomberg Export & Run")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    print()

    # Step 1: Open Bloomberg Excel, refresh, export to CSV
    print("Step 1: Bloomberg Excel export...")
    print("-"*40)
    if not run_bloomberg_export(wait_seconds=args.wait, close_excel=not args.no_close):
        print("Failed to export Bloomberg data.")
        return 1

    # Step 2: Run dashboard
    print("\nStep 2: Running dashboard report...")
    print("-"*40)
    if not run_dashboard():
        print("Failed to run dashboard.")
        return 1

    # Step 3: Open report
    if not args.no_report:
        print("\nStep 3: Opening report...")
        print("-"*40)
        open_report()

    print("\n" + "="*60)
    print("Done!")
    print("="*60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
