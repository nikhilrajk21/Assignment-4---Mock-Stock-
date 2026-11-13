# Prompt 6 · Record market observations in SQLite

~~~text
Read AGENTS.md and inspect the backend that receives Yahoo Finance updates.
Connect that receiver to a local SQLite database using Python's sqlite3 module.
Retain the source fields, ticker, source time, and backend receipt time so that
a saved observation can be traced back to its incoming message.

Explain how the recorder recognizes an exact repeat and how it treats a changed
message. Preserve earlier values when a revision can be identified. If two
distinct messages share a timestamp and the feed cannot establish that one is
a correction, retain both. Keep source time and receipt order available for
observations that arrive late.

Verify the recorder in a disposable database. Send one observation twice, then
send a changed value with the same source time. Show the stored rows and explain
how a reader can avoid counting the repeat twice. Restart the backend, reopen
the database, and check the same records. Label any constructed input as test
data. Record the database path and initialization command in README.md and the
expected and observed results in docs/verification.md.
~~~
