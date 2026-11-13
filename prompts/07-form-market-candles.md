# Prompt 7 · Form candles from saved observations

~~~text
Read AGENTS.md and inspect the observations stored by the backend. Write the
Python logic that groups one ticker's observations into one-minute candles,
the same base resolution as the CSV. For each minute, return exactly
timestamp, open, high, low, close, and volume. Use the minute's start date
and time in UTC for timestamp. Track whether the minute has ended separately.
Use source time to order prices within the minute.
Document how late observations and identifiable corrections update a candle.

Verify a one-minute candle with the following test observations. Times are UTC
on November 9, 2026. The volume column holds the running session total.

Source time    Price    Cumulative volume
14:59:59       99       1000
15:00:05      100       1004
15:00:20      103       1009
15:00:50      101       1011

The candle at 2026-11-09T15:00:00Z should have open 100, high 103, low 100,
close 101, and volume 11. Check it before the minute ends and after it ends.
Deliver the middle observation late and check the final values again. When a
cumulative volume baseline is unavailable or a session total resets, report
any volume that cannot be determined as unknown. Record the aggregation rules
and the expected and observed results in the project documentation.
~~~
