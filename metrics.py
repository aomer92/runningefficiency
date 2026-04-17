"""
Advanced running metrics.

- find_prs: best efforts at standard race distances
- compute_fitness_fatigue: CTL/ATL/TSB (fitness / fatigue / form)
- year_over_year: monthly mileage indexed by year
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STANDARD_DISTANCES = {
    "1K": 1.0,
    "5K": 5.0,
    "10K": 10.0,
    "Half Marathon": 21.0975,
    "Marathon": 42.195,
}


def find_prs(df: pd.DataFrame) -> dict[str, dict]:
    """
    For each standard distance find the fastest run within ±15% of that
    distance. Returns a dict keyed by distance name.
    """
    prs: dict[str, dict] = {}
    for label, target_km in STANDARD_DISTANCES.items():
        band = df["distance_km"].between(target_km * 0.85, target_km * 1.15)
        candidates = df[band].dropna(subset=["pace_min_km"])
        if not candidates.empty:
            best = candidates.loc[candidates["pace_min_km"].idxmin()]
            prs[label] = {
                "pace": best["pace_min_km"],
                "date": best["date"],
                "distance_km": best["distance_km"],
            }
    return prs


def compute_fitness_fatigue(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a daily CTL / ATL / TSB series using exponentially weighted moving
    averages (42-day and 7-day half-lives respectively).

    Load is estimated from suffer_score when >50 % of activities have it,
    otherwise from distance × normalised pace effort.
    """
    df2 = df.copy()
    df2["date_only"] = df2["date"].dt.normalize()

    use_suffer = df2["suffer_score"].notna().sum() > len(df2) * 0.5
    if use_suffer:
        daily_load = (
            df2.groupby("date_only")["suffer_score"]
            .sum()
            .reset_index()
            .rename(columns={"suffer_score": "load"})
        )
    else:
        median_pace = df2["pace_min_km"].median()
        # Effort factor: runs at median pace score 1.0; faster runs score higher.
        df2["effort"] = (median_pace / df2["pace_min_km"].fillna(median_pace)).clip(0.5, 2.0)
        df2["load"] = df2["distance_km"] * df2["effort"]
        daily_load = (
            df2.groupby("date_only")["load"]
            .sum()
            .reset_index()
        )

    # Fill the full date range so EMA has no gaps
    full_range = pd.date_range(daily_load["date_only"].min(), daily_load["date_only"].max(), freq="D")
    daily = pd.DataFrame({"date": full_range})
    daily = daily.merge(daily_load.rename(columns={"date_only": "date"}), on="date", how="left").fillna(0)

    # Exponentially weighted moving averages
    ctl_alpha = 1 - np.exp(-1 / 42)  # chronic (fitness), 42-day half-life
    atl_alpha = 1 - np.exp(-1 / 7)   # acute  (fatigue),  7-day half-life

    daily["CTL"] = daily["load"].ewm(alpha=ctl_alpha, adjust=False).mean()
    daily["ATL"] = daily["load"].ewm(alpha=atl_alpha, adjust=False).mean()
    daily["TSB"] = daily["CTL"] - daily["ATL"]

    return daily


def year_over_year(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a pivot table: rows = month (1-12), columns = year,
    values = total km per month.
    """
    df2 = df.copy()
    df2["year"] = df2["date"].dt.year
    df2["month"] = df2["date"].dt.month
    pivot = (
        df2.groupby(["year", "month"])["distance_km"]
        .sum()
        .unstack("year")
        .reindex(range(1, 13))
    )
    return pivot
