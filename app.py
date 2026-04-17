"""
Flask web app for Strava running performance dashboard.

Usage:
    python app.py

Visit http://localhost:5000, click "Connect with Strava", and authorize.
"""

from __future__ import annotations

import time
from functools import wraps

import pandas as pd
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
import os

from analyze import format_pace, load_dataframe
from metrics import compute_fitness_fatigue, find_prs, year_over_year
from strava_api import StravaClient

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"


# ── auth helpers ──────────────────────────────────────────────────────────────

def _refresh_token(refresh_token: str) -> dict:
    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "token" not in session:
            return redirect(url_for("index"))
        token = session["token"]
        if token.get("expires_at", 0) < time.time() + 60:
            try:
                session["token"] = _refresh_token(token["refresh_token"])
            except Exception:
                session.clear()
                return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "token" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/auth/strava")
def auth_strava():
    redirect_uri = url_for("auth_callback", _external=True)
    auth_url = (
        f"{STRAVA_AUTH_URL}?client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=activity:read_all"
        f"&approval_prompt=auto"
    )
    return redirect(auth_url)


@app.route("/auth/callback")
def auth_callback():
    error = request.args.get("error")
    if error:
        return redirect(url_for("index"))

    code = request.args.get("code")
    if not code:
        return redirect(url_for("index"))

    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    }, timeout=10)
    resp.raise_for_status()
    token = resp.json()
    session["token"] = token
    session["athlete"] = token.get("athlete", {})
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@require_auth
def dashboard():
    athlete = session.get("athlete", {})
    return render_template("dashboard.html", athlete=athlete)


@app.route("/api/data")
@require_auth
def api_data():
    client = StravaClient(session["token"]["access_token"])

    runs = client.get_running_activities()
    if not runs:
        return jsonify({"error": "No running activities found on your Strava account."})

    df = load_dataframe(runs)

    # ── per-run series ────────────────────────────────────────────────────────
    run_rows = (
        df[["date", "distance_km", "pace_min_km", "heart_rate", "elevation_m"]]
        .copy()
    )
    run_rows["date"] = run_rows["date"].dt.strftime("%Y-%m-%d")
    run_rows = run_rows.where(pd.notnull(run_rows), None)

    # ── weekly volume ─────────────────────────────────────────────────────────
    weekly = (
        df.groupby("week")
        .agg(total_km=("distance_km", "sum"), runs=("distance_km", "count"))
        .reset_index()
    )
    weekly["week"] = weekly["week"].dt.strftime("%Y-%m-%d")

    # ── fitness / fatigue / form ──────────────────────────────────────────────
    ff = compute_fitness_fatigue(df)
    ff["date"] = ff["date"].dt.strftime("%Y-%m-%d")

    # ── personal records ──────────────────────────────────────────────────────
    prs_raw = find_prs(df)
    prs = {
        label: {
            "pace": format_pace(info["pace"]),
            "pace_raw": round(info["pace"], 2),
            "date": info["date"].strftime("%d %b %Y"),
            "distance_km": round(info["distance_km"], 2),
        }
        for label, info in prs_raw.items()
    }

    # ── year-over-year ────────────────────────────────────────────────────────
    yoy = year_over_year(df)
    yoy_payload = {
        "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "years": {str(yr): [round(v, 1) for v in yoy[yr].fillna(0).tolist()]
                  for yr in yoy.columns},
    }

    # ── cumulative distance ───────────────────────────────────────────────────
    cum = df.sort_values("date")[["date", "distance_km"]].copy()
    cum["cumulative_km"] = cum["distance_km"].cumsum().round(1)
    cum["date"] = cum["date"].dt.strftime("%Y-%m-%d")

    # ── aerobic efficiency ────────────────────────────────────────────────────
    eff_df = df.dropna(subset=["pace_min_km", "heart_rate"]).copy()
    eff_df["efficiency"] = (1000 / eff_df["pace_min_km"]) / eff_df["heart_rate"]
    eff_df = eff_df[["date", "efficiency"]].copy()
    eff_df["date"] = eff_df["date"].dt.strftime("%Y-%m-%d")

    # ── summary cards ─────────────────────────────────────────────────────────
    valid = df.dropna(subset=["pace_min_km"])
    summary: dict = {
        "total_runs": len(df),
        "total_km": round(df["distance_km"].sum(), 1),
        "avg_distance": round(df["distance_km"].mean(), 2),
    }
    if len(valid) >= 20:
        early = valid.head(10)["pace_min_km"].mean()
        recent = valid.tail(10)["pace_min_km"].mean()
        summary["early_pace"] = format_pace(early)
        summary["recent_pace"] = format_pace(recent)
        summary["pace_improved"] = early > recent
    hr_df = df.dropna(subset=["heart_rate"])
    if not hr_df.empty:
        summary["avg_hr"] = round(hr_df["heart_rate"].mean())

    return jsonify({
        "summary": summary,
        "runs": run_rows.to_dict("records"),
        "weekly": weekly.to_dict("records"),
        "fitness": ff[["date", "CTL", "ATL", "TSB"]].round(2).to_dict("records"),
        "prs": prs,
        "yoy": yoy_payload,
        "cumulative": cum[["date", "cumulative_km"]].to_dict("records"),
        "efficiency": eff_df.to_dict("records"),
    })


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
