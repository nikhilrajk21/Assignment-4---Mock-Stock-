"""Verify Prompt 10 using disposable market and account records."""
import argparse
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.decision_provider import ProviderError
from backend.main import app
from backend.observations import ObservationStore


def ledger(path):
    with closing(sqlite3.connect(path)) as db:
        return [
            db.execute(sql).fetchall()
            for sql in (
                "SELECT id, cash FROM paper_account",
                "SELECT * FROM paper_positions",
                "SELECT * FROM paper_orders",
                "SELECT * FROM paper_fills",
            )
        ]


def verify(live: bool) -> None:
    with TemporaryDirectory(prefix="ist402-decisions-") as directory:
        path = Path(directory) / "decisions.sqlite3"
        store = ObservationStore(path)
        for minute, close in enumerate((13, 10, 7, 13, 19, 7, 1)):
            stamp = datetime.fromisoformat(f"2026-11-09T15:{minute:02d}:05+00:00")
            store.record({"id": "AAPL", "time": int(stamp.timestamp() * 1000), "price": close}, stamp)
        env = {"IST402_OBSERVATIONS_DB": str(path), "IST402_YAHOO_LIVE": "0"}
        with patch.dict("os.environ", env), TestClient(app) as client:
            before = ledger(path)
            response = client.post("/api/decision-snapshots", json={
                "symbol": "AAPL", "timeframe": "1m", "source": "sample" if live else "recorded",
                "timestamp": "2026-11-09T14:32:00Z" if live else "2026-11-09T15:04:00Z",
                "short_window": 2, "long_window": 3, "order_size": 1,
            })
            assert response.status_code in (200, 201), response.text
            snapshot = response.json()
            assert snapshot["cash"] == 1000 and snapshot["shares"] == 0
            if not live:
                assert snapshot["close"] == 19 and snapshot["short_sma"] == 16
                assert snapshot["long_sma"] == 13 and snapshot["crossover"] == "up"
                assert snapshot["eligible"] is True

            def submit():
                response = client.post("/api/decisions", json={"snapshot_id": snapshot["id"]})
                assert response.status_code in (200, 201), response.text
                result = response.json()
                saved = client.get("/api/decisions/" + str(result["id"]))
                assert saved.status_code == 200, saved.text
                assert saved.json()["snapshot"] == snapshot
                assert all(saved.json()[key] == value for key, value in result.items())
                assert ledger(path) == before
                return result

            if live:
                result = submit()
                print("LIVE provider, synthetic fixture:", result["model"], result["status"],
                      result["proposal"], result["explanation"], flush=True)
                assert result["proposal"] in {"buy", "sell", "hold", "wait", "close"}, result
                assert not result["eligible"], result
            else:
                response = {"model": "test-double", "answers": [
                    {"type": "choice", "name": "action", "choice": "buy"}
                ]}
                def verdict(choice):
                    return {"model": "review-fixture", "answers": [
                        {"type": "choice", "name": "review", "choice": choice}
                    ]}

                with patch("backend.decisions.ask_decisions", side_effect=[response, verdict("accept")]) as provider:
                    result = submit()
                    assert result["proposal"] == "buy" and result["eligible"], result
                    assert result["review"]["verdict"] == "accept"
                    analyst, reviewer = [call.args for call in provider.call_args_list]
                    assert analyst[0] == snapshot and analyst[1][0]["name"] == "action"
                    assert reviewer[0]["id"] == snapshot["id"] and reviewer[0]["analyst_proposal"] == "buy"
                    assert reviewer[1][0]["name"] == "review"
                with patch("backend.decisions.ask_decisions",
                           side_effect=[response, verdict("unsupported_signal")]):
                    result = submit()
                    assert result["status"] == "review_rejected" and not result["eligible"], result
                original = snapshot
                costly = client.post("/api/decision-snapshots", json={
                    "source": "recorded", "timestamp": "2026-11-09T15:04:00Z", "order_size": 100,
                })
                assert costly.status_code == 201, costly.text
                snapshot = costly.json()
                with patch("backend.decisions.ask_decisions", side_effect=[response, verdict("accept")]):
                    result = submit()
                    assert result["status"] == "invalid_action" and not result["eligible"], result
                    assert result["review"]["verdict"] == "accept"
                snapshot = original
                with patch("backend.decisions.ask_decisions",
                           side_effect=ProviderError("timeout", "Injected timeout")):
                    result = submit()
                    assert result["status"] == "timeout" and not result["eligible"], result
                with patch("backend.decisions.ask_decisions",
                           return_value={"model": "test-double", "answers": []}):
                    result = submit()
                    assert result["status"] == "malformed_answer" and not result["eligible"], result
                print("PASS: immutable snapshot, stored buy, injected timeout, malformed answer, unchanged ledger")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    verify(parser.parse_args().live)
