#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import random
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo


TZ = ZoneInfo(os.environ.get("AUTOPILOT_TZ", "Asia/Shanghai"))
ENABLED = os.environ.get("CIRCADIAN_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
WAKE_RANGE = os.environ.get("CIRCADIAN_WAKE_RANGE", "06:45-08:20")
SLEEP_RANGE = os.environ.get("CIRCADIAN_SLEEP_RANGE", "25:15-26:40")
NOTIFY_ENABLED = os.environ.get("CIRCADIAN_NOTIFY", "1").strip().lower() not in {"0", "false", "no", "off"}


def parse_time_minutes(value: str) -> int:
    hour_text, minute_text = str(value).strip().split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 47 or minute < 0 or minute > 59:
        raise ValueError(f"invalid circadian time: {value}")
    return hour * 60 + minute


def parse_range(value: str, fallback: str) -> tuple[int, int]:
    raw = str(value or fallback).strip()
    try:
        start_text, end_text = raw.split("-", 1)
        start = parse_time_minutes(start_text)
        end = parse_time_minutes(end_text)
    except Exception:
        start_text, end_text = fallback.split("-", 1)
        start = parse_time_minutes(start_text)
        end = parse_time_minutes(end_text)
    if end < start:
        end += 24 * 60
    return start, end


def day_key(now: datetime | None = None) -> str:
    local = (now or datetime.now(TZ)).astimezone(TZ)
    if local.hour < 5:
        local -= timedelta(days=1)
    return local.strftime("%Y-%m-%d")


def day_midnight(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=TZ)


def minutes_to_dt(day: str, minutes: int) -> datetime:
    return day_midnight(day) + timedelta(minutes=minutes)


def display_hhmm(dt: datetime, base_day: str) -> str:
    local = dt.astimezone(TZ)
    prefix = "次日" if local.strftime("%Y-%m-%d") != base_day else ""
    return prefix + local.strftime("%H:%M")


def load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="circadian.", suffix=".json", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_name, path)


@contextmanager
def state_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = -1
    for _ in range(20):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 20:
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            time.sleep(0.15)
    try:
        yield
    finally:
        if fd >= 0:
            os.close(fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def generate_schedule(day: str) -> dict[str, Any]:
    wake_start, wake_end = parse_range(WAKE_RANGE, "06:45-08:20")
    sleep_start, sleep_end = parse_range(SLEEP_RANGE, "25:15-26:40")
    wake_minute = random.randint(wake_start, wake_end)
    sleep_minute = random.randint(sleep_start, sleep_end)
    if sleep_minute <= wake_minute:
        sleep_minute += 24 * 60
    wake_at = minutes_to_dt(day, wake_minute)
    sleep_at = minutes_to_dt(day, sleep_minute)
    active_hours = round((sleep_at - wake_at).total_seconds() / 3600, 2)
    return {
        "date": day,
        "timezone": str(TZ),
        "wake_at": wake_at.isoformat(),
        "sleep_at": sleep_at.isoformat(),
        "active_hours": active_hours,
        "generated_at": datetime.now(TZ).isoformat(),
        "notified": False,
    }


def append_log(action_log: Path | None, event: dict[str, Any]) -> None:
    if not action_log:
        return
    try:
        action_log.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": int(time.time()), **event}
        with action_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


def notification_text(schedule: dict[str, Any]) -> str:
    day = str(schedule.get("date") or "")
    wake = datetime.fromisoformat(str(schedule["wake_at"]))
    sleep = datetime.fromisoformat(str(schedule["sleep_at"]))
    return (
        f"今天作息已生成：{display_hhmm(wake, day)} 醒，"
        f"{display_hhmm(sleep, day)} 睡。"
        "自动发帖/刷推/回复会尽量集中在醒着的时候。"
    )


def ensure_schedule(
    state_path: Path,
    action_log: Path | None = None,
    notify: Callable[[str], Any] | None = None,
    now: datetime | None = None,
    for_day: str | None = None,
) -> dict[str, Any]:
    if not ENABLED:
        local = (now or datetime.now(TZ)).astimezone(TZ)
        day = for_day or day_key(local)
        return {
            "date": day,
            "timezone": str(TZ),
            "wake_at": day_midnight(day).isoformat(),
            "sleep_at": (day_midnight(day) + timedelta(days=1)).isoformat(),
            "active_hours": 24,
            "generated_at": local.isoformat(),
            "notified": True,
        }
    day = for_day or day_key(now)
    with state_lock(state_path):
        state = load_state(state_path)
        schedules = state.setdefault("schedules", {})
        schedule = schedules.get(day)
        if not isinstance(schedule, dict):
            schedule = generate_schedule(day)
            schedules[day] = schedule
            state["current_date"] = day
            append_log(action_log, {"type": "circadian_schedule_created", "schedule": schedule})
        if notify and NOTIFY_ENABLED and not schedule.get("notified"):
            try:
                notify(notification_text(schedule))
                schedule["notified"] = True
                schedule["notified_at"] = datetime.now(TZ).isoformat()
                append_log(action_log, {"type": "circadian_schedule_notified", "date": day})
            except Exception as exc:
                append_log(action_log, {"type": "circadian_schedule_notify_error", "date": day, "error": str(exc)[:240]})
        cutoff = (datetime.now(TZ) - timedelta(days=3)).strftime("%Y-%m-%d")
        state["schedules"] = {key: value for key, value in schedules.items() if str(key) >= cutoff}
        save_state(state_path, state)
        return dict(schedule)


def window_for_day(state_path: Path, day: str, action_log: Path | None = None) -> tuple[datetime, datetime, dict[str, Any]]:
    schedule = ensure_schedule(state_path, action_log=action_log, for_day=day)
    return datetime.fromisoformat(schedule["wake_at"]), datetime.fromisoformat(schedule["sleep_at"]), schedule


def is_active(schedule: dict[str, Any], now: datetime | None = None) -> bool:
    if not ENABLED:
        return True
    local = (now or datetime.now(TZ)).astimezone(TZ)
    wake = datetime.fromisoformat(str(schedule["wake_at"])).astimezone(TZ)
    sleep = datetime.fromisoformat(str(schedule["sleep_at"])).astimezone(TZ)
    return wake <= local < sleep


def inactive_reason(schedule: dict[str, Any], now: datetime | None = None) -> str:
    local = (now or datetime.now(TZ)).astimezone(TZ)
    day = str(schedule.get("date") or day_key(local))
    wake = datetime.fromisoformat(str(schedule["wake_at"])).astimezone(TZ)
    sleep = datetime.fromisoformat(str(schedule["sleep_at"])).astimezone(TZ)
    if local < wake:
        return f"sleeping_until_{display_hhmm(wake, day)}"
    if local >= sleep:
        return f"sleeping_after_{display_hhmm(sleep, day)}"
    return "active"
