"""Freeze paper account evidence, request a model proposal, and save its result."""

from base64 import b64decode
from binascii import Error as BinasciiError
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
from typing import Annotated, Literal
from uuid import uuid4

from PIL import Image
from pydantic import BaseModel, Field, model_validator

from backend.candles import Minute, aggregate_minutes
from backend.decision_provider import MODEL, ProviderError, action_question, ask_decisions
from backend.indicators import SmaCandle, SmaRequest, Window, calculate_sma
from backend.observations import Observation
from backend.paper import Quantity, ReplaySelection
from backend.replay import execution_observations
from backend.timeframes import INTERVALS, roll_up, trading_sessions

Timeframe = Literal["1m", "5m", "15m", "1h", "1d"]
ACTIONS = {"buy", "sell", "hold", "wait", "close"}
UTC = timezone.utc
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_IMAGE_LENGTH = len("data:image/png;base64,") + ((MAX_IMAGE_BYTES + 2) // 3 * 4)


class SnapshotRequest(BaseModel):
    symbol: Literal["AAPL"] = "AAPL"
    timeframe: Timeframe = "1m"
    timestamp: datetime
    short_window: Window = 2
    long_window: Window = 3
    order_size: Quantity = 1
    sell_size: Quantity | None = None
    source: Literal["sample", "recorded"] = "sample"
    replay: ReplaySelection | None = None

    @model_validator(mode="after")
    def validate_input(self) -> "SnapshotRequest":
        if self.timestamp.utcoffset() is None:
            raise ValueError("Candle timestamp must include a timezone")
        if self.short_window >= self.long_window:
            raise ValueError("The short window must be smaller than the long window")
        if self.source != "recorded" and self.replay is not None:
            raise ValueError("Replay requires recorded market data")
        return self


class DecisionRequest(BaseModel):
    snapshot_id: Annotated[str, Field(min_length=1, max_length=128)]
    image_data: Annotated[str, Field(max_length=MAX_IMAGE_LENGTH)] | None = None
    chart_start: datetime | None = None
    chart_end: datetime | None = None

    @model_validator(mode="after")
    def validate_capture_fields(self) -> "DecisionRequest":
        supplied = tuple(value is not None for value in (self.image_data, self.chart_start, self.chart_end))
        if any(supplied) and not all(supplied):
            raise ValueError("Recapture the chart with its PNG and both time range endpoints.")
        return self



class ChartCaptureError(ValueError):
    """The chart must be captured again from the frozen snapshot."""


def validate_chart(snapshot: dict, image_data: str, start: datetime, end: datetime) -> None:
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ChartCaptureError("Recapture the chart with time zone offsets for both endpoints.")
    stamps = {datetime.fromisoformat(row["timestamp"]) for row in snapshot["candles"]}
    if start > end or start not in stamps or end not in stamps or end != datetime.fromisoformat(snapshot["timestamp"]):
        raise ChartCaptureError("Recapture the chart from the frozen candles through the selected candle.")

    prefix = "data:image/png;base64,"
    if not image_data.startswith(prefix) or len(image_data) > MAX_IMAGE_LENGTH:
        raise ChartCaptureError("Recapture the chart as a PNG no larger than 6 MiB.")
    try:
        raw = b64decode(image_data[len(prefix):], validate=True)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("Invalid size")
        with Image.open(BytesIO(raw), formats=("PNG",)) as image:
            if (
                image.width < 1 or image.height < 1
                or image.width > 4096 or image.height > 4096
                or image.width * image.height > 8_388_608
                or getattr(image, "n_frames", 1) != 1
            ):
                raise ValueError("Invalid dimensions or frame count")
            image.verify()
        with Image.open(BytesIO(raw), formats=("PNG",)) as image:
            image.load()
    except (BinasciiError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
        raise ChartCaptureError("The PNG could not be decoded. Recapture the chart from the selected snapshot.") from error


def chart_questions() -> list[dict]:
    return [
        action_question(),
        {
            "type": "choice",
            "name": "crossover",
            "instructions": (
                "At the selected candle on the PNG, identify the visible crossover using only "
                "the chart. Choose unreadable if you cannot inspect it."
            ),
            "choices": [
                {"value": "up", "description": "The short SMA crosses above the long SMA."},
                {"value": "down", "description": "The short SMA crosses below the long SMA."},
                {"value": "none", "description": "There is no crossover at the selected candle."},
                {"value": "unreadable", "description": "The crossover cannot be read."},
            ],
        },
        {
            "type": "choice",
            "name": "evidence",
            "instructions": "Does the visible chart provide enough evidence to assess the signal at the cutoff?",
            "choices": [
                {"value": "sufficient", "description": "The chart shows enough evidence."},
                {"value": "insufficient", "description": "The chart does not show enough evidence."},
            ],
        },
    ]


def chart_verdict(answers, expected: str) -> tuple[str, str, str | None, str | None]:
    crossover = named_choice(answers, "crossover", {"up", "down", "none", "unreadable"})
    evidence = named_choice(answers, "evidence", {"sufficient", "insufficient"})
    if crossover is None or evidence is None or len(answers) != 3:
        return "malformed_answer", "The provider did not return all three named chart answers.", crossover, evidence
    if crossover == "unreadable":
        return "chart_unreadable", "The provider could not read the chart. Recapture the selected candle.", crossover, evidence
    if evidence == "insufficient":
        return "insufficient_evidence", "The provider found insufficient chart evidence. Recapture with the signal visible.", crossover, evidence
    if crossover != expected:
        return "conflicting_signal", f"The chart answer {crossover} conflicts with the calculated crossover {expected}.", crossover, evidence
    return "ok", f"The chart agrees with the calculated crossover {expected}.", crossover, evidence


def utc_text(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value is not None else None


def interval_close(start: datetime, timeframe: str) -> datetime | None:
    placeholder = Minute({"timestamp": utc_text(start), "open": 0, "high": 0, "low": 0, "close": 0, "volume": None}, True)
    size = INTERVALS[timeframe]
    for session_open, session_close in trading_sessions([placeholder]):
        if not session_open <= start < session_close:
            continue
        offset = (start - session_open).total_seconds()
        if size is None:
            return session_close if offset == 0 else None
        if offset % (size * 60) == 0:
            return min(start + timedelta(minutes=size), session_close)
    return None


def available_observations(db, payload: SnapshotRequest, cutoff: datetime, replay_id: int | None):
    rows = db.execute("""
        SELECT o.id, o.source_time_ms, o.received_at_utc, o.source_json, r.supersedes_id
        FROM observations AS o
        LEFT JOIN observation_revisions AS r ON r.observation_id = o.id
        WHERE o.symbol = ? AND o.source_time_ms < ?
        ORDER BY o.id
    """, (payload.symbol, cutoff.timestamp() * 1000))
    lower = None
    if payload.replay:
        start = payload.replay.start
        minute = start.replace(second=0, microsecond=0)
        lower = (minute - timedelta(minutes=1) if start == minute else start).timestamp() * 1000
    return [
        Observation(row_id, source_time, received_at, json.loads(source), supersedes)
        for row_id, source_time, received, source, supersedes in rows
        if (received_at := datetime.fromisoformat(received)) <= cutoff
        and (payload.replay is None or (
            replay_id is not None and row_id <= replay_id
            and lower <= source_time < payload.replay.end.timestamp() * 1000
        ))
    ]


def account_at(db, payload: SnapshotRequest, cutoff: datetime, replay_id: int | None) -> tuple[Decimal, int]:
    cash, shares = Decimal(1000), 0
    scope = payload.replay.key() if payload.replay else None
    fills = db.execute("""
        SELECT o.symbol, o.side, f.quantity, f.price, f.executed_at, f.observation_id
        FROM paper_fills AS f JOIN paper_orders AS o ON o.id = f.order_id
        WHERE o.replay_key IS ?
    """, (scope,))
    for symbol, side, quantity, price, executed, observation_id in fills:
        if datetime.fromisoformat(executed) > cutoff:
            continue
        if payload.replay and (replay_id is None or observation_id > replay_id):
            continue
        direction = 1 if side == "buy" else -1
        cash -= direction * quantity * Decimal(price)
        if symbol == payload.symbol:
            shares += direction * quantity
    return cash, shares


class DecisionStore:
    def __init__(self, path: Path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS decision_snapshots (
                    id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL REFERENCES decision_snapshots(id),
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS decision_images (
                    decision_id TEXT PRIMARY KEY REFERENCES decisions(id), image_data TEXT NOT NULL
                )
            """)

    def connect(self):
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def freeze(self, payload: SnapshotRequest, sample_loader) -> dict:
        start = payload.timestamp.astimezone(UTC)
        close_time = interval_close(start, payload.timeframe)
        now = datetime.now(UTC)
        cutoff = min(now, close_time or start)
        replay_id = None
        missing = []
        with closing(self.connect()) as db, db:
            db.execute("BEGIN")
            if payload.replay:
                selection = payload.replay
                if not selection.start <= start < selection.end:
                    missing.append("candle outside replay range")
                visible = execution_observations(
                    db, payload.symbol, selection.start, selection.end, selection.step
                )
                if visible:
                    replay_id = visible[-1][0]
                    cutoff = min(cutoff, max(datetime.fromisoformat(row[2]) for row in visible))
                else:
                    missing.append("replay observations")
            if close_time is None:
                missing.append("valid interval start")
            elif cutoff < close_time:
                missing.append("completed candle")
            if payload.source == "sample":
                minutes = sample_loader(cutoff)
                observations = []
            else:
                observations = available_observations(db, payload, cutoff, replay_id)
                minutes = aggregate_minutes(observations, as_of=cutoff)
                if payload.replay:
                    first = payload.replay.start.replace(second=0, microsecond=0)
                    minutes = [minute for minute in minutes if datetime.fromisoformat(minute.candle["timestamp"]) >= first]
            cash, shares = account_at(db, payload, cutoff, replay_id)

        candles = [
            row for row in roll_up(minutes, payload.timeframe, trading_sessions(minutes), as_of=cutoff)
            if datetime.fromisoformat(row.candle["timestamp"]) <= start and row.complete
        ]
        target = candles[-1] if candles and datetime.fromisoformat(candles[-1].candle["timestamp"]) == start else None
        points = calculate_sma(SmaRequest(
            short_window=payload.short_window,
            long_window=payload.long_window,
            candles=[SmaCandle(timestamp=row.candle["timestamp"], close=row.candle["close"], complete=True)
                     for row in candles],
        ))
        point = points[-1] if target else None
        if target is None and "completed candle" not in missing:
            missing.append("completed candle")
        if point is None or point.short is None or point.long is None:
            missing.append("both completed-candle moving averages")
        snapshot = {
            "id": uuid4().hex,
            "symbol": payload.symbol,
            "timeframe": payload.timeframe,
            "timestamp": utc_text(start),
            "closed_at": utc_text(close_time),
            "cutoff": utc_text(cutoff),
            "source": payload.source,
            "market_data_label": (
                "Synthetic sample" if payload.source == "sample"
                else "Synthetic replay fixture" if os.environ.get("IST402_TEST_MARKET_DATA") == "1"
                else "Recorded Yahoo Finance"
            ),
            "candles": [row.candle for row in candles],
            "indicator_points": [item.model_dump() for item in points],
            "short_window": payload.short_window,
            "long_window": payload.long_window,
            "short_sma": point.short if point else None,
            "long_sma": point.long if point else None,
            "crossover": point.crossover if point else None,
            "close": target.candle["close"] if target else None,
            "cash": float(cash),
            "shares": shares,
            "order_size": payload.order_size,
            "sell_size": payload.sell_size or payload.order_size,
            "eligible": payload.source == "recorded" and not missing,
            "missing_inputs": missing,
            "replay": payload.replay.model_dump(mode="json") if payload.replay else None,
            "observation_watermark": max((row.id for row in observations), default=None),
        }
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO decision_snapshots VALUES (?, ?, ?)",
                (snapshot["id"], json.dumps(snapshot, allow_nan=False), utc_text(now)),
            )
        return snapshot

    def snapshot(self, snapshot_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT payload_json FROM decision_snapshots WHERE id=?", (snapshot_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def decide(
        self, snapshot_id: str, *, image_data: str | None = None,
        chart_start: datetime | None = None, chart_end: datetime | None = None,
    ) -> dict:
        snapshot = self.snapshot(snapshot_id)
        if snapshot is None:
            raise KeyError(snapshot_id)
        if image_data is not None:
            if chart_start is None or chart_end is None:
                raise ChartCaptureError("Recapture the chart with both time range endpoints.")
            validate_chart(snapshot, image_data, chart_start, chart_end)

        result = {
            "id": uuid4().hex,
            "snapshot_id": snapshot_id,
            "provider": "openai",
            "model": None,
            "status": "missing_input",
            "proposal": None,
            "explanation": "",
            "eligible": False,
            "answers": [],
        }
        questions = chart_questions() if image_data is not None else [action_question()]
        expected = snapshot["crossover"] or "none"
        if image_data is not None:
            result.update(
                questions=questions, chart_start=utc_text(chart_start), chart_end=utc_text(chart_end),
                expected_crossover=expected, visual_crossover=None, evidence=None,
            )
        if snapshot["missing_inputs"]:
            result["explanation"] = "Snapshot is missing " + ", ".join(snapshot["missing_inputs"]) + "."
        else:
            try:
                if image_data is not None:
                    chart_snapshot = {**snapshot, "chart_start": utc_text(chart_start), "chart_end": utc_text(chart_end)}
                    response = ask_decisions(chart_snapshot, questions, image_data=image_data)
                else:
                    response = ask_decisions(snapshot, questions)
            except ProviderError as error:
                result["status"] = error.status
                result["model"] = MODEL
                result["explanation"] = str(error)
            else:
                result["model"] = response.get("model")
                answers = response.get("answers")
                if isinstance(answers, list):
                    result["answers"] = answers
                proposal = named_action(answers)
                if proposal is None:
                    result["status"] = "malformed_answer"
                    result["explanation"] = "The provider did not return one valid named action."
                else:
                    valid, explanation = validate_action(snapshot, proposal)
                    result.update(
                        status="ok" if valid else "invalid_action",
                        proposal=proposal,
                        explanation=explanation,
                        eligible=valid and snapshot["eligible"],
                    )
                    if image_data is not None:
                        status, detail, visual, evidence = chart_verdict(answers, expected)
                        result.update(visual_crossover=visual, evidence=evidence)
                        result["explanation"] += " " + detail
                        if status != "ok":
                            result.update(status=status, eligible=False)
                    review_proposal(chart_snapshot if image_data is not None else snapshot, result, image_data)
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?)",
                (result["id"], snapshot_id, json.dumps(result, allow_nan=False), utc_text(datetime.now(UTC))),
            )
            if image_data is not None:
                db.execute("INSERT INTO decision_images VALUES (?, ?)", (result["id"], image_data))
        return result

    def decision(self, decision_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("""
                SELECT d.result_json, s.payload_json, i.image_data
                FROM decisions AS d JOIN decision_snapshots AS s ON s.id = d.snapshot_id
                LEFT JOIN decision_images AS i ON i.decision_id = d.id
                WHERE d.id = ?
            """, (decision_id,)).fetchone()
        if row is None:
            return None
        result = {**json.loads(row[0]), "snapshot": json.loads(row[1])}
        if row[2] is not None:
            result["image_data"] = row[2]
        return result

    def recent(self) -> list[dict]:
        with closing(self.connect()) as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT result_json FROM decisions ORDER BY created_at DESC, id DESC LIMIT 100"
            )]


def named_action(answers) -> str | None:
    return named_choice(answers, "action", ACTIONS)


def named_choice(answers, name: str, choices: set[str]) -> str | None:
    if not isinstance(answers, list):
        return None
    matches = [answer for answer in answers if isinstance(answer, dict) and answer.get("name") == name]
    if len(matches) != 1 or matches[0].get("type") != "choice":
        return None
    choice = matches[0].get("choice")
    return choice if isinstance(choice, str) and choice in choices else None


def review_question() -> dict:
    return {
        "type": "choice", "name": "review",
        "instructions": (
            "Review the analyst's actual paper action against the same frozen evidence. "
            "Reject an unaffordable purchase, an unsupported crossover or an invalid position. "
            "Purchases require an upward crossover and partial sales a downward crossover. "
            "A close exits an existing position. Accept only when the evidence supports the action."
        ),
        "choices": [
            {"value": "accept", "description": "The proposal is supported by the frozen evidence."},
            {"value": "insufficient_cash", "description": "The account cannot fund the proposed purchase."},
            {"value": "unsupported_signal", "description": "The signal or position does not support the proposal."},
        ],
    }


def review_proposal(snapshot: dict, result: dict, image_data: str | None) -> None:
    """Save the independent review without allowing it to override Python checks."""
    question = review_question()
    review = {"question": question, "model": MODEL, "answers": [], "verdict": None}
    result["review"] = review
    evidence = {
        **snapshot,
        "analyst_proposal": result["proposal"],
        "analyst_answers": result["answers"],
        "backend_facts": result["explanation"],
    }
    try:
        response = (ask_decisions(evidence, [question], image_data=image_data)
                    if image_data is not None else ask_decisions(evidence, [question]))
    except ProviderError as error:
        review.update(status=error.status, explanation=str(error))
    else:
        answers = response.get("answers")
        verdict = named_choice(answers, "review", {"accept", "insufficient_cash", "unsupported_signal"})
        review.update(model=response.get("model"), answers=answers if isinstance(answers, list) else [],
                      verdict=verdict, status="ok" if verdict else "malformed_answer")
        review["explanation"] = (
            f"Reviewer chose {verdict.replace('_', ' ')}." if verdict else "Reviewer returned no valid verdict."
        )
    result["explanation"] += " " + review["explanation"]
    if review["verdict"] != "accept":
        if result["status"] == "ok":
            result["status"] = "review_rejected" if review["verdict"] else "review_" + review["status"]
        result["eligible"] = False


def validate_action(snapshot: dict, action: str) -> tuple[bool, str]:
    close = Decimal(str(snapshot["close"]))
    cash = Decimal(str(snapshot["cash"]))
    shares = snapshot["shares"]
    size = snapshot.get("sell_size", snapshot["order_size"]) if action == "sell" else snapshot["order_size"]
    evidence = (
        f"Frozen {snapshot['symbol']} close {close}, cash {cash}, shares {shares}, "
        f"short SMA {snapshot['short_sma']}, long SMA {snapshot['long_sma']}, "
        f"crossover {snapshot['crossover'] or 'none'}."
    )
    if action == "buy":
        valid = close > 0 and cash >= size * close and snapshot["crossover"] == "up"
        reason = f"{size} shares at the recorded close would cost {size * close}. Buy requires an upward crossover."
    elif action == "sell":
        valid = shares >= size and snapshot["crossover"] == "down"
        reason = f"Selling {size} shares requires at least {size} shares held and a downward crossover."
    elif action in {"close", "hold"}:
        valid = shares > 0
        reason = f"{action.capitalize()} requires an open position."
    else:
        valid = shares == 0
        reason = "Wait requires a flat position."
    return valid, f"{evidence} Proposed {action}. {reason}"
