# Running Efficiency — Strava Performance Analyzer

Visualizes your running performance over time using data from the Strava API.

## What it shows

- **Pace over time** — are you getting faster?
- **Weekly distance** — training volume trends
- **Heart rate trends** — aerobic fitness over time
- **Longest run per month** — endurance progression
- **Runs per month** — consistency
- **Pace vs distance scatter** — effort distribution across run lengths

## Setup

### 1. Create a Strava API app

1. Go to https://www.strava.com/settings/api
2. Create an application (any name, set *Authorization Callback Domain* to `localhost`)
3. Copy your **Client ID** and **Client Secret**

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your Client ID and Client Secret
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run

```bash
python analyze.py
```

A browser window will open asking you to authorize the app with Strava. After authorizing, the script fetches your runs, prints a summary, and saves a chart to `output/performance.png`.

Your token is saved in `token.json` and refreshed automatically on subsequent runs — you only authorize once.
