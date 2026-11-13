# Prompt 14 · Run the workstation smoke test from one command

~~~text
Implement the SmokeTest defined in AGENTS.md. Give the project one documented
command that starts FastAPI and Vue, waits until both are ready, opens a real
browser, performs the checks below, and exits with a failing status when any
expected result is missing. Use the project's existing browser test tools.

CHECK
Inspect the test commands, browser tooling, lockfiles, and local runtimes.
TAKE ACTION
If software is missing, give its purpose, version, exact install command,
target, and affected files. Wait for approval before downloading a browser,
installing packages, or changing dependency files.
VERIFY
Run the command using an isolated SQLite database and deterministic market
events. Stub the external Yahoo and model connections. Run the real Vue UI,
FastAPI routes, chart capture, agent coordination, simulator, and database.

1. Open a recorded session in Vue. Add an SMA, change its window, and compare
   its displayed value at a known candle with a hand calculation.
2. Click "Ask about chart." At the model boundary, verify that the payload
   contains decodable chart pixels and the matching symbol and candle time.
   Return known answers, check them on screen, and confirm the fill count is
   unchanged. Repeat with a provider failure and check the visible status.
3. Start paper automation in the browser. Deliver completed candles and marks
   through the test feed with predetermined proposals and reviews. Start with
   $1,000 and zero fees. Configure four shares for the buy and one for the
   partial sale. After each approved order, deliver its eligible fill price:
   $100 for the buy, $110 for the sale, and $105 to close the remaining three
   shares. Check for $1,025 cash, zero shares, $25
   realized and $0 unrealized P&L on screen and in SQLite. Include a veto
   and a duplicate event and verify neither adds a fill. Stop automation,
   deliver another candle, and verify it places no order.

Write the commands, expected and observed values, and any failure evidence
in docs/verification.md. End the browser and processes started by the test,
including on failure. Run it twice to confirm a clean test account each time.
Run the same command on pushes through GitHub Actions, using the offline
fixtures so a push can be checked without provider credentials. Keep the live Yahoo,
image-model, and two-way voice checks as separate documented observations.
SmokeTest reports failures without source edits. AutoLoop may apply a scoped
fix and rerun the failing check, up to five correction cycles.
~~~
