# Design pipeline

Planned local request and response flow:

```text
Learner
  | enters input or selects an action
  v
Vue UI (frontend/) -- HTTP request --> FastAPI route (backend/)
                                           |
                                           v
                                      Python logic (backend/)
                                           |
                                           v
Vue UI (frontend/) <-- JSON response -- FastAPI route (backend/)
  |
  v
Learner sees the result
```

Vue displays historical candles fetched through FastAPI. The Yahoo probe can store decoded observations in SQLite. The Python aggregation layer reads one ticker and builds UTC one-minute candles from those observations. Later prompts connect those candles to the live chart and replay.

### Market observation schema

The default SQLite file is `backend/data/observations.sqlite3`. From the project root, `python -B -m backend.observations` creates its tables and index if needed. FastAPI also initializes the recorder at startup. `IST402_OBSERVATIONS_DB` selects a different database for testing.

| Table | Columns and purpose |
| --- | --- |
| `observations` | `id` is the observation identity and insertion order. `symbol` identifies the instrument. `source_time_ms` is the source time in Unix milliseconds. `received_at_utc` is the UTC receipt time. `source_json` contains the decoded provider fields as canonical JSON and has a unique constraint. |
| `observation_revisions` | `observation_id` identifies the correcting row, and `supersedes_id` identifies the earlier row for the same symbol. Both refer to `observations.id`. |

The `observations_symbol_time` index covers symbol, source time, and ID. A duplicate preserves the original ID and receipt time. Replay walks saved IDs in receipt order. Candle aggregation orders eligible quotes by source time and uses the ID to break ties. Candle completion is derived at the selected cutoff and returned with the candle, so the same stored observations can reproduce both forming and completed candles.

### One-minute aggregation

The aggregator sorts available observations by source time, then receipt ID for ties. Open and close are the first and last prices in the UTC minute, and high and low are its extrema. The six candle fields carry prices and volume. A separate completion flag indicates that the minute ended at the requested cutoff.

Late messages affect only views at or after their receipt. A correction with an explicit superseded observation ID replaces that observation for aggregation after the correction arrives. SQLite retains both source records. Distinct observations without a revision link remain separate.

Volume sums increases in the cumulative share count. A missing counter, missing baseline, gap of more than one minute, exchange date change, or counter reset leaves the affected volume unknown where increments cannot be assigned. An unchanged known counter contributes zero.

### Live updates

The FastAPI lifespan optionally starts one Yahoo worker. The worker timestamps received messages, and the backend stores them in SQLite. The WebSocket reads the same one-minute aggregation and exchange calendar rollup as history, with feed and completion metadata alongside each candle. Vite proxies the WebSocket to Vue, which applies updates by timestamp and keeps synthetic candles separate from recorded observations.

### Replay

The replay API opens SQLite read-only and selects a receipt-ordered prefix within a recorded UTC range. Each step recalculates candles with the same aggregation and exchange session rules as live mode. Vue shows the source and receipt timestamps and replaces the chart with the selected step.

### Saved indicators

Python registers each indicator type with its label, units, and calculator. The calculator receives completed candles in timestamp order and a validated positive whole-number window. An SMA averages closing prices and a rolling price range subtracts the lowest low from the highest high in its window. Both are in price units. The API aligns one value or a null warm-up gap to each input timestamp. Unfinished candles have a null value and do not advance the window.

To add another single-window indicator, register its calculator in `backend/indicators.py`. FastAPI exposes the registry and stores each named configuration in SQLite. Vue reads the catalog, saves independent settings, and shows each value for the selected candle. The short and long SMA crossover calculation uses the same registry.

### Paper account

FastAPI sends paper intents to a single Python ledger. Each accepted order records the observation watermark at submission. A newly available quote fills pending orders in submission order after checking cash and shares. Replay uses its explicit receipt step. Orders, fills, and balances remain in SQLite and share one transaction per fill.

### Paper valuation history

The simulator records cumulative realized and unrealized P&L with each fill and records completed-candle valuations for open positions. Purchases update weighted average cost. Partial sales preserve that cost for the remaining shares. Each valuation identifies its price and event so that retries preserve one entry. Vue displays the saved timeline, including unavailable prices where applicable.

### Chart analysis, paper automation, and voice

```text
Completed candle + saved paper account
  -> FastAPI freezes snapshot in SQLite
  -> Vue renders and captures chart PNG
  -> FastAPI sends snapshot and PNG to analyst and independent reviewer
  -> Python checks eligibility and stores the decision
  -> automation queues an eligible, approved paper order
  -> eligible quote triggers final checks and a SQLite fill or skip
  -> Vue displays the decision, review, and account outcome

Selected decision ID + WebRTC offer
  -> FastAPI reads the saved decision and linked paper outcome
  -> GPT-Live receives the read-only summary and returns the answer
  -> browser completes WebRTC and plays the remote audio
```

`backend/decisions.py` stores the frozen evidence and results. `frontend/decision-capture.mjs` supplies the chart PNG to both manual questions and automation. `backend/automation.py` tracks completed candles and run generations, while `backend/paper.py` owns fill eligibility and the ledger transaction. The deduplication key combines account, strategy, symbol, timeframe, and candle. `backend/voice.py` reads the saved evidence for the selected decision. `frontend/decision-voice.mjs` owns the microphone, peer connection, and playback lifecycle.
