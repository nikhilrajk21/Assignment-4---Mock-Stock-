"""Keep short chart conversations and call the isolated Agents SDK worker."""

from collections import OrderedDict
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.decisions import DecisionRequest

ROOT = Path(__file__).resolve().parent.parent


class ChartChatRequest(BaseModel):
    conversation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    message: str = Field(min_length=1, max_length=2000)
    capture: DecisionRequest | None = None


class ChatUnavailable(RuntimeError):
    pass


def run_worker(payload: dict) -> dict:
    default = ROOT / '.agent-venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    interpreter = Path(os.environ.get('IST402_AGENT_PYTHON') or default)
    if not interpreter.is_file():
        raise ChatUnavailable('The project’s Agents SDK environment is unavailable.')
    if not os.environ.get('OPENAI_API_KEY', '').strip():
        raise ChatUnavailable('Configure an OpenAI API key on the backend to use chat.')
    try:
        result = subprocess.run(
            [str(interpreter), '-B', '-m', 'backend.agent_worker'], cwd=ROOT,
            input=json.dumps(payload, allow_nan=False), capture_output=True, encoding='utf-8',
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=75, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        if result.returncode:
            raise ChatUnavailable('The chart assistant could not complete this turn.')
        output = json.loads(result.stdout)
    except subprocess.TimeoutExpired as error:
        raise ChatUnavailable('The chart assistant timed out. Try again.') from error
    except (OSError, ValueError) as error:
        raise ChatUnavailable('The chart assistant could not start or returned an invalid result.') from error
    if (not isinstance(output, dict) or not isinstance(output.get('message'), str)
            or not isinstance(output.get('calls'), list) or not isinstance(output.get('history'), list)):
        raise ChatUnavailable('The chart assistant returned an incomplete turn.')
    return output


@dataclass
class Conversation:
    history: list[dict] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)


class ChartChats:
    def __init__(self):
        self.conversations: OrderedDict[str, Conversation] = OrderedDict()
        self.lock = Lock()

    def answer(self, request: ChartChatRequest, prepared: dict | None) -> dict:
        with self.lock:
            identifier = request.conversation_id or uuid4().hex
            if request.conversation_id and identifier not in self.conversations:
                raise KeyError(identifier)
            conversation = self.conversations.setdefault(identifier, Conversation())
            self.conversations.move_to_end(identifier)
            if len(self.conversations) > 32:
                self.conversations.popitem(last=False)
        with conversation.lock:
            output = run_worker({'message': request.message, 'history': conversation.history, 'prepared': prepared})
            # Keep complete user turns so stored tool call/output pairs remain valid.
            history = output['history']
            starts = [i for i, item in enumerate(history) if isinstance(item, dict) and item.get('role') == 'user']
            conversation.history = history[starts[-8]:] if len(starts) >= 8 else history
        return {'conversation_id': identifier, 'message': output['message'], 'calls': output['calls']}
