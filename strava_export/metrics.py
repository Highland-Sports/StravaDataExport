from __future__ import annotations


def pace_min_per_km(distance_meters: float | int | None, moving_time_seconds: float | int | None) -> float | None:
    if not distance_meters or not moving_time_seconds or distance_meters <= 0:
        return None
    return float(moving_time_seconds) / 60 / (float(distance_meters) / 1000)


def crossed_pace_threshold(
    distance_meters: float | int | None,
    moving_time_seconds: float | int | None,
    threshold_min_per_km: float,
) -> bool | None:
    pace = pace_min_per_km(distance_meters, moving_time_seconds)
    if pace is None:
        return None
    return pace <= threshold_min_per_km
