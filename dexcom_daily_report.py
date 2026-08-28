#!/usr/bin/env python3
"""Fetch a daily report of Dexcom EGVs and export it as a CSV.

Calls the Dexcom API v3 EGVs endpoint for one full calendar day
(00:00:00 - 23:59:59) and writes a CSV with one row per reading.

Auth: set the DEXCOM_ACCESS_TOKEN environment variable to a valid
OAuth 2.0 bearer token. Until real auth is provided, a placeholder
is used (the API will return 401).

Usage:
    python3 dexcom_daily_report.py                    # yesterday, sandbox
    python3 dexcom_daily_report.py --date 2026-08-27
    python3 dexcom_daily_report.py --date 2026-08-27 --env us --out report.csv
"""

import argparse
import csv
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URLS = {
    "sandbox": "https://sandbox-api.dexcom.com",  # simulated test users
    "us": "https://api.dexcom.com",
    "eu": "https://api.dexcom.eu",
    "jp": "https://api.dexcom.jp",
}

def get_token() -> str:
    """Saved OAuth tokens first (auto-refreshed), then env var fallback."""
    try:
        import dexcom_auth
        token = dexcom_auth.get_access_token()
        if token:
            return token
    except Exception as err:
        print(f"Warning: could not use saved tokens ({err})", file=sys.stderr)
    return os.environ.get("DEXCOM_ACCESS_TOKEN", "PLACEHOLDER_ACCESS_TOKEN")

EGVS_PATH = "/v3/users/self/egvs"


def _ssl_context() -> ssl.SSLContext:
    """SSL context using certifi's CA bundle when available.

    Works around macOS python.org installs that ship without a linked
    system CA bundle (CERTIFICATE_VERIFY_FAILED).
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def fetch_egvs(env: str, day: date) -> list[dict]:
    """Fetch all EGV records for one calendar day (00:00:00-23:59:59)."""
    start = datetime.combine(day, datetime.min.time())          # 00:00:00
    end = start + timedelta(hours=23, minutes=59, seconds=59)   # 23:59:59

    query = urllib.parse.urlencode({
        "startDate": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "endDate": end.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    url = f"{BASE_URLS[env]}{EGVS_PATH}?{query}"

    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {get_token()}",
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        if err.code == 401:
            sys.exit(
                "Error: Dexcom API returned 401 Unauthorized.\n"
                "Run 'python3 dexcom_auth.py' to authorize with Dexcom "
                "(or set DEXCOM_ACCESS_TOKEN).\n"
                f"Response: {body}"
            )
        sys.exit(f"Error: Dexcom API returned HTTP {err.code}.\nResponse: {body}")
    except urllib.error.URLError as err:
        sys.exit(f"Error: could not reach Dexcom API: {err.reason}")

    return payload.get("records", [])


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def write_csv(records: list[dict], out_path: str) -> None:
    """Write one row per EGV reading: timestamp + glucose value (mg/dL)."""
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["displayTime", "value_mg_dl"])
        for record in records:
            writer.writerow([record.get("displayTime"), record.get("value")])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export one day of Dexcom EGVs to a CSV."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=1),
        help="Day to report on, YYYY-MM-DD (default: yesterday)",
    )
    parser.add_argument(
        "--env",
        choices=BASE_URLS,
        default="sandbox",
        help="Dexcom API environment (default: sandbox)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path (default: egvs_<date>.csv)",
    )
    args = parser.parse_args()

    out_path = args.out or f"egvs_{args.date.isoformat()}.csv"

    records = fetch_egvs(args.env, args.date)
    write_csv(records, out_path)

    print(f"Wrote {len(records)} EGV readings for {args.date} to {out_path}")


if __name__ == "__main__":
    main()
