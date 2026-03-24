"""Email sender for DAT Dashboard reports."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
from pathlib import Path
from typing import Optional


class EmailSender:
    """Send email notifications with DAT Dashboard reports."""

    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        sender_email: str,
        sender_password: str,
        recipient_email: str,
    ):
        """Initialize email sender.

        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP server port
            sender_email: Sender email address
            sender_password: Sender email password/app password
            recipient_email: Recipient email address
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.recipient_email = recipient_email

    def send_report(
        self,
        html_content: str,
        plain_text: str,
        subject: Optional[str] = None,
        pdf_path: Optional[Path] = None,
    ) -> bool:
        """Send DAT Dashboard report email.

        Args:
            html_content: HTML version of report
            plain_text: Plain text version of report
            subject: Optional custom subject line
            pdf_path: Optional path to PDF file to attach

        Returns:
            True if email sent successfully
        """
        if subject is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            subject = f"DAT Dashboard Report - {date_str}"

        # Create mixed message (supports both alternative body + attachments)
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = self.recipient_email

        # Email body (plain text + HTML alternatives)
        body = MIMEMultipart("alternative")
        body.attach(MIMEText(plain_text, "plain"))
        body.attach(MIMEText(html_content, "html"))
        msg.attach(body)

        # Attach PDF if provided
        if pdf_path and pdf_path.exists():
            with open(pdf_path, "rb") as f:
                pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
                pdf_attachment.add_header(
                    "Content-Disposition", "attachment",
                    filename=pdf_path.name,
                )
                msg.attach(pdf_attachment)

        # Send email
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, self.recipient_email, msg.as_string())
            print(f"Report email sent to {self.recipient_email}")
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    def send_alert(
        self,
        ticker: str,
        alert_type: str,
        message: str,
    ) -> bool:
        """Send an alert email for significant events.

        Args:
            ticker: Company ticker
            alert_type: Type of alert (e.g., "Treasury Update", "Filing")
            message: Alert message

        Returns:
            True if email sent successfully
        """
        subject = f"DAT Alert: {ticker} - {alert_type}"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 20px; }}
        .alert-box {{
            background-color: #fef3c7;
            border: 1px solid #f59e0b;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .alert-title {{
            color: #92400e;
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
        }}
    </style>
</head>
<body>
    <div class="alert-box">
        <div class="alert-title">{ticker} - {alert_type}</div>
        <p>{message}</p>
        <p><small>Alert generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
    </div>
</body>
</html>
"""

        plain_text = f"""
DAT Dashboard Alert
===================
Ticker: {ticker}
Type: {alert_type}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{message}
"""

        return self.send_report(html_content, plain_text, subject)
