# StravaDataExport

Fetch Strava athlete activity data and validate pace thresholds such as "did this activity average 8 min/km or faster?"

## What This Handles

- OAuth onboarding for each athlete who connects your Strava app.
- Token storage and refresh in a local SQLite database.
- Activity sync from Strava's `/athlete/activities` API.
- Pace calculation from `moving_time / distance`.
- Threshold reports for 8 min/km or any other pace target.

## Strava Setup

Create a Strava API application from the Strava developer dashboard and set a callback URL. Each athlete must sign in with Strava and authorize your app before you can fetch their activity data.

For private activities, request `activity:read_all`. If you only need visible activity data, use `activity:read`.

New Strava apps start with limited athlete capacity and API rate limits. For roughly 100 people, plan to request Strava review/approval before production use.

## Local Setup

Use Python 3.10+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Set your Strava application credentials:

```powershell
$env:STRAVA_CLIENT_ID = "your-client-id"
$env:STRAVA_CLIENT_SECRET = "your-client-secret"
$env:STRAVA_REDIRECT_URI = "http://localhost:8080/callback"
```

## Onboard an Athlete

Generate an authorization URL:

```powershell
strava-export auth-url
```

Open the URL, have the athlete authorize the app, then copy the returned `code` from your redirect URL.

Store the token bundle:

```powershell
strava-export exchange-code "returned-code"
```

Repeat this for each athlete.

## Sync Activities

Sync every stored athlete:

```powershell
strava-export sync
```

Sync only activities after a date:

```powershell
strava-export sync --after 2026-01-01
```

## Report Pace Thresholds

Print activities that were synced, including whether they averaged 8 min/km or faster:

```powershell
strava-export report --threshold-min-per-km 8
```

Write the report to CSV:

```powershell
strava-export report --threshold-min-per-km 8 --csv data/pace-report.csv
```

The report treats `crossed_threshold=True` as `pace_min_per_km <= threshold`, so a 7.5 min/km activity passes an 8 min/km threshold.

## Report Split Pace

By default, `sync` fetches detailed activity data and stores metric splits when Strava provides them, usually for runs.

Print split-wise average pace for each activity:

```powershell
strava-export splits-report --threshold-min-per-km 8
```

Filter to one activity:

```powershell
strava-export splits-report --activity-id 123456789 --threshold-min-per-km 8
```

Write the split report to CSV:

```powershell
strava-export splits-report --threshold-min-per-km 8 --csv data/split-pace-report.csv
```
