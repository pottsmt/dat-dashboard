# Bloomberg Excel Template for DAT Dashboard

## Setup Instructions

1. Open a new Excel workbook
2. Ensure Bloomberg Excel Add-in is enabled (Bloomberg menu should be visible)
3. Create the "Data" sheet as described below
4. Save as `dat_bloomberg.xlsm` (macro-enabled workbook)

---

## Sheet 1: "Data" (Main Data Sheet)

### Row 1: Headers
```
A: Ticker
B: Price
C: Volume
D: Avg_Vol_30D
E: Shares_Out
F: Market_Cap
G: Total_Debt
H: Cash
I: Enterprise_Value
J: VWAP
K: Price_3D_Ago
L: Price_7D_Ago
M: Price_30D_Ago
```

### Data Rows (2-40): Bloomberg Formulas

Copy these formulas for each ticker. Replace "TICKER US Equity" with the actual Bloomberg ticker.

| Row | A (Ticker) | B (Price) | C (Volume) | D (Avg Vol 30D) | E (Shares Out) |
|-----|------------|-----------|------------|-----------------|----------------|
| 2 | ALTS | `=BDP("ALTS US Equity","PX_LAST")` | `=BDP("ALTS US Equity","VOLUME")` | `=BDP("ALTS US Equity","VOLUME_AVG_30D")` | `=BDP("ALTS US Equity","EQY_SH_OUT")` |
| 3 | ASST | `=BDP("ASST US Equity","PX_LAST")` | `=BDP("ASST US Equity","VOLUME")` | `=BDP("ASST US Equity","VOLUME_AVG_30D")` | `=BDP("ASST US Equity","EQY_SH_OUT")` |
| 4 | AVX | `=BDP("AVX US Equity","PX_LAST")` | `=BDP("AVX US Equity","VOLUME")` | `=BDP("AVX US Equity","VOLUME_AVG_30D")` | `=BDP("AVX US Equity","EQY_SH_OUT")` |
| 5 | BMNR | `=BDP("BMNR US Equity","PX_LAST")` | `=BDP("BMNR US Equity","VOLUME")` | `=BDP("BMNR US Equity","VOLUME_AVG_30D")` | `=BDP("BMNR US Equity","EQY_SH_OUT")` |
| 6 | BNC | `=BDP("BNC US Equity","PX_LAST")` | `=BDP("BNC US Equity","VOLUME")` | `=BDP("BNC US Equity","VOLUME_AVG_30D")` | `=BDP("BNC US Equity","EQY_SH_OUT")` |
| 7 | BRR | `=BDP("BRR US Equity","PX_LAST")` | `=BDP("BRR US Equity","VOLUME")` | `=BDP("BRR US Equity","VOLUME_AVG_30D")` | `=BDP("BRR US Equity","EQY_SH_OUT")` |
| 8 | BTBT | `=BDP("BTBT US Equity","PX_LAST")` | `=BDP("BTBT US Equity","VOLUME")` | `=BDP("BTBT US Equity","VOLUME_AVG_30D")` | `=BDP("BTBT US Equity","EQY_SH_OUT")` |
| 9 | BTOG | `=BDP("BTOG US Equity","PX_LAST")` | `=BDP("BTOG US Equity","VOLUME")` | `=BDP("BTOG US Equity","VOLUME_AVG_30D")` | `=BDP("BTOG US Equity","EQY_SH_OUT")` |
| 10 | CEPO | `=BDP("CEPO US Equity","PX_LAST")` | `=BDP("CEPO US Equity","VOLUME")` | `=BDP("CEPO US Equity","VOLUME_AVG_30D")` | `=BDP("CEPO US Equity","EQY_SH_OUT")` |
| 11 | CYPH | `=BDP("CYPH US Equity","PX_LAST")` | `=BDP("CYPH US Equity","VOLUME")` | `=BDP("CYPH US Equity","VOLUME_AVG_30D")` | `=BDP("CYPH US Equity","EQY_SH_OUT")` |
| 12 | DFDV | `=BDP("DFDV US Equity","PX_LAST")` | `=BDP("DFDV US Equity","VOLUME")` | `=BDP("DFDV US Equity","VOLUME_AVG_30D")` | `=BDP("DFDV US Equity","EQY_SH_OUT")` |
| 13 | EMPD | `=BDP("EMPD US Equity","PX_LAST")` | `=BDP("EMPD US Equity","VOLUME")` | `=BDP("EMPD US Equity","VOLUME_AVG_30D")` | `=BDP("EMPD US Equity","EQY_SH_OUT")` |
| 14 | ETHM | `=BDP("ETHM US Equity","PX_LAST")` | `=BDP("ETHM US Equity","VOLUME")` | `=BDP("ETHM US Equity","VOLUME_AVG_30D")` | `=BDP("ETHM US Equity","EQY_SH_OUT")` |
| 15 | ETHZ | `=BDP("ETHZ US Equity","PX_LAST")` | `=BDP("ETHZ US Equity","VOLUME")` | `=BDP("ETHZ US Equity","VOLUME_AVG_30D")` | `=BDP("ETHZ US Equity","EQY_SH_OUT")` |
| 16 | FGNX | `=BDP("FGNX US Equity","PX_LAST")` | `=BDP("FGNX US Equity","VOLUME")` | `=BDP("FGNX US Equity","VOLUME_AVG_30D")` | `=BDP("FGNX US Equity","EQY_SH_OUT")` |
| 17 | FWDI | `=BDP("FWDI US Equity","PX_LAST")` | `=BDP("FWDI US Equity","VOLUME")` | `=BDP("FWDI US Equity","VOLUME_AVG_30D")` | `=BDP("FWDI US Equity","EQY_SH_OUT")` |
| 18 | GNLN | `=BDP("GNLN US Equity","PX_LAST")` | `=BDP("GNLN US Equity","VOLUME")` | `=BDP("GNLN US Equity","VOLUME_AVG_30D")` | `=BDP("GNLN US Equity","EQY_SH_OUT")` |
| 19 | HSDT | `=BDP("HSDT US Equity","PX_LAST")` | `=BDP("HSDT US Equity","VOLUME")` | `=BDP("HSDT US Equity","VOLUME_AVG_30D")` | `=BDP("HSDT US Equity","EQY_SH_OUT")` |
| 20 | HYPD | `=BDP("HYPD US Equity","PX_LAST")` | `=BDP("HYPD US Equity","VOLUME")` | `=BDP("HYPD US Equity","VOLUME_AVG_30D")` | `=BDP("HYPD US Equity","EQY_SH_OUT")` |
| 21 | IPST | `=BDP("IPST US Equity","PX_LAST")` | `=BDP("IPST US Equity","VOLUME")` | `=BDP("IPST US Equity","VOLUME_AVG_30D")` | `=BDP("IPST US Equity","EQY_SH_OUT")` |
| 22 | LITS | `=BDP("LITS US Equity","PX_LAST")` | `=BDP("LITS US Equity","VOLUME")` | `=BDP("LITS US Equity","VOLUME_AVG_30D")` | `=BDP("LITS US Equity","EQY_SH_OUT")` |
| 23 | MLAC | `=BDP("MLAC US Equity","PX_LAST")` | `=BDP("MLAC US Equity","VOLUME")` | `=BDP("MLAC US Equity","VOLUME_AVG_30D")` | `=BDP("MLAC US Equity","EQY_SH_OUT")` |
| 24 | MSTR | `=BDP("MSTR US Equity","PX_LAST")` | `=BDP("MSTR US Equity","VOLUME")` | `=BDP("MSTR US Equity","VOLUME_AVG_30D")` | `=BDP("MSTR US Equity","EQY_SH_OUT")` |
| 25 | NA | `=BDP("NA US Equity","PX_LAST")` | `=BDP("NA US Equity","VOLUME")` | `=BDP("NA US Equity","VOLUME_AVG_30D")` | `=BDP("NA US Equity","EQY_SH_OUT")` |
| 26 | NAKA | `=BDP("NAKA US Equity","PX_LAST")` | `=BDP("NAKA US Equity","VOLUME")` | `=BDP("NAKA US Equity","VOLUME_AVG_30D")` | `=BDP("NAKA US Equity","EQY_SH_OUT")` |
| 27 | ORBS | `=BDP("ORBS US Equity","PX_LAST")` | `=BDP("ORBS US Equity","VOLUME")` | `=BDP("ORBS US Equity","VOLUME_AVG_30D")` | `=BDP("ORBS US Equity","EQY_SH_OUT")` |
| 28 | PAPL | `=BDP("PAPL US Equity","PX_LAST")` | `=BDP("PAPL US Equity","VOLUME")` | `=BDP("PAPL US Equity","VOLUME_AVG_30D")` | `=BDP("PAPL US Equity","EQY_SH_OUT")` |
| 29 | PURR | `=BDP("PURR US Equity","PX_LAST")` | `=BDP("PURR US Equity","VOLUME")` | `=BDP("PURR US Equity","VOLUME_AVG_30D")` | `=BDP("PURR US Equity","EQY_SH_OUT")` |
| 30 | SBET | `=BDP("SBET US Equity","PX_LAST")` | `=BDP("SBET US Equity","VOLUME")` | `=BDP("SBET US Equity","VOLUME_AVG_30D")` | `=BDP("SBET US Equity","EQY_SH_OUT")` |
| 31 | SLMT | `=BDP("SLMT US Equity","PX_LAST")` | `=BDP("SLMT US Equity","VOLUME")` | `=BDP("SLMT US Equity","VOLUME_AVG_30D")` | `=BDP("SLMT US Equity","EQY_SH_OUT")` |
| 32 | STSS | `=BDP("STSS US Equity","PX_LAST")` | `=BDP("STSS US Equity","VOLUME")` | `=BDP("STSS US Equity","VOLUME_AVG_30D")` | `=BDP("STSS US Equity","EQY_SH_OUT")` |
| 33 | SUIG | `=BDP("SUIG US Equity","PX_LAST")` | `=BDP("SUIG US Equity","VOLUME")` | `=BDP("SUIG US Equity","VOLUME_AVG_30D")` | `=BDP("SUIG US Equity","EQY_SH_OUT")` |
| 34 | SVRN | `=BDP("SVRN US Equity","PX_LAST")` | `=BDP("SVRN US Equity","VOLUME")` | `=BDP("SVRN US Equity","VOLUME_AVG_30D")` | `=BDP("SVRN US Equity","EQY_SH_OUT")` |
| 35 | THAR | `=BDP("THAR US Equity","PX_LAST")` | `=BDP("THAR US Equity","VOLUME")` | `=BDP("THAR US Equity","VOLUME_AVG_30D")` | `=BDP("THAR US Equity","EQY_SH_OUT")` |
| 36 | TLGYF | `=BDP("TLGYF US Equity","PX_LAST")` | `=BDP("TLGYF US Equity","VOLUME")` | `=BDP("TLGYF US Equity","VOLUME_AVG_30D")` | `=BDP("TLGYF US Equity","EQY_SH_OUT")` |
| 37 | TONX | `=BDP("TONX US Equity","PX_LAST")` | `=BDP("TONX US Equity","VOLUME")` | `=BDP("TONX US Equity","VOLUME_AVG_30D")` | `=BDP("TONX US Equity","EQY_SH_OUT")` |
| 38 | TRON | `=BDP("TRON US Equity","PX_LAST")` | `=BDP("TRON US Equity","VOLUME")` | `=BDP("TRON US Equity","VOLUME_AVG_30D")` | `=BDP("TRON US Equity","EQY_SH_OUT")` |
| 39 | UPXI | `=BDP("UPXI US Equity","PX_LAST")` | `=BDP("UPXI US Equity","VOLUME")` | `=BDP("UPXI US Equity","VOLUME_AVG_30D")` | `=BDP("UPXI US Equity","EQY_SH_OUT")` |
| 40 | ZONE | `=BDP("ZONE US Equity","PX_LAST")` | `=BDP("ZONE US Equity","VOLUME")` | `=BDP("ZONE US Equity","VOLUME_AVG_30D")` | `=BDP("ZONE US Equity","EQY_SH_OUT")` |

