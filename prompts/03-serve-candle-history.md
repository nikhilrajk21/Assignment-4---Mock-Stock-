# Serve one-minute candle history

Read README.md and AGENTS.md. Use Python's built-in csv module to read a local candle file and serve it through GET /api/history. Each row is one minute for one instrument. The UTC timestamp marks the inclusive start, and the next minute is excluded. Use exactly six fields.

```csv
timestamp,open,high,low,close,volume
2026-11-09T14:30:00Z,100,103,99,102,1200
2026-11-09T14:31:00Z,102,104,100,101,850
2026-11-09T14:32:00Z,101,105,101,104,1500
```

Use prompts/data/sample-candles.csv if supplied, or create backend/data/sample-candles.csv with the synthetic rows above. Prices are numeric and volume is the share count. Use the one-minute candles as the source for larger timeframes, including daily candles.

Return a JSON array ordered by timestamp with the same six names. Start FastAPI, request the endpoint, and compare all six values at 2026-11-09T14:31:00Z with the second CSV row. Record the result in docs/verification.md.
