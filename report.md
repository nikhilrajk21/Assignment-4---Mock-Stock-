# Assignment 4, Part 2 — Indicators, Simulated Trading, and Backtesting

## What I completed

The workstation displays two configurable simple moving averages and marks upward and downward crossovers. The **Apply SMA crossover** action is available only during replay of a recorded session. When I request it for a completed candle, the app automatically applies the strategy to the long-only paper account. A confirmed upward crossover can queue a buy while the account is flat, and a confirmed downward crossover can queue a close when it holds shares. The dashboard shows order status, fill price, cash, shares, and realized and unrealized P&L.

The backtest uses its own starting balance, reads completed one-minute bars, and shows crossovers, orders, fills, and equity after each bar. The dashboard can run the synthetic example or load a historical CSV.

## Design choices

SMA windows use completed closing prices. A forming candle contributes no average or confirmed crossover. Replay fills occur at the next eligible recorded observation. The historical simulator decides at the candle close and uses the next available bar’s open for the fill. Both assume zero fees. The paper ledger uses weighted average cost. Reapplying the same replay signal creates no duplicate order.

## Verification

- Four unit tests passed. I compared SMA values and crossover markers with hand-calculated results and compared full-batch output with incremental replay. The tests also checked an unfinished candle, weighted average cost, next-bar backtest fills, and an order that ran out of data before it could fill.
- I reproduced a timing issue in recorded replay. Clicking **Next observation** while a crossover request was still being submitted could advance the chart before the paper order was queued. In local application commit `337c6cf`, replay waits for submission to finish. All four unit tests and seven Edge scenarios passed on the repaired version.
- In the eight-observation test session, the short SMA crossed above the long SMA at 16.00 versus 13.00. Applying the signal twice queued one buy. The next observation filled one share at $7, leaving $993 cash. After the downward crossover, the close filled at $100, leaving zero shares, $1,093 cash, and $93 realized profit. Running the separate $100 backtest then produced $96 ending equity while the replay account still held $1,093.
- On the partial November 13 AAPL recording, the browser showed 42 account valuations, 15 fills, and $1,002.34 ending equity from $1,000 using SMA windows 2 and 3 and two shares per buy. A separate hand-worked example produced $96 from $100.
- GitHub Actions passed all four unit tests and seven browser scenarios on the published application version `b3e9c43`. The later replay timing fix in `337c6cf` was verified locally. [Published workflow run](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-/actions/runs/44601056708)

## Limitations

The recorded AAPL sample covers parts of one session. Quote-derived opens approximate fill prices. Missing intervals, fees, spreads, slippage, and a different choice of windows could materially change results. The recorded export uses observations received by each bar’s close. Other imported CSVs may contain later revisions. These runs establish expected simulator behavior on the examples. They do not establish future returns.

## Repository and evidence

- [GitHub repository](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-)
- [Published commit b3e9c43ffc82859d93426d5e9235862011aa7be6](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-/commit/b3e9c43ffc82859d93426d5e9235862011aa7be6)
- [Setup and usage](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-/blob/b3e9c43ffc82859d93426d5e9235862011aa7be6/README.md#part-42-strategy-and-backtest)
- [Verification log](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-/blob/b3e9c43ffc82859d93426d5e9235862011aa7be6/docs/verification.md#graded-part-42-acceptance-checks)
- [AI use disclosure](https://github.com/nikhilrajk21/Assignment-4---Mock-Stock-/blob/b3e9c43ffc82859d93426d5e9235862011aa7be6/AI-USE.md)

## Video Link

[Workstation demonstration](https://drive.google.com/file/d/1fhG4qB_kOzieyWNSN9yR0jRWTg3zKpTi/view?usp=sharing) (4 minutes 48 seconds). The required 30–60 second cut is pending.
