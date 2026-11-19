"""Evaluate the long-only SMA strategy on completed historical minute bars."""

import csv
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from typing import Literal

from pydantic import Field, FiniteFloat, model_validator

from backend.indicators import SmaCandle, SmaRequest, calculate_sma


class HistoricalBar(SmaCandle):
    open: FiniteFloat = Field(gt=0)
    close: FiniteFloat = Field(gt=0)


class BacktestRequest(SmaRequest):
    candles: list[HistoricalBar] = Field(min_length=1, max_length=10_000)
    initial_cash: Decimal = Field(default=Decimal("1000"), gt=0, max_digits=14, decimal_places=2)
    quantity: int = Field(default=1, strict=True, gt=0, le=1_000_000)

    @model_validator(mode="after")
    def validate_minute_boundaries(self) -> "BacktestRequest":
        if any((stamp := datetime.fromisoformat(bar.timestamp)).second or stamp.microsecond
               for bar in self.candles):
            raise ValueError("Historical bars must start on one-minute boundaries")
        return self


class BacktestCsvRequest(SmaRequest):
    candles: list[SmaCandle] = Field(default_factory=list, exclude=True)
    csv: str = Field(min_length=1, max_length=1_000_000)
    initial_cash: Decimal = Field(default=Decimal("1000"), gt=0, max_digits=14, decimal_places=2)
    quantity: int = Field(default=1, strict=True, gt=0, le=1_000_000)

    def to_backtest(self) -> BacktestRequest:
        reader = csv.DictReader(StringIO(self.csv.removeprefix("\ufeff")), strict=True)
        columns = ("timestamp", "open", "close")
        if not reader.fieldnames or not set(columns).issubset(reader.fieldnames):
            raise ValueError("CSV must contain timestamp, open, and close columns")
        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV column names must be unique")
        bars = []
        for row in reader:
            if len(bars) == 10_000:
                raise ValueError("Use at most 10,000 one-minute candles")
            if None in row or any(row[column] is None for column in columns):
                raise ValueError(f"Malformed CSV row near line {reader.line_num}")
            try:
                bars.append(HistoricalBar(**{column: row[column] for column in columns}, complete=True))
            except ValueError:
                raise ValueError(f"Invalid timestamp or price near CSV line {reader.line_num}") from None
        return BacktestRequest(short_window=self.short_window, long_window=self.long_window,
                               candles=bars, initial_cash=self.initial_cash, quantity=self.quantity)


def run_backtest(request: BacktestRequest) -> dict:
    """Signals use the close. An order can fill at the next completed bar's open."""
    cash = request.initial_cash
    shares = 0
    cost = Decimal(0)
    realized = Decimal(0)
    signals = []
    orders = []
    equity_curve = []
    pending = None

    for bar, point in zip(request.candles, calculate_sma(request)):
        if not bar.complete:
            continue
        opened_at = datetime.fromisoformat(bar.timestamp)
        closed_at = opened_at + timedelta(minutes=1)
        if pending is not None:
            price = Decimal(str(bar.open))
            quantity = pending["quantity"]
            amount = price * quantity
            if pending["side"] == "buy" and amount > cash:
                pending.update(status="skipped", reason="Insufficient cash at the next open")
            else:
                if pending["side"] == "buy":
                    cash -= amount
                    shares = quantity
                    cost = price
                else:
                    cash += amount
                    realized += (price - cost) * quantity
                    shares = 0
                    cost = Decimal(0)
                pending.update(status="filled", fill_at=opened_at.isoformat(), price=str(price))
            pending = None

        if point.crossover:
            side: Literal["buy", "sell"] = "buy" if point.crossover == "up" else "sell"
            signal = {"time": closed_at.isoformat(), "side": side, "short": point.short, "long": point.long}
            signals.append(signal)
            if (side == "buy" and shares) or (side == "sell" and not shares):
                signal["reason"] = "Position already open" if shares else "No position to close"
            else:
                pending = {"signal_at": signal["time"], "side": side,
                           "quantity": request.quantity if side == "buy" else shares,
                           "status": "pending"}
                orders.append(pending)

        close = Decimal(str(bar.close))
        unrealized = (close - cost) * shares
        equity_curve.append({"time": closed_at.isoformat(), "cash": str(cash), "shares": shares,
                             "realized": str(realized), "unrealized": str(unrealized),
                             "equity": str(cash + close * shares)})

    if pending is not None:
        pending.update(status="unfilled", reason="No eligible next bar in this dataset")
    ending_equity = Decimal(equity_curve[-1]["equity"]) if equity_curve else request.initial_cash
    return {"signals": signals, "orders": orders, "equity_curve": equity_curve,
            "starting_cash": str(request.initial_cash), "ending_equity": str(ending_equity),
            "return_percent": str((ending_equity - request.initial_cash) / request.initial_cash * 100)}
