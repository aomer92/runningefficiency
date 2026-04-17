"""
Strava OAuth2 authentication flow.
Starts a local Flask server to handle the callback, exchanges the code
for tokens, and saves them to token.json for reuse.
"""

import json
import os
import threading
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, request

load_dotenv()

TOKEN_FILE = Path("token.json")
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"

_auth_code: str | None = None
_server_done = threading.Event()


def _get_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Missing required env var: {key}. Copy .env.example to .env and fill it in.")
    return value


def load_token() -> dict | None:
    if TOKEN_FILE.exists():
        token = json.loads(TOKEN_FILE.read_text())
        # Refresh if expired (with 60s buffer)
        import time
        if token.get("expires_at", 0) > time.time() + 60:
            return token
        return _refresh_token(token["refresh_token"])
    return None


def _refresh_token(refresh_token: str) -> dict:
    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": _get_env("STRAVA_CLIENT_ID"),
        "client_secret": _get_env("STRAVA_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })
    resp.raise_for_status()
    token = resp.json()
    TOKEN_FILE.write_text(json.dumps(token))
    return token


def _exchange_code(code: str) -> dict:
    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": _get_env("STRAVA_CLIENT_ID"),
        "client_secret": _get_env("STRAVA_CLIENT_SECRET"),
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    token = resp.json()
    TOKEN_FILE.write_text(json.dumps(token))
    return token


def _run_callback_server(port: int) -> None:
    app = Flask(__name__)

    @app.route("/callback")
    def callback():
        global _auth_code
        _auth_code = request.args.get("code")
        _server_done.set()
        return "<h2>Authorization complete! You can close this tab.</h2>"

    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(port=port, use_reloader=False)


def authorize() -> dict:
    client_id = _get_env("STRAVA_CLIENT_ID")
    redirect_uri = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8000/callback")
    port = int(redirect_uri.split(":")[-1].split("/")[0])

    auth_url = (
        f"{STRAVA_AUTH_URL}?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=activity:read_all"
    )

    server_thread = threading.Thread(target=_run_callback_server, args=(port,), daemon=True)
    server_thread.start()

    print(f"\nOpening Strava authorization page in your browser...")
    print(f"If it doesn't open automatically, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    _server_done.wait(timeout=120)
    if not _auth_code:
        raise TimeoutError("Authorization timed out after 120 seconds.")

    return _exchange_code(_auth_code)


def get_token() -> dict:
    """Return a valid token dict, authorizing via browser if needed."""
    token = load_token()
    if token:
        return token
    print("No saved token found. Starting Strava OAuth2 flow...")
    return authorize()
