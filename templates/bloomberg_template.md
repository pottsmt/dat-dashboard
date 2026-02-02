# Bloomberg Excel Template for DAT Dashboard

## Setup Instructions

1. Open a new Excel workbook
2. Ensure Bloomberg Excel Add-in is enabled (Bloomberg menu should be visible)
3. Create sheets as described below
4. Save as `dat_bloomberg.xlsm` (macro-enabled workbook)

---

## Sheet 1: "Data" (Main Data Sheet)

This sheet contains all Bloomberg formulas. The Python script reads from the CSV export of this sheet.

### Row 1: Headers
| A | B | C | D | E | F | G | H | I | J | K | L | M |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ticker | Price | Volume | Avg_Vol_30D | Shares_Out | Market_Cap | Total_Debt | Cash | Enterprise_Value | VWAP | Price_3D_Ago | Price_7D_Ago | Price_30D_Ago |

### Row 2: BNC Data (Bloomberg Formulas)
| Cell | Formula |
|------|---------|
| A2 | `BNC` |
| B2 | `=BDP("BNC US Equity","PX_LAST")` |
| C2 | `=BDP("BNC US Equity","VOLUME")` |
| D2 | `=BDP("BNC US Equity","VOLUME_AVG_30D")` |
| E2 | `=BDP("BNC US Equity","EQY_SH_OUT")` |
| F2 | `=BDP("BNC US Equity","CUR_MKT_CAP")` |
| G2 | `=BDP("BNC US Equity","TOT_DEBT")` |
| H2 | `=BDP("BNC US Equity","CASH_AND_ST_INVESTMENTS")` |
| I2 | `=BDP("BNC US Equity","CURR_ENTP_VAL")` |
| J2 | `=BDP("BNC US Equity","VWAP")` |
| K2 | `=BDH("BNC US Equity","PX_LAST",TODAY()-3,TODAY()-3)` |
| L2 | `=BDH("BNC US Equity","PX_LAST",TODAY()-7,TODAY()-7)` |
| M2 | `=BDH("BNC US Equity","PX_LAST",TODAY()-30,TODAY()-30)` |

### Additional Rows
When expanding to all companies, add rows 3-40 with the same formulas but different tickers.

---

## Sheet 2: "VWAP_History" (For Shares Estimation)

Used when estimating shares issued between treasury updates.

### Headers (Row 1)
| A | B | C | D |
|---|---|---|---|
| Ticker | Start_Date | End_Date | Period_VWAP |

### Data Entry
When a treasury update occurs without shares update:
1. Enter the ticker
2. Enter the last treasury update date
3. Enter the new treasury update date
4. Formula calculates period VWAP

### VWAP Calculation Formula (D2)
```
=AVERAGE(INDEX(BDH(A2&" US Equity","VWAP",B2,C2),0,2))
```

---

## Sheet 3: "Export_Log"

Tracks export timestamps for debugging.

| A | B |
|---|---|
| Last_Export | `=NOW()` |
| Export_Count | `=COUNTA(A:A)-1` |

---

## Bloomberg Field Reference

| Field | Bloomberg Code | Description |
|-------|----------------|-------------|
| Last Price | PX_LAST | Current stock price |
| Volume | VOLUME | Today's trading volume |
| 30D Avg Volume | VOLUME_AVG_30D | 30-day average volume |
| Shares Outstanding | EQY_SH_OUT | Total shares outstanding (millions) |
| Market Cap | CUR_MKT_CAP | Market capitalization |
| Total Debt | TOT_DEBT | Total debt |
| Cash | CASH_AND_ST_INVESTMENTS | Cash and short-term investments |
| Enterprise Value | CURR_ENTP_VAL | Enterprise value |
| VWAP | VWAP | Volume-weighted average price |
| Historical Price | PX_LAST (via BDH) | Historical closing price |

---

## Notes

- Shares Outstanding (EQY_SH_OUT) is typically in millions - multiply by 1,000,000 for actual count
- Market Cap (CUR_MKT_CAP) is typically in millions
- BDH returns an array; for single values, may need INDEX() wrapper
- Bloomberg updates data when Terminal is open and connected
