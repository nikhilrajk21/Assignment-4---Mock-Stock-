"""Transactional local paper orders and zero-fee fills against observed prices."""

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from backend import pnl
from backend.replay import execution_observations

Quantity = Annotated[int, Field(strict=True, gt=0, le=1_000_000_000)]
Step = Annotated[int, Field(strict=True, ge=0)]
AUTOMATION_MAX_AGE = timedelta(minutes=5)


class ReplaySelection(BaseModel):
    start: datetime
    end: datetime
    step: Step

    @model_validator(mode="after")
    def validate_range(self) -> "ReplaySelection":
        if self.start.utcoffset() is None or self.end.utcoffset() is None or self.end <= self.start:
            raise ValueError("Replay bounds must include time zones and end after start")
        return self

    def key(self) -> str:
        return json.dumps([
            self.start.astimezone(timezone.utc).isoformat(),
            self.end.astimezone(timezone.utc).isoformat(),
        ])


class ReplayAdvance(ReplaySelection):
    symbol: Literal["AAPL"] = "AAPL"


class PaperOrder(BaseModel):
    request_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    symbol: Literal["AAPL"] = "AAPL"
    side: Literal["buy", "sell", "close", "hold", "wait"]
    quantity: Quantity | None = None
    replay: ReplaySelection | None = None

    @model_validator(mode="after")
    def validate_quantity(self) -> "PaperOrder":
        if self.side in ("buy", "sell") and self.quantity is None:
            raise ValueError("Buy and sell require a positive whole number of shares")
        if self.side not in ("buy", "sell") and self.quantity is not None:
            raise ValueError("Close, hold and wait do not take a quantity")
        return self


class RequestConflict(ValueError):
    pass


@dataclass(frozen=True)
class MarketPrice:
    observation_id: int
    source_time_ms: int
    received_at: datetime
    price: Decimal

    @classmethod
    def from_row(cls, row) -> "MarketPrice | None":
        row_id, source_time, received, raw = row[:4]
        try:
            price = Decimal(str(json.loads(raw)["price"]))
            if price.is_finite() and price > 0:
                return cls(row_id, source_time, datetime.fromisoformat(received), price)
        except (KeyError, InvalidOperation, ValueError):
            pass
        return None


