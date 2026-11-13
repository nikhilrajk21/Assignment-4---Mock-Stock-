"""Independent educational chart interpretation without paper account actions."""

from base64 import b64decode
from binascii import Error as BinasciiError
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
import json
from uuid import uuid4

from PIL import Image
from pydantic import Field

from backend.chart_history import fetch_chart_history
from backend.decision_provider import MODEL, ProviderError, ask_decisions
from backend.decisions import (
    ChartCaptureError, DecisionRequest, MAX_IMAGE_BYTES, MAX_IMAGE_LENGTH,
    named_choice, utc_text, validate_chart,
)

POLICY_VERSION = "chart-direction-2026-11-12"
POLICY = (
    "Study the chart images for the trend over the last one to two trading days. "
    "Use the beginning of that period as reference. If the move exceeds 10 percent "
    "in either direction, examine the available five-minute and extended-hours detail. "
    "If evidence is unclear or stale, consider comparable prior recorded situations "
    "only if supplied. Do not invent unavailable evidence. These are revised historical "
    "bars retrieved later and cannot establish what was known during replay."
)
QUESTION = {
    "type": "choice", "name": "direction", "instructions": POLICY,
    "choices": [
        {"value": "long", "description": "A hypothetical long direction is supported."},
        {"value": "short", "description": "A hypothetical short direction is supported."},
        {"value": "wait", "description": "The available evidence does not support a direction."},
    ],
}
EVIDENCE_QUESTION = {
    "type": "choice", "name": "clarity",
    "instructions": "Is the current chart evidence clear enough to support a direction without relying on prior examples?",
    "choices": [
        {"value": "clear", "description": "The current chart supports a directional interpretation."},
        {"value": "unclear", "description": "The current chart does not clearly support a direction."},
    ],
}


class ChartAnalysisRequest(DecisionRequest):
    history_id: str | None = Field(default=None, max_length=128)
    history_image_data: str | None = Field(default=None, max_length=MAX_IMAGE_LENGTH)


