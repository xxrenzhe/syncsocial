from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.utils.time import ensure_utc


def compute_next_run_at(*, frequency: str, schedule_spec: dict, random_config: dict, now: datetime) -> datetime | None:
    freq = str(frequency).strip().lower()
    if freq == "manual":
        return None

    now_utc = ensure_utc(now)

    if freq == "interval":
        every_minutes = _get_int(schedule_spec, ["every_minutes", "interval_minutes"], default=60)
        if every_minutes <= 0:
            every_minutes = 60
        next_at = now_utc + timedelta(minutes=every_minutes)
        return _apply_random_offset(next_at, random_config)

    if freq == "daily":
        hour, minute = _parse_time_of_day(str(schedule_spec.get("time_of_day") or "09:00"))
        candidate = datetime(
            year=now_utc.year,
            month=now_utc.month,
            day=now_utc.day,
            hour=hour,
            minute=minute,
            tzinfo=timezone.utc,
        )
        if candidate <= now_utc:
            candidate = candidate + timedelta(days=1)
        return _apply_random_offset(candidate, random_config)

    return _apply_random_offset(now_utc + timedelta(hours=24), random_config)


def should_skip_run(*, random_config: dict) -> bool:
    raw = random_config.get("skip_probability")
    try:
        prob = float(raw)
    except Exception:
        return False
    if prob <= 0:
        return False
    if prob >= 1:
        return True
    return random.random() < prob


def _apply_random_offset(next_at: datetime, random_config: dict) -> datetime:
    max_offset = _get_int(random_config, ["offset_minutes_max", "random_offset_minutes_max"], default=0)
    if max_offset <= 0:
        return next_at
    return ensure_utc(next_at) + timedelta(minutes=random.randint(0, max_offset))


def _get_int(source: dict, keys: list[str], *, default: int) -> int:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return default


def _parse_time_of_day(value: str) -> tuple[int, int]:
    raw = value.strip()
    if not raw:
        return 9, 0
    parts = raw.split(":")
    if len(parts) < 2:
        return 9, 0
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except Exception:
        return 9, 0
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return hour, minute

