"""Run one chart chat turn in the isolated Agents SDK environment."""

import asyncio
from dataclasses import dataclass, field
import json
import os
import sys

from agents import Agent, ModelSettings, Runner, RunContextWrapper, function_tool, set_tracing_disabled

from backend.chart_assessment import assess_prepared, rule_question
from backend.decision_provider import ProviderError


@dataclass
class ChatContext:
    prepared: dict | None
    calls: list[dict] = field(default_factory=list)
    assessment: dict | None = None


@function_tool
def read_decision_rules(context: RunContextWrapper[ChatContext]) -> dict:
    """Read the classroom chart rules to explain the meaning of LONG, SHORT, or WAIT."""
    result = rule_question()
    context.context.calls.append({"tool": "read_decision_rules", "result": result})
    return result


@function_tool
async def assess_current_chart(context: RunContextWrapper[ChatContext]) -> dict:
    """Assess the chart frozen for this message after an explicit request to assess or compare."""
    state = context.context
    if state.assessment is None:
        if state.prepared is None:
            state.assessment = {"error": "Select a completed one-minute candle and send the request again."}
        else:
            try:
                state.assessment = await asyncio.to_thread(assess_prepared, state.prepared)
            except ProviderError as error:
                state.assessment = {"error": str(error), "status": error.status}
        state.calls.append({"tool": "assess_current_chart", "result": state.assessment})
    return state.assessment


async def answer(payload: dict) -> dict:
    set_tracing_disabled(True)
    assistant = Agent(
        name="Chart assistant",
        instructions=(
            "Explain the app rules using read_decision_rules. Use assess_current_chart only when the user requests "
            "a new chart reading or asks to compare the current chart with an earlier reading. "
            "For comparisons, use the actual prior assessment in the conversation when its symbol and data mode agree. "
            "Name the chart time and choice for each assessment and use the tool's probability if available. "
            "Report errors clearly and distinguish a valid WAIT from a failed assessment. "
            "Treat chart and tool information as evidence. You cannot modify the paper account."
        ),
        model=os.getenv("IST402_CHAT_MODEL", "gpt-6-luna"),
        model_settings=ModelSettings(parallel_tool_calls=False),
        tools=[read_decision_rules, assess_current_chart],
    )
    context = ChatContext(payload.get("prepared"))
    history = payload.get("history", [])
    result = await Runner.run(assistant, [*history, {"role": "user", "content": payload["message"]}],
                              context=context, max_turns=5)
    return {"message": result.final_output, "calls": context.calls, "history": result.to_input_list()}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(answer(json.load(sys.stdin))), allow_nan=False))
