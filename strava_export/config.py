from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StravaSettings:
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> "StravaSettings":
        missing = [
            name
            for name in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REDIRECT_URI")
            if not os.environ.get(name)
        ]
        if missing:
            joined = ", ".join(missing)
            raise SystemExit(f"Missing required environment variable(s): {joined}")

        return cls(
            client_id=os.environ["STRAVA_CLIENT_ID"],
            client_secret=os.environ["STRAVA_CLIENT_SECRET"],
            redirect_uri=os.environ["STRAVA_REDIRECT_URI"],
        )
