# Prompt 10A · Ask the Decisions API about a chart screenshot

~~~text
Read AGENTS.md and find the Vue chart and POST /api/decisions. Add an
"Ask about chart" button to the dashboard. It should let a student inspect a
specific chart, see what the model was asked, and read its answers.

On click, freeze the selected symbol, interval, chart range, and decision
snapshot at the selected completed candle. Render the candles, volume, and
indicator lines through that cutoff and capture the chart as a PNG. Show the
captured chart with its symbol, interval, and cutoff so the student can check
what the model saw even as live updates continue. Use the chart's image export
when available. Keep the capture limited to the chart.

Send the PNG and snapshot ID to the existing FastAPI decision route. Python
loads the matching indicator values and paper position from SQLite. Send the
actual PNG as an input_image whose image_url is a data:image/png;base64,...
URL, alongside the snapshot in input_json.data. Both parts belong in the same
user message to POST /v1/decisions. Reject an unreadable image or mismatched
snapshot and show what must be recaptured.

Ask three named choice questions in the same request:
1. action: Which action fits this paper position and the strategy rules?
   Buy adds shares, sell reduces the position, hold keeps an open position,
   wait stays flat, and close exits the entire position.
2. crossover: At the selected candle, is an upward crossover, a downward
   crossover, or no crossover visible? Include an unreadable option.
3. evidence: Is the visible chart sufficient to assess the signal at the cutoff?

Validate each answer by name. Display the three answers and compare the visual
claim with the crossover Python calculated. Mark unreadable images, missing
answers, and conflicting signals ineligible for automated execution.
Save the PNG or its retrievable local reference with the snapshot ID,
questions, and answers under the decision ID. The button requests analysis and
leaves paper balances and orders untouched.

Run SmokeTest in a browser with a recorded crossover. Click the button, inspect
the preview and cutoff, and verify that the provider test double received a
decodable PNG matching the saved capture. Compare the displayed answers with
SQLite and check the order count. Then exercise one live image request and
record the model's actual answers separately from the mocked check.

OpenAI Decisions API request format
https://developers.openai.com/api/reference/resources/decisions/methods/create
Lightweight Charts image capture
https://tradingview.github.io/lightweight-charts/examples/data/screenshot
~~~
