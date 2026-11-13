# Prompt 9A · Calculate and display two simple moving averages

~~~text
Read README.md and AGENTS.md. Add a short and a long simple moving average
(SMA) to the existing candle chart. Let me choose the two window lengths.
Require positive whole numbers with the short window smaller than the long
one. Python calculates the values. Vue draws each line and marks crossovers.

For each symbol and interval, average the closing prices of the last N
completed candles, including the candle at the displayed time. Leave the
value unavailable until N completed candles exist. A crossover occurs when
the short average moves from below to above the long average, or vice versa.
While they are equal, retain the last known side. The first comparable pair
establishes a side. Only a change of side produces a signal. Compare at full
precision before rounding for display.

Use this hand calculation as a reference. For completed closes of 13, 10, 7,
13, 19, 7, 1 and windows of 2 and 3, the third candle has averages of 8.5
and 10. The fourth is a tie at 10. The fifth crosses upward at 16 and 13.
The sixth ties at 13. The seventh crosses downward at 4 and 9.

Run the calculation once over all seven candles and again by revealing one
candle at a time in replay. Compare every value and signal, including the
warm-up gaps. An unfinished candle must not trigger a confirmed crossover.
Use only observations and revisions available at each replay step. Run the
app, inspect the two crossover markers in the browser, and record the checked
values in docs/verification.md.
~~~
