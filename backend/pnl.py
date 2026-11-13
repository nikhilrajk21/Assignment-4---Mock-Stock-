"""Persistent paper-account cost basis and valuation history."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

from backend.candles import aggregate_minutes
from backend.observations import Observation
from backend.timeframes import roll_up, trading_sessions

ZERO = Decimal(0)
MINUTE = timedelta(minutes=1)
LIVE = "live"


def _utc(value):
    if value.utcoffset() is None:
        raise ValueError("Valuation times must include a timezone")
    return value.astimezone(timezone.utc)


def initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS paper_cost_basis (
            symbol TEXT PRIMARY KEY,
            average_cost TEXT,
            realized TEXT NOT NULL,
            scope TEXT NOT NULL,
            last_fill TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS paper_pnl (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES paper_account(id),
            symbol TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            price_time TEXT NOT NULL,
            price TEXT,
            price_source TEXT NOT NULL,
            cash TEXT NOT NULL,
            shares INTEGER NOT NULL,
            realized TEXT NOT NULL,
            unrealized TEXT,
            total TEXT,
            UNIQUE(account_id, symbol, event_type, event_id)
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS paper_pnl_symbol_id ON paper_pnl(symbol, id)
    """)


def _apply_cost(average, realized, shares, side, quantity, price):
    if side == "buy":
        if shares and average is None:
            return None, realized
        return ((average or ZERO) * shares + price * quantity) / (shares + quantity), realized
    if average is not None:
        realized += quantity * (price - average)
    return (average if shares > quantity else None), realized


def _basis(db, symbol):
    row = db.execute("""
        SELECT average_cost, realized, scope, last_fill
        FROM paper_cost_basis WHERE symbol=?
    """, (symbol,)).fetchone()
    if row is not None:
        return (
            Decimal(row[0]) if row[0] is not None else None,
            Decimal(row[1]), row[2], datetime.fromisoformat(row[3]),
        )

    # Accounts created before valuation history was enabled still have fills.
    average, realized, shares, scope, last = None, ZERO, 0, LIVE, None
    for row in db.execute("""
        SELECT o.side, f.quantity, f.price, o.replay_key, f.executed_at
        FROM paper_fills f JOIN paper_orders o ON o.id=f.order_id
        WHERE o.symbol=? ORDER BY f.executed_at, f.order_id
    """, (symbol,)):
        side, quantity, price, replay_key, executed = row
        if side != "buy" and quantity > shares:
            # Older databases may mix historical replay and wall-clock fills.
            # Leave unverifiable cost unknown instead of fabricating it.
            return None, ZERO, LIVE, None
        average, realized = _apply_cost(average, realized, shares, side, quantity, Decimal(price))
        shares += quantity if side == "buy" else -quantity
        scope, last = replay_key or LIVE, datetime.fromisoformat(executed)
    return average, realized, scope, last


def _text(value):
    return str(value) if value is not None else None


def _append(db, *, symbol, event_type, event_id, timestamp, price_time, price, cash, shares,
            average, realized):
    unrealized = ZERO if not shares else None
    if shares and price is not None and average is not None:
        unrealized = shares * (price - average)
    total = realized + unrealized if unrealized is not None else None
    db.execute("""
        INSERT INTO paper_pnl (
            account_id, symbol, event_type, event_id, timestamp, price_time,
            price, price_source, cash, shares, realized, unrealized, total
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, symbol, event_type, event_id) DO NOTHING
    """, (
        symbol, event_type, event_id, _utc(timestamp).isoformat(), _utc(price_time).isoformat(),
        _text(price), "Paper fill" if event_type == "fill" else "Completed candle close",
        str(cash), shares, str(realized), _text(unrealized), _text(total),
    ))


