"""Deterministic checks for the chart-history corporate-action boundary."""
from datetime import datetime, timezone

import pandas as pd

from backend.chart_history import fetch_chart_history


def fixture(action_date=None, action_type=None, unavailable=False):
    rows = []
    days = ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
    for day in days:
        times = pd.date_range(day + " 04:00", periods=192, freq="5min", tz="America/New_York")
        for index, stamp in enumerate(times):
            close = 110 if day in ("2026-11-05", "2026-11-10") and index == 191 else 100
            rows.append((stamp, 100, max(100, close), min(100, close), close))
    frame = pd.DataFrame(rows, columns=["timestamp", "Open", "High", "Low", "Close"]).set_index("timestamp")
    actions = pd.DataFrame(
        [{"Dividends": 0.25, "Stock Splits": 0}],
        index=[pd.Timestamp("2026-07-01", tz="America/New_York")],
    )
    if action_date:
        actions.loc[pd.Timestamp(action_date, tz="America/New_York")] = {
            "Dividends": 0.25 if action_type == "dividend" else 0,
            "Stock Splits": 2 if action_type == "split" else 0,
        }
    if unavailable:
        actions = pd.DataFrame()

    class Ticker:
        def __init__(self, symbol):
            pass

        def history(self, **kwargs):
            return frame

        @property
        def actions(self):
            return actions

    return fetch_chart_history(
        "AAPL", datetime(2026, 11, 11, 2, tzinfo=timezone.utc), ticker_factory=Ticker
    )


def main():
    clear = fixture()
    assert clear["error"] is None and len(clear["comparables"]) == 1
    assert clear["corporate_actions"]["affected_dates"] == []
    assert fixture("2026-11-10", "dividend")["error"]
    assert fixture("2026-11-09", "split")["error"]
    assert not fixture("2026-11-04", "split")["comparables"]
    assert not fixture("2026-11-06", "dividend")["comparables"]
    assert fixture(unavailable=True)["error"].startswith("Corporate action history")
    outside = fixture("2026-10-01", "dividend")
    assert outside["error"] is None and len(outside["comparables"]) == 1
    print("PASS: no action, dividend, split, unavailable feed, and outside-period action")


if __name__ == "__main__":
    main()
