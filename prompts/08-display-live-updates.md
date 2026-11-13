# Prompt 8 · Display live updates on the existing chart

~~~text
Connect the existing Vue candlestick chart to the candles produced by the
Python backend. Read AGENTS.md and docs/design-pipeline.md. Locate the chart,
the Yahoo Finance subscription, and the function that updates a candle when
an observation arrives. Trace their inputs and outputs before editing.

Default the chart to one minute. Add a timeframe selector for the intervals
the backend supports, including daily. When the user switches, load the
matching history and display live updates for that same symbol and timeframe.
Use the backend's aggregation for both. Use a FastAPI WebSocket to send candle
updates to Vue. Use the same six candle fields as the CSV. Carry the symbol,
interval, and feed and completion status alongside the candle in the WebSocket
message. Use the existing backend subscription. When a new price
arrives in the same interval, update the candle and its volume in place.
When the next interval begins, show the next candle. Display the symbol,
interval, source, age of the most recent source observation, and feed status.
Show when a candle is still forming. If additional WebSocket support is
needed, follow CHECK, TAKE ACTION, and VERIFY in AGENTS.md.

Open the dashboard and follow one actual Yahoo update from its stored record
to the candle on screen. Compare the time and values. Disconnect the upstream
feed while the page is open and check that the status changes even if the
browser still has a connection to FastAPI. Record what the browser showed.
If no live observation arrives during the check, identify the live check as
pending and label any recorded input used to exercise the interface.
~~~
