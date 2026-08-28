#!/usr/bin/env python3
"""Dexcom OAuth 2.0 helper: obtain, store, and refresh access tokens.

Run directly to do the one-time browser authorization:

    python3 dexcom_auth.py            # sandbox
    python3 dexcom_auth.py --env us   # production

This opens Dexcom's login page in your browser, catches the redirect on
localhost, exchanges the code for tokens, and saves them next to this
file in .dexcom_tokens.json. After that, dexcom_daily_report.py uses
(and silently refreshes) the saved tokens automatically.

Credentials are read from environment variables or a .env file in this
directory: DEXCOM_CLIENT_ID, DEXCOM_CLIENT_SECRET, DEXCOM_REDIRECT_URI.
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE_URLS = {
    "sandbox": "https://sandbox-api.dexcom.com",
    "us": "https://api.dexcom.com",
    "eu": "https://api.dexcom.eu",
    "jp": "https://api.dexcom.jp",
}

PROJECT_DIR = Path(__file__).resolve().parent
TOKENS_FILE = PROJECT_DIR / ".dexcom_tokens.json"
ENV_FILE = PROJECT_DIR / ".env"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def load_env() -> dict:
    """Read DEXCOM_* settings from the environment, then .env as fallback."""
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    for key in ("DEXCOM_CLIENT_ID", "DEXCOM_CLIENT_SECRET", "DEXCOM_REDIRECT_URI"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    missing = [k for k in ("DEXCOM_CLIENT_ID", "DEXCOM_CLIENT_SECRET") if not values.get(k)]
    if missing:
        sys.exit(f"Error: missing {', '.join(missing)} (set in environment or {ENV_FILE})")
    values.setdefault("DEXCOM_REDIRECT_URI", "http://localhost:8080/callback")
    return values


# ---------------------------------------------------------------------------
# Token exchange / refresh
# ---------------------------------------------------------------------------

def _token_request(env: str, form: dict) -> dict:
    url = f"{BASE_URLS[env]}/v2/oauth2/token"
    data = urllib.parse.urlencode(form).encode()
    request = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
            tokens = json.load(response)
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        sys.exit(f"Error: token request failed (HTTP {err.code}).\nResponse: {body}")
    tokens["obtained_at"] = int(time.time())
    tokens["env"] = env
    return tokens


def save_tokens(tokens: dict) -> None:
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2))
    TOKENS_FILE.chmod(0o600)


def exchange_code(env: str, code: str, cfg: dict) -> dict:
    return _token_request(env, {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": cfg["DEXCOM_CLIENT_ID"],
        "client_secret": cfg["DEXCOM_CLIENT_SECRET"],
        "redirect_uri": cfg["DEXCOM_REDIRECT_URI"],
    })


def refresh_tokens(tokens: dict, cfg: dict) -> dict:
    return _token_request(tokens.get("env", "sandbox"), {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": cfg["DEXCOM_CLIENT_ID"],
        "client_secret": cfg["DEXCOM_CLIENT_SECRET"],
    })


def get_access_token() -> str | None:
    """Return a valid access token from the store, refreshing if stale.

    Returns None when no token store exists (caller decides the fallback).
    """
    if not TOKENS_FILE.exists():
        return None
    tokens = json.loads(TOKENS_FILE.read_text())
    age = time.time() - tokens.get("obtained_at", 0)
    # Refresh a minute before the reported expiry (typically 7200s).
    if age > tokens.get("expires_in", 7200) - 60:
        tokens = refresh_tokens(tokens, load_env())
        save_tokens(tokens)
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# One-time browser authorization
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CallbackHandler.code = (params.get("code") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        message = ("Authorization complete. You can close this tab."
                   if _CallbackHandler.code else
                   f"No authorization code received. Query: {self.path}")
        self.wfile.write(f"<h2>{message}</h2>".encode())

    def log_message(self, *args):
        pass  # keep the console quiet


def authorize(env: str) -> None:
    cfg = load_env()
    redirect = urllib.parse.urlparse(cfg["DEXCOM_REDIRECT_URI"])
    port = redirect.port or 8080

    auth_url = f"{BASE_URLS[env]}/v2/oauth2/login?" + urllib.parse.urlencode({
        "client_id": cfg["DEXCOM_CLIENT_ID"],
        "redirect_uri": cfg["DEXCOM_REDIRECT_URI"],
        "response_type": "code",
        "scope": "offline_access",
    })

    server = HTTPServer(("localhost", port), _CallbackHandler)
    print(f"Opening Dexcom login in your browser ({env})...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print(f"Waiting for redirect on {cfg['DEXCOM_REDIRECT_URI']} ...")
    while _CallbackHandler.code is None:
        server.handle_request()
    server.server_close()

    tokens = exchange_code(env, _CallbackHandler.code, cfg)
    save_tokens(tokens)
    print(f"Success! Tokens saved to {TOKENS_FILE}")
    print(f"Access token expires in {tokens.get('expires_in')}s; "
          "it will be refreshed automatically.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Authorize with Dexcom (one-time).")
    parser.add_argument("--env", choices=BASE_URLS, default="sandbox",
                        help="Dexcom environment (default: sandbox)")
    authorize(parser.parse_args().env)
