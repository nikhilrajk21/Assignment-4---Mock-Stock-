"""Record live Yahoo quotes and publish Nasdaq-session candle snapshots."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
from collections.abc import Callable

from backend.candles import aggregate_minutes
from backend.observations import DEFAULT_DATABASE, ObservationStore
from backend.timeframes import roll_up, trading_sessions
from backend.yahoo_probe import matches_quote

SYMBOL = "AAPL"
SOURCE = "Yahoo Finance"
STALE_AFTER = 25
IDLE_TIMEOUT = 90
LOGGER = logging.getLogger(__name__)


@dataclass
class LiveFeed:
    store: ObservationStore
    status: str = "disabled"
    last_activity: float = 0
    on_recorded: Callable[[], None] | None = None

    @classmethod
    def from_environment(cls) -> "LiveFeed":
        path = os.environ.get("IST402_OBSERVATIONS_DB")
        return cls(ObservationStore(Path(path) if path else DEFAULT_DATABASE))

    def snapshot(self, symbol: str, timeframe: str) -> dict:
        cutoff = datetime.now(timezone.utc)
        observations = self.store.for_symbol(symbol)
        minutes = aggregate_minutes(observations, as_of=cutoff)
        rollups = roll_up(minutes, timeframe, trading_sessions(minutes), as_of=cutoff)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": SOURCE,
            "feed_status": self.status,
            "source_time_ms": max(
                (row.source_time_ms for row in observations if row.received_at <= cutoff),
                default=None,
            ),
            "candles": [row.candle for row in rollups],
            "coverage": [
                {
                    "timestamp": row.candle["timestamp"],
                    "complete": row.complete,
                    "covered_minutes": row.covered_minutes,
                    "expected_minutes": row.expected_minutes,
                }
                for row in rollups
            ],
        }

    async def run(self) -> None:
        """Keep a single isolated subscription worker and back off on disconnect."""
        delay = 1
        while True:
            self.status = "connecting"
            try:
                await self._consume_worker()
            except (TimeoutError, OSError, ValueError) as error:
                LOGGER.warning("Yahoo subscription ended: %s", error)
            finally:
                self.status = "disconnected"
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def _consume_worker(self) -> None:
        # A separate process lets us stop yfinance even if its listener stalls.
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-B", "-m", "backend.live_feed",
            stdout=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        clock = asyncio.get_running_loop()
        try:
            while True:
                waiting = IDLE_TIMEOUT - (clock.time() - self.last_activity)
                if self.status != "stale":
                    waiting = STALE_AFTER
                if waiting <= 0:
                    break
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=waiting)
                except TimeoutError:
                    if self.status != "connected":
                        break
                    self.status = "stale"
                    continue
                if not line:
                    break
                event = json.loads(line)
                if event["type"] == "subscribed":
                    self.last_activity = clock.time()
                    self.status = "connected"
                elif event["type"] == "quote":
                    received = datetime.fromisoformat(event["received_at"])
                    _, created = await asyncio.to_thread(self.store.record, event["source"], received)
                    if created and self.on_recorded is not None:
                        await asyncio.to_thread(self.on_recorded)
                    self.last_activity = clock.time()
                    self.status = "connected"
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()


def valid_observation(message: dict) -> bool:
    if not matches_quote(message, SYMBOL):
        return False
    try:
        if not math.isfinite(float(message["price"])):
            return False
        timestamp = datetime.fromtimestamp(int(message["time"]) / 1000, timezone.utc)
        if timestamp.year < 1970:
            return False
        volume = message.get("day_volume")
        return volume is None or (str(volume).isdigit() and int(volume) >= 0)
    except (ValueError, TypeError, OverflowError, OSError):
        return False


async def subscribe_worker() -> None:
    from yfinance import AsyncWebSocket

    def receive(message: dict) -> None:
        received_at = datetime.now(timezone.utc).isoformat()
        if valid_observation(message):
            print(json.dumps({"type": "quote", "received_at": received_at, "source": message}), flush=True)

    async with AsyncWebSocket(verbose=False) as client:
        await client.subscribe(SYMBOL)
        print(json.dumps({"type": "subscribed"}), flush=True)
        await client.listen(receive)


if __name__ == "__main__":
    asyncio.run(subscribe_worker())
