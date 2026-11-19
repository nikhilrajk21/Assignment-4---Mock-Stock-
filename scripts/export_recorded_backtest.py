"""Export one recorded session using observations available by each minute close."""

import argparse
import csv
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys

from backend.candles import aggregate_minutes
from backend.observations import Observation


def export(database: Path, symbol: str, start: datetime, end: datetime) -> None:
    if start.utcoffset() is None or end.utcoffset() is None or not timedelta(0) < end - start <= timedelta(days=1):
        raise ValueError("Use timezone-aware bounds covering at most one session")
    if start.second or start.microsecond or end.second or end.microsecond:
        raise ValueError("Use minute boundaries")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("""
            SELECT o.id, o.source_time_ms, o.received_at_utc, o.source_json, r.supersedes_id
            FROM observations o LEFT JOIN observation_revisions r ON r.observation_id=o.id
            WHERE o.symbol=? AND o.source_time_ms>=? AND o.source_time_ms<?
            ORDER BY o.source_time_ms, o.id
        """, (symbol, start.timestamp() * 1000, end.timestamp() * 1000)).fetchall()
    by_minute: dict[int, list[Observation]] = {}
    for identifier, source_ms, received, payload, superseded in rows:
        bucket = source_ms // 60_000
        by_minute.setdefault(bucket, []).append(
            Observation(identifier, source_ms, datetime.fromisoformat(received), json.loads(payload), superseded)
        )
    columns = ("timestamp", "open", "close")
    writer = csv.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    last_receipt = max((datetime.fromisoformat(row[2]) for row in rows), default=start)
    for bucket, observations in by_minute.items():
        cutoff = datetime.fromtimestamp((bucket + 1) * 60, timezone.utc)
        if cutoff > last_receipt:
            break
        for minute in aggregate_minutes(observations, as_of=cutoff):
            writer.writerow(minute.candle)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("symbol")
    parser.add_argument("start", type=datetime.fromisoformat)
    parser.add_argument("end", type=datetime.fromisoformat)
    args = parser.parse_args()
    export(args.database, args.symbol, args.start, args.end)