### Columns F-M: Additional Fields

For each row, add these formulas (example for row 2 - ALTS):

| Column | Header | Formula |
|--------|--------|---------|
| F | Market_Cap | `=BDP("ALTS US Equity","CUR_MKT_CAP")` |
| G | Total_Debt | `=BDP("ALTS US Equity","TOT_DEBT")` |
| H | Cash | `=BDP("ALTS US Equity","CASH_AND_ST_INVESTMENTS")` |
| I | Enterprise_Value | `=BDP("ALTS US Equity","CURR_ENTP_VAL")` |
| J | VWAP | `=BDP("ALTS US Equity","VWAP")` |
| K | Price_3D_Ago | `=BDH("ALTS US Equity","PX_LAST",TODAY()-3,TODAY()-3)` |
| L | Price_7D_Ago | `=BDH("ALTS US Equity","PX_LAST",TODAY()-7,TODAY()-7)` |
| M | Price_30D_Ago | `=BDH("ALTS US Equity","PX_LAST",TODAY()-30,TODAY()-30)` |

---

## Quick Setup Using BDS Formula

Alternatively, use a BDS formula to pull all fields at once (more advanced):

```
=BDS("ALTS US Equity","PX_LAST,VOLUME,VOLUME_AVG_30D,EQY_SH_OUT,CUR_MKT_CAP,TOT_DEBT,CASH_AND_ST_INVESTMENTS,CURR_ENTP_VAL,VWAP")
```

