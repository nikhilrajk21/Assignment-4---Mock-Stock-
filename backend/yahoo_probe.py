"""Receive one Yahoo Finance quote through yfinance within a bounded wait."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import subprocess
import sys
from pathlib import Path

from backend.observations import ObservationStore


def matches_quote(message: dict, symbol: str) -> bool:
    return message.get("id") == symbol and "price" in message and "time" in message


async def probe(symbol: str, timeout: float, database: Path | None = None) -> int:
    from yfinance import AsyncWebSocket

    update = asyncio.get_running_loop().create_future()
    connected = False

    def receive(message: dict) -> None:
        if update.done() or not matches_quote(message, symbol):
            return
        update.set_result((datetime.now(timezone.utc), message))

    client = AsyncWebSocket(verbose=False)
    listener = None
    try:
        async with asyncio.timeout(timeout):
            async with client:
                connected = True
                print("Connection opened", flush=True)
                await client.subscribe(symbol)
                listener = asyncio.create_task(client.listen(receive))
                try:
                    done, _ = await asyncio.wait(
                        (update, listener), return_when=asyncio.FIRST_COMPLETED
                    )
                    if update not in done:
                        await listener
                        print("Listener ended before receiving a quote.")
                        return 1
                    received_at, message = update.result()
                finally:
                    listener.cancel()
                    await asyncio.gather(listener, return_exceptions=True)
    except TimeoutError:
        print(f"Timed out. Connection opened: {connected}. Quote receipt unverified.")
        return 1

    observation_id = None
    if database is not None:
        observation_id, _ = ObservationStore(database).record(message, received_at)

    print(json.dumps({
        "observation_id": observation_id,
        "symbol": symbol,
        "price": message["price"],
        "source_time_unix_ms": int(message["time"]),
        "received_at_utc": received_at.isoformat(),
        "day_volume": message.get("day_volume"),
        "last_size": message.get("last_size"),
        "source": message,
    }, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", nargs="?", default="AAPL")
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--database", default="", help="SQLite path for recording the quote")
    args = parser.parse_args()
    if not 0 < args.timeout <= 120:
        parser.error("--timeout must be greater than 0 and at most 120 seconds")
    # Keep a wall-clock deadline even if the third-party listener stops yielding.
    worker = (
        "import asyncio, sys; from pathlib import Path; from backend.yahoo_probe import probe; "
        "raise SystemExit(asyncio.run(probe(sys.argv[1], float(sys.argv[2]), Path(sys.argv[3]) if sys.argv[3] else None)))"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-c", worker, args.symbol.strip().upper(), str(args.timeout), args.database],
            timeout=args.timeout + 5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("Probe exceeded its deadline. Quote receipt unverified.", flush=True)
        raise SystemExit(1)
    raise SystemExit(result.returncode)
