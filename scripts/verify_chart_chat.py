"""Offline checks for the assessment mapping and conversation bridge."""

from unittest.mock import patch

from backend.chart_assessment import parse_assessment, rule_question
from backend.chart_chat import ChartChatRequest, ChartChats, ChatUnavailable
from backend.decision_provider import ProviderError


def main() -> None:
    question = rule_question()
    answer = {"type": "choice", "name": "chart_signal", "choice": "wait"}
    provider = {"model": "fixture", "answers": [answer]}
    assert parse_assessment(provider, question)["probability"] is None
    answer["probabilities"] = [{"value": "long", "probability": 1}, {"value": "wait", "probability": 0}]
    assert parse_assessment(provider, question)["probability"] == 0
    answer["probabilities"].append({"value": "wait", "probability": 0})
    try:
        parse_assessment(provider, question)
    except ProviderError as error:
        assert error.status == "malformed_answer"
    else:
        raise AssertionError("A duplicate probability should fail validation")

    def stub(payload):
        message = {"role": "user", "content": payload["message"]}
        calls = [{"tool": "read_decision_rules", "result": question}]
        history = [*payload["history"], message]
        return {"message": f"Turn {len(history)}", "history": history, "calls": calls}

    chats = ChartChats()
    with patch("backend.chart_chat.run_worker", side_effect=stub) as worker:
        first = chats.answer(ChartChatRequest(message="What does WAIT mean?"), None)
        joined = chats.answer(ChartChatRequest(conversation_id=first["conversation_id"], message="Compare"), None)
        new = chats.answer(ChartChatRequest(message="What did I ask before?"), None)
        assert first["message"] == new["message"] == "Turn 1"
        assert joined["message"] == "Turn 2"
        assert joined["calls"][0]["tool"] == "read_decision_rules"
        assert new["conversation_id"] != first["conversation_id"]
        assert worker.call_args.args[0]["history"] == []
    with patch("backend.chart_chat.run_worker", side_effect=ChatUnavailable("Provider offline")):
        try:
            chats.answer(ChartChatRequest(conversation_id=first["conversation_id"], message="Try again"), None)
        except ChatUnavailable:
            pass
        else:
            raise AssertionError("A failed worker should remain an error")
    assert len(chats.conversations[first["conversation_id"]].history) == 2
    print("PASS: response parsing, conversation continuity, fresh chat, and worker failure isolation")


if __name__ == "__main__":
    main()
