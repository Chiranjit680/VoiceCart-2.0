"""Decides whether something a shopper said belongs in long-term memory."""
from typing import Literal, Sequence

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .models import Turn, Verdict

MAX_TURN_CHARS = 2000

PROMPT = """You manage the long-term memory of a voice shopping assistant for a grocery and general store.
You are shown one thing a shopper said, with the conversation before it. Decide whether it contains
durable personal information that would help serve this shopper in FUTURE conversations.

Save, for example:
- dietary needs and allergies ("I'm vegetarian", "allergic to peanuts")
- brand or product preferences they state as a general habit ("I always buy Amul", "only organic")
- household details ("we are a family of five", "I cook for two")
- where they live or usually get deliveries, and budget habits
- recurring needs ("I buy milk every week")

Do not save:
- one-off requests and commands ("add two of those", "show me milk", "check out")
- questions, confirmations, thanks, greetings, small talk
- a product they merely searched for, without saying anything about themselves
- anything the assistant said (you only see it as context)

If you save something, write it as one short, self-contained sentence about the shopper that makes sense
without the conversation, for example "Is vegetarian." or "Prefers Amul butter." Never invent details: use
only what the shopper actually said. When in doubt, do not save."""


class _Decision(BaseModel):
    remember: bool = Field(description="True only if this contains durable personal information worth saving.")
    memory: str = Field(default="", description="The memory as one short sentence about the shopper. Empty if remember is false.")
    kind: Literal["dietary", "preference", "household", "location", "other"] = "other"


def _label(turn: Turn) -> str:
    return "Shopper" if turn.role == "user" else "Assistant"


class LLMJudge:
    """Asks the same model the agents use (agent/.env) for a structured yes/no with the memory text."""

    def __init__(self, llm=None):
        if llm is None:
            from agent.llm import get_llm  # same endpoint and settings as the agents; also loads agent/.env

            llm = get_llm()
        self._decide = llm.with_structured_output(_Decision, method="function_calling")

    def judge(self, turn: Turn, context: Sequence[Turn]) -> Verdict:
        earlier = "\n".join(f"{_label(t)}: {t.content[:MAX_TURN_CHARS]}" for t in context) or "(nothing)"
        decision: _Decision = self._decide.invoke(
            [
                SystemMessage(PROMPT),
                HumanMessage(f"Earlier in the conversation:\n{earlier}\n\nThe shopper just said:\n{turn.content[:MAX_TURN_CHARS]}"),
            ]
        )
        return Verdict(remember=decision.remember, memory=decision.memory.strip(), kind=decision.kind)
