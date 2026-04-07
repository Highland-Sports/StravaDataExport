from __future__ import annotations

import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE_URL = "https://www.strava.com/api/v3"
CA_BUNDLE_CANDIDATES = (
    Path("C:/msys64/usr/ssl/certs/ca-bundle.crt"),
    Path("C:/Program Files/Git/mingw64/etc/ssl/certs/ca-bundle.crt"),
    Path("C:/Program Files/Git/usr/ssl/certs/ca-bundle.crt"),
)


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    scope: str = "read,activity:read_all",
    approval_prompt: str = "auto",
) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "approval_prompt": approval_prompt,
            "scope": scope,
        }
    )
    return f"{AUTH_URL}?{query}"


def exchange_code(client_id: str, client_secret: str, code: str) -> dict[str, Any]:
    return _post_form(
        TOKEN_URL,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
        },
    )


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict[str, Any]:
    return _post_form(
        TOKEN_URL,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )


def ensure_fresh_token(
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    expires_at: int,
) -> tuple[str, dict[str, Any] | None]:
    if expires_at > int(time.time()) + 60:
        return access_token, None
    token_bundle = refresh_access_token(client_id, client_secret, refresh_token)
    return token_bundle["access_token"], token_bundle


def list_athlete_activities(
    access_token: str,
    *,
    after_epoch: int | None = None,
    before_epoch: int | None = None,
    per_page: int = 200,
) -> list[dict[str, Any]]:
    page = 1
    activities: list[dict[str, Any]] = []
    while True:
        query: dict[str, int] = {"page": page, "per_page": per_page}
        if after_epoch is not None:
            query["after"] = after_epoch
        if before_epoch is not None:
            query["before"] = before_epoch

        batch = _get_json(f"{API_BASE_URL}/athlete/activities?{urllib.parse.urlencode(query)}", access_token)
        if not batch:
            break

        activities.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return activities


def get_activity(access_token: str, activity_id: int, *, include_all_efforts: bool = False) -> dict[str, Any]:
    query = urllib.parse.urlencode({"include_all_efforts": str(include_all_efforts).lower()})
    return _get_json(f"{API_BASE_URL}/activities/{activity_id}?{query}", access_token)


def _post_form(url: str, values: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(values).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, access_token: str) -> Any:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def _ssl_context() -> ssl.SSLContext:
    verify_paths = ssl.get_default_verify_paths()
    if os.environ.get(verify_paths.openssl_cafile_env) or verify_paths.cafile:
        return ssl.create_default_context()

    for candidate in CA_BUNDLE_CANDIDATES:
        if candidate.exists():
            return ssl.create_default_context(cafile=str(candidate))

    return ssl.create_default_context()
