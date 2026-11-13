# Prompt 10 · Request a decision about one completed candle

~~~text
Add POST /api/decisions to the local FastAPI app. Its job is to answer one
question about a paper account. Given the information available when this
candle closed, what action does the model propose?

Read README.md and AGENTS.md. Find the completed candles, the two simple moving
averages (SMAs) and their crossover, and the SQLite paper ledger. For one symbol,
freeze the interval, candle timestamp and closing price, indicator values,
crossover, simulated cash, and position as of the decision time. Give this
snapshot an ID.
Keep snapshot creation independent of the model call so a chart can be
rendered from exactly those records before being submitted for analysis.
In replay, use only observations and revisions received by that time. If an
indicator or account is still being developed, use a clearly labeled test
snapshot for an isolated test. An incomplete application snapshot is ineligible
for a paper order.

Make the model request from Python. For an OpenAI implementation, use
POST /v1/decisions with the snapshot as input and a named choice question
whose allowed answers are buy, sell, hold, wait, and close. For this long-only
simulation, buy adds shares, sell reduces a position by the requested size,
hold keeps an open position, wait stays flat, and close exits the entire
position. For buy and sell, use the simulator's configured order size. Check
the named answer against the snapshot and account rules. Build a short,
factual explanation from recorded evidence.
Distinguish the model's proposal from the facts the backend supplied. Keep
the provider key in the backend environment. Follow CHECK, TAKE ACTION, and
VERIFY in AGENTS.md if a package is needed.

Save the snapshot, provider/model, proposal, explanation, and validation
status in SQLite under one decision ID. Return that ID and result to the
caller. A timeout, malformed answer, or missing input should have its own
status. A valid hold is a decision. This endpoint leaves the paper account
untouched.

Verify with a fixed snapshot and a controlled provider failure. Then make one
live provider request and match its result to the saved decision. Label the
model call and the market data separately: a live model can evaluate recorded
or test data. Record what actually ran in docs/verification.md.

OpenAI Decisions API documentation
https://developers.openai.com/api/docs/guides/decisions
~~~
