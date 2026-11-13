"""Extensible indicators computed from completed chart candles."""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, Field, FiniteFloat, StrictBool, field_validator, model_validator

Window = Annotated[int, Field(strict=True, gt=0, le=9_007_199_254_740_991)]
Crossover = Literal["up", "down"]


class SmaCandle(BaseModel):
    timestamp: str
    close: FiniteFloat
    complete: StrictBool

    @field_validator("timestamp")
    @classmethod
    def timestamp_has_timezone(cls, value: str) -> str:
        if datetime.fromisoformat(value).utcoffset() is None:
            raise ValueError("Candle timestamps must include a timezone")
        return value


def validate_order(candles: list[SmaCandle]) -> None:
    timestamps = [datetime.fromisoformat(candle.timestamp) for candle in candles]
    if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
        raise ValueError("Candles must have unique timestamps in ascending order")


class SmaRequest(BaseModel):
    short_window: Window
    long_window: Window
    candles: list[SmaCandle]

    @model_validator(mode="after")
    def validate_settings_and_order(self) -> "SmaRequest":
        if self.short_window >= self.long_window:
            raise ValueError("The short window must be smaller than the long window")
        validate_order(self.candles)
        return self


class SmaPoint(BaseModel):
    timestamp: str
    short: float | None = None
    long: float | None = None
    crossover: Crossover | None = None


class IndicatorCandle(SmaCandle):
    high: FiniteFloat
    low: FiniteFloat

    @model_validator(mode="after")
    def validate_range(self) -> "IndicatorCandle":
        if self.high < self.low:
            raise ValueError("Candle high must be at least its low")
        return self


class IndicatorEvaluation(BaseModel):
    candles: list[IndicatorCandle]

    @model_validator(mode="after")
    def validate_candle_order(self) -> "IndicatorEvaluation":
        validate_order(self.candles)
        return self


class IndicatorPoint(BaseModel):
    timestamp: str
    value: float | None


def _averages(candles: list[SmaCandle], window: int) -> list[Fraction | None]:
    closes: deque[Fraction] = deque()
    total = Fraction()
    result = []
    for candle in candles:
        close = Fraction(str(candle.close))
        closes.append(close)
        total += close
        if len(closes) > window:
            total -= closes.popleft()
        result.append(total / window if len(closes) == window else None)
    return result


def _ranges(candles: list[SmaCandle], window: int) -> list[Fraction | None]:
    highs: deque[tuple[int, Fraction]] = deque()
    lows: deque[tuple[int, Fraction]] = deque()
    result = []
    for index, candle in enumerate(candles):
        if not isinstance(candle, IndicatorCandle):
            raise ValueError("Rolling range requires highs and lows")
        high = Fraction(str(candle.high))
        low = Fraction(str(candle.low))
        while highs and highs[-1][1] <= high:
            highs.pop()
        while lows and lows[-1][1] >= low:
            lows.pop()
        highs.append((index, high))
        lows.append((index, low))
        if highs[0][0] <= index - window:
            highs.popleft()
        if lows[0][0] <= index - window:
            lows.popleft()
        result.append(highs[0][1] - lows[0][1] if index + 1 >= window else None)
    return result


@dataclass(frozen=True)
class IndicatorType:
    label: str
    units: str
    calculate: Callable[[list[SmaCandle], int], list[Fraction | None]]


# Add an indicator by registering a calculator that accepts completed candles
# and a validated window and returns one value or warm-up gap per input candle.
INDICATOR_TYPES = {
    "sma": IndicatorType("Simple moving average", "price", _averages),
    "range": IndicatorType("Rolling price range", "price", _ranges),
}


def indicator_catalog() -> list[dict]:
    return [
        {
            "type": kind,
            "label": definition.label,
            "units": definition.units,
            "settings": {"window": {"type": "integer", "minimum": 1}},
        }
        for kind, definition in INDICATOR_TYPES.items()
    ]


def indicator_values(
    kind: str, candles: list[SmaCandle], window: int
) -> list[Fraction | None]:
    """Place values on their completed candle and preserve gaps at other times."""
    completed = [candle for candle in candles if candle.complete]
    values = iter(INDICATOR_TYPES[kind].calculate(completed, window))
    return [next(values) if candle.complete else None for candle in candles]


def evaluate_indicator(kind: str, candles: list[IndicatorCandle], window: int) -> list[IndicatorPoint]:
    return [
        IndicatorPoint(timestamp=candle.timestamp, value=float(value) if value is not None else None)
        for candle, value in zip(candles, indicator_values(kind, candles, window))
    ]


def calculate_sma(request: SmaRequest) -> list[SmaPoint]:
    """Return two shared SMA calculations and compare them before float rounding."""
    short_values = indicator_values("sma", request.candles, request.short_window)
    long_values = indicator_values("sma", request.candles, request.long_window)
    side = 0
    points = []
    for candle, short, long in zip(request.candles, short_values, long_values):
        point = SmaPoint(
            timestamp=candle.timestamp,
            short=float(short) if short is not None else None,
            long=float(long) if long is not None else None,
        )
        if short is not None and long is not None:
            new_side = (short > long) - (short < long)
            if new_side:
                if side and new_side != side:
                    point.crossover = "up" if new_side > 0 else "down"
                side = new_side
        points.append(point)
    return points
