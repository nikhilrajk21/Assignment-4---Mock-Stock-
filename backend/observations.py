"""SQLite storage for decoded market observations."""

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3

DEFAULT_DATABASE = Path(__file__).parent / "data" / "observations.sqlite3"


@dataclass(frozen=True)
class Observation:
    id: int
    source_time_ms: int
    received_at: datetime
    source: dict
    supersedes_id: int | None


class ObservationStore:
    def __init__(self, path: Path = DEFAULT_DATABASE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    source_time_ms INTEGER NOT NULL,
                    received_at_utc TEXT NOT NULL,
                    source_json TEXT NOT NULL UNIQUE
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS observations_symbol_time
                ON observations (symbol, source_time_ms, id)
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS observation_revisions (
                    observation_id INTEGER PRIMARY KEY REFERENCES observations(id),
                    supersedes_id INTEGER NOT NULL REFERENCES observations(id)
                )
            """)

    def record(self, message: dict, received_at: datetime, *, supersedes_id: int | None = None) -> tuple[int, bool]:
        """Return the row ID and whether the source message was newly stored."""
        payload = json.dumps(message, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            if supersedes_id is not None:
                prior = connection.execute(
                    "SELECT symbol FROM observations WHERE id = ?", (supersedes_id,)
                ).fetchone()
                if prior is None or prior[0] != message["id"]:
                    raise ValueError("A correction must reference a saved observation for the same ticker")
            cursor = connection.execute("""
                INSERT INTO observations (symbol, source_time_ms, received_at_utc, source_json)
                VALUES (?, ?, ?, ?) ON CONFLICT(source_json) DO NOTHING
            """, (message["id"], int(message["time"]), received_at.isoformat(), payload))
            if cursor.rowcount:
                if supersedes_id is not None:
                    connection.execute(
                        "INSERT INTO observation_revisions VALUES (?, ?)", (cursor.lastrowid, supersedes_id)
                    )
                return cursor.lastrowid, True
            row = connection.execute(
                "SELECT id FROM observations WHERE source_json = ?", (payload,)
            ).fetchone()
            return row[0], False


    def for_symbol(self, symbol: str) -> list[Observation]:
        """Read immutable observations in receipt order, with explicit revision links."""
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute("""
                SELECT o.id, o.source_time_ms, o.received_at_utc, o.source_json, r.supersedes_id
                FROM observations AS o
                LEFT JOIN observation_revisions AS r ON r.observation_id = o.id
                WHERE o.symbol = ?
                ORDER BY o.id
            """, (symbol,))
            return [
                Observation(row_id, source_time, datetime.fromisoformat(received), json.loads(source), supersedes)
                for row_id, source_time, received, source, supersedes in rows
            ]


if __name__ == "__main__":
    store = ObservationStore()
    print(store.path)
