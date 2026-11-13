"""Seed the labeled Prompt 09D fixture through the production ledger."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys

from backend.observations import ObservationStore
from backend.paper import MarketPrice, PaperOrder, PaperStore

path = Path(sys.argv[1])
quotes = ObservationStore(path)
store = PaperStore(path)
origin = datetime(2026, 11, 9, 15, tzinfo=timezone.utc)


def fill(side, price, minute, quantity=None):
    timestamp = origin + timedelta(minutes=minute)
    milliseconds = int(timestamp.timestamp() * 1000)
    request = PaperOrder(request_id=f"fixture-{side}", side=side, quantity=quantity)
    state = store.submit(request)
    order_id = next(order["id"] for order in state["orders"] if order["request_id"] == request.request_id)
    quote_id, _ = quotes.record(
        {"id": "AAPL", "time": milliseconds, "price": price}, timestamp
    )
    quote = MarketPrice(quote_id, milliseconds, timestamp, Decimal(price))
    with store.transaction() as db:
        order = db.execute("SELECT * FROM paper_orders WHERE id=?", (order_id,)).fetchone()
        store._fill(db, order, quote)


fill("buy", 100, 0, 4)
store.mark_completed_candle(symbol="AAPL", timestamp=origin + timedelta(minutes=1),
                            price=Decimal("110"), scope="fixture")
fill("sell", 110, 2, 1)
store.mark_completed_candle(symbol="AAPL", timestamp=origin + timedelta(minutes=3),
                            price=Decimal("95"), scope="fixture")
store.mark_completed_candle(symbol="AAPL", timestamp=origin + timedelta(minutes=3),
                            price=Decimal("95"), scope="fixture")
fill("close", 105, 4)
