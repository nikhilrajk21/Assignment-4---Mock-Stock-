"""Claim completed candles and apply reviewed proposals to the simulated ledger."""

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, Field, StrictBool, model_validator

from backend.decisions import ChartCaptureError, DecisionRequest, DecisionStore, validate_action
from backend.observations import DEFAULT_DATABASE
from backend.replay import execution_observations
from backend.paper import (
    AUTOMATION_MAX_AGE,
    PaperOrder,
    PaperStore,
    ReplaySelection,
)

STRATEGY = "sma-crossover"


class AutomationControl(BaseModel):
    enabled: StrictBool


class AutomationRequest(DecisionRequest):
    generation: Annotated[int, Field(strict=True, ge=0)]
    capture_error: Annotated[str, Field(max_length=300)] | None = None

    @model_validator(mode="after")
    def validate_error(self) -> "AutomationRequest":
        if self.capture_error and self.image_data is not None:
            raise ValueError("Send a fresh chart capture or a capture failure")
        return self


class PaperAutomation:
    def __init__(self, paper: PaperStore, decisions: DecisionStore):
        self.paper = paper
        self.decisions = decisions
        with paper.transaction() as db:
            db.execute("""
                UPDATE paper_automation_attempts
                SET status='interrupted', explanation='Backend restarted during analysis.'
                WHERE status='analyzing'
            """)

    def state(self) -> dict:
        with self.paper.transaction(write=False) as db:
            return self._state(db)

    def control(self, enabled: bool) -> dict:
        with self.paper.transaction() as db:
            current = db.execute("SELECT enabled FROM paper_automation_state WHERE account_id=1").fetchone()[0]
            if bool(current) != enabled:
                db.execute("UPDATE paper_automation_state SET enabled=?, generation=generation+1 WHERE account_id=1",
                           (enabled,))
            if not enabled:
                db.execute("""
                    UPDATE paper_orders SET status='rejected', rejection_reason='Paper automation stopped'
                    WHERE status='pending' AND id IN (
                        SELECT order_id FROM paper_automation_attempts WHERE status='queued'
                    )
                """)
                db.execute("""
                    UPDATE paper_automation_attempts SET status='stopped', explanation='Paper automation stopped.'
                    WHERE status IN ('analyzing','queued')
                """)
            return self._state(db)

    @staticmethod
    def _active(db, generation: int) -> bool:
        row = db.execute("SELECT enabled, generation FROM paper_automation_state WHERE account_id=1").fetchone()
        return bool(row[0]) and row[1] == generation

    def _attempt(self, db, attempt_id: str) -> dict:
        row = db.execute("""
            SELECT a.*, d.result_json, o.status AS order_status, f.price AS fill_price,
                   p.cash AS fill_cash, p.shares AS fill_shares, p.realized AS fill_realized,
                   p.unrealized AS fill_unrealized
            FROM paper_automation_attempts AS a
            LEFT JOIN decisions AS d ON d.id=a.decision_id
            LEFT JOIN paper_orders AS o ON o.id=a.order_id
            LEFT JOIN paper_fills AS f ON f.order_id=o.id
            LEFT JOIN paper_pnl AS p ON p.event_type='fill' AND p.event_id=CAST(o.id AS TEXT)
            WHERE a.id=?
        """, (attempt_id,)).fetchone()
        attempt = dict(row)
        decision = json.loads(attempt.pop("result_json") or "{}")
        attempt["proposal"] = decision.get("proposal")
        attempt["review"] = (decision.get("review") or {}).get("verdict")
        for field in ("fill_price", "fill_cash", "fill_realized", "fill_unrealized"):
            if attempt[field] is not None:
                attempt[field] = float(attempt[field])
        return attempt

    def _state(self, db) -> dict:
        row = db.execute("SELECT enabled, generation FROM paper_automation_state WHERE account_id=1").fetchone()
        ids = db.execute("""
            SELECT id FROM paper_automation_attempts ORDER BY rowid DESC LIMIT 50
        """).fetchall()
        return {"enabled": bool(row[0]), "generation": row[1],
                "attempts": [self._attempt(db, item[0]) for item in ids]}

    @staticmethod
    def _finish(db, attempt_id, status, detail, *, decision_id=None, order_id=None) -> None:
        db.execute("""
            UPDATE paper_automation_attempts
            SET status=?, explanation=?, decision_id=?, order_id=?
            WHERE id=?
        """, (status, detail, decision_id, order_id, attempt_id))

    def analyze(self, payload: AutomationRequest) -> dict:
        snapshot = self.decisions.snapshot(payload.snapshot_id)
        if snapshot is None:
            raise KeyError(payload.snapshot_id)
        attempt_id = uuid4().hex
        key = (STRATEGY, snapshot["symbol"], snapshot["timeframe"], snapshot["timestamp"])
        closed_at = snapshot.get("closed_at")
        with self.paper.transaction() as db:
            existing = db.execute("""
                SELECT id FROM paper_automation_attempts
                WHERE account_id=1 AND strategy=? AND symbol=? AND timeframe=? AND candle_timestamp=?
            """, key).fetchone()
            if existing:
                return self._attempt(db, existing[0])
            if not self._active(db, payload.generation):
                raise AutomationStopped("Paper automation is stopped or has restarted.")
            db.execute("""
                INSERT INTO paper_automation_attempts (
                    id, account_id, generation, strategy, symbol, timeframe, candle_timestamp,
                    snapshot_id, status, explanation, closed_at, crossover
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, 'analyzing', '', ?, ?)
            """, (attempt_id, payload.generation, *key, payload.snapshot_id, closed_at, snapshot["crossover"]))

        if payload.capture_error or payload.image_data is None:
            return self._record_skip(attempt_id, "capture_failed", payload.capture_error or "No chart PNG was supplied.")
        if not snapshot["eligible"] or not closed_at:
            return self._record_skip(attempt_id, "ineligible", "The snapshot lacks eligible completed-candle evidence.")
        if os.getenv("IST402_TEST_MARKET_DATA") == "1" and (
            not os.getenv("IST402_OBSERVATIONS_DB")
            or self.paper.path.resolve() == DEFAULT_DATABASE.resolve()
            or not self.paper.path.resolve().is_relative_to(Path(gettempdir()).resolve())
        ):
            return self._record_skip(attempt_id, "ineligible", "Test data requires a disposable paper database.")

        try:
            result = self.decisions.decide(
                payload.snapshot_id, image_data=payload.image_data,
                chart_start=payload.chart_start, chart_end=payload.chart_end,
            )
        except ChartCaptureError as error:
            return self._record_skip(attempt_id, "capture_failed", str(error))

        with self.paper.transaction() as db:
            if not self._active(db, payload.generation):
                self._finish(db, attempt_id, "stopped", "Automation stopped before the model reply.",
                             decision_id=result["id"])
            elif result.get("review", {}).get("verdict") != "accept" or not result["eligible"]:
                self._finish(db, attempt_id, "ineligible", result["explanation"], decision_id=result["id"])
            else:
                self._enqueue(db, attempt_id, snapshot, result)
            return self._attempt(db, attempt_id)

    def _record_skip(self, attempt_id, status, detail) -> dict:
        with self.paper.transaction() as db:
            current = self._attempt(db, attempt_id)
            if current["status"] == "analyzing":
                self._finish(db, attempt_id, status, detail)
            return self._attempt(db, attempt_id)

    def _enqueue(self, db, attempt_id, snapshot, result) -> None:
        symbol = snapshot["symbol"]
        action = result["proposal"]
        selection = ReplaySelection.model_validate(snapshot["replay"]) if snapshot["replay"] else None
        if selection:
            progress = db.execute("""
                SELECT step FROM paper_automation_replay
                WHERE generation=(SELECT generation FROM paper_automation_state WHERE account_id=1)
                  AND symbol=? AND replay_key=?
            """, (symbol, selection.key())).fetchone()
            if progress and progress[0] > selection.step:
                selection = selection.model_copy(update={"step": progress[0]})
            visible = execution_observations(db, symbol, selection.start, selection.end, selection.step)
            now = max(datetime.fromisoformat(row[2]) for row in visible) if visible else None
        else:
            now = datetime.now(timezone.utc)
        closed = datetime.fromisoformat(snapshot["closed_at"])
        cash, shares = self.paper._balance(db, symbol)
        valid, explanation = validate_action({**snapshot, "cash": cash, "shares": shares}, action)
        if now is None or not closed <= now <= closed + AUTOMATION_MAX_AGE:
            self._finish(db, attempt_id, "stale", "The completed candle is outside the five-minute execution window.",
                         decision_id=result["id"])
        elif not valid:
            self._finish(db, attempt_id, "ineligible", explanation, decision_id=result["id"])
        elif action in {"hold", "wait"}:
            self._finish(db, attempt_id, "no_order", f"{action.capitalize()} leaves the account as it is.",
                         decision_id=result["id"])
        else:
            order = PaperOrder(
                request_id="automation:" + attempt_id, symbol=symbol, side=action,
                quantity=(snapshot["order_size"] if action == "buy"
                          else (snapshot.get("sell_size") or snapshot["order_size"]) if action == "sell"
                          else None),
                replay=selection,
            )
            order_id = self.paper._submit(db, order)
            self._finish(db, attempt_id, "queued", "Waiting for the next eligible price.",
                         decision_id=result["id"], order_id=order_id)


class AutomationStopped(ValueError):
    pass
