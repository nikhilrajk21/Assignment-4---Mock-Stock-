"""Read-only playback of SQLite market observations in original receipt order."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from pandas_market_calendars import get_calendar

from backend.candles import aggregate_minutes
from backend.observations import Observation
from backend.timeframes import roll_up


def _source_time(milliseconds: int) -> datetime:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sessions(first: datetime, last: datetime) -> list[tuple[datetime, datetime]]:
    schedule = get_calendar("NASDAQ").schedule(start_date=first.date(), end_date=last.date())
    return [
        (row.market_open.to_pydatetime(), row.market_close.to_pydatetime())
        for row in schedule.itertuples()
    ]


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def recorded_sessions(path: Path) -> list[dict]:
    """List regular sessions with at least one recording for the given symbol."""
    by_symbol = defaultdict(list)
    with closing(_read_only(path)) as connection:
        for symbol, stamp in connection.execute(
            "SELECT DISTINCT symbol, source_time_ms FROM observations ORDER BY symbol, source_time_ms"
        ):
            by_symbol[symbol].append(_source_time(stamp))
    result = []
    for symbol, timestamps in by_symbol.items():
        for start, end in _sessions(timestamps[0], timestamps[-1]):
            index = bisect_left(timestamps, start)
            if index < len(timestamps) and timestamps[index] < end:
                result.append({"symbol": symbol, "start": _utc_text(start), "end": _utc_text(end)})
    return result


def _regular_rows(rows: list) -> tuple[list, list[tuple[datetime, datetime]]]:
    if not rows:
        return [], []
    timestamps = [_source_time(row[1]) for row in rows]
    sessions = _sessions(min(timestamps), max(timestamps))
    starts = [opened for opened, _ in sessions]
    selected = []
    for row, stamp in zip(rows, timestamps):
        # The session ending at a timestamp is exclusive.
        index = bisect_right(starts, stamp) - 1
        if index >= 0 and stamp < sessions[index][1]:
            selected.append(row)
    return selected, sessions


def execution_observations(
    connection: sqlite3.Connection, symbol: str, start: datetime, end: datetime, step: int
) -> list:
    """Return only the selected replay prefix in original receipt order."""
    if step == 0:
        return []
    rows = connection.execute("""
        SELECT id, source_time_ms, received_at_utc, source_json
        FROM observations WHERE symbol=? AND source_time_ms>=? AND source_time_ms<?
        ORDER BY id
    """, (symbol, start.timestamp() * 1000, end.timestamp() * 1000)).fetchall()
    return _regular_rows(rows)[0][:step]


def replay(
    path: Path, symbol: str, start: datetime, end: datetime, timeframe: str, step: int
) -> dict:
    """Recompute candles with exactly the receipt prefix visible at this step."""
    result = {
        "symbol": symbol,
        "timeframe": timeframe,
        "step": 0,
        "total": 0,
        "source_time_ms": None,
        "received_at_utc": None,
        "candles": [],
        "coverage": [],
    }
    first_minute = start.replace(second=0, microsecond=0)
    # Keep the previous minute as volume context for a full first minute.
    baseline_start = first_minute - timedelta(minutes=1) if start == first_minute else start
    with closing(_read_only(path)) as connection:
        records = connection.execute("""
            SELECT o.id, o.source_time_ms, o.received_at_utc, o.source_json, r.supersedes_id
            FROM observations AS o
            LEFT JOIN observation_revisions AS r ON r.observation_id = o.id
            WHERE o.symbol = ? AND o.source_time_ms >= ? AND o.source_time_ms < ?
            ORDER BY o.id
        """, (symbol, baseline_start.timestamp() * 1000, end.timestamp() * 1000)).fetchall()
    in_range = [row for row in records if _source_time(row[1]) >= start]
    if not in_range:
        return result

    selected, sessions = _regular_rows(in_range)
    result["total"] = len(selected)
    result["step"] = min(step, len(selected))
    if result["step"] == 0:
        return result

    current = selected[result["step"] - 1]
    prefix = selected[:result["step"]]
    prior = [
        row for row in records if row[0] <= current[0] and _source_time(row[1]) < start
    ]
    available = [
        Observation(row_id, source_time, datetime.fromisoformat(received), json.loads(raw), supersedes)
        for row_id, source_time, received, raw, supersedes in prior + prefix
    ]
    cutoff = max(row.received_at for row in available)
    minutes = [
        minute for minute in aggregate_minutes(available, as_of=cutoff)
        if datetime.fromisoformat(minute.candle["timestamp"]) >= first_minute
    ]
    rollups = roll_up(minutes, timeframe, sessions, as_of=cutoff)
    result.update(
        source_time_ms=current[1],
        received_at_utc=_utc_text(datetime.fromisoformat(current[2])),
        candles=[row.candle for row in rollups],
        coverage=[
            {
                "timestamp": row.candle["timestamp"],
                "complete": row.complete,
                "covered_minutes": row.covered_minutes,
                "expected_minutes": row.expected_minutes,
            }
            for row in rollups
        ],
    )
    return result
