"""
Strava API client — fetches activities and athlete data.
"""

from __future__ import annotations

import time
from typing import Any

import requests

BASE_URL = "https://www.strava.com/api/v3"


class StravaClient:
    def __init__(self, access_token: str) -> None:
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {access_token}"

    def _get(self, path: str, **params) -> Any:
        resp = self._session.get(f"{BASE_URL}{path}", params=params)
        # Respect Strava rate limits
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(retry_after - int(time.time()), 10)
            print(f"Rate limited. Waiting {wait}s...")
            time.sleep(wait)
            return self._get(path, **params)
        resp.raise_for_status()
        return resp.json()

    def get_athlete(self) -> dict:
        return self._get("/athlete")

    def get_activities(self, per_page: int = 200) -> list[dict]:
        """Fetch all activities, handling pagination automatically."""
        all_activities: list[dict] = []
        page = 1
        while True:
            batch = self._get("/athlete/activities", per_page=per_page, page=page)
            if not batch:
                break
            all_activities.extend(batch)
            print(f"  Fetched page {page} ({len(batch)} activities, {len(all_activities)} total)")
            if len(batch) < per_page:
                break
            page += 1
        return all_activities

    def get_running_activities(self) -> list[dict]:
        """Return only Run-type activities."""
        activities = self.get_activities()
        return [a for a in activities if a.get("type") == "Run"]
