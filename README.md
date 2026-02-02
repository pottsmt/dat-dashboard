# DAT Dashboard - Digital Asset Treasury Monitor

Monitor and track companies with digital asset (Bitcoin, Ethereum, etc.) treasuries.

## Features

- **Treasury Tracking**: Track BTC/ETH/SOL holdings from SEC filings
- **NAV Calculations**: mNAV (Market Cap / NAV) and EV/NAV ratios
- **Performance Comparison**: Stock performance vs underlying crypto asset
- **Shares Estimation**: VWAP-based estimation of shares issued between filings
- **Daily Reports**: Automated HTML email reports

## Quick Start

### 1. Install

```bash
cd ~/Documents/Claude/dat-dashboard
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Set Up Bloomberg Excel

1. Open Bloomberg Terminal
2. Create new Excel workbook with formulas from `templates/bloomberg_template.md`
3. Add VBA code from `templates/bloomberg_vba.bas`
4. Save as `dat_bloomberg.xlsm`

### 4. Initialize Company Data

```bash
# Scan SEC filings for BNC
python -m src.main init BNC

# View extracted data
python -m src.main show BNC
```

### 5. Generate Report

```bash
# Ensure Bloomberg CSV is exported first
python -m src.main run
```

## Project Structure

```
dat-dashboard/
├── config/
│   ├── config.yaml       # Main configuration
│   └── companies.json    # Tracked companies
├── src/
│   ├── main.py           # CLI and orchestration
│   ├── bloomberg_reader.py   # Bloomberg CSV parser
│   ├── coingecko_client.py   # Crypto price API
│   ├── edgar_client.py       # SEC EDGAR API
│   ├── filing_analyzer.py    # Claude-powered analysis
│   ├── holdings_tracker.py   # Treasury/shares tracking
│   ├── report_generator.py   # HTML/text reports
│   └── email_sender.py       # Email delivery
├── data/
│   ├── exports/          # Bloomberg CSV exports
│   ├── filings/          # Downloaded SEC filings
│   ├── reports/          # Generated reports
│   └── history/          # Holdings tracking data
└── templates/
    ├── bloomberg_template.md  # Excel setup guide
    └── bloomberg_vba.bas      # VBA automation code
```

## CLI Commands

```bash
# Run daily report
python -m src.main run

# Scan filings for a company
python -m src.main scan BNC --lookback 365

# Initialize a company
python -m src.main init BNC

# Show current data
python -m src.main show BNC
```

## Data Flow

1. **Bloomberg Excel** → exports stock data to CSV
2. **CoinGecko API** → provides crypto prices
3. **SEC EDGAR** → provides filings for analysis
4. **Claude AI** → extracts treasury holdings from filings
5. **Report Generator** → creates HTML dashboard
6. **Email Sender** → delivers daily report

## Metrics Explained

| Metric | Formula | Interpretation |
|--------|---------|----------------|
| NAV | Treasury Units × Crypto Price | Net Asset Value |
| mNAV | Market Cap / NAV | >1x = premium, <1x = discount |
| EV/NAV | Enterprise Value / NAV | Includes debt impact |
| Relative Perf | Stock % - Crypto % | Positive = outperforming |
