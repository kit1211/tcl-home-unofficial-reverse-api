from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable
from urllib.parse import urlparse


_DATE_HEADER_RE = re.compile(r"(?im)^Date:\s*(.+)$")
_REQUEST_LINE_RE = re.compile(r"^(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)")


@dataclass
class BurpHistoryItem:
    request: str
    response: str
    notes: str = ""
    response_at: datetime | None = None

    @classmethod
    def from_mcp(cls, payload: dict[str, Any]) -> "BurpHistoryItem":
        response = payload.get("response") or ""
        return cls(
            request=payload.get("request") or "",
            response=response,
            notes=payload.get("notes") or "",
            response_at=parse_response_date(response),
        )


def parse_response_date(raw_response: str) -> datetime | None:
    match = _DATE_HEADER_RE.search(raw_response or "")
    if not match:
        return None
    try:
        dt = parsedate_to_datetime(match.group(1).strip())
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError, IndexError):
        return None


def _parse_clock(value: str) -> time:
    parts = value.strip().split(":")
    if len(parts) == 2:
        hour, minute = parts
        second = "0"
    elif len(parts) == 3:
        hour, minute, second = parts
    else:
        raise ValueError(f"รูปแบบเวลาไม่ถูกต้อง: {value!r} (ใช้ HH:MM หรือ HH:MM:SS)")
    return time(int(hour), int(minute), int(second))


def _resolve_day(day: date | None) -> date:
    if day is not None:
        return day
    env_day = os.environ.get("TCL_BURP_DATE")
    if env_day:
        return date.fromisoformat(env_day)
    return datetime.now().astimezone().date()


def _combine(day: date, clock: time, tz: timezone) -> datetime:
    return datetime(day.year, day.month, day.day, clock.hour, clock.minute, clock.second, tzinfo=tz)


def filter_items(
    items: Iterable[BurpHistoryItem | dict[str, Any]],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    since_clock: str | None = None,
    until_clock: str | None = None,
    day: date | None = None,
    tz: timezone | None = None,
) -> list[BurpHistoryItem]:
    tz_name = os.environ.get("TCL_BURP_TZ", "UTC")
    if tz is None:
        from zoneinfo import ZoneInfo

        compare_tz = ZoneInfo(tz_name)
    else:
        compare_tz = tz
    target_day = _resolve_day(day)

    since_env = os.environ.get("TCL_BURP_SINCE")
    until_env = os.environ.get("TCL_BURP_UNTIL")
    since_clock = since_clock or since_env
    until_clock = until_clock or until_env

    if since is None and since_clock:
        since = _combine(target_day, _parse_clock(since_clock), compare_tz)
    if until is None and until_clock:
        until = _combine(target_day, _parse_clock(until_clock), compare_tz)

    normalized: list[BurpHistoryItem] = []
    for item in items:
        normalized.append(item if isinstance(item, BurpHistoryItem) else BurpHistoryItem.from_mcp(item))

    filtered: list[BurpHistoryItem] = []
    for item in normalized:
        when = item.response_at or parse_response_date(item.response)
        if when is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when_cmp = when.astimezone(compare_tz)
        if since and when_cmp < since:
            continue
        if until and when_cmp > until:
            continue
        filtered.append(item)
    return filtered


def summarize_item(item: BurpHistoryItem) -> str:
    request_line = (item.request or "").splitlines()[0] if item.request else ""
    path = request_line
    match = _REQUEST_LINE_RE.match(request_line)
    if match:
        path = match.group(1)
    host = ""
    for line in (item.request or "").splitlines():
        if line.lower().startswith("host:"):
            host = line.split(":", 1)[1].strip()
            break
    when_dt = item.response_at or parse_response_date(item.response)
    when = when_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") if when_dt else "unknown-time"
    status = "?"
    first = (item.response or "").splitlines()[0] if item.response else ""
    if first.startswith("HTTP/"):
        parts = first.split()
        if len(parts) >= 2:
            status = parts[1]
    return f"{when} | {status} | {host}{path}"
