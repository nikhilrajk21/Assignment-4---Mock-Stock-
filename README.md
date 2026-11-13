# Assignment 4: Financial Knowledge and Market Understanding

This local application is for learners who want to build financial knowledge and better understand markets. The initial goal is to help learners explore financial concepts and relate them to how markets work. Learners can inspect synthetic or recorded AAPL candles, compare indicators, replay a session, and follow decisions and trades in a simulated paper account.

## Stack and prerequisites

Reuse Python 3.12.6 with FastAPI 0.104.1 and Uvicorn 0.24.0. The frontend uses Vue 3.5.27 and Vite 7.3.1. Node.js 24.20.0 and npm 11.19.0 were verified.

## Running locally

From the project root in PowerShell 7, restore packages as needed with `python -m pip install -r backend/requirements.txt` in the existing Python environment and `npm.cmd --prefix frontend ci`. With ports 8000 and 5173 free, run:

```powershell
pwsh -NoProfile -File .\scripts\check-proxy.ps1 -LeaveRunning
```

This starts both services, checks the proxy, and leaves the services running. Open [the Vue frontend](http://127.0.0.1:5173/) to see the candle chart, aligned volume, and candle inspector.

To stop both services, run the `Stop-Process -Id` command printed by the script with the process IDs for that run.

For a repeatable HTTP check that stops both services when it finishes, omit `-LeaveRunning`.

### Start or stop one service

Run these PowerShell commands from the project root. Start only the service whose port is free. The returned process object gives you the ID to use when stopping it.

```powershell
# FastAPI on 127.0.0.1:8000
$backend = Start-Process -FilePath (Get-Command python).Source -ArgumentList '-B','-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru

# Vue on 127.0.0.1:5173
$frontend = Start-Process -FilePath (Get-Command node).Source -ArgumentList 'node_modules/vite/bin/vite.js' -WorkingDirectory (Join-Path (Get-Location).Path 'frontend') -WindowStyle Hidden -PassThru
```

If you started both with the script above, use the backend or frontend PID it printed in place of `$backend.Id` or `$frontend.Id`.

```powershell
# Stop FastAPI, then check the proxy while Vue is still running
Stop-Process -Id $backend.Id
Invoke-WebRequest -Uri 'http://127.0.0.1:5173/api/health' -SkipHttpErrorCheck

# Stop Vue when finished
Stop-Process -Id $frontend.Id
```

The proxy returned HTTP 500 with an empty body after FastAPI stopped. To restore the connection while Vue is running, rerun the FastAPI start command and check the proxy again. Expect HTTP 200 with `{"status":"ok"}`.

## Record market observations

Initialize the local SQLite database and capture one AAPL observation from the project root:

```powershell
python -B -m backend.observations
python -B -m backend.yahoo_probe AAPL --timeout 25 --database backend/data/observations.sqlite3
```

The database is `backend/data/observations.sqlite3`. The live probe uses yfinance 1.8.0. The recorder compares decoded source fields as canonical JSON. An exact repeat keeps the first row and its receipt time, even when JSON keys arrive in a different order. A distinct message at the same source time gets a separate row. The observed Yahoo payload provides no explicit revision link. Read each ID once, in ID order for replay or source-time order to reconstruct market time.

## Candle timeframes

The history route serves the synthetic AAPL fixture. Use `GET /api/history?timeframe=5m` for a five-minute view. Supported timeframes are `1m`, `5m`, `15m`, `1h`, and `1d`. Append `include_metadata=true` to see elapsed and covered minutes separately from the candle data. An optional UTC `as_of` limits the fixture to minutes completed by that time.

Install the calendar package in the existing Python environment with `python -m pip install pandas-market-calendars==5.6.0` if needed. The Nasdaq calendar supplies the regular session open and close, including early closes and UTC offset changes.

## Live chart

Enable the Yahoo Finance feed before starting the backend with `$env:IST402_YAHOO_LIVE = '1'` in PowerShell. Open the Vue page to see AAPL, choose a timeframe, and inspect a candle. The chart starts with synthetic data until it has stored Nasdaq regular-session candles. The Yahoo status and the age of the most recent source observation appear above the chart. Set `IST402_OBSERVATIONS_DB` before starting FastAPI to use a different local SQLite file.

Run the repeatable Edge test from the project root with `node frontend/scripts/smoke-live.mjs`. It launches both services on isolated ports, uses a temporary database and simulated upstream updates, and shuts down the test processes. Append `--live` for the separate live Yahoo check. That check requires a matching quote during the regular trading session.

## Replay a recording

With the Yahoo feed disabled, open Vue and choose **Replay recorded session**. Select a stored symbol and session, adjust the UTC range if needed, and choose **Start replay**. Use **Next observation** and **Previous observation** to follow the original receipt order. The chart shows both source and receipt time. Select **Return to market chart** to leave replay.

Run the disposable replay browser check with `node frontend/scripts/smoke-live.mjs --replay`.

## Paper account

The local simulated account starts with $1,000. Buy and Sell take whole-share quantities. Close exits the position. Orders wait for the next eligible quote after submission and pay zero fees. In replay, advance the recording to make a new quote eligible. The simulator rechecks cash and shares at the fill and commits the fill and balance changes in one SQLite transaction. A retry uses the original request ID.

Run the disposable account check with `node frontend/scripts/smoke-live.mjs --paper`.

## Chart decisions, automation, and voice

In the chart, select a completed candle and choose **Ask about chart**. FastAPI saves the frozen snapshot and captured chart, records the analyst's proposal and the reviewer's verdict, and independently validates the result. A manual question creates no order.

The automation panel controls the simulated account. Set the buy and partial sale quantities and start automation to analyze each newly completed candle. An approved, validated order waits for an eligible quote. A decision more than five minutes old cannot fill. Stop automation to cancel pending automated orders and prevent an in-flight model reply from submitting one. The history links the chart decision to the review, fill or skip, and resulting account balance.

Select a saved decision and start voice to discuss the recorded findings and account outcome. Allow microphone access and use **End voice** to release it. FastAPI uses its `OPENAI_API_KEY` environment variable for live model requests. Set it in the project-root .env file or in the environment that starts FastAPI. A value already present in the process environment takes precedence. Restart FastAPI after changing the file.

## Workstation SmokeTest

From the project root, run:

```powershell
node frontend/scripts/smoke-workstation.mjs
```

The test runs FastAPI and Vue on isolated ports with disposable SQLite accounts and controlled market and model replies. It opens a real browser, checks SMA editing, chart capture and provider failure, automated paper fills and stop behavior, and voice startup failure. It stops the browser and services and exits with a nonzero status on failure. It uses Edge on Windows and Playwright Chromium on Linux. The GitHub Actions workflow uses the same command on pushes and pull requests.

Live checks run separately. Use `node frontend/scripts/smoke-live.mjs --live` during a Nasdaq regular session for the live Yahoo check. Use `python -B -m scripts.verify_decisions --live` and `node frontend/scripts/smoke-live.mjs --chart-decision --live` with a working backend key. To verify live speech, open localhost with a physical microphone and speaker. Select a saved decision and ask “What did the agents decide for this symbol?” and “What happened to the paper account?” Compare both replies with the stored decision and linked fill or skip, then end the session and verify microphone release.

## Folder map

```text
Assignment 4/
|-- .github/workflows/workstation-smoke.yml
|-- README.md
|-- AGENTS.md
|-- backend/
|   |-- data/sample-candles.csv
|   |-- main.py
|   |-- requirements.txt
|   '-- Python modules for market data, indicators, decisions, voice, and paper trading
|-- frontend/
|   |-- index.html
|   |-- package.json
|   |-- package-lock.json
|   |-- vite.config.mjs
|   |-- Vue chart and workstation modules
|   '-- scripts/
|       |-- smoke-live.mjs
|       '-- smoke-workstation.mjs
|-- docs/
|   |-- design-pipeline.md
|   |-- prompt-checklist.md
|   '-- verification.md
|-- prompts/
|   '-- 20 guidance files, 01 through 14 with lettered steps
|-- scripts/
|   '-- Service, replay fixture, and decision verification scripts
'-- handoffs/
    |-- create-handoff.md
    '-- current.md
```
