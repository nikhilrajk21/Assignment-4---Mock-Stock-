# Prompt 7A · Derive larger candles from one-minute data

~~~text
Read AGENTS.md and find the backend's one-minute candles. Let the history
endpoint return 1-minute, 5-minute, 15-minute, hourly, or daily candles for
one symbol. Default to one minute. Derive each larger timeframe from the
same one-minute data on request. Keep the chosen timeframe in the request
and the same six fields in each returned candle.

Group minutes by their timestamps. For stocks, use the exchange's regular
trading session unless the project specifies another session. Align intraday
groups to the session open. A daily candle covers one trading session and is
timestamped at its open in UTC. Follow the exchange calendar for early closes
and time changes. Keep each session's minutes together, including when a gap
occurs.

For each group, take the first open, highest high, lowest low, last close,
and sum of the minute volumes. A revised minute replaces its earlier value
in the calculation. Mark unknown volume and incomplete coverage separately
from a known zero. Keep coverage and completion status outside the six fields.
During live use or replay, use only minutes available at the displayed time.

Verify with the three supplied sample minutes starting at 14:30 UTC. The
five-minute candle starts at 14:30 and has open 100, high 105, low 99, close
104, and volume 3550. The three minutes give only partial coverage of that
five-minute interval and of the day. Add a test minute at 14:35 and confirm
it starts a second five-minute candle but belongs to the same daily candle.
Add a minute from the next trading session and confirm it starts a new daily
candle. Record the comparisons in docs/verification.md.
~~~
