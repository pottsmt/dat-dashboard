"""
Email notification for SEC filing scan results.

Sends email via Gmail SMTP with summary of new filings.
"""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Sends email notifications for filing scan results."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize email notifier.

        Args:
            config_path: Path to email config JSON file
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "email_config.json"

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load email configuration."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Email config not found at {self.config_path}\n"
                "Create config/email_config.json with:\n"
                "{\n"
                '  "smtp_server": "smtp.gmail.com",\n'
                '  "smtp_port": 587,\n'
                '  "sender_email": "your.email@gmail.com",\n'
                '  "sender_password": "your-app-password",\n'
                '  "recipient_emails": ["recipient@example.com"]\n'
                "}"
            )

        with open(self.config_path) as f:
            return json.load(f)

    def format_filing_html(self, filing: Dict, is_flagged: bool = False) -> str:
        """Format a single filing as HTML."""
        style = 'style="background-color: #fff3cd; padding: 10px; margin: 10px 0; border-left: 4px solid #ffc107;"' if is_flagged else 'style="padding: 10px; margin: 10px 0; border-left: 4px solid #dee2e6;"'

        flag_badge = '<span style="background-color: #ffc107; color: #000; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 10px;">REVIEW</span>' if is_flagged else ''

        html = f"""
        <div {style}>
            <strong>{filing['ticker']}</strong> - {filing['form_type']} ({filing['filing_date']}){flag_badge}<br>
            <span style="color: #666;">{filing.get('company', '')}</span><br>
            <a href="{filing['filing_url']}" style="color: #0066cc;">View Filing</a>
        """

        # Add analysis details if flagged
        if is_flagged and filing.get('analysis'):
            analysis = filing['analysis']
            if analysis.get('treasury_mentions'):
                html += '<br><br><strong style="color: #856404;">Treasury mentions:</strong><ul style="margin: 5px 0;">'
                for keyword, context in analysis['treasury_mentions'][:2]:
                    snippet = context[:150] + '...' if len(context) > 150 else context
                    html += f'<li><em>{keyword}</em>: {snippet}</li>'
                html += '</ul>'

            if analysis.get('shares_mentions'):
                html += '<strong style="color: #856404;">Shares mentions:</strong><ul style="margin: 5px 0;">'
                for keyword, context in analysis['shares_mentions'][:2]:
                    snippet = context[:150] + '...' if len(context) > 150 else context
                    html += f'<li><em>{keyword}</em>: {snippet}</li>'
                html += '</ul>'

        html += "</div>"
        return html

    def create_email_body(self, scan_results: Dict) -> str:
        """Create HTML email body from scan results."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Separate flagged and regular filings
        flagged = scan_results.get('filings_with_updates', [])
        flagged_ids = {f['filing_id'] for f in flagged}
        regular = [f for f in scan_results.get('new_filings', []) if f['filing_id'] not in flagged_ids]

        total_new = scan_results.get('total_new_filings', 0)
        companies_scanned = scan_results.get('companies_scanned', 0)

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 10px;">
                DAT Dashboard - SEC Filing Scan
            </h2>

            <p style="color: #666;">
                Scan completed: {now}<br>
                Companies scanned: {companies_scanned}<br>
                New filings found: <strong>{total_new}</strong>
            </p>
        """

        if not flagged and not regular:
            html += """
            <div style="background-color: #d4edda; padding: 15px; border-radius: 4px; margin: 20px 0;">
                <strong>No new filings found.</strong>
            </div>
            """
        else:
            # Flagged filings section
            if flagged:
                html += f"""
                <h3 style="color: #856404; background-color: #fff3cd; padding: 10px; margin-top: 20px;">
                    Filings Requiring Review ({len(flagged)})
                </h3>
                <p style="color: #666; font-size: 14px;">
                    These filings contain potential treasury or shares updates. Review and update holdings.json if needed.
                </p>
                """
                for filing in flagged:
                    html += self.format_filing_html(filing, is_flagged=True)

            # Regular filings section
            if regular:
                html += f"""
                <h3 style="color: #333; margin-top: 30px;">
                    Other New Filings ({len(regular)})
                </h3>
                """
                for filing in regular:
                    html += self.format_filing_html(filing, is_flagged=False)

        html += """
            <hr style="margin-top: 30px; border: none; border-top: 1px solid #dee2e6;">
            <p style="color: #999; font-size: 12px;">
                DAT Dashboard Automated Scan<br>
                To stop these emails, remove or rename config/email_config.json
            </p>
        </body>
        </html>
        """

        return html

    def send_email(self, scan_results: Dict, subject_prefix: str = "") -> bool:
        """
        Send email with scan results.

        Args:
            scan_results: Results from FilingScanner.scan_all()
            subject_prefix: Optional prefix for email subject

        Returns:
            True if email sent successfully
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')

            total_new = scan_results.get('total_new_filings', 0)
            flagged_count = len(scan_results.get('filings_with_updates', []))

            # Subject line
            if flagged_count > 0:
                subject = f"{subject_prefix}[ACTION] {flagged_count} filing(s) need review - {total_new} total new"
            elif total_new > 0:
                subject = f"{subject_prefix}SEC Scan: {total_new} new filing(s)"
            else:
                subject = f"{subject_prefix}SEC Scan: No new filings"

            msg['Subject'] = subject
            msg['From'] = self.config['sender_email']
            msg['To'] = ', '.join(self.config['recipient_emails'])

            # Create HTML body
            html_body = self.create_email_body(scan_results)
            msg.attach(MIMEText(html_body, 'html'))

            # Send email
            with smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port']) as server:
                server.starttls()
                server.login(self.config['sender_email'], self.config['sender_password'])
                server.send_message(msg)

            logger.info(f"Email sent successfully to {len(self.config['recipient_emails'])} recipient(s)")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


def send_scan_notification(scan_results: Dict) -> bool:
    """
    Convenience function to send scan notification.

    Args:
        scan_results: Results from FilingScanner.scan_all()

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        notifier = EmailNotifier()
        return notifier.send_email(scan_results)
    except FileNotFoundError as e:
        logger.warning(f"Email notifications disabled: {e}")
        return False
    except Exception as e:
        logger.error(f"Email notification failed: {e}")
        return False


if __name__ == "__main__":
    # Test with existing scan results
    import sys

    data_dir = Path(__file__).parent.parent / "data"
    results_file = data_dir / "scan_results.json"

    if results_file.exists():
        with open(results_file) as f:
            results = json.load(f)

        print("Sending test email with latest scan results...")
        success = send_scan_notification(results)

        if success:
            print("Email sent successfully!")
        else:
            print("Failed to send email. Check config/email_config.json")
    else:
        print(f"No scan results found at {results_file}")
        print("Run scan_filings.py first to generate results.")
