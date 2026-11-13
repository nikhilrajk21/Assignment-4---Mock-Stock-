"""Small HTTP client for the OpenAI Decisions API."""

import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = "gpt-6-luna"
ENDPOINT = "https://api.openai.com/v1/decisions"
ACTIONS = {
    "buy": "Add the configured number of shares to the paper position.",
    "sell": "Reduce the paper position by the configured number of shares.",
    "hold": "Keep an existing paper position.",
    "wait": "Stay in cash with no open position.",
    "close": "Exit the entire paper position.",
}


class ProviderError(RuntimeError):
    def __init__(self, status: str, detail: str):
        super().__init__(detail)
        self.status = status


def action_question() -> dict:
    return {
        "type": "choice",
        "name": "action",
        "instructions": (
            "Propose one action for the simulated account using only the frozen snapshot. "
            "Consider its signal, cash, and share count. The order size applies to buy and sell."
        ),
        "choices": [
            {"value": value, "description": description} for value, description in ACTIONS.items()
        ],
    }


def ask_decisions(
    snapshot: dict, questions: list[dict], *, image_data: str | None = None,
    additional_images: list[str] | None = None, timeout: float = 15
) -> dict:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ProviderError("provider_unconfigured", "The backend has no OpenAI API key.")

    content = [{"type": "input_json", "data": snapshot}]
    if image_data is not None:
        content.append({"type": "input_image", "image_url": image_data})
    for image in additional_images or []:
        content.append({"type": "input_image", "image_url": image})

    request = Request(
        ENDPOINT,
        data=json.dumps({
            "model": MODEL, "input": [{"role": "user", "content": content}], "questions": questions,
        }, allow_nan=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as error:
        error.close()
        raise ProviderError("provider_error", f"OpenAI Decisions returned HTTP {error.code}.") from None
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise ProviderError("timeout", "The Decisions request timed out.") from None
        raise ProviderError("provider_error", "Could not reach the Decisions API.") from None
    except TimeoutError:
        raise ProviderError("timeout", "The Decisions request timed out.") from None
    except (ValueError, UnicodeError):
        raise ProviderError("malformed_answer", "The Decisions response was not valid JSON.") from None

    if (not isinstance(result, dict) or not isinstance(result.get("model"), str)
            or not isinstance(result.get("answers"), list)):
        raise ProviderError("malformed_answer", "The Decisions response lacks a model or answers.")
    return result