def record_fill(db, order, quote, *, quantity, previous_shares, cash, shares):
    """Save basis and valuation using the surrounding fill transaction."""
    symbol = order["symbol"]
    average, realized, _, _ = _basis(db, symbol)
    average, realized = _apply_cost(average, realized, previous_shares, order["side"], quantity, quote.price)
    db.execute("""
        INSERT INTO paper_cost_basis VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET average_cost=excluded.average_cost,
            realized=excluded.realized, scope=excluded.scope, last_fill=excluded.last_fill
    """, (
        symbol, _text(average), str(realized), order["replay_key"] or LIVE,
        _utc(quote.received_at).isoformat(),
    ))
    _append(
        db, symbol=symbol, event_type="fill", event_id=str(order["id"]), timestamp=quote.received_at,
        price_time=datetime.fromtimestamp(quote.source_time_ms / 1000, timezone.utc), price=quote.price,
        cash=cash, shares=shares, average=average, realized=realized,
    )


def record_mark(db, *, symbol, timestamp, price, scope, cash, shares, observed_at=None):
    """Store the first valuation of a completed candle for this account and scope."""
    if not shares:
        return
    start = _utc(timestamp)
    if start.second or start.microsecond:
        raise ValueError("Completed candle timestamp must align to a minute")
    if price is not None and (not price.is_finite() or price <= ZERO):
        price = None
    average, realized, _, _ = _basis(db, symbol)
    _append(
        db, symbol=symbol, event_type="mark", event_id=json.dumps([scope, start.isoformat()]),
        timestamp=observed_at or start + MINUTE, price_time=start + MINUTE, price=price,
        cash=cash, shares=shares, average=average, realized=realized,
    )


def mark_completed(db, *, symbol, cutoff, scope, cash, shares, replay_rows=None, max_observation=None):
    """Derive newly completed market prices without advancing the order ledger."""
    if not shares:
        return
    _, _, last_scope, last_fill = _basis(db, symbol)
    if last_fill is None or last_scope != scope or cutoff <= last_fill:
        return
    start = last_fill.replace(second=0, microsecond=0)
    end = _utc(cutoff).replace(second=0, microsecond=0)
    if end <= start:
        return

    if replay_rows is None:
        rows = db.execute("""
            SELECT id, source_time_ms, received_at_utc, source_json FROM observations
            WHERE symbol=? AND source_time_ms>=? AND source_time_ms<? AND id<=?
        """, (
            symbol, int(start.timestamp() * 1000), int(end.timestamp() * 1000),
            max_observation if max_observation is not None else 2**63 - 1,
        )).fetchall()
    else:
        rows = [row for row in replay_rows if start.timestamp() * 1000 <= row[1] < end.timestamp() * 1000]
    if not rows:
        return

    revisions = dict(db.execute("""
        SELECT r.observation_id, r.supersedes_id
        FROM observation_revisions r JOIN observations o ON o.id=r.observation_id
        WHERE o.symbol=? AND o.source_time_ms>=? AND o.source_time_ms<?
    """, (symbol, int(start.timestamp() * 1000), int(end.timestamp() * 1000))))
    observations = [
        Observation(row[0], row[1], datetime.fromisoformat(row[2]), json.loads(row[3]), revisions.get(row[0]))
        for row in rows
    ]
    minutes = aggregate_minutes(observations, as_of=cutoff)
    for item in roll_up(minutes, "1m", trading_sessions(minutes), as_of=cutoff):
        if item.complete:
            record_mark(
                db, symbol=symbol, timestamp=datetime.fromisoformat(item.candle["timestamp"]),
                price=Decimal(str(item.candle["close"])), scope=scope, cash=cash, shares=shares,
                observed_at=cutoff,
            )


def history(db, symbol):
    result = []
    for row in db.execute("SELECT * FROM paper_pnl WHERE symbol=? ORDER BY id", (symbol,)):
        item = dict(row)
        for key in ("price", "cash", "realized", "unrealized", "total"):
            if item[key] is not None:
                item[key] = float(item[key])
        result.append(item)
    return result
