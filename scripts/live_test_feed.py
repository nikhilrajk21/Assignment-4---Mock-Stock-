"""Local server launcher that replaces only the upstream worker for the browser test."""
import asyncio
import os
from pathlib import Path
import sys

import uvicorn

create_worker = asyncio.create_subprocess_exec

if __name__ == "__main__" and sys.argv[1] == "worker":
    import json
    import time
    from datetime import datetime, timezone

    directory = Path(sys.argv[2])

    def wait_for(marker):
        until = time.monotonic() + 35
        while not (directory / marker).exists():
            if time.monotonic() > until:
                raise TimeoutError(marker)
            time.sleep(0.05)

    def quote(clock, price, total):
        stamp = datetime.fromisoformat(f"2026-11-09T{clock}+00:00")
        print(json.dumps({"type": "quote", "received_at": datetime.now(timezone.utc).isoformat(),
                          "source": {"id": "AAPL", "time": str(int(stamp.timestamp() * 1000)),
                                     "price": price, "day_volume": str(total)}}), flush=True)

    if (directory / "disconnect").exists():
        time.sleep(35)
        raise SystemExit(0)
    wait_for("begin")
    print('{"type":"subscribed"}', flush=True)
    quote("14:59:59", 99, 1000)
    quote("15:00:05", 100, 1004)
    wait_for("update")
    quote("15:00:50", 101, 1011)
    wait_for("append")
    quote("15:01:05", 104, 1015)
    wait_for("disconnect")
elif __name__ == "__main__":
    from backend.main import app
    directory = Path(sys.argv[2])
    os.environ["IST402_YAHOO_LIVE"] = "1"
    os.environ["IST402_OBSERVATIONS_DB"] = str(directory / "observations.sqlite3")

    async def fixture_worker(*args, **kwargs):
        if args[2:] != ("-m", "backend.live_feed"):
            raise ValueError("Unexpected child process")
        return await create_worker(sys.executable, "-B", "-m", "scripts.live_test_feed", "worker", str(directory), **kwargs)

    asyncio.create_subprocess_exec = fixture_worker
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
