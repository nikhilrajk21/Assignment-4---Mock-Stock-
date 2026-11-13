"""Later-retrieved Yahoo history for chart reading, never receipt-time replay."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from pandas_market_calendars import get_calendar

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
INTERVAL = timedelta(minutes=5)


def _text(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _coverage(bars, start, end):
    expected = int((end - start).total_seconds() // 300)
    observed = sum(start <= item["start"] < end for item in bars)
    return {"expected": expected, "observed": observed, "complete": observed == expected}


def _session(bars, day, opened, closed, cutoff):
    local_midnight = datetime.combine(day, datetime.min.time(), NEW_YORK)
    pre = local_midnight + timedelta(hours=4)
    post = local_midnight + timedelta(hours=20)
    pre, post = pre.astimezone(UTC), post.astimezone(UTC)
    visible = [item for item in bars if pre <= item["start"] < post and item["start"] + INTERVAL <= cutoff]
    regular = [item for item in visible if opened <= item["start"] < closed]
    completed = cutoff >= closed
    regular_coverage = _coverage(regular, opened, closed)
    regular_coverage["complete"] = completed and regular_coverage["complete"]
    pre_coverage = _coverage(visible, pre, opened)
    post_coverage = _coverage(visible, closed, post)
    post_coverage["complete"] = cutoff >= post and post_coverage["complete"]
    return {
        "date": day.isoformat(), "market_open": _text(opened), "market_close": _text(closed),
        "regular": regular_coverage, "premarket": pre_coverage, "postmarket": post_coverage,
        "_bars": visible, "_regular": regular,
    }


def fetch_chart_history(symbol: str, cutoff: datetime, *, ticker_factory=yf.Ticker) -> dict:
    """Return cutoff-bounded 5-minute bars, coverage and comparable completed sessions.

    Yahoo bars are later-retrieved and potentially revised, not proof of what was
    known at a replay step. Comparables match the same-direction two-session
    return within two percentage points. They describe historical outcomes,
    not predictions or proof of a recurring pattern.
    """
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must include a timezone")
    cutoff = cutoff.astimezone(UTC)
    result = {
        "symbol": symbol, "cutoff": _text(cutoff), "retrieved_at": _text(datetime.now(UTC)),
        "source": "Yahoo Finance via yfinance", "interval": "5m",
        "provenance": "Later-retrieved historical bars may be revised and are not receipt-time replay data.",
        "bars": [], "coverage": {"sessions": [], "complete": False},
        "reference_price": None, "last_price": None, "change_percent": None,
        "large_move": None, "comparables": [], "error": None,
    }
    try:
        first = (cutoff - timedelta(days=55)).date()
        last = (cutoff + timedelta(days=1)).date()
        ticker = ticker_factory(symbol)
        frame = ticker.history(
            start=first.isoformat(), end=last.isoformat(), interval="5m", prepost=True,
            auto_adjust=False, actions=False, raise_errors=True,
        )
        actions = ticker.actions
        if (actions is None or actions.empty
                or not {"Dividends", "Stock Splits"}.issubset(actions.columns)):
            result["error"] = "Corporate action history was unavailable or could not be verified."
            return result
        action_dates = set()
        for timestamp, row in actions.iterrows():
            action_day = timestamp.date()
            if first <= action_day <= cutoff.astimezone(NEW_YORK).date():
                dividend = row.get("Dividends", 0)
                split = row.get("Stock Splits", 0)
                if (not pd.isna(dividend) and float(dividend) != 0) or (
                    not pd.isna(split) and float(split) != 0
                ):
                    action_dates.add(action_day.isoformat())
        result["corporate_actions"] = {
            "source": "Yahoo Finance actions",
            "affected_dates": sorted(action_dates),
            "policy": "Unadjusted returns exclude windows containing a dividend or split.",
        }
        schedule = get_calendar("NASDAQ").schedule(start_date=first, end_date=last)
        raw = {}
        for timestamp, row in frame.iterrows():
            stamp = timestamp.to_pydatetime()
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                continue
            stamp = stamp.astimezone(UTC)
            if stamp + INTERVAL > cutoff:
                continue
            values = [float(row[name]) for name in ("Open", "High", "Low", "Close")]
            if not all(math.isfinite(value) and value > 0 for value in values):
                continue
            if stamp.second or stamp.microsecond or stamp.minute % 5:
                continue
            raw[stamp] = {"start": stamp, "open": values[0], "high": values[1],
                          "low": values[2], "close": values[3]}
        bars = sorted(raw.values(), key=lambda item: item["start"])
        sessions = []
        for row in schedule.itertuples():
            opened, closed = row.market_open.to_pydatetime(), row.market_close.to_pydatetime()
            if opened >= cutoff:
                continue
            sessions.append(_session(bars, opened.astimezone(NEW_YORK).date(), opened, closed, cutoff))
        finished = [session for session in sessions if datetime.fromisoformat(session["market_close"]) <= cutoff]
        selected = finished[-2:]
        if not selected or not selected[-1]["regular"]["complete"]:
            selected = []
        elif len(selected) == 2 and not selected[0]["regular"]["complete"]:
            selected = selected[-1:]
        if not selected:
            result["error"] = "No complete regular trading session is available before the cutoff."
            return result
        result["coverage"]["sessions"] = [
            {key: value for key, value in session.items() if not key.startswith("_")}
            for session in selected
        ]
        result["coverage"]["complete"] = len(selected) == 2
        result["coverage"]["note"] = (
            "Two complete regular sessions." if len(selected) == 2
            else "One complete regular session; a second complete session was unavailable."
        )
        if any(session["date"] in action_dates for session in selected):
            result["error"] = "The selected period contains a dividend or stock split; unadjusted returns are unavailable."
            result["coverage"]["complete"] = False
            return result
        visible = [bar for session in selected for bar in session["_bars"]]
        result["bars"] = [
            {"timestamp": _text(bar["start"]), "open": bar["open"], "high": bar["high"],
             "low": bar["low"], "close": bar["close"]}
            for bar in visible
        ]
        first_bar = selected[0]["_bars"][0]
        last_bar = selected[-1]["_bars"][-1]
        reference = first_bar["open"]
        last_price = last_bar["close"]
        result["reference_timestamp"] = _text(first_bar["start"])
        result["last_timestamp"] = _text(last_bar["start"])
        result["reference_note"] = (
            "First available five-minute bar of the selected period, including premarket when available. "
            "Check session coverage for gaps before this bar."
        )
        change_decimal = (Decimal(str(last_price)) / Decimal(str(reference)) - 1) * 100
        change = float(change_decimal)
        result.update(reference_price=reference, last_price=last_price, change_percent=change,
                      large_move=abs(change_decimal) > 10)
        if len(selected) == 2 and all(
            session["premarket"]["complete"] and session["postmarket"]["complete"]
            for session in selected
        ):
            previous = [session for session in finished if session["date"] < selected[0]["date"]]
            for index in range(1, len(previous) - 1):
                older, newer, outcome = previous[index - 1:index + 2]
                if any(session["date"] in action_dates for session in (older, newer, outcome)):
                    continue
                if not all(session["regular"]["complete"] for session in (older, newer, outcome)):
                    continue
                if not all(
                    session["premarket"]["complete"] and session["postmarket"]["complete"]
                    for session in (older, newer)
                ):
                    continue
                old_first = older["_bars"][0]
                old_last = newer["_bars"][-1]
                old_reference = old_first["open"]
                old_close = old_last["close"]
                old_change = float((Decimal(str(old_close)) / Decimal(str(old_reference)) - 1) * 100)
                if change * old_change > 0 and abs(old_change - change) <= 2:
                    outcome_first = outcome["_regular"][0]
                    outcome_last = outcome["_regular"][-1]
                    outcome_change = float((Decimal(str(outcome_last["close"])) / Decimal(str(outcome_first["open"])) - 1) * 100)
                    result["comparables"].append({
                        "start": older["date"], "end": newer["date"],
                        "reference_timestamp": _text(old_first["start"]),
                        "last_timestamp": _text(old_last["start"]),
                        "change_percent": old_change,
                        "difference_percentage_points": abs(old_change - change),
                        "outcome": {
                            "session": outcome["date"],
                            "start_timestamp": _text(outcome_first["start"]),
                            "end_timestamp": _text(outcome_last["start"]),
                            "reference_price": outcome_first["open"],
                            "closing_price": outcome_last["close"],
                            "change_percent": outcome_change,
                        },
                    })
            result["comparables"] = sorted(
                result["comparables"], key=lambda match: match["difference_percentage_points"]
            )[:3]
        result["limitations"] = [
            "Five-minute historical bars can be revised and can omit provider data.",
            "Periods containing listed dividends or splits are excluded; Yahoo action records can be revised.",
            "Comparable moves use two-session return within two percentage points; subsequent regular-session results are not predictive.",
        ]
    except Exception:
        result["error"] = "Yahoo historical data could not be retrieved or interpreted."
    return result
