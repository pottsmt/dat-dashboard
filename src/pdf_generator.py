"""PDF generation for DAT Dashboard reports using headless Chrome."""

import base64
import os
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


class PDFGenerator:
    """Generate PDF reports from HTML using Chrome's print-to-PDF."""

    def __init__(self, chrome_path: Optional[str] = None):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self._driver = None

    def _get_driver(self):
        if self._driver:
            return self._driver

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.binary_location = self.chrome_path

        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=options)
        return self._driver

    def html_to_pdf(self, html_path: Path, pdf_path: Path) -> bool:
        """Convert an HTML file to PDF using Chrome's print-to-PDF.

        Args:
            html_path: Path to the HTML file
            pdf_path: Path where the PDF should be saved

        Returns:
            True if PDF was generated successfully
        """
        try:
            driver = self._get_driver()
            file_url = html_path.resolve().as_uri()
            driver.get(file_url)

            # Use CDP command for print-to-PDF with landscape for wide tables
            pdf_params = {
                "landscape": True,
                "printBackground": True,
                "preferCSSPageSize": True,
                "paperWidth": 11,      # inches (letter landscape)
                "paperHeight": 8.5,
                "marginTop": 0.4,
                "marginBottom": 0.4,
                "marginLeft": 0.4,
                "marginRight": 0.4,
                "scale": 0.7,
            }

            result = driver.execute_cdp_cmd("Page.printToPDF", pdf_params)
            pdf_data = base64.b64decode(result["data"])

            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(pdf_data)
            return True

        except Exception as e:
            print(f"   PDF generation failed: {e}")
            return False

    def close(self):
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
