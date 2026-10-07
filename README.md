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
| `--from-clarity` | — | Read a Dexcom Clarity CSV export instead of calling the API |

## From a Dexcom Clarity export

If the API isn't returning your data (for example with a Stelo sensor),
export it from the Clarity web app and let the script split it into the
same daily files.

### Workflow after wearing your CGM

1. **Export the CSV from Clarity.** In the Clarity web app, use the
   **Export** button, choose the date range you wore the sensor, and
   download the `.csv` file. Use the CSV export, not the PDF report; the
   PDF only has charts, so the script can't read it.
2. **Put the CSV in this folder.** All `.csv` files are gitignored, so
   neither the export (which includes your name and date of birth) nor
   the daily files will be committed.
3. **Run the script.** Adding the file doesn't do anything on its own:

   ```bash
   python3 dexcom_daily_report.py --from-clarity <export-file>.csv
   ```

   This writes one `egvs_<date>.csv` per day into this folder.

Tips:

- Export after the last day you want, so that day is complete. Days with
  incomplete data are flagged as `(partial day)` in the output.
- Overlapping exports are fine: days that appear again are rewritten
  with the same readings.

### Options

```bash
# One egvs_<date>.csv per day in the export
python3 dexcom_daily_report.py --from-clarity clarity_export.csv

# Just one day
python3 dexcom_daily_report.py --from-clarity clarity_export.csv \
    --date 2026-08-26 --out report.csv
```

Only EGV rows are used (alerts, events and patient info are skipped).
Days at the edges of the export range are flagged as partial. mmol/L
exports are converted to mg/dL, and out-of-range readings stay as
`Low` / `High`.

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
