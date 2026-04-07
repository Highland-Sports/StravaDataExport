from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

from . import db
from .config import StravaSettings
from .metrics import crossed_pace_threshold, pace_min_per_km
from .strava_client import (
    build_authorization_url,
    ensure_fresh_token,
    exchange_code,
    get_activity,
    list_athlete_activities,
)


DEFAULT_DB = "data/strava.sqlite3"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Sync and validate Strava activity data.")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite database path. Default: {DEFAULT_DB}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("auth-url", help="Print the Strava OAuth authorization URL.")
    auth_parser.add_argument("--scope", default="read,activity:read_all")
    auth_parser.add_argument("--approval-prompt", default="auto", choices=("auto", "force"))

    exchange_parser = subparsers.add_parser("exchange-code", help="Store an athlete token from an OAuth code.")
    exchange_parser.add_argument("code", help="The code returned to your redirect URI by Strava.")

    sync_parser = subparsers.add_parser("sync", help="Sync activities for all stored athletes.")
    sync_parser.add_argument("--after", help="Only fetch activities after this date, formatted YYYY-MM-DD.")
    sync_parser.add_argument("--before", help="Only fetch activities before this date, formatted YYYY-MM-DD.")
    sync_parser.add_argument(
        "--skip-details",
        action="store_true",
        help="Skip per-activity detail fetches. Faster, but split reports will not be populated.",
    )

    report_parser = subparsers.add_parser("report", help="Report whether activities beat a pace threshold.")
    report_parser.add_argument("--threshold-min-per-km", type=float, default=8.0)
    report_parser.add_argument("--csv", help="Optional CSV output path.")

    splits_parser = subparsers.add_parser("splits-report", help="Report split-wise average pace per activity.")
    splits_parser.add_argument("--activity-id", type=int, help="Only show splits for one activity.")
    splits_parser.add_argument("--threshold-min-per-km", type=float, default=8.0)
    splits_parser.add_argument("--csv", help="Optional CSV output path.")

    args = parser.parse_args(argv)

    if args.command == "auth-url":
        settings = StravaSettings.from_env()
        print(build_authorization_url(settings.client_id, settings.redirect_uri, args.scope, args.approval_prompt))
        return

    connection = db.connect(args.db)

    if args.command == "exchange-code":
        settings = StravaSettings.from_env()
        token_bundle = exchange_code(settings.client_id, settings.client_secret, args.code)
        athlete_id = db.upsert_token_bundle(connection, token_bundle)
        print(f"Stored token for athlete {athlete_id}.")
        return

    if args.command == "sync":
        settings = StravaSettings.from_env()
        after_epoch = _date_to_epoch(args.after) if args.after else None
        before_epoch = _date_to_epoch(args.before) if args.before else None
        total = 0
        for token in db.list_tokens(connection):
            access_token, refreshed = ensure_fresh_token(
                settings.client_id,
                settings.client_secret,
                token["access_token"],
                token["refresh_token"],
                int(token["expires_at"]),
            )
            if refreshed:
                db.update_token(connection, int(token["athlete_id"]), refreshed)

            activities = list_athlete_activities(
                access_token,
                after_epoch=after_epoch,
                before_epoch=before_epoch,
            )
            if not args.skip_details:
                activities = [get_activity(access_token, int(activity["id"])) for activity in activities]
            count = db.upsert_activities(connection, int(token["athlete_id"]), activities)
            total += count
            print(f"Synced {count} activities for athlete {token['athlete_id']}.")
        print(f"Synced {total} activities total.")
        return

    if args.command == "splits-report":
        rows = _split_rows(connection, args.threshold_min_per_km, args.activity_id)
        if args.csv:
            _write_split_csv(Path(args.csv), rows)
            print(f"Wrote {len(rows)} rows to {args.csv}.")
        else:
            _print_split_report(rows)
        return

    if args.command == "report":
        rows = _threshold_rows(connection, args.threshold_min_per_km)
        if args.csv:
            _write_csv(Path(args.csv), rows)
            print(f"Wrote {len(rows)} rows to {args.csv}.")
        else:
            _print_report(rows)
        return

    parser.print_help()
    sys.exit(2)


def _date_to_epoch(value: str) -> int:
    parsed = dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp())


def _threshold_rows(connection, threshold: float) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query = """
        SELECT activity_id, athlete_id, name, sport_type, start_date, distance_meters, moving_time_seconds
        FROM activities
        ORDER BY start_date DESC, activity_id DESC
    """
    for row in connection.execute(query):
        pace = pace_min_per_km(row["distance_meters"], row["moving_time_seconds"])
        rows.append(
            {
                "activity_id": row["activity_id"],
                "athlete_id": row["athlete_id"],
                "name": row["name"],
                "sport_type": row["sport_type"],
                "start_date": row["start_date"],
                "pace_min_per_km": round(pace, 2) if pace is not None else None,
                "crossed_threshold": crossed_pace_threshold(
                    row["distance_meters"],
                    row["moving_time_seconds"],
                    threshold,
                ),
            }
        )
    return rows


def _print_report(rows: list[dict[str, object]]) -> None:
    for row in rows:
        print(
            "{athlete_id} | {start_date} | {sport_type} | {pace_min_per_km} min/km | "
            "threshold={crossed_threshold} | {name}".format(**row)
        )


def _split_rows(connection, threshold: float, activity_id: int | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    where = "WHERE a.activity_id = ?" if activity_id is not None else ""
    parameters = (activity_id,) if activity_id is not None else ()
    query = f"""
        SELECT
            a.activity_id,
            a.athlete_id,
            a.name,
            a.sport_type,
            a.start_date,
            s.split_number,
            s.distance_meters,
            s.moving_time_seconds,
            s.elapsed_time_seconds,
            s.average_speed_mps
        FROM activity_splits s
        JOIN activities a ON a.activity_id = s.activity_id
        {where}
        ORDER BY a.start_date DESC, a.activity_id DESC, s.split_number ASC
    """
    for row in connection.execute(query, parameters):
        pace = pace_min_per_km(row["distance_meters"], row["moving_time_seconds"])
        rows.append(
            {
                "activity_id": row["activity_id"],
                "athlete_id": row["athlete_id"],
                "name": row["name"],
                "sport_type": row["sport_type"],
                "start_date": row["start_date"],
                "split_number": row["split_number"],
                "distance_meters": row["distance_meters"],
                "pace_min_per_km": round(pace, 2) if pace is not None else None,
                "crossed_threshold": crossed_pace_threshold(
                    row["distance_meters"],
                    row["moving_time_seconds"],
                    threshold,
                ),
            }
        )
    return rows


def _print_split_report(rows: list[dict[str, object]]) -> None:
    for row in rows:
        print(
            "{activity_id} | split {split_number} | {pace_min_per_km} min/km | "
            "threshold={crossed_threshold} | {start_date} | {sport_type} | {name}".format(**row)
        )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "activity_id",
                "athlete_id",
                "name",
                "sport_type",
                "start_date",
                "pace_min_per_km",
                "crossed_threshold",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_split_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "activity_id",
                "athlete_id",
                "name",
                "sport_type",
                "start_date",
                "split_number",
                "distance_meters",
                "pace_min_per_km",
                "crossed_threshold",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
