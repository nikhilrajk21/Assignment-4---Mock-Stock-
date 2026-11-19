# Assignment 4.2 — SMA strategy and historical backtest

## Work completed

I added a rule that applies a crossover to the simulated account in replay. When the short SMA crosses above the long SMA and the account is flat, the app queues a buy. The reverse crossover queues a close when the account holds shares. The simulator then uses the next eligible replay observation for the fill. A repeated request for the same signal reuses the existing order. The account shows orders, fills, shares, cash, and realized and unrealized profit and loss.

I also added a historical backtest with its own account. The strategy evaluates each completed bar at its close. The simulator fills at the next available bar's open, assumes zero fees, and uses a fixed share quantity. An order can remain unfilled if the file ends before the next bar. For the AAPL sample, I exported only observations received by the relevant minute close.

## Verification and design decisions

- A hand-worked example with two shares bought at $10 and sold at $8 produced a $4 realized loss and $96 final equity from $100. The forming-candle case left an exit unfilled. The browser suite also verified crossover markers, no-action and repeat cases, and a full replay buy and close.
- A partial November 13, 2026 AAPL recording supplied 42 completed bars from 16:19 through 17:07 UTC. SMA windows of 2 and 3, two shares per buy, and $1,000 initial cash produced 15 fills and $1,002.336 ending equity. The result is sensitive to the time range, SMA windows, missing minutes, and assumed fill prices and costs. A later revision or a backtest using a long history may produce a different result.
- A live November 19 browser run verified the Yahoo chart, SQLite persistence, feed disconnect, and replay of the same recorded quote. An initial check raced with arriving quotes. I revised it to match the visible close to a stored quote for the same minute, then verified the disconnected recording independently.
- I compared 40 estimated minute volumes from the November 13 recording with Yahoo’s historical minute bars. Two matched exactly. The app labels counter-derived volume as an estimate and displays the later historical value with its own retrieval time.
- The classroom chart Decision API returned WAIT with a 74% choice probability for a synthetic AAPL chart in a live OpenAI request. The probability describes the model’s choice among the supplied options. The chatbot bridge passed offline checks for conversation continuity, fresh chats, and worker failure. Live SDK chat verification is pending.

## Evidence

- [Setup and controls](../README.md#part-42-strategy-and-backtest)
- [Verification log](verification.md#prompt-15--part-41-baseline-check-and-historical-strategy)
- [AI use disclosure](../AI-USE.md)
- Repository commit and completed GitHub Actions run must be linked from the final `report.md`.
- Add the instructor-accessible demo link after checking the published video.
