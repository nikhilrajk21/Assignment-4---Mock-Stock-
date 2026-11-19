"""Classroom chart assessment using the existing Decisions provider."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import TYPE_CHECKING

from backend.decision_provider import ProviderError, ask_decisions

if TYPE_CHECKING:
    from backend.decisions import DecisionRequest


def rule_question() -> dict:
    return {
        "type": "choice",
        "name": "chart_signal",
        "instructions": (
            "Assess only the last two completed visible one-minute candles in the frozen chart. "
            "Choose wait if either candle is missing or unclear or if the supplied metadata says the evidence is stale."
        ),
        "choices": [
            {"value": "long", "description": "Both completed candles close above their own open."},
            {"value": "short", "description": "Both completed candles close below their own open."},
            {"value": "wait", "description": "Directions differ, either candle is flat, or evidence is insufficient or stale."},
        ],
    }


def parse_assessment(result: dict, question: dict) -> dict:
    answers = result["answers"]
    allowed = {item["value"] for item in question["choices"]}
    if len(answers) != 1 or not isinstance(answers[0], dict):
        raise ProviderError("malformed_answer", "Expected exactly one chart assessment answer.")
    answer = answers[0]
    choice = answer.get("choice")
    if (answer.get("name") != question["name"] or answer.get("type") != "choice"
            or not isinstance(choice, str) or choice not in allowed):
        raise ProviderError("malformed_answer", "The chart assessment choice was not accepted.")
    probabilities = answer.get("probabilities")
    if probabilities is None:
        probabilities = []
    if not isinstance(probabilities, list):
        raise ProviderError("malformed_answer", "Chart assessment probabilities must be a list.")
    by_choice = {}
    for entry in probabilities:
        if not isinstance(entry, dict):
            raise ProviderError("malformed_answer", "Invalid chart assessment probability entry.")
        value, probability = entry.get("value"), entry.get("probability")
        if (not isinstance(value, str) or value not in allowed or value in by_choice
                or type(probability) not in (int, float) or not 0 <= probability <= 1 or not isfinite(probability)):
            raise ProviderError("malformed_answer", "Invalid chart assessment probability entry.")
        by_choice[value] = probability
    return {"choice": choice, "probability": by_choice.get(choice), "probabilities": by_choice, "model": result["model"]}


def prepare_assessment(snapshot: dict, capture: DecisionRequest) -> dict:
    from backend.decisions import ChartCaptureError, validate_chart

    if capture.image_data is None or capture.chart_start is None or capture.chart_end is None:
        raise ChartCaptureError("A frozen chart PNG and its time range are required.")
    if snapshot["timeframe"] != "1m":
        raise ChartCaptureError("Select the one-minute chart for this assessment rule.")
    validate_chart(snapshot, capture.image_data, capture.chart_start, capture.chart_end)
    metadata = {key: snapshot[key] for key in ("id", "symbol", "timeframe", "timestamp", "cutoff", "market_data_label")}
    metadata["is_stale"] = datetime.fromisoformat(snapshot["closed_at"]) > datetime.fromisoformat(snapshot["cutoff"])
    metadata.update(chart_start=capture.chart_start.isoformat(), chart_end=capture.chart_end.isoformat())
    return {"metadata": metadata, "image": capture.image_data}


def assess_prepared(prepared: dict) -> dict:
    question = rule_question()
    metadata = prepared["metadata"]
    result = ask_decisions(metadata, [question], image_data=prepared["image"])
    return {"snapshot": metadata, **parse_assessment(result, question)}


def assess_chart(snapshot: dict, capture: DecisionRequest) -> dict:
    return assess_prepared(prepare_assessment(snapshot, capture))
