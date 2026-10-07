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

from __future__ import annotations

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
DATA_RANGE_PATH = "/v3/users/self/dataRange"


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
    """Fetch all EGV records for one local calendar day (00:00:00-23:59:59).

    The API interprets startDate/endDate as UTC (systemTime), but a "day"
    for the wearer is defined by displayTime (their local clock). Query a
    padded window, then keep only readings whose displayTime falls on the
    requested date.
    """
    start = datetime.combine(day, datetime.min.time()) - timedelta(days=1)
    end = start + timedelta(days=3)

    payload = api_get(env, EGVS_PATH, {
        "startDate": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "endDate": end.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    records = payload.get("records", [])
    matched = [r for r in records if str(r.get("displayTime", "")).startswith(day.isoformat())]

    if not matched:
        explain_empty(env, day, start, end, records)
    return matched


def api_get(env: str, path: str, params: dict | None = None) -> dict:
    """GET a Dexcom API path and return the decoded JSON body."""
    url = f"{BASE_URLS[env]}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

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
    return payload


def explain_empty(env: str, day: date, start: datetime, end: datetime,
                  records: list[dict]) -> None:
    """Print why a day came back empty: what the API returned and what it holds."""
    print(f"Diagnostics ({env}, {BASE_URLS[env]}):", file=sys.stderr)
    try:
        import dexcom_auth
        token_env = json.loads(dexcom_auth.TOKENS_FILE.read_text()).get("env")
        print(f"  Saved login is for env: {token_env}", file=sys.stderr)
    except Exception:
        print("  No saved login found (using DEXCOM_ACCESS_TOKEN)", file=sys.stderr)
    print(f"  Queried {start:%Y-%m-%dT%H:%M:%S} to {end:%Y-%m-%dT%H:%M:%S} (UTC): "
          f"{len(records)} records returned", file=sys.stderr)
    if records:
        times = sorted(str(r.get("displayTime")) for r in records)
        print(f"  Their displayTime spans {times[0]} to {times[-1]}; "
              f"none start with {day.isoformat()}", file=sys.stderr)

    payload = api_get(env, DATA_RANGE_PATH)
    egvs = payload.get("egvs")
    if egvs:
        first = (egvs.get("start") or {}).get("displayTime")
        last = (egvs.get("end") or {}).get("displayTime")
        print(f"  Dexcom holds EGVs for this account from {first} to {last}",
              file=sys.stderr)
        print_daily_counts(env, "around the requested day",
                           datetime.combine(day, datetime.min.time()) - timedelta(days=14))
        last_system = (egvs.get("end") or {}).get("systemTime") or last
        if last_system:
            latest = datetime.fromisoformat(str(last_system)[:19])
            print_daily_counts(env, "the last week of data Dexcom reports",
                               latest - timedelta(days=7), days=8)
    else:
        print("  Dexcom reports NO EGV data for this account at all "
              f"(dataRange response: {json.dumps(payload)})", file=sys.stderr)



def print_daily_counts(env: str, label: str, start: datetime, days: int = 29) -> None:
    """Print EGV readings per local day for a window (stays under the API's range limit)."""
    end = start + timedelta(days=days)
    payload = api_get(env, EGVS_PATH, {
        "startDate": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "endDate": end.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    counts: dict[str, int] = {}
    for record in payload.get("records", []):
        key = str(record.get("displayTime", ""))[:10]
        counts[key] = counts.get(key, 0) + 1
    print(f"  Readings per day {label} ({start:%Y-%m-%d} to {end:%Y-%m-%d} UTC): "
          f"{sum(counts.values())} total", file=sys.stderr)
    for key in sorted(counts):
        print(f"    {key}: {counts[key]}", file=sys.stderr)

# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def write_csv(records: list[dict], out_path: str) -> None:
    """Write one row per EGV reading: timestamp + glucose value (mg/dL)."""
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["displayTime", "value_mg_dl"])
        # API returns newest-first; write chronologically for analysis.
        for record in sorted(records, key=lambda r: r.get("systemTime", "")):
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
