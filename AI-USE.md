# AI use for Assignment 4.2

Codex assisted with reviewing the course activities and existing project, defining verification steps, implementing changes, and checking the app. The user set the project scope and asked to include the classroom Decisions API and Agents SDK work in the Part 4.2 milestone.

The chart assessment uses the OpenAI Decisions API with `gpt-6-luna`. The chart chat worker is configured to use `gpt-6-luna` by default through the Agents SDK. Local fixture checks use controlled responses. The verification log records provider and fixture evidence separately.

- [Prompt 15](prompts/15-verify-baseline-and-backtest.md) covers the market baseline and strategy work.
- [Verification evidence](docs/verification.md#prompt-15--part-41-baseline-check-and-historical-strategy) connects expected outcomes, changes, observed results, and remaining limitations.
