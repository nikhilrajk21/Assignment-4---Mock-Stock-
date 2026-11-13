"""Launch FastAPI with a recording Decisions provider for the chart smoke test."""
import base64
import io
import json
from pathlib import Path
import sys

from PIL import Image
import uvicorn

import backend.decisions
import backend.chart_analysis as chart_analysis
from backend.decision_provider import ProviderError
from backend.main import app

directory = Path(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 else "chart"


def record_provider(snapshot, questions, *, image_data=None, **kwargs):
    if (directory / "provider-fail").exists():
        raise ProviderError("provider_error", "Controlled provider failure.")
    assert image_data.startswith("data:image/png;base64,")
    pixels = base64.b64decode(image_data.split(",", 1)[1], validate=True)
    with Image.open(io.BytesIO(pixels)) as image:
        image.load()
        assert image.format == "PNG" and image.width >= 960 and image.height >= 540
        assert len(image.getcolors(500_000)) > 10
    if mode == "automation":
        minute = snapshot["timestamp"][11:16]
        if questions[0]["name"] == "review":
            verdict = "unsupported_signal" if minute == "15:08" else "accept"
            return {"model": "review-fixture", "answers": [
                {"name": "review", "type": "choice", "choice": verdict}
            ]}
        action = {"15:04": "buy", "15:06": "sell", "15:07": "close", "15:08": "buy"}.get(
            minute, "hold" if snapshot["shares"] else "wait"
        )
        return {"model": "analyst-fixture", "answers": [
            {"name": name, "type": "choice", "choice": choice}
            for name, choice in {
                "action": action, "crossover": snapshot["crossover"] or "none", "evidence": "sufficient"
            }.items()
        ]}
    if questions[0]["name"] == "review":
        first = json.loads((directory / "provider-record.json").read_text(encoding="utf-8"))
        assert snapshot["id"] == first["snapshot"]["id"] and image_data == first["image_data"]
        assert snapshot["analyst_proposal"] == "buy" and len(snapshot["analyst_answers"]) == 3
        return {"model": "review-fixture", "answers": [
            {"name": "review", "type": "choice", "choice": "accept"}
        ]}
    choices = {"action": "buy", "crossover": "up", "evidence": "sufficient"}
    assert [question["name"] for question in questions] == list(choices)
    (directory / "provider-record.json").write_text(json.dumps({
        "snapshot": snapshot, "questions": questions, "image_data": image_data,
    }), encoding="utf-8")
    return {"model": "fixture", "answers": [
        {"name": name, "type": "choice", "choice": choice} for name, choice in choices.items()
    ]}



if mode == "history":
    def fake_history(symbol, cutoff):
        bars = [{"timestamp": f"2026-11-09T{14 + (30+5*i)//60:02d}:{(30+5*i)%60:02d}:00Z", "open":100+i, "high":102+i, "low":99+i, "close":101+i} for i in range(12)]
        complete = {"complete": True, "observed": 1, "expected": 1}
        session = {"date":"2026-11-09", "market_open":"2026-11-09T14:30:00Z", "market_close":"2026-11-09T21:00:00Z", "regular":complete, "premarket":complete, "postmarket":complete}
        return {"symbol":symbol,"source":"Synthetic history fixture","interval":"5m","bars":bars,
                "coverage":{"sessions":[session],"complete":True}, "reference_price":100,
                "last_price":112,"change_percent":12,"large_move":True,"comparables":[],
                "provenance":"Synthetic fixture", "limitations":[], "error":None}
    def fake_provider(context, questions, *, image_data=None, additional_images=None, **kwargs):
        assert [q["name"] for q in questions] == ["direction", "clarity"]
        assert not ({"candles","cash","shares","crossover","indicator_points"} & context.keys())
        assert len(additional_images) == 1
        for item in (image_data, additional_images[0]):
            data = base64.b64decode(item.split(",",1)[1], validate=True)
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                assert image.width >= 960 and image.height >= 540 and len(image.getcolors(500000)) > 10
        count_file = directory / "history-count"
        count = int(count_file.read_text()) if count_file.exists() else 0
        count_file.write_text(str(count+1))
        (directory / f"history-provider-{count}.json").write_text(json.dumps({"context":context,"current":image_data,"history":additional_images[0]}), encoding="utf-8")
        return {"model":"fixture","answers":[{"name":"direction","type":"choice","choice":["long","short","wait"][count]}, {"name":"clarity","type":"choice","choice":"clear"}]}
    class FixtureStore:
        def __init__(self, store):
            self.store = store
        def snapshot(self, snapshot_id):
            result = self.store.snapshot(snapshot_id)
            if result:
                result["market_data_label"] = "Recorded Yahoo Finance"
                result["replay"] = None
            return result
        def __getattr__(self, name):
            return getattr(self.store,name)
    original_analyze = chart_analysis.analyze_chart
    def analyze_fixture(store, payload):
        return original_analyze(FixtureStore(store), payload)
    chart_analysis.fetch_chart_history = fake_history
    chart_analysis.ask_decisions = fake_provider
    chart_analysis._source_freshness = lambda *_: {"status":"fresh","age_seconds":0,"source_time":"2026-11-09T15:05:00Z"}
    chart_analysis.analyze_chart = analyze_fixture

backend.decisions.ask_decisions = record_provider
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
