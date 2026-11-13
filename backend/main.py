import asyncio
from contextlib import asynccontextmanager
import csv
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from websockets.exceptions import ConnectionClosed

from backend.automation import AutomationControl, AutomationRequest, AutomationStopped, PaperAutomation
from backend.candles import Candle, Minute
from backend.decisions import ChartCaptureError, DecisionRequest, DecisionStore, SnapshotRequest
from backend.chart_analysis import ChartAnalysisRequest
from backend.indicator_store import DuplicateIndicator, EvaluatedIndicator, IndicatorSettings, IndicatorStore, IndicatorWindowUpdate, SavedIndicator
from backend.indicators import IndicatorEvaluation, SmaPoint, SmaRequest, calculate_sma, evaluate_indicator, indicator_catalog
from backend.live_feed import LiveFeed, SYMBOL
from backend.paper import PaperOrder, PaperStore, ReplayAdvance, RequestConflict
from backend.replay import recorded_sessions, replay
from backend.timeframes import INTERVALS, roll_up, trading_sessions
from backend.voice import VoiceError, VoiceOffer, open_voice_session

async def mark_live_minutes(paper: PaperStore) -> None:
    while True:
        await asyncio.to_thread(paper.mark_live)
        now = datetime.now(timezone.utc)
        await asyncio.sleep(60 - now.second - now.microsecond / 1_000_000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(Path(__file__).resolve().parent.parent / '.env', override=False)
    feed = LiveFeed.from_environment()
    app.state.live_feed = feed
    app.state.indicators = IndicatorStore(feed.store.path)
    paper = PaperStore(feed.store.path)
    app.state.paper = paper
    app.state.decisions = DecisionStore(feed.store.path)
    app.state.automation = PaperAutomation(paper, app.state.decisions)
    feed.on_recorded = paper.process_live
    tasks = []
    if os.environ.get("IST402_YAHOO_LIVE") == "1":
        await asyncio.to_thread(paper.process_live)
        feed.status = "connecting"
        tasks.append(asyncio.create_task(feed.run()))
        tasks.append(asyncio.create_task(mark_live_minutes(paper)))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(lifespan=lifespan)
CANDLE_FILE = Path(__file__).with_name("data") / "sample-candles.csv"
Timeframe = Literal["1m", "5m", "15m", "1h", "1d"]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class CandleResponse(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int | None


class Coverage(BaseModel):
    timestamp: str
    complete: bool
    covered_minutes: int
    expected_minutes: int


class History(BaseModel):
    candles: list[CandleResponse]
    coverage: list[Coverage]


def sample_minutes(as_of: datetime) -> list[Minute]:
    with CANDLE_FILE.open(encoding="utf-8", newline="") as source:
        minutes = []
        for row in csv.DictReader(source):
            start = datetime.fromisoformat(row["timestamp"])
            if start + timedelta(minutes=1) > as_of:
                continue
            candle: Candle = {
                "timestamp": row["timestamp"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
            }
            minutes.append(Minute(candle, complete=True))
    return minutes


@app.get("/api/history", response_model=list[CandleResponse] | History)
def history(
    symbol: Literal["AAPL"] = "AAPL",
    timeframe: Timeframe = "1m",
    as_of: datetime | None = None,
    include_metadata: bool = False,
):
    """Serve the synthetic AAPL fixture on the Nasdaq regular session schedule."""
    if as_of is not None and as_of.utcoffset() is None:
        raise HTTPException(status_code=422, detail="as_of must include a timezone")
    cutoff = as_of or datetime.now(timezone.utc)
    minutes = sample_minutes(cutoff)
    rollups = roll_up(minutes, timeframe, trading_sessions(minutes), as_of=cutoff)
    candles = [row.candle for row in rollups]
    if not include_metadata:
        return candles
    return {
        "candles": candles,
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


@app.websocket("/api/live")
async def live(websocket: WebSocket, symbol: str = "AAPL", timeframe: str = "1m") -> None:
    if symbol != SYMBOL or timeframe not in INTERVALS:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    previous = None
    try:
        while True:
            snapshot = await asyncio.to_thread(websocket.app.state.live_feed.snapshot, symbol, timeframe)
            if snapshot != previous:
                await websocket.send_json(snapshot)
                previous = snapshot
            try:
                incoming = await asyncio.wait_for(websocket.receive(), timeout=1)
            except TimeoutError:
                continue
            if incoming["type"] == "websocket.disconnect":
                return
    except (WebSocketDisconnect, ConnectionClosed, OSError):
        return


@app.get("/api/replay/sessions")
def list_replay_sessions(request: Request):
    return recorded_sessions(request.app.state.live_feed.store.path)


@app.get("/api/replay")
def replay_step(
    request: Request,
    start: datetime,
    end: datetime,
    symbol: str = SYMBOL,
    timeframe: Timeframe = "1m",
    step: int = Query(default=1, ge=0),
):
    if start.utcoffset() is None or end.utcoffset() is None:
        raise HTTPException(status_code=422, detail="Replay start and end must include a timezone")
    if end <= start:
        raise HTTPException(status_code=422, detail="Replay end must be after its start")
    return replay(
        request.app.state.live_feed.store.path,
        symbol.strip().upper(),
        start.astimezone(timezone.utc),
        end.astimezone(timezone.utc),
        timeframe,
        step,
    )


@app.post("/api/indicators/sma", response_model=list[SmaPoint])
def simple_moving_averages(request: SmaRequest) -> list[SmaPoint]:
    return calculate_sma(request)


@app.get("/api/indicators/types")
def list_indicator_types() -> list[dict]:
    return indicator_catalog()


@app.get("/api/indicators", response_model=list[SavedIndicator])
def list_indicators(request: Request) -> list[SavedIndicator]:
    return request.app.state.indicators.all()


@app.post("/api/indicators", response_model=SavedIndicator, status_code=201)
def add_indicator(request: Request, settings: IndicatorSettings) -> SavedIndicator:
    try:
        return request.app.state.indicators.add(settings)
    except DuplicateIndicator as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.patch("/api/indicators/{indicator_id}", response_model=SavedIndicator)
def change_indicator_window(request: Request, indicator_id: int, payload: IndicatorWindowUpdate):
    saved = request.app.state.indicators.change_window(indicator_id, payload.window)
    if saved is None:
        raise HTTPException(status_code=404, detail="Indicator not found")
    return saved


@app.post("/api/indicators/evaluate", response_model=list[EvaluatedIndicator])
def evaluate_indicators(request: Request, payload: IndicatorEvaluation) -> list[EvaluatedIndicator]:
    return [
        EvaluatedIndicator(
            **saved.model_dump(),
            values=evaluate_indicator(saved.type, payload.candles, saved.window),
        )
        for saved in request.app.state.indicators.all()
    ]


@app.get("/api/paper")
def paper_state(request: Request):
    return request.app.state.paper.state()


@app.post("/api/paper/orders")
def paper_order(request: Request, payload: PaperOrder):
    try:
        return request.app.state.paper.submit(payload)
    except RequestConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/paper/replay-step")
def paper_replay_step(request: Request, payload: ReplayAdvance):
    return request.app.state.paper.advance_replay(payload)


@app.get("/api/paper/pnl")
def paper_pnl(request: Request):
    return request.app.state.paper.pnl_history()



@app.post("/api/decision-snapshots", status_code=201)
def create_decision_snapshot(request: Request, payload: SnapshotRequest):
    return request.app.state.decisions.freeze(payload, sample_minutes)


@app.get("/api/decision-snapshots/{snapshot_id}")
def read_decision_snapshot(request: Request, snapshot_id: str):
    snapshot = request.app.state.decisions.snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Decision snapshot not found")
    return snapshot


@app.post("/api/decisions", status_code=201)
def create_decision(request: Request, payload: DecisionRequest):
    try:
        return request.app.state.decisions.decide(
            payload.snapshot_id, image_data=payload.image_data,
            chart_start=payload.chart_start, chart_end=payload.chart_end,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision snapshot not found") from error
    except ChartCaptureError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/chart-history")
def get_chart_history(request: Request, snapshot_id: str):
    from backend.chart_analysis import prepare_history

    try:
        return prepare_history(request.app.state.decisions, snapshot_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision snapshot not found") from error


@app.post("/api/chart-analysis", status_code=201)
def create_chart_analysis(request: Request, payload: ChartAnalysisRequest):
    from backend.chart_analysis import analyze_chart

    try:
        return analyze_chart(request.app.state.decisions, payload)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision snapshot not found") from error
    except ChartCaptureError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

@app.get("/api/decisions")
def list_decisions(request: Request):
    return request.app.state.decisions.recent()


@app.get("/api/decisions/{decision_id}")
def read_decision(request: Request, decision_id: str):
    result = request.app.state.decisions.decision(decision_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return result


@app.get("/api/paper/automation")
def paper_automation(request: Request):
    return request.app.state.automation.state()


@app.post("/api/paper/automation/control")
def paper_automation_control(request: Request, payload: AutomationControl):
    return request.app.state.automation.control(payload.enabled)


@app.post("/api/paper/automation/analyze")
def paper_automation_analyze(request: Request, payload: AutomationRequest):
    try:
        return request.app.state.automation.analyze(payload)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Decision snapshot not found") from error
    except AutomationStopped as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/voice/sessions", status_code=201)
def create_voice_session(request: Request, offer: VoiceOffer):
    try:
        return open_voice_session(request.app.state.paper.path, offer)
    except VoiceError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from None
