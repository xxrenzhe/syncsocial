from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.utils.time import ensure_utc

try:
    from croniter import croniter  # type: ignore
except Exception:  # pragma: no cover
    croniter = None


def compute_next_run_at(*, frequency: str, schedule_spec: dict, random_config: dict, now: datetime) -> datetime | None:
    freq = str(frequency).strip().lower()
    if freq in {"manual", "disabled"}:
        return None

    now_utc = ensure_utc(now)

    if freq == "once":
        run_at = _parse_run_at(schedule_spec)
        if run_at is None:
            return None
        run_at_utc = ensure_utc(run_at)
        if run_at_utc <= now_utc:
            return now_utc
        return _apply_random_offset(run_at_utc, random_config)

    if freq in {"interval", "custom"}:
        every_minutes = _get_int(schedule_spec, ["every_minutes", "interval_minutes"], default=60)
        every_hours = _get_int(schedule_spec, ["every_hours", "interval_hours"], default=0)
        if every_hours > 0 and every_minutes <= 0:
            every_minutes = every_hours * 60
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

    if freq == "weekly":
        hour, minute = _parse_time_of_day(str(schedule_spec.get("time_of_day") or "09:00"))
        weekdays = _parse_weekdays(schedule_spec.get("weekdays"))
        if not weekdays:
            weekdays = [now_utc.weekday()]

        candidates: list[datetime] = []
        for weekday in weekdays:
            try:
                weekday_int = int(weekday)
            except Exception:
                continue
            weekday_int = max(0, min(6, weekday_int))
            delta = (weekday_int - now_utc.weekday()) % 7
            candidate = datetime(
                year=now_utc.year,
                month=now_utc.month,
                day=now_utc.day,
                hour=hour,
                minute=minute,
                tzinfo=timezone.utc,
            ) + timedelta(days=delta)
            if candidate <= now_utc:
                candidate = candidate + timedelta(days=7)
            candidates.append(candidate)

        if candidates:
            return _apply_random_offset(min(candidates), random_config)

        return _apply_random_offset(now_utc + timedelta(days=7), random_config)

    if freq == "cron":
        expr = str(schedule_spec.get("cron") or "").strip()
        if not expr:
            return _apply_random_offset(now_utc + timedelta(hours=24), random_config)
        if croniter is None:
            return _apply_random_offset(now_utc + timedelta(hours=24), random_config)
        try:
            it = croniter(expr, now_utc)
            nxt = it.get_next(datetime)
            nxt_utc = ensure_utc(nxt)
            return _apply_random_offset(nxt_utc, random_config)
        except Exception:
            return _apply_random_offset(now_utc + timedelta(hours=24), random_config)

    return _apply_random_offset(now_utc + timedelta(hours=24), random_config)


def should_skip_run(*, random_config: dict) -> bool:
    if random_config.get("enabled") is False:
        return False
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
    if random_config.get("enabled") is False:
        return ensure_utc(next_at)
    min_offset = _get_int(random_config, ["offset_minutes_min", "time_offset_min"], default=0)
    max_offset = _get_int(random_config, ["offset_minutes_max", "random_offset_minutes_max", "time_offset_max"], default=0)
    if min_offset < 0:
        min_offset = 0
    if max_offset <= 0:
        return ensure_utc(next_at)
    if max_offset < min_offset:
        min_offset, max_offset = max_offset, min_offset
    return ensure_utc(next_at) + timedelta(minutes=random.randint(min_offset, max_offset))


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


def _parse_weekdays(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    days: list[int] = []
    for item in value:
        try:
            n = int(item)
        except Exception:
            continue
        if 1 <= n <= 7:
            n -= 1
        if 0 <= n <= 6:
            days.append(n)
    return sorted(set(days))


def _parse_run_at(schedule_spec: dict) -> datetime | None:
    raw = schedule_spec.get("run_at") or schedule_spec.get("at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
