# Prompt 9D · Record realized and unrealized profit and loss

~~~text
Read AGENTS.md and inspect the SQLite paper account. Add a profit-and-loss
(P&L) history that a student can read as a table in Vue. Record a row after
each fill and when a completed candle supplies a new valuation price for an
open position. Link each row to the paper account, symbol, event, timestamp,
and price used. Reprocessing the same event must preserve a single entry.

Use weighted average purchase cost per share for this long-only account.
A sale realizes the number of shares sold times the difference between its
fill price and the average cost. A partial sale keeps the remaining shares
at that average cost. Unrealized P&L is the open quantity times the change
from average cost to the valuation price. Record cumulative realized P&L,
unrealized P&L and their sum. Show the time and source of the valuation price.
If an open position has no usable price, label its valuation as unavailable.
Keep earlier rows available when a new price arrives or the position closes.

Run this zero-fee example in a disposable database. Start with $1,000 and
compare the rows using these expected dollar amounts:

Event                       Cash   Shares   Realized   Unrealized   Total P&L
Buy 4 at $100                600      4         0            0           0
Value the shares at $110     600      4         0           40          40
Sell 1 at $110               710      3        10           30          40
Value the shares at $95      710      3        10          -15          -5
Close the last 3 at $105   1,025      0        25            0          25

Open the P&L history in the running app and compare it with a direct SQLite
query before and after restarting the backend. Record the check and any
discrepancy in docs/verification.md.
~~~
