# Current handoff — 2026-11-12

The project root is `C:\Users\nikhi\Documents\ChatGPT\Assignment 4`. The workstation helps learners explore market candles, indicators, replay, and simulated trading decisions.

The scaffold now includes the Yahoo recorder and replay pipeline, live and historical candles, saved indicators, the simulated order and P&L ledger, frozen chart decisions, independent review, paper automation, and read-only decision voice. The original guidance files are saved under `prompts/`. Recent files include `backend/automation.py`, `backend/voice.py`, `backend/requirements.txt`, `frontend/paper-automation.mjs`, `frontend/decision-voice.mjs`, `frontend/scripts/smoke-workstation.mjs`, and `.github/workflows/workstation-smoke.yml`.

The offline workstation command passed twice with Edge and fresh SQLite databases. Both runs confirmed the edited SMA, chart pixels and answers, visible provider failure, automated paper fills and P&L, and voice startup cleanup. See [verification](../docs/verification.md) and the [checklist](../docs/prompt-checklist.md) for the observed results.

Live OpenAI Decisions and GPT-Live returned HTTP 401. The next task is to configure a working backend key, rerun live decisions and independent review, and compare the two spoken answers with the selected SQLite record using a physical microphone and speaker. After student review of the changes, push the workflow and confirm the GitHub Actions job passes.

## Chart direction work in progress

The student chose long, short, or wait and a large move strictly over 10 percent from the start of the one-to-two-day period. When evidence is unclear, consider available similar past situations. The separate educational endpoint and Vue control are incomplete: recorded history, extended-hours data, and comparable-case retrieval need implementation and verification. Until then the endpoint reports insufficient evidence. The existing workstation regression passed after fixing its isolated Vite server configuration. Normal FastAPI startup now loads the root .env without overriding an existing process variable. The live image flow and successful physical voice session remain open.

## Latest live checks and historical-data investigation

The live image decision and independent reviewer passed with the configured key and a synthetic replay. A live WebRTC voice session connected with simulated audio. Physical microphone and speaker verification is still needed.

An experimental Yahoo history fetcher returned hourly AAPL bars for two dates, including extended-hour timestamps. It is not integrated. Review found that hourly bars can cross session boundaries, complete coverage is unproven, comparable-case matching is missing, and revised historical downloads cannot establish replay-time knowledge. Next, use appropriately bounded data and the exchange calendar to establish coverage and session boundaries, implement and save comparable evidence, build historical chart captures, and verify provider and browser behavior. Preserve the existing paper automation and avoid feeding later-retrieved Yahoo history into replay decisions.

## Historical direction integration update

The historical analysis is now connected to the Vue chart and provider boundary. It uses a cutoff-bounded Yahoo five-minute history, labels its later retrieval, reports session coverage and compares prior two-session moves with following-session outcomes when extended coverage is complete. User-selected threshold is strictly greater than 10 percent from the first available bar. A five-minute quote freshness threshold was chosen during implementation and should be reviewed. The model receives chart images and coverage metadata, while the paper automation remains separate.

Before completion, verify the new flow in the browser and live provider, including image-to-data correspondence, order/fill invariants, persistence, and displayed long/short/wait. Verify physical voice answers against a saved decision and linked outcome. The latest full workstation run timed out in voice after its other scenarios passed; the standalone voice scenario passed on retry.
