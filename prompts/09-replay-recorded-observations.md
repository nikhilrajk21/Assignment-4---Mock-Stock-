# Prompt 9 · Replay a recorded session from SQLite

~~~text
Make it possible to review a recorded market session with the Yahoo feed
disconnected. Read AGENTS.md and identify the SQLite observation store,
candle calculation, and Vue chart that already exist.

Select a saved symbol and time range. Feed its observations to the existing
candle calculation in the order they originally arrived. Preserve source
timestamps so a late arrival or revision becomes visible at the same point in
the replay. Label the chart "Replay" and show the time of the observation
being replayed. Keep replay read-only with respect to the recorded session.
If the selection is empty, tell the user that it has no recorded observations.

Restart the backend with the live feed off. Choose one recorded interval,
work out its expected closing price and volume from SQLite, and compare those
values with the replayed chart. Run the same selection again and check that
the result and stored observation count agree with the first run. If no live
session has been captured, use clearly labeled test data in a separate test
database and record which checks still require an actual capture.
~~~
