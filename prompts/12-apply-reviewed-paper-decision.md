# Prompt 12 · Apply a reviewed decision to the paper account

~~~text
Connect the reviewed decision to the existing trading simulator. Start by
tracing one saved decision from its completed candle through the analyst's
proposal, the reviewer's verdict, and the Python validation result. Locate the
simulator's order and fill logic and its SQLite cash, position, and P&L records.

Add Start and Stop paper automation controls in Vue. While enabled, run the
decision service and agent review once per newly completed candle. Reuse the
chart capture function from the manual question. When a completed candle
arrives during automation, render its frozen snapshot and submit a fresh PNG
for that candle automatically. If the chart or image is unavailable, record
the failed analysis and skip execution. Apply only eligible, approved decisions for the
same paper account and symbol. Buy and sell use the configured order size,
close exits the whole position, and hold and wait record no order. Route test
snapshots to the disposable test account. Immediately before
a fill, recheck the available cash or position, the age of the decision, and
whether it was already handled, using the simulator's documented rules.
Use the simulator's transaction to record the fill, balances, P&L, and decision
ID together, or record why execution was skipped. Deduplicate by account,
strategy, symbol, interval, and candle, including after restart. Stop must
disable new executions, including any pending model reply. A manual chart
question by itself creates no order.

In Vue, let the student follow one decision ID from the crossover through the
proposal and review to the paper fill or skip and resulting account state.
Verify against a disposable account with a known starting balance. Use the
same approved decision twice and compare the expected and observed fill count,
cash, and position. Then try a vetoed proposal and confirm the account state.
Record the observed results and whether the provider responses were live or
mocked.
~~~
