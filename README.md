# Running Efficiency — Strava Performance Analyzer

Visualizes your running performance over time using data from the Strava API.
Available as a **web app** (recommended) or a **CLI tool**.

## What it shows

- **Pace over time** — are you getting faster?
- **Weekly distance** — training volume trends
- **Heart rate & aerobic efficiency** — fitness over time
- **Fitness / Fatigue / Form** — Performance Management Chart (CTL/ATL/TSB)
- **Personal records** — best pace at 1K, 5K, 10K, half, full marathon
- **Year-over-year** — monthly mileage comparison across years
- **Cumulative distance** — total km banked

## Setup

### 1. Create a Strava API app

1. Go to https://www.strava.com/settings/api
2. Create an application — set **Authorization Callback Domain** to `localhost`
3. Copy your **Client ID** and **Client Secret**

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in Client ID, Client Secret, and a random Flask secret key
```

Generate a Flask secret key with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Web App (recommended)

```bash
python app.py
```

Open http://localhost:5000, click **Connect with Strava**, and authorize.
Your dashboard loads with interactive charts. Token is stored in the session
and refreshed automatically.

---

## CLI Tool

```bash
python analyze.py
```

Opens a browser for one-time authorization, fetches all runs, prints a summary,
and saves two chart images to `output/`.
