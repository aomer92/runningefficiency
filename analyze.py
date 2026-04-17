"""
Running performance analyzer.

Usage:
    python analyze.py

Produces two charts saved to output/ and displayed on screen:
  performance.png  — pace, volume, HR, distance trends
  advanced.png     — fitness/fatigue/form, personal records, year-over-year

Requires .env with STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from metrics import compute_fitness_fatigue, find_prs, year_over_year
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


# ── advanced chart ────────────────────────────────────────────────────────────

def plot_advanced(df: pd.DataFrame, athlete_name: str) -> None:
    """Second chart page: fitness/fatigue/form, personal records, year-over-year."""
    if df.empty:
        return

    fig = plt.figure(figsize=(14, 16))
    fig.suptitle(
        f"{athlete_name} — Advanced Metrics",
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

    def style_date_ax(ax, title, ylabel):
        ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.tick_params(axis="both", labelsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        ax.spines[["top", "right"]].set_visible(False)

    # 1. Fitness / Fatigue / Form (CTL / ATL / TSB) — tall panel, full width
    ax1 = fig.add_subplot(3, 1, 1)
    ff = compute_fitness_fatigue(df)

    ax1.fill_between(ff["date"], ff["CTL"], alpha=0.15, color=palette["blue"])
    ax1.plot(ff["date"], ff["CTL"], color=palette["blue"], linewidth=2, label="Fitness (CTL 42d)")
    ax1.plot(ff["date"], ff["ATL"], color=palette["orange"], linewidth=1.5,
             linestyle="--", label="Fatigue (ATL 7d)")

    ax_tsb = ax1.twinx()
    ax_tsb.fill_between(
        ff["date"], ff["TSB"], 0,
        where=(ff["TSB"] >= 0), alpha=0.2, color=palette["green"], label="Form +"
    )
    ax_tsb.fill_between(
        ff["date"], ff["TSB"], 0,
        where=(ff["TSB"] < 0), alpha=0.2, color=palette["red"], label="Form −"
    )
    ax_tsb.axhline(0, color="grey", linewidth=0.8, linestyle=":")
    ax_tsb.set_ylabel("Form (TSB)", fontsize=9, color="grey")
    ax_tsb.tick_params(axis="y", labelsize=8, labelcolor="grey")
    ax_tsb.spines[["top"]].set_visible(False)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax_tsb.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper left")
    style_date_ax(ax1, "Performance Management Chart (Fitness / Fatigue / Form)", "Load (arb. units)")

    # 2. Personal Records table — bottom left
    ax2 = fig.add_subplot(3, 2, 3)
    ax2.axis("off")
    prs = find_prs(df)
    if prs:
        rows = [
            [
                label,
                format_pace(info["pace"]),
                f"{info['distance_km']:.2f} km",
                info["date"].strftime("%d %b %Y"),
            ]
            for label, info in prs.items()
        ]
        tbl = ax2.table(
            cellText=rows,
            colLabels=["Distance", "Best Pace", "Actual dist.", "Date"],
            cellLoc="center",
            loc="center",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        tbl.scale(1, 1.6)
        for (r, c), cell in tbl.get_celld().items():
            cell.set_edgecolor("#dddddd")
            if r == 0:
                cell.set_facecolor("#2563EB")
                cell.set_text_props(color="white", fontweight="bold")
            elif r % 2 == 0:
                cell.set_facecolor("#f0f4ff")
    ax2.set_title("Personal Records (best pace ±15% of distance)", fontsize=11, fontweight="bold", pad=8)

    # 3. Year-over-year monthly mileage — bottom right
    ax3 = fig.add_subplot(3, 2, 4)
    yoy = year_over_year(df)
    years = yoy.columns.tolist()
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    x = np.arange(12)
    bar_width = 0.8 / max(len(years), 1)
    year_colors = plt.cm.tab10(np.linspace(0, 0.6, len(years)))

    for i, (year, color) in enumerate(zip(years, year_colors)):
        vals = yoy[year].fillna(0).values
        ax3.bar(x + i * bar_width, vals, width=bar_width, label=str(year),
                color=color, alpha=0.85)

    ax3.set_xticks(x + bar_width * (len(years) - 1) / 2)
    ax3.set_xticklabels(months, fontsize=8)
    ax3.set_title("Year-over-Year Monthly Distance", fontsize=11, fontweight="bold", pad=8)
    ax3.set_ylabel("km", fontsize=9)
    ax3.tick_params(axis="y", labelsize=8)
    ax3.legend(fontsize=8, title="Year", title_fontsize=8)
    ax3.grid(axis="y", alpha=0.3, linestyle="--")
    ax3.spines[["top", "right"]].set_visible(False)

    # 4. Effort efficiency: pace vs heart rate (aerobic efficiency)
    ax4 = fig.add_subplot(3, 2, 5)
    eff = df.dropna(subset=["pace_min_km", "heart_rate"]).copy()
    if not eff.empty:
        # Aerobic efficiency = speed (m/min) / heart rate
        eff["speed_m_min"] = 1000 / eff["pace_min_km"]
        eff["efficiency"] = eff["speed_m_min"] / eff["heart_rate"]
        sc = ax4.scatter(
            eff["date"], eff["efficiency"],
            c=mdates.date2num(eff["date"]), cmap="plasma",
            alpha=0.5, s=18,
        )
        smooth_eff = eff.set_index("date")["efficiency"].rolling(10, min_periods=1).mean().reset_index()
        ax4.plot(smooth_eff["date"], smooth_eff["efficiency"], color=palette["teal"],
                 linewidth=2, label="10-run avg")
        ax4.legend(fontsize=8)
        style_date_ax(ax4, "Aerobic Efficiency (speed / HR, higher = better)", "m/min per bpm")
    else:
        ax4.text(0.5, 0.5, "Heart rate data not available",
                 ha="center", va="center", transform=ax4.transAxes, color="grey")
        ax4.axis("off")

    # 5. Cumulative distance (progress line)
    ax5 = fig.add_subplot(3, 2, 6)
    df_sorted = df.sort_values("date")
    ax5.fill_between(df_sorted["date"], df_sorted["distance_km"].cumsum(),
                     alpha=0.2, color=palette["purple"])
    ax5.plot(df_sorted["date"], df_sorted["distance_km"].cumsum(),
             color=palette["purple"], linewidth=2)
    style_date_ax(ax5, "Cumulative Distance", "km")

    plt.tight_layout(rect=[0, 0, 1, 0.97])

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "advanced.png"
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Chart saved to {output_path}")
    plt.show()


# ── summary stats ─────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        return

    total_runs = len(df)
    total_km = df["distance_km"].sum()
    date_range = f"{df['date'].min().strftime('%b %Y')} → {df['date'].max().strftime('%b %Y')}"

    valid = df.dropna(subset=["pace_min_km"])
    if len(valid) >= 20:
        early_pace = valid.head(10)["pace_min_km"].mean()
        recent_pace = valid.tail(10)["pace_min_km"].mean()
        pace_delta = early_pace - recent_pace
        improvement = f"+{pace_delta:.2f} min/km faster" if pace_delta > 0 else f"{pace_delta:.2f} min/km"
    else:
        early_pace = recent_pace = None
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

    prs = find_prs(df)
    if prs:
        print("\nPersonal Records:")
        for label, info in prs.items():
            print(f"  {label:<16} {format_pace(info['pace'])} min/km  ({info['date'].strftime('%d %b %Y')})")

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

    label = name or "Athlete"
    plot_performance(df, label)
    plot_advanced(df, label)


if __name__ == "__main__":
    main()
