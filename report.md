# Assignment 4, Part 1 — Market Data and the Dashboard

## What I completed

I built an AAPL dashboard with a Vue frontend, a FastAPI backend, and a Yahoo Finance feed. FastAPI sends candlestick and volume updates over a WebSocket. The dashboard identifies the data source, shows the age of the last source observation, and reports when the feed disconnects. A candle inspector shows UTC timestamps, prices, volume when available, and whether the candle has completed. The replay controls let me step through observations saved in SQLite.

## Design decisions

I chose TradingView Lightweight Charts to display price and volume on a shared time axis. I used SQLite to retain each observation's ID, ticker, source time, receipt time, and decoded provider fields. Exact duplicates retain their original row. Explicitly linked revisions keep both versions and change the reconstructed candle only after the correction arrives. Late observations affect the replay view from the step at which they were received. The backend derives candle completion at the selected cutoff and reports unknown volume when the available quotes cannot establish a share count.

## Verification

- **Live feed and disconnect.** On November 12, 2026, the Edge live test recorded a Yahoo AAPL quote in SQLite. The chart displayed the corresponding 15:49 UTC candle with a close of 357.93, matching the saved quote. Stopping the Yahoo worker changed the dashboard to disconnected while the browser WebSocket stayed open.
- **Persistence and replay.** The SQLite checks covered exact duplicates, changed messages at the same source time, and explicitly linked revisions. The browser replayed the same four-observation fixture twice. The late observation changed the candle high from 101 to 103 when it arrived. The final close was 101 and volume was 11 shares. The observation rows stayed unchanged.
- **Chart updates.** The controlled-feed browser test checked volume alignment, an update to an existing candle, a new candle, and an upstream disconnect.

## Remaining limitations

Yahoo messages can omit volume or contain partial quote coverage. The observed Yahoo payload did not carry an explicit revision identifier, so the revision test used a controlled correction. The new check for browser replay of the same real Yahoo recording remains open. The evening run timed out waiting for a regular-session quote. The recorded fixture replay and the earlier live stream and disconnect checks passed.

## Repository and evidence

- [GitHub repository](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-)
- [Submitted application commit 62175bc45f96e32c14ba85e04f65af6530421b48](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-/commit/62175bc45f96e32c14ba85e04f65af6530421b48)
- [Setup and startup](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-/blob/62175bc45f96e32c14ba85e04f65af6530421b48/README.md)
- [Data flow and SQLite schema](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-/blob/62175bc45f96e32c14ba85e04f65af6530421b48/docs/design-pipeline.md)
- [Verification commands and results](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-/blob/62175bc45f96e32c14ba85e04f65af6530421b48/docs/verification.md#prompt-08--live-chart-updates)
- [Dashboard demonstration video](https://drive.google.com/file/d/1vL2FBc9gQRpQgsbbjku7XzKPW711GkCh/view?usp=sharing)
