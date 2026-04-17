"""
Running performance analyzer.

Usage:
    python analyze.py

Produces a multi-panel chart saved to output/performance.png and displayed
on screen. Requires .env with STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET.
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from strava_api import StravaClient
from strava_auth import get_token


# ── helpers ──────────────────────────────────────────────────────────────────

def pace_to_min_per_km(speed_m_s: float) -> float:
    """Convert m/s to min/km. Returns NaN for zero or missing speed."""
    if not speed_m_s:
        return float("nan")
    return 1000 / speed_m_s / 60


def format_pace(min_per_km: float) -> str:
    if np.isnan(min_per_km):
        return "—"
    mins = int(min_per_km)
    secs = int((min_per_km - mins) * 60)
    return f"{mins}:{secs:02d}"


def rolling_mean(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=1).mean()


# ── data loading ─────────────────────────────────────────────────────────────

def load_dataframe(activities: list[dict]) -> pd.DataFrame:
    rows = []
    for a in activities:
        rows.append({
            "date": pd.to_datetime(a["start_date_local"]),
            "distance_km": a["distance"] / 1000,
            "moving_time_min": a["moving_time"] / 60,
            "pace_min_km": pace_to_min_per_km(a.get("average_speed", 0)),
            "heart_rate": a.get("average_heartrate"),
            "max_hr": a.get("max_heartrate"),
            "elevation_m": a.get("total_elevation_gain", 0),
            "suffer_score": a.get("suffer_score"),
            "name": a.get("name", ""),
        })

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df["week"] = df["date"].dt.to_period("W").dt.start_time
    df["month"] = df["date"].dt.to_period("M").dt.start_time
    return df


# ── plotting ─────────────────────────────────────────────────────────────────

def plot_performance(df: pd.DataFrame, athlete_name: str) -> None:
    if df.empty:
        print("No running activities found.")
        return

    # Weekly aggregates
    weekly = (
        df.groupby("week")
        .agg(
            total_km=("distance_km", "sum"),
            runs=("distance_km", "count"),
            avg_pace=("pace_min_km", "mean"),
            avg_hr=("heart_rate", "mean"),
            longest=("distance_km", "max"),
        )
        .reset_index()
    )

    fig, axes = plt.subplots(3, 2, figsize=(14, 16))
    fig.suptitle(
        f"{athlete_name} — Running Performance Over Time",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    palette = {
        "blue": "#2563EB",
        "green": "#16A34A",
        "red": "#DC2626",
        "orange": "#EA580C",
        "purple": "#7C3AED",
        "teal": "#0D9488",
    }

    def style_ax(ax, title, ylabel, color):
        ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.tick_params(axis="both", labelsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        ax.spines[["top", "right"]].set_visible(False)

    # 1. Pace over time (lower = faster)
    ax = axes[0, 0]
    valid_pace = df.dropna(subset=["pace_min_km"])
    if not valid_pace.empty:
        ax.scatter(valid_pace["date"], valid_pace["pace_min_km"], alpha=0.3, s=15, color=palette["blue"])
        smooth = rolling_mean(valid_pace.set_index("date")["pace_min_km"], 10).reset_index()
        ax.plot(smooth["date"], smooth["pace_min_km"], color=palette["blue"], linewidth=2, label="10-run avg")

        # Y-axis: invert so faster (lower min/km) appears higher
        ylim = ax.get_ylim()
        ax.set_ylim(ylim[1], ylim[0])
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: format_pace(v)))
    style_ax(ax, "Pace Over Time (lower = faster)", "min/km", palette["blue"])
    ax.legend(fontsize=8)

    # 2. Weekly mileage
    ax = axes[0, 1]
    ax.bar(weekly["week"], weekly["total_km"], width=5, color=palette["green"], alpha=0.7)
    ax.plot(weekly["week"], rolling_mean(weekly["total_km"], 4), color=palette["green"],
            linewidth=2, label="4-week avg")
    style_ax(ax, "Weekly Distance", "km", palette["green"])
    ax.legend(fontsize=8)

    # 3. Heart rate trend
    ax = axes[1, 0]
    hr_df = df.dropna(subset=["heart_rate"])
    if not hr_df.empty:
        ax.scatter(hr_df["date"], hr_df["heart_rate"], alpha=0.3, s=15, color=palette["red"])
        smooth_hr = rolling_mean(hr_df.set_index("date")["heart_rate"], 10).reset_index()
        ax.plot(smooth_hr["date"], smooth_hr["heart_rate"], color=palette["red"],
                linewidth=2, label="10-run avg")
    style_ax(ax, "Average Heart Rate", "bpm", palette["red"])
    ax.legend(fontsize=8)

    # 4. Longest run per month
    ax = axes[1, 1]
    monthly_long = df.groupby("month")["distance_km"].max().reset_index()
    ax.bar(monthly_long["month"], monthly_long["distance_km"], width=20,
           color=palette["orange"], alpha=0.8)
    style_ax(ax, "Longest Run Per Month", "km", palette["orange"])

    # 5. Run count per month
    ax = axes[2, 0]
    monthly_count = df.groupby("month")["distance_km"].count().reset_index()
    monthly_count.columns = ["month", "count"]
    ax.bar(monthly_count["month"], monthly_count["count"], width=20,
           color=palette["purple"], alpha=0.8)
    style_ax(ax, "Runs Per Month", "count", palette["purple"])

    # 6. Pace vs distance scatter (effort analysis)
    ax = axes[2, 1]
    valid = df.dropna(subset=["pace_min_km"])
    if not valid.empty:
        sc = ax.scatter(
            valid["distance_km"],
            valid["pace_min_km"],
            c=mdates.date2num(valid["date"]),
            cmap="viridis",
            alpha=0.6,
            s=20,
        )
        cbar = plt.colorbar(sc, ax=ax)
        cbar.ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: mdates.num2date(v).strftime("%b '%y"))
        )
        cbar.ax.tick_params(labelsize=7)

        # Invert Y so faster is higher
        ylim = ax.get_ylim()
        ax.set_ylim(ylim[1], ylim[0])
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: format_pace(v)))

    ax.set_title("Pace vs Distance (color = recency)", fontsize=11, fontweight="bold", pad=8)
    ax.set_xlabel("Distance (km)", fontsize=9)
    ax.set_ylabel("Pace (min/km)", fontsize=9)
    ax.tick_params(axis="both", labelsize=8)
    ax.grid(alpha=0.3, linestyle="--")
    ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.97])

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "performance.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"\nChart saved to {output_path}")
    plt.show()


# ── summary stats ─────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        return

    total_runs = len(df)
    total_km = df["distance_km"].sum()
    date_range = f"{df['date'].min().strftime('%b %Y')} → {df['date'].max().strftime('%b %Y')}"

    # Compare first vs last 10 runs by pace
    valid = df.dropna(subset=["pace_min_km"])
    if len(valid) >= 20:
        early_pace = valid.head(10)["pace_min_km"].mean()
        recent_pace = valid.tail(10)["pace_min_km"].mean()
        pace_delta = early_pace - recent_pace
        improvement = f"+{pace_delta:.2f} min/km faster" if pace_delta > 0 else f"{pace_delta:.2f} min/km"
    else:
        early_pace = recent_pace = pace_delta = None
        improvement = "not enough data"

    print("\n" + "=" * 50)
    print("RUNNING PERFORMANCE SUMMARY")
    print("=" * 50)
    print(f"Period:          {date_range}")
    print(f"Total runs:      {total_runs}")
    print(f"Total distance:  {total_km:.1f} km")
    print(f"Avg distance:    {df['distance_km'].mean():.2f} km/run")
    if early_pace:
        print(f"Early avg pace:  {format_pace(early_pace)} min/km (first 10 runs)")
        print(f"Recent avg pace: {format_pace(recent_pace)} min/km (last 10 runs)")
        print(f"Pace change:     {improvement}")
    hr_df = df.dropna(subset=["heart_rate"])
    if not hr_df.empty:
        print(f"Avg heart rate:  {hr_df['heart_rate'].mean():.0f} bpm")
    print("=" * 50)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Strava Running Performance Analyzer")
    print("─" * 40)

    token = get_token()
    client = StravaClient(token["access_token"])

    athlete = client.get_athlete()
    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    print(f"\nAuthenticated as: {name}")

    print("\nFetching running activities...")
    runs = client.get_running_activities()
    print(f"Found {len(runs)} run(s).")

    if not runs:
        print("No running activities found on your Strava account.")
        return

    df = load_dataframe(runs)
    print_summary(df)
    plot_performance(df, name or "Athlete")


if __name__ == "__main__":
    main()
