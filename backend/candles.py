"""Aggregate saved source observations into UTC one-minute candles."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo

from backend.observations import Observation

MINUTE_MS = 60_000


class Candle(TypedDict):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int | None


@dataclass(frozen=True)
class Minute:
    candle: Candle
    complete: bool


def aggregate_minutes(
    observations: list[Observation], *, as_of: datetime, exchange_timezone: str = "America/New_York"
) -> list[Minute]:
    """Build one ticker's candles from observations available at the cutoff."""
    if as_of.utcoffset() is None:
        raise ValueError("as_of must include a timezone")
    available = [row for row in observations if row.received_at <= as_of]
    superseded = {row.supersedes_id for row in available if row.supersedes_id is not None}
    ordered = sorted(
        (row for row in available if row.id not in superseded),
        key=lambda row: (row.source_time_ms, row.id),
    )
    exchange_zone = ZoneInfo(exchange_timezone)
    buckets: dict[int, list[tuple[float, int | None]]] = {}
    prior_total: int | None = None
    prior_bucket: int | None = None
    prior_day = None

    for row in ordered:
        timestamp = datetime.fromtimestamp(row.source_time_ms / 1000, timezone.utc)
        session_day = timestamp.astimezone(exchange_zone).date()
        bucket = row.source_time_ms // MINUTE_MS * MINUTE_MS
        if session_day != prior_day or (prior_bucket is not None and bucket - prior_bucket > MINUTE_MS):
            prior_total = None

        raw_total = row.source.get("day_volume")
        total = int(raw_total) if raw_total is not None else None
        delta = (
            total - prior_total
            if total is not None and prior_total is not None and total >= prior_total
            else None
        )
        buckets.setdefault(bucket, []).append((float(row.source["price"]), delta))
        prior_total, prior_bucket, prior_day = total, bucket, session_day

    result = []
    for bucket, points in buckets.items():
        prices, deltas = zip(*points)
        start = datetime.fromtimestamp(bucket / 1000, timezone.utc)
        end = datetime.fromtimestamp((bucket + MINUTE_MS) / 1000, timezone.utc)
        result.append(Minute(
            candle={
                "timestamp": start.isoformat().replace("+00:00", "Z"),
                "open": prices[0],
                "high": max(prices),
                "low": min(prices),
                "close": prices[-1],
                "volume": sum(delta for delta in deltas if delta is not None)
                if all(delta is not None for delta in deltas) else None,
            },
            complete=as_of >= end,
        ))
    return result
