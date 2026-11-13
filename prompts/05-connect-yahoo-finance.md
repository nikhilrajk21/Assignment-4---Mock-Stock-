# Prompt 5 · Receive a Yahoo Finance update

~~~text
Read README.md and AGENTS.md. Connect the Python backend to the Yahoo Finance
stream for one ticker. Use the ticker I specify, or AAPL for the first check.

CHECK
Inspect the project instructions, dependency files, lockfiles, OS, and active
Python interpreter. In that interpreter, check whether yfinance and its
WebSocket client are available. Reuse the existing Python environment.

TAKE ACTION
If a dependency is missing, explain why it is needed, its compatible version,
the exact installation command and target, and which project files would
change. Wait for my approval before installing or changing dependencies.
Use the yfinance WebSocket client to subscribe from Python. The subscription
does not need a Yahoo login. If I choose to create a personal watchlist, I can
create or use a Yahoo account on the website and enter my credentials there.

VERIFY
Confirm the import and version in the backend interpreter. Run a bounded
subscription check. For one received update, display the ticker, price, source
time, backend receipt time, and any available volume field. Identify the time
units and what the volume field measures. If no message arrives before the
timeout, report whether the connection opened and mark receipt as unverified.
Record the command and observation in docs/verification.md.

WebSocket client documentation:
https://ranaroussi.github.io/yfinance/reference/yfinance.websocket.html
~~~