---

## Bloomberg Field Reference

| Field | Bloomberg Code | Description |
|-------|----------------|-------------|
| Last Price | PX_LAST | Current stock price |
| Volume | VOLUME | Today's trading volume |
| 30D Avg Volume | VOLUME_AVG_30D | 30-day average volume |
| Shares Outstanding | EQY_SH_OUT | Total shares outstanding (millions) |
| Market Cap | CUR_MKT_CAP | Market capitalization (millions) |
| Total Debt | TOT_DEBT | Total debt |
| Cash | CASH_AND_ST_INVESTMENTS | Cash and short-term investments |
| Enterprise Value | CURR_ENTP_VAL | Enterprise value (millions) |
| VWAP | VWAP | Volume-weighted average price |

---

## Exporting to CSV

### Manual Export
1. Select all data (Ctrl+A)
2. Copy (Ctrl+C)
3. Open new workbook
4. Paste Values (Ctrl+Shift+V or Paste Special > Values)
5. Save As > CSV > `bloomberg_data.csv`
6. Place in `data\exports\` folder

### Automated Export (VBA)
See `bloomberg_vba.bas` for automation code.

---

## Notes

- Shares Outstanding (EQY_SH_OUT) is in millions - the Python script handles conversion
- Market Cap (CUR_MKT_CAP) is in millions - the Python script handles conversion
- BDH for historical prices may return arrays - use INDEX() if needed
- Some tickers may not be found - Bloomberg will show #N/A
- Refresh data before exporting: Bloomberg menu > Refresh All Data