class PaperStore:
    def __init__(self, path: Path):
        self.path = path
        with self.transaction() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS paper_account (
                    id INTEGER PRIMARY KEY CHECK (id = 1), cash TEXT NOT NULL
                )
            """)
            db.execute("INSERT OR IGNORE INTO paper_account VALUES (1, '1000')")
            db.execute("""
                CREATE TABLE IF NOT EXISTS paper_positions (
                    symbol TEXT PRIMARY KEY, shares INTEGER NOT NULL CHECK (shares >= 0)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS paper_orders (
                    id INTEGER PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                    request_body TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
                    quantity INTEGER NOT NULL, status TEXT NOT NULL, rejection_reason TEXT,
                    submitted_at TEXT NOT NULL, replay_key TEXT, after_observation_id INTEGER NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS paper_fills (
                    order_id INTEGER PRIMARY KEY REFERENCES paper_orders(id),
                    quantity INTEGER NOT NULL, price TEXT NOT NULL,
                    observation_id INTEGER NOT NULL REFERENCES observations(id),
                    source_time_ms INTEGER NOT NULL, executed_at TEXT NOT NULL
                )
            """)

            pnl.initialize(db)
            db.execute("""
                CREATE TABLE IF NOT EXISTS paper_automation_state (
                    account_id INTEGER PRIMARY KEY REFERENCES paper_account(id),
                    enabled INTEGER NOT NULL, generation INTEGER NOT NULL
                )
            """)
            db.execute("INSERT OR IGNORE INTO paper_automation_state VALUES (1, 0, 0)")
            db.execute("""
                CREATE TABLE IF NOT EXISTS paper_automation_attempts (
                    id TEXT PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES paper_account(id),
                    generation INTEGER NOT NULL, strategy TEXT NOT NULL, symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL, candle_timestamp TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL REFERENCES decision_snapshots(id),
                    status TEXT NOT NULL, explanation TEXT NOT NULL, closed_at TEXT, crossover TEXT,
                    decision_id TEXT REFERENCES decisions(id), order_id INTEGER UNIQUE REFERENCES paper_orders(id),
                    UNIQUE(account_id, strategy, symbol, timeframe, candle_timestamp)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS paper_automation_replay (
                    generation INTEGER NOT NULL, symbol TEXT NOT NULL,
                    replay_key TEXT NOT NULL, step INTEGER NOT NULL,
                    PRIMARY KEY(generation, symbol, replay_key)
                )
            """)

    @contextmanager
    def transaction(self, *, write=True):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db

    def state(self, symbol: str = "AAPL") -> dict:
        with self.transaction(write=False) as db:
            return self._state(db, symbol)

    def pnl_history(self, symbol: str = "AAPL") -> list[dict]:
        with self.transaction(write=False) as db:
            return pnl.history(db, symbol)

    def mark_completed_candle(
        self, *, symbol: str, timestamp: datetime, price: Decimal | None, scope: str
    ) -> None:
        """Record a completed candle valuation supplied by a trusted caller."""
        with self.transaction() as db:
            cash, shares = self._balance(db, symbol)
            pnl.record_mark(
                db, symbol=symbol, timestamp=timestamp, price=price,
                scope=scope, cash=cash, shares=shares,
            )

    def mark_live(self, as_of: datetime | None = None) -> None:
        cutoff = as_of or datetime.now(timezone.utc)
        with self.transaction() as db:
            cash, shares = self._balance(db, "AAPL")
            pnl.mark_completed(db, symbol="AAPL", cutoff=cutoff, scope=pnl.LIVE, cash=cash, shares=shares)

    @staticmethod
    def _balance(db, symbol):
        cash = Decimal(db.execute("SELECT cash FROM paper_account WHERE id=1").fetchone()[0])
        row = db.execute("SELECT shares FROM paper_positions WHERE symbol=?", (symbol,)).fetchone()
        return cash, row[0] if row else 0

    def _state(self, db, symbol):
        cash, shares = self._balance(db, symbol)
        orders = []
        for row in db.execute("""
            SELECT o.id, o.request_id, o.symbol, o.side, o.quantity, o.status,
                   o.rejection_reason, o.submitted_at, o.replay_key, a.decision_id,
                   f.quantity AS filled_quantity, f.price, f.observation_id,
                   f.source_time_ms, f.executed_at
            FROM paper_orders AS o
            LEFT JOIN paper_fills AS f ON f.order_id=o.id
            LEFT JOIN paper_automation_attempts AS a ON a.order_id=o.id
            WHERE o.symbol=? ORDER BY o.id
        """, (symbol,)):
            order = dict(row)
            order["mode"] = "live" if order.pop("replay_key") is None else "replay"
            fill = {key: order.pop(key) for key in ("price", "observation_id", "source_time_ms", "executed_at")}
            fill["quantity"] = order.pop("filled_quantity")
            if fill["price"] is not None:
                fill["price"] = float(fill["price"])
                order["fill"] = fill
            orders.append(order)
        return {"cash": float(cash), "shares": shares, "orders": orders}

    def submit(self, request: PaperOrder) -> dict:
        """Accept an idempotent intent, recording pending or rejected orders."""
        with self.transaction() as db:
            self._submit(db, request)
            return self._state(db, request.symbol)

    def _submit(self, db, request: PaperOrder) -> int | None:
        fingerprint = request.model_dump_json()
        old = db.execute(
            "SELECT request_body, id FROM paper_orders WHERE request_id=?", (request.request_id,)
        ).fetchone()
        if old:
            if old[0] != fingerprint:
                raise RequestConflict("This request ID already belongs to a different order")
            return old[1]
        if request.side in ("hold", "wait"):
            return None

        submitted_at = datetime.now(timezone.utc)
        replay_key = None
        if request.replay is None:
            watermark = db.execute("SELECT COALESCE(MAX(id), 0) FROM observations").fetchone()[0]
        else:
            selection = request.replay
            replay_key = selection.key()
            visible = execution_observations(db, request.symbol, selection.start, selection.end, selection.step)
            watermark = visible[-1][0] if visible else 0
            if visible:
                submitted_at = datetime.fromisoformat(visible[-1][2])

        _, shares = self._balance(db, request.symbol)
        quantity = shares if request.side == "close" else request.quantity
        rejection = None
        if request.side == "close" and shares == 0:
            rejection = "There is no position to close"
        elif request.side == "sell" and quantity > shares:
            rejection = "Cannot sell more shares than the position holds"
        cursor = db.execute("""
            INSERT INTO paper_orders (
                request_id, request_body, symbol, side, quantity, status,
                rejection_reason, submitted_at, replay_key, after_observation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (request.request_id, fingerprint, request.symbol, request.side, quantity,
              "rejected" if rejection else "pending", rejection, submitted_at.isoformat(),
              replay_key, watermark))
        return cursor.lastrowid

    def _fill(self, db, order, quote: MarketPrice) -> None:
        automation = db.execute("""
            SELECT a.id, a.generation, a.closed_at, s.enabled, s.generation AS current_generation
            FROM paper_automation_attempts AS a
            JOIN paper_automation_state AS s ON a.account_id=s.account_id
            WHERE a.order_id=?
        """, (order["id"],)).fetchone()
        if automation:
            closed = datetime.fromisoformat(automation["closed_at"])
            if not automation["enabled"] or automation["generation"] != automation["current_generation"]:
                self._reject_fill(db, order, automation, "stopped", "Paper automation stopped")
                return
            fill_time = max(quote.received_at, datetime.now(timezone.utc)) if order["replay_key"] is None else quote.received_at
            if not closed <= fill_time <= closed + AUTOMATION_MAX_AGE:
                self._reject_fill(db, order, automation, "stale", "Decision expired before fill")
                return
        cash, shares = self._balance(db, order["symbol"])
        side = order["side"]
        quantity = shares if side == "close" else order["quantity"]
        amount = quote.price * quantity
        rejection = None
        if side == "buy" and amount > cash:
            rejection = "Insufficient cash at the observed fill price"
        elif side != "buy" and (quantity <= 0 or quantity > shares):
            rejection = "Insufficient shares at the observed fill price"
        if rejection:
            self._reject_fill(db, order, automation, "ineligible", rejection)
            return

        direction = 1 if side == "buy" else -1
        db.execute("UPDATE paper_account SET cash=? WHERE id=1", (str(cash - direction * amount),))
        db.execute("""
            INSERT INTO paper_positions (symbol, shares) VALUES (?, ?)
            ON CONFLICT(symbol) DO UPDATE SET shares=excluded.shares
        """, (order["symbol"], shares + direction * quantity))
        pnl.record_fill(
            db, order, quote, quantity=quantity, previous_shares=shares,
            cash=cash - direction * amount, shares=shares + direction * quantity,
        )
        db.execute("""
            INSERT INTO paper_fills (order_id, quantity, price, observation_id, source_time_ms, executed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order["id"], quantity, str(quote.price), quote.observation_id, quote.source_time_ms,
              quote.received_at.isoformat()))
        db.execute("UPDATE paper_orders SET status='filled', quantity=? WHERE id=?", (quantity, order["id"]))

        if automation:
            db.execute("""
                UPDATE paper_automation_attempts SET status='filled', explanation='Filled at the next eligible price.'
                WHERE id=?
            """, (automation["id"],))

    @staticmethod
    def _reject_fill(db, order, automation, status, reason) -> None:
        db.execute("UPDATE paper_orders SET status='rejected', rejection_reason=? WHERE id=?",
                   (reason, order["id"]))
        if automation:
            db.execute("UPDATE paper_automation_attempts SET status=?, explanation=? WHERE id=?",
                       (status, reason, automation["id"]))

    def advance_replay(self, selection: ReplayAdvance) -> dict:
        with self.transaction() as db:
            db.execute("""
                INSERT INTO paper_automation_replay (generation, symbol, replay_key, step)
                SELECT generation, ?, ?, ? FROM paper_automation_state WHERE account_id=1 AND enabled=1
                ON CONFLICT(generation, symbol, replay_key) DO UPDATE SET step=MAX(step,excluded.step)
            """, (selection.symbol, selection.key(), selection.step))
            orders = db.execute("""
                SELECT * FROM paper_orders
                WHERE status='pending' AND symbol=? AND replay_key=? ORDER BY id
            """, (selection.symbol, selection.key())).fetchall()
            rows = execution_observations(db, selection.symbol, selection.start, selection.end, selection.step)
            for index, row in enumerate(rows):
                cash, shares = self._balance(db, selection.symbol)
                pnl.mark_completed(
                    db, symbol=selection.symbol, cutoff=datetime.fromisoformat(row[2]),
                    scope=selection.key(), cash=cash, shares=shares, replay_rows=rows[:index + 1],
                )
                quote = MarketPrice.from_row(row)
                if quote is None:
                    continue
                pending = []
                for order in orders:
                    if quote.observation_id > order["after_observation_id"]:
                        self._fill(db, order, quote)
                    else:
                        pending.append(order)
                orders = pending
            return self._state(db, selection.symbol)

    def process_live(self) -> None:
        """Fill live pending orders from the first eligible saved quote, including after restart."""
        with self.transaction() as db:
            pending = db.execute("""
                SELECT * FROM paper_orders
                WHERE status='pending' AND replay_key IS NULL ORDER BY id
            """).fetchall()
            if not pending:
                return
            first = min(order["after_observation_id"] for order in pending)
            for row in db.execute("""
                SELECT id, source_time_ms, received_at_utc, source_json, symbol
                FROM observations WHERE id>? ORDER BY id
            """, (first,)):
                quote = MarketPrice.from_row(row)
                if quote is None:
                    continue
                remaining = []
                for order in pending:
                    if (row["symbol"] == order["symbol"]
                            and quote.observation_id > order["after_observation_id"]
                            and quote.received_at >= datetime.fromisoformat(order["submitted_at"])):
                        cash, shares = self._balance(db, order["symbol"])
                        pnl.mark_completed(
                            db, symbol=order["symbol"], cutoff=quote.received_at, scope=pnl.LIVE,
                            cash=cash, shares=shares, max_observation=quote.observation_id,
                        )
                        self._fill(db, order, quote)
                    else:
                        remaining.append(order)
                pending = remaining
                if not pending:
                    break