def _initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS chart_histories (
        id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, payload_json TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS chart_analyses (
        id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, result_json TEXT NOT NULL,
        image_data TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS chart_analysis_history_images (
        analysis_id TEXT PRIMARY KEY, history_id TEXT NOT NULL, image_data TEXT NOT NULL
    )""")


def prepare_history(store, snapshot_id):
    snapshot = store.snapshot(snapshot_id)
    if snapshot is None:
        raise KeyError(snapshot_id)
    history = fetch_chart_history(snapshot["symbol"], datetime.fromisoformat(snapshot["cutoff"]))
    history["id"] = uuid4().hex
    history["snapshot_id"] = snapshot_id
    with closing(store.connect()) as db, db:
        _initialize(db)
        db.execute(
            "INSERT INTO chart_histories VALUES (?, ?, ?)",
            (history["id"], snapshot_id, json.dumps(history, allow_nan=False)),
        )
    return history


def _history(store, history_id, snapshot_id):
    with closing(store.connect()) as db, db:
        _initialize(db)
        row = db.execute(
            "SELECT payload_json FROM chart_histories WHERE id=? AND snapshot_id=?",
            (history_id, snapshot_id),
        ).fetchone()
    if row is None:
        raise ChartCaptureError("The historical chart no longer matches this snapshot.")
    return json.loads(row[0])


def _validate_image(image_data):
    prefix = "data:image/png;base64,"
    if not image_data.startswith(prefix) or len(image_data) > MAX_IMAGE_LENGTH:
        raise ChartCaptureError("Recapture the historical chart as a PNG.")
    try:
        raw = b64decode(image_data[len(prefix):], validate=True)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("Invalid size")
        with Image.open(BytesIO(raw), formats=("PNG",)) as image:
            if (image.width < 1 or image.height < 1 or image.width > 4096 or
                    image.height > 4096 or image.width * image.height > 8_388_608 or
                    getattr(image, "n_frames", 1) != 1):
                raise ValueError("Invalid dimensions")
            image.verify()
        with Image.open(BytesIO(raw), formats=("PNG",)) as image:
            image.load()
    except (BinasciiError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise ChartCaptureError("The historical chart PNG could not be decoded.") from None


def _source_freshness(store, snapshot):
    watermark = snapshot.get("observation_watermark")
    if not watermark:
        return {"status": "unknown", "age_seconds": None, "source_time": None}
    cutoff = datetime.fromisoformat(snapshot["cutoff"])
    with closing(store.connect()) as db:
        row = db.execute(
            """SELECT MAX(source_time_ms) FROM observations
               WHERE symbol = ? AND id <= ? AND source_time_ms <= ?
               AND julianday(received_at_utc) <= julianday(?)""",
            (snapshot["symbol"], watermark, cutoff.timestamp() * 1000, snapshot["cutoff"]),
        ).fetchone()
    if not row or row[0] is None:
        return {"status": "unknown", "age_seconds": None, "source_time": None}
    source_time = datetime.fromtimestamp(row[0] / 1000, timezone.utc)
    age = (cutoff - source_time).total_seconds()
    return {"status": "fresh" if age <= 300 else "stale",
            "age_seconds": age, "source_time": utc_text(source_time)}


def analyze_chart(store, payload):
    snapshot = store.snapshot(payload.snapshot_id)
    if snapshot is None:
        raise KeyError(payload.snapshot_id)
    if payload.image_data is None or payload.chart_start is None or payload.chart_end is None:
        raise ChartCaptureError("A chart image and its time range are required.")
    validate_chart(snapshot, payload.image_data, payload.chart_start, payload.chart_end)
    if bool(payload.history_id) != bool(payload.history_image_data):
        raise ChartCaptureError("The historical chart and its history ID are both required.")

    history = _history(store, payload.history_id, payload.snapshot_id) if payload.history_id else None
    if history:
        _validate_image(payload.history_image_data)
    sessions = history.get("coverage", {}).get("sessions", []) if history else []
    freshness = _source_freshness(store, snapshot)
    coverage = {
        "chart_start": utc_text(payload.chart_start), "chart_end": utc_text(payload.chart_end),
        "history": history.get("coverage", {}) if history else "Historical chart unavailable.",
        "reference_price": history.get("reference_price") if history else None,
        "last_price": history.get("last_price") if history else None,
        "change_percent": history.get("change_percent") if history else None,
        "large_move": history.get("large_move") if history else None,
        "comparables": history.get("comparables", []) if history else [],
        "provenance": history.get("provenance") if history else "No historical data supplied.",
        "limitations": history.get("limitations", []) if history else [],
        "freshness": freshness,
        "reference_scope": history.get("reference_note") if history else None,
        "reference_timestamp": history.get("reference_timestamp") if history else None,
        "last_timestamp": history.get("last_timestamp") if history else None,
        "image_validation": "PNG structure was checked; the server cannot independently prove that the image depicts the supplied historical bars.",
    }
    has_regular = bool(sessions) and all(item["regular"]["complete"] for item in sessions)
    extended = bool(sessions) and all(
        item["premarket"]["complete"] and item["postmarket"]["complete"] for item in sessions
    )
    if not extended:
        coverage["change_percent"] = None
        coverage["large_move"] = None
        coverage["threshold_status"] = "Unavailable because extended-hours coverage is incomplete."
    else:
        coverage["threshold_status"] = "Calculated from the complete selected period."
    replay = snapshot.get("replay") is not None
    history_delay = None
    if history and history.get("retrieved_at"):
        try:
            retrieved = datetime.fromisoformat(history["retrieved_at"])
            cutoff = datetime.fromisoformat(snapshot["cutoff"])
            if retrieved.utcoffset() is not None and cutoff.utcoffset() is not None:
                history_delay = (retrieved - cutoff).total_seconds()
        except (ValueError, TypeError, OverflowError):
            pass
    current_history = history_delay is not None and 0 <= history_delay <= 300
    coverage["history_retrieval_delay_seconds"] = history_delay
    coverage["history_timing"] = (
        "History retrieved within five minutes of the snapshot cutoff."
        if current_history else
        "Historical retrieval is retrospective or its timing is unavailable."
    )
    adequate = bool(history and history.get("bars") and not history.get("error") and has_regular
                    and extended and not replay and current_history
                    and snapshot.get("source") == "recorded"
                    and snapshot.get("market_data_label") == "Recorded Yahoo Finance")
    comparable_outcomes = [
        item for item in coverage["comparables"] if item.get("outcome") is not None
    ] if extended else []
    if freshness["status"] != "fresh" and not comparable_outcomes:
        adequate = False
    context = {
        "symbol": snapshot["symbol"], "timeframe": snapshot["timeframe"],
        "chart_start": coverage["chart_start"], "chart_end": coverage["chart_end"],
        "market_data_label": snapshot["market_data_label"],
        "history_source": history.get("source") if history else None,
        "history_interval": history.get("interval") if history else None,
        "image_order": [
            "Selected chart with its volume and indicator series.",
            "Five-minute historical chart for the selected one or two sessions.",
        ],
        "chart_colors": (
            "On the historical chart, blue candles indicate premarket and purple candles "
            "indicate postmarket. Green and red candles indicate rising and falling prices "
            "during regular hours. The selected chart uses green and red for rising and "
            "falling prices, blue for the short SMA, and brown for the long SMA."
        ),
        "coverage": coverage,
    }
    result = {
        "id": uuid4().hex, "snapshot_id": snapshot["id"], "policy_version": POLICY_VERSION,
        "policy": POLICY, "model": MODEL, "status": "insufficient_evidence", "choice": None,
        "explanation": "History, freshness, comparable outcomes, or extended-hours evidence is insufficient, or the chart uses synthetic data.",
        "coverage": coverage,
    }
    if replay:
        result["explanation"] = (
            "Later-retrieved Yahoo history cannot establish what was known during replay. "
            "A chart direction is unavailable for this replay snapshot."
        )
    elif history and not current_history:
        result["explanation"] = (
            "History was retrieved more than five minutes after the selected cutoff, "
            "or retrieval timing is unavailable. A retrospective direction is unavailable."
        )
    if adequate:
        try:
            reply = ask_decisions(context, [QUESTION, EVIDENCE_QUESTION], image_data=payload.image_data,
                                  additional_images=[payload.history_image_data])
            choice = named_choice(reply.get("answers"), "direction", {"long", "short", "wait"})
            clarity = named_choice(reply.get("answers"), "clarity", {"clear", "unclear"})
            if choice is None or clarity is None:
                result.update(status="malformed_answer", explanation="The model did not return valid direction and clarity answers.")
            elif clarity == "unclear" and not comparable_outcomes:
                result.update(status="insufficient_evidence", explanation="The chart was unclear and no comparable outcome was available.")
            else:
                result.update(status="ok", choice=choice, model=reply["model"],
                              explanation="The model evaluated the supplied chart images and coverage.", clarity=clarity)
        except ProviderError as error:
            result.update(status=error.status, explanation=str(error))
    with closing(store.connect()) as db, db:
        _initialize(db)
        db.execute(
            "INSERT INTO chart_analyses VALUES (?, ?, ?, ?)",
            (result["id"], snapshot["id"], json.dumps(result, allow_nan=False), payload.image_data),
        )
        if history:
            db.execute(
                "INSERT INTO chart_analysis_history_images VALUES (?, ?, ?)",
                (result["id"], history["id"], payload.history_image_data),
            )
    return result
