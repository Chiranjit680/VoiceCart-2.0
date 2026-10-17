"""
Trace of what goes into the model and what comes out, one block per model call, grouped by turn.

Everything an agent is sent is logged in full (system prompt, the history it was given, tool results),
followed by what it answered (text or tool calls) and how long it took. Written to the console and to
agent/logs/trace.log (rotated). The log contains conversations, so treat it as private.

    AGENT_TRACE=off           turn it off
    AGENT_TRACE_MAX_CHARS=n   cut each message after n characters (default 3000)
"""
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import LLMResult
from langchain_core.runnables import RunnableConfig

from .toolresult import text

LOG_FILE = Path(__file__).resolve().parent / "logs" / "trace.log"
trace_log = logging.getLogger("voicecart.trace")
_configured = False


def enabled() -> bool:
    return os.getenv("AGENT_TRACE", "on").strip().lower() not in {"0", "off", "false", "no"}


def _max_chars() -> int:
    try:
        return max(200, int(os.getenv("AGENT_TRACE_MAX_CHARS", "3000")))
    except ValueError:
        return 3000


def _configure_once() -> None:
    """Send the trace to a rotating file as well as the console (the root logger)."""
    global _configured
    if _configured:
        return
    _configured = True
    LOG_FILE.parent.mkdir(exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    trace_log.addHandler(handler)
    trace_log.setLevel(logging.INFO)


def _cut(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[:limit]} …[+{len(value) - limit} chars]"


def _indent(block: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in block.splitlines() or [""])


def describe_message(message: BaseMessage, limit: int) -> str:
    """One message as '<ROLE>: <content>', including any tool calls an assistant message made."""
    if isinstance(message, SystemMessage):
        label = "SYSTEM"
    elif isinstance(message, HumanMessage):
        label = "USER"
    elif isinstance(message, ToolMessage):
        label = f"TOOL RESULT[{message.name or '?'}]"
    elif isinstance(message, AIMessage):
        label = f"ASSISTANT[{message.name}]" if message.name else "ASSISTANT"
    else:
        label = message.type.upper()

    body = _cut(text(message.content), limit)
    calls = getattr(message, "tool_calls", None) or []
    if calls:
        rendered = "; ".join(f"{c['name']}({c['args']})" for c in calls)
        body = f"{body}\n-> tool calls: {rendered}".strip()
    return f"{label}: {body}" if "\n" not in body else f"{label}:\n{_indent(body, '    ')}"


class TurnTrace:
    """Logs one user turn: the request, every model call it caused, and the final reply."""

    def __init__(self, session_id: str):
        self.tag = session_id[:8]
        self.limit = _max_chars()
        self.calls = 0
        self.started_at = time.perf_counter()
        self.handler = _ModelCallLogger(self)

    def model_for(self, model: BaseChatModel, node: str) -> BaseChatModel:
        """A copy of the model that reports its calls to this trace, labelled with the node that uses it.

        The callback is attached to the model itself rather than passed in the run config, because the
        agent framework calls its model without a config, so on Python 3.10 a config callback never
        reaches those calls. The copy shares the original's HTTP client.
        """
        return model.model_copy(
            update={
                "callbacks": [*(model.callbacks or []), self.handler],
                "metadata": {**(model.metadata or {}), "agent": node},
            }
        )

    def start(self, user_id: str, turn_number: int, said: str) -> None:
        bar = "=" * 100
        trace_log.info("\n%s\nTURN %d | user %s | session %s\nUSER SAID: %s\n%s", bar, turn_number, user_id, self.tag, said, bar)

    def finish(self, reply: str, products: List[dict]) -> None:
        names = ", ".join(p.get("name", "?") for p in products) or "none"
        trace_log.info(
            "[%s] TURN DONE in %.1fs | %d model call(s)\n    REPLY SENT TO USER: %s\n    PRODUCT CARDS: %s\n%s",
            self.tag, time.perf_counter() - self.started_at, self.calls, _cut(reply, self.limit), names, "=" * 100,
        )

    def fail(self, error: str) -> None:
        trace_log.info("[%s] TURN FAILED after %.1fs | %s\n%s", self.tag, time.perf_counter() - self.started_at, error, "=" * 100)


class _ModelCallLogger(BaseCallbackHandler):
    run_inline = True  # log in call order, on the event loop

    def __init__(self, turn: TurnTrace):
        self.turn = turn
        self.running: Dict[UUID, tuple] = {}

    def on_chat_model_start(self, serialized, messages: List[List[BaseMessage]], *, run_id: UUID, metadata=None, **kwargs):
        self.turn.calls += 1
        number = self.turn.calls
        meta = metadata or {}
        node = meta.get("agent") or meta.get("langgraph_node") or "?"
        self.running[run_id] = (number, node, time.perf_counter())

        sent = messages[0] if messages else []
        lines = [f"[{self.turn.tag}] MODEL CALL #{number} | {node} | {meta.get('ls_model_name', '')} | sent {len(sent)} message(s)"]
        lines += [_indent(describe_message(m, self.turn.limit)) for m in sent]
        trace_log.info("\n".join(lines))

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs):
        number, node, t0 = self.running.pop(run_id, (0, "?", time.perf_counter()))
        message: Optional[Any] = None
        if response.generations and response.generations[0]:
            message = getattr(response.generations[0][0], "message", None)
        reply = describe_message(message, self.turn.limit) if message is not None else "(no message)"
        usage = getattr(message, "usage_metadata", None) or {}
        tokens = f" | tokens in/out {usage.get('input_tokens', '?')}/{usage.get('output_tokens', '?')}" if usage else ""
        trace_log.info("[%s] MODEL REPLY #%d | %s | %.1fs%s\n%s", self.turn.tag, number, node, time.perf_counter() - t0, tokens, _indent(reply))

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs):
        number, node, t0 = self.running.pop(run_id, (0, "?", time.perf_counter()))
        trace_log.info("[%s] MODEL ERROR #%d | %s | %.1fs | %s: %s", self.turn.tag, number, node, time.perf_counter() - t0, type(error).__name__, error)


def new_turn_trace(session_id: str) -> Optional[TurnTrace]:
    """A trace for one turn, or None when tracing is switched off."""
    if not enabled():
        return None
    _configure_once()
    return TurnTrace(session_id)


def note(config: RunnableConfig, message: str) -> None:
    """A line in the trace for a decision made without a model call (e.g. the supervisor hitting its step limit)."""
    if not enabled():
        return
    session = str((config.get("configurable") or {}).get("thread_id", "?"))[:8]
    trace_log.info("[%s] %s", session, message)
