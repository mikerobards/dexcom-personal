# Dexcom Daily EGV Report

Fetches one full calendar day (00:00:00–23:59:59) of estimated glucose
values (EGVs) from the Dexcom API v3 and exports them as a CSV, for use
as CGM experiment data.

## Requirements

- Python 3.9+ (standard library only, nothing to install)
- A Dexcom OAuth 2.0 access token (placeholder used until provided)

## Usage

```bash
# Yesterday's readings from the sandbox environment
python3 dexcom_daily_report.py

# A specific day
python3 dexcom_daily_report.py --date 2026-08-27

# Production (US) with a custom output path
DEXCOM_ACCESS_TOKEN="your-token" python3 dexcom_daily_report.py \
    --date 2026-08-27 --env us --out report.csv
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--date` | yesterday | Day to report on, `YYYY-MM-DD` |
| `--env` | `sandbox` | `sandbox`, `us`, `eu`, or `jp` |
| `--out` | `egvs_<date>.csv` | Output CSV path |

## Auth

Set the `DEXCOM_ACCESS_TOKEN` environment variable to a valid bearer
token. Until then the script uses a placeholder and the API will return
401 Unauthorized (the script reports this clearly).

## Output

CSV with one row per reading (~288/day at 5-minute intervals):

```csv
displayTime,value_mg_dl
2026-08-27T00:02:33-07:00,112
2026-08-27T00:07:33-07:00,115
```
