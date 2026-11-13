# Prompt 11 · Have a second agent review a proposed decision

~~~text
Read AGENTS.md and trace one request through POST /api/decisions. Extend that
endpoint so a student can inspect how a proposal passed or failed review.
Reuse its provider client, response format, and SQLite decision record.

Give the analyst and reviewer separate instructions and separate model calls.
They may use the same model. Freeze one snapshot at the decision time,
including the symbol, completed candles, simple moving averages and crossover,
and simulated cash and position. Both agents must use that same snapshot.

The analyst proposes buy, sell, hold, wait, or close. Pass its actual choice,
the backend's supporting facts, and the snapshot to the reviewer. For a chart
question, attach the same frozen image and the analyst's named answers.
Ask the reviewer to choose
a verdict from a small list such as accept, reject for insufficient cash, or
reject for an unsupported signal. This works with a provider that only returns
a category. Python can explain a verdict by displaying the relevant observed
values. For example, compare the simulated cash with the cost of one share
when an upward crossover leads the analyst to propose a purchase.

Use at most one call per role, each with a timeout. Python validates the
outputs and enforces the account and strategy rules even when the reviewer
accepts. A rejection, timeout, or invalid reply makes the proposal ineligible
for execution. Save both roles' visible outputs, model names, snapshot ID,
and final check under the same decision ID. Keep the account read-only here.

Use fixed replies to check three cases: an agreed eligible proposal, a
reviewer rejection, and an unaffordable buy accepted by both agents. Inspect
each saved result. Run one live two-call example with the configured provider
and compare both outputs with the saved snapshot. Record live and mocked
observations separately in docs/verification.md.
~~~
