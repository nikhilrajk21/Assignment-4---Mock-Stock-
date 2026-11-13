# Prompt 9C · Buy, sell, and close a simulated position

~~~text
Read README.md and AGENTS.md. Build a local, long-only paper account in the
existing SQLite database. In Vue, show the cash balance, shares held, and
order history. Let me buy a whole number of shares, sell part of a holding,
or close the entire position. Use FastAPI to send these requests to one Python
execution function that the decision agent can reuse later. Hold keeps an
existing position and wait stays in cash. Neither action creates an order.

Explain the simulated fill rule. For a simple first implementation, fill at
the next eligible observed price after submission, with zero fees. In replay,
use only observations as they arrive. Reject invalid quantities and sales
larger than the position. Keep an accepted order pending until a price is
available. Recheck cash and shares when filling. Record the order ID, symbol,
side, quantity, submission time, status and any rejection reason. Link a fill
to its order and record the price, market observation, and execution time.
Commit the fill and updates to cash and shares in one SQLite transaction.
Use a stable request ID so retrying the same request cannot create another
order or fill.

Run the app against a disposable SQLite account starting with $1,000. Operate
the Vue controls with the browser and supply these known prices in sequence:
buy 4 at $100 (cash $600, 4 shares), sell 1 at $110 (cash $710, 3 shares),
then close at $105 (cash $1,025, 0 shares). Retry one request and attempt to
sell from the empty account. Check the rejection and verify that exactly three
fills persist after a backend restart. Compare the dashboard with the SQLite
records and save expected and observed results in docs/verification.md.
~~~
