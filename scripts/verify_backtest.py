"""Check the historical strategy against a hand-worked trade."""

from decimal import Decimal

from backend.backtest import BacktestRequest, run_backtest


def main() -> None:
    closes = [13, 10, 7, 13, 19, 7, 1, 2]
    candles = [
        {"timestamp": f"2026-11-09T15:0{i}:00Z", "open": {5: 10, 7: 8}.get(i, close),
         "close": close, "complete": True}
        for i, close in enumerate(closes)
    ]
    request = BacktestRequest(
        short_window=2, long_window=3, candles=candles, initial_cash=100, quantity=2
    )
    result = run_backtest(request)
    assert [(row["side"], row["short"], row["long"]) for row in result["signals"]] == [
        ("buy", 16, 13), ("sell", 4, 9),
    ]
    assert [Decimal(row["price"]) for row in result["orders"]] == [10, 8]
    assert Decimal(result["equity_curve"][5]["unrealized"]) == -6
    assert Decimal(result["equity_curve"][-1]["realized"]) == -4
    assert Decimal(result["ending_equity"]) == 96

    forming = request.candles[-1].model_copy(update={"complete": False})
    prefix = request.model_copy(update={"candles": [*request.candles[:-1], forming]})
    earlier = run_backtest(prefix)
    assert earlier["equity_curve"] == result["equity_curve"][:-1]
    assert earlier["orders"][-1]["status"] == "unfilled"
    low_cash = request.model_copy(update={"initial_cash": Decimal(1)})
    assert run_backtest(low_cash)["orders"][0]["status"] == "skipped"
    print("PASS: SMA crosses, next-open fills, equity, forming candle, and cash limit")


if __name__ == "__main__":
    main()
