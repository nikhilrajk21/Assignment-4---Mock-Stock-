# Prompt 9B · Create and configure a chart indicator

~~~text
Read AGENTS.md and find the existing SMA calculation and chart. Make it
possible to add a new indicator type in Python and create a named instance
of it from the Vue dashboard. Document the calculation's inputs (completed
candles and validated settings), units, and output (one value or a warm-up
gap at each candle time). Reuse the SMA through this same interface.

Demonstrate the extension by adding a rolling price range. For a window of
N completed candles, subtract the lowest low from the highest high. Provide
the available indicator types and settings to Vue through FastAPI. Let the
user choose a type, name the indicator, set its window, and inspect its values
alongside the candles. Keep its settings in SQLite so the user can reopen
the same chart configuration. Each configured indicator uses its own settings.

Run the app against a labeled fixture. Use three candles with (high, low)
pairs of (12, 9), (15, 10), and (13, 11). In the browser, add “Range 2” and
“Range 3”. At the third candle their values should be 5 and 6 respectively.
Refresh the page and confirm both configurations return. Try a window of zero
and verify that the app explains the error and keeps the valid indicators.
Record the expected and observed values in docs/verification.md.
~~~
