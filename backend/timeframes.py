"""Roll up one-minute candles using explicit exchange session boundaries."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.candles import Candle, Minute

INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "1d": None}


@dataclass(frozen=True)
class Rollup:
    candle: Candle
    complete: bool
    covered_minutes: int
    expected_minutes: int


def roll_up(
    minutes: list[Minute],
    interval: str,
    sessions: list[tuple[datetime, datetime]],
    *,
    as_of: datetime,
) -> list[Rollup]:
    """Group available minutes by session and use the latest value for each minute."""
    size = INTERVALS[interval]
    latest = {}
    for minute in minutes:
        start = datetime.fromisoformat(minute.candle["timestamp"])
        if start <= as_of:
            latest[start] = minute

    result = []
    starts = sorted(latest)
    for session_open, session_close in sessions:
        groups = {}
        for start in starts:
            if not session_open <= start < session_close:
                continue
            offset = int((start - session_open).total_seconds()) // 60
            bucket_offset = offset // size * size if size is not None else 0
            group_start = session_open + timedelta(minutes=bucket_offset)
            groups.setdefault(group_start, []).append(latest[start])

        for group_start, group in groups.items():
            end = min(group_start + timedelta(minutes=size), session_close) if size else session_close
            candles = [minute.candle for minute in group]
            volumes = [candle["volume"] for candle in candles]
            volume = None if None in volumes else sum(volumes)
            result.append(Rollup(
                candle={
                    "timestamp": group_start.isoformat().replace("+00:00", "Z"),
                    "open": candles[0]["open"],
                    "high": max(candle["high"] for candle in candles),
                    "low": min(candle["low"] for candle in candles),
                    "close": candles[-1]["close"],
                    "volume": volume,
                },
                complete=as_of >= end and all(minute.complete for minute in group),
                covered_minutes=len(group),
                expected_minutes=int((end - group_start).total_seconds()) // 60,
            ))
    return result


def trading_sessions(minutes: list[Minute]) -> list[tuple[datetime, datetime]]:
    """Return UTC open/close pairs from the Nasdaq exchange calendar."""
    if not minutes:
        return []

    from pandas_market_calendars import get_calendar

    dates = [datetime.fromisoformat(minute.candle["timestamp"]).date() for minute in minutes]
    schedule = get_calendar("NASDAQ").schedule(start_date=min(dates), end_date=max(dates))
    return [
        (row.market_open.to_pydatetime(), row.market_close.to_pydatetime())
        for row in schedule.itertuples()
    ]
