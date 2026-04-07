from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS athletes (
    athlete_id INTEGER PRIMARY KEY,
    username TEXT,
    firstname TEXT,
    lastname TEXT,
    profile_medium TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tokens (
    athlete_id INTEGER PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    scope TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (athlete_id) REFERENCES athletes(athlete_id)
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id INTEGER PRIMARY KEY,
    athlete_id INTEGER NOT NULL,
    name TEXT,
    sport_type TEXT,
    start_date TEXT,
    distance_meters REAL,
    moving_time_seconds INTEGER,
    elapsed_time_seconds INTEGER,
    average_speed_mps REAL,
    raw_json TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (athlete_id) REFERENCES athletes(athlete_id)
);

CREATE TABLE IF NOT EXISTS activity_splits (
    activity_id INTEGER NOT NULL,
    split_number INTEGER NOT NULL,
    split_type TEXT NOT NULL,
    distance_meters REAL,
    moving_time_seconds INTEGER,
    elapsed_time_seconds INTEGER,
    average_speed_mps REAL,
    elevation_difference_meters REAL,
    pace_zone INTEGER,
    raw_json TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (activity_id, split_number, split_type),
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def upsert_token_bundle(connection: sqlite3.Connection, token_bundle: dict[str, Any]) -> int:
    athlete = token_bundle["athlete"]
    athlete_id = int(athlete["id"])
    connection.execute(
        """
        INSERT INTO athletes (athlete_id, username, firstname, lastname, profile_medium)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(athlete_id) DO UPDATE SET
            username = excluded.username,
            firstname = excluded.firstname,
            lastname = excluded.lastname,
            profile_medium = excluded.profile_medium,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            athlete_id,
            athlete.get("username"),
            athlete.get("firstname"),
            athlete.get("lastname"),
            athlete.get("profile_medium"),
        ),
    )
    connection.execute(
        """
        INSERT INTO tokens (athlete_id, access_token, refresh_token, expires_at, scope)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(athlete_id) DO UPDATE SET
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            expires_at = excluded.expires_at,
            scope = excluded.scope,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            athlete_id,
            token_bundle["access_token"],
            token_bundle["refresh_token"],
            int(token_bundle["expires_at"]),
            token_bundle.get("scope"),
        ),
    )
    connection.commit()
    return athlete_id


def list_tokens(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(connection.execute("SELECT * FROM tokens ORDER BY athlete_id"))


def update_token(connection: sqlite3.Connection, athlete_id: int, token_bundle: dict[str, Any]) -> None:
    connection.execute(
        """
        UPDATE tokens
        SET access_token = ?, refresh_token = ?, expires_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE athlete_id = ?
        """,
        (
            token_bundle["access_token"],
            token_bundle["refresh_token"],
            int(token_bundle["expires_at"]),
            athlete_id,
        ),
    )
    connection.commit()


def upsert_activities(connection: sqlite3.Connection, athlete_id: int, activities: Iterable[dict[str, Any]]) -> int:
    count = 0
    for activity in activities:
        connection.execute(
            """
            INSERT INTO activities (
                activity_id,
                athlete_id,
                name,
                sport_type,
                start_date,
                distance_meters,
                moving_time_seconds,
                elapsed_time_seconds,
                average_speed_mps,
                raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                athlete_id = excluded.athlete_id,
                name = excluded.name,
                sport_type = excluded.sport_type,
                start_date = excluded.start_date,
                distance_meters = excluded.distance_meters,
                moving_time_seconds = excluded.moving_time_seconds,
                elapsed_time_seconds = excluded.elapsed_time_seconds,
                average_speed_mps = excluded.average_speed_mps,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                int(activity["id"]),
                athlete_id,
                activity.get("name"),
                activity.get("sport_type") or activity.get("type"),
                activity.get("start_date"),
                activity.get("distance"),
                activity.get("moving_time"),
                activity.get("elapsed_time"),
                activity.get("average_speed"),
                json.dumps(activity, separators=(",", ":"), sort_keys=True),
            ),
        )
        upsert_activity_splits(connection, int(activity["id"]), activity.get("splits_metric", []), "metric")
        count += 1
    connection.commit()
    return count


def upsert_activity_splits(
    connection: sqlite3.Connection,
    activity_id: int,
    splits: Iterable[dict[str, Any]],
    split_type: str,
) -> int:
    connection.execute(
        "DELETE FROM activity_splits WHERE activity_id = ? AND split_type = ?",
        (activity_id, split_type),
    )
    count = 0
    for fallback_number, split in enumerate(splits, start=1):
        connection.execute(
            """
            INSERT INTO activity_splits (
                activity_id,
                split_number,
                split_type,
                distance_meters,
                moving_time_seconds,
                elapsed_time_seconds,
                average_speed_mps,
                elevation_difference_meters,
                pace_zone,
                raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                int(split.get("split") or fallback_number),
                split_type,
                split.get("distance"),
                split.get("moving_time"),
                split.get("elapsed_time"),
                split.get("average_speed"),
                split.get("elevation_difference"),
                split.get("pace_zone"),
                json.dumps(split, separators=(",", ":"), sort_keys=True),
            ),
        )
        count += 1
    return count
