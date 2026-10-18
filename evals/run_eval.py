"""
Runs the evaluation conversations against the live agent and reports what passed.

    python -m evals.run_eval                  # all 15, from the repo root, with the services running
    python -m evals.run_eval --only checkout,recipe
    python -m evals.run_eval --no-judge       # skip the model-judged rubric lines (regex/state checks only)

Every conversation registers its own throwaway shopper, so the carts and orders it creates belong to nobody real
and cannot affect another conversation. A conversation passes when
every check on every turn passes and every rubric line is judged satisfied. Results go to evals/results/.
"""
import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import httpx
from pydantic import BaseModel, Field

if __package__ in (None, ""):  # started as `python evals/run_eval.py`: put the repo root on the path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from evals.checks import final_problems, turn_problems, voice_problems
    from evals.conversations import CONVERSATIONS
else:
    from .checks import final_problems, turn_problems, voice_problems
    from .conversations import CONVERSATIONS

PRODUCT_SERVICE = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8000").rstrip("/")
AGENT_SERVICE = os.getenv("AGENT_BASE_URL", "http://localhost:8002").rstrip("/")
TURN_TIMEOUT = 150.0
RESULTS_DIR = Path(__file__).parent / "results"


class RubricVerdict(BaseModel):
    line: int = Field(description="Number of the rubric line, starting at 1.")
    satisfied: bool
    reason: str = Field(description="One sentence citing what the assistant said or did.")


class RubricVerdicts(BaseModel):
    verdicts: List[RubricVerdict]


@dataclass
class TurnResult:
    said: str
    reply: str = ""
    cards: List[str] = field(default_factory=list)
    seconds: float = 0.0
    problems: List[str] = field(default_factory=list)


@dataclass
class ConversationResult:
    id: str
    title: str
    turns: List[TurnResult] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)  # conversation-level: end state, rubric, crashes

    @property
    def passed(self) -> bool:
        return not self.problems and not any(t.problems for t in self.turns)


class Shopper:
    """A throwaway account, with helpers to read its cart and orders."""

    def __init__(self):
        self.http = httpx.Client(timeout=15.0)
        stamp = f"{int(time.time())}{uuid.uuid4().hex[:4]}"
        self.email, password = f"eval-{stamp}@voicecart.dev", uuid.uuid4().hex
        created = self.http.post(f"{PRODUCT_SERVICE}/user/register", json={
            "name": "Eval Shopper", "email": self.email, "password": password, "address": "12 Test Street, Pune 411001",
        })
        created.raise_for_status()
        self.user_id = created.json()["id"]
        login = self.http.post(f"{PRODUCT_SERVICE}/user/login", data={"username": self.email, "password": password})
        login.raise_for_status()
        self.auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
        self.sessions: List[str] = []

    def open_session(self) -> str:
        # Open sessions are never reused, so keeping earlier ones open gives each conversation a new one.
        response = self.http.post(f"{PRODUCT_SERVICE}/chat/sessions/open", headers=self.auth)
        response.raise_for_status()
        self.sessions.append(response.json()["id"])
        return self.sessions[-1]

    def cart(self) -> Dict[str, int]:
        response = self.http.get(f"{PRODUCT_SERVICE}/cart/", headers=self.auth)
        if response.status_code == 404:  # the Product Service answers 404 for an empty cart
            return {}
        response.raise_for_status()
        rows = response.json()
        return {row["product"]["name"]: row["quantity"] for row in rows if row.get("product")}

    def clear_cart(self):
        self.http.delete(f"{PRODUCT_SERVICE}/cart/clear", headers=self.auth)

    def order_count(self) -> int:
        response = self.http.get(f"{PRODUCT_SERVICE}/orders/", headers=self.auth)
        if response.status_code == 404:  # no orders yet
            return 0
        response.raise_for_status()
        return len(response.json())

    def say(self, session_id: str, message: str) -> dict:
        response = self.http.post(
            f"{AGENT_SERVICE}/agent/{self.user_id}", json={"msg": message}, timeout=TURN_TIMEOUT,
            headers={**self.auth, "X-Session-Id": session_id},
        )
        response.raise_for_status()
        return response.json()

    def finish(self):
        for session_id in self.sessions:
            try:
                self.http.post(f"{PRODUCT_SERVICE}/chat/sessions/{session_id}/end", json={"reason": "eval"}, headers=self.auth)
            except httpx.HTTPError:
                pass


def run_conversation(shopper: Shopper, spec: dict) -> ConversationResult:
    result = ConversationResult(spec["id"], spec["title"])
    session_id = shopper.open_session()
    orders_before = shopper.order_count()
    for turn in spec["turns"]:
        outcome = TurnResult(said=turn["say"])
        result.turns.append(outcome)
        started = time.time()
        try:
            body = shopper.say(session_id, turn["say"])
        except Exception as exc:  # the agent crashed or timed out: this turn and the rest cannot be judged
            outcome.problems.append(f"no reply: {type(exc).__name__}: {exc}")
            return result
        outcome.seconds = time.time() - started
        outcome.reply = body.get("response", "")
        outcome.cards = [p.get("name", "") for p in body.get("products", [])]
        outcome.problems = [f"voice: {p}" for p in voice_problems(outcome.reply)]
        outcome.problems += turn_problems(
            turn.get("expect", {}), outcome.reply, outcome.cards, shopper.cart(), shopper.order_count() - orders_before
        )
    result.problems += final_problems(spec.get("final"), shopper.cart())
    return result


def judge_rubric(spec: dict, result: ConversationResult) -> List[str]:
    """Ask the model whether each rubric line holds for the transcript. Returns the lines that failed."""
    rubric = spec.get("rubric") or []
    if not rubric or not result.turns or not result.turns[-1].reply:
        return []
    from agent.llm import get_llm  # same endpoint as the agents; loads agent/.env

    transcript = "\n".join(f"Shopper: {t.said}\nAssistant: {t.reply}" + (f"\n[product cards shown: {', '.join(t.cards)}]" if t.cards else "")
                           for t in result.turns)
    lines = "\n".join(f"{i}. {line}" for i, line in enumerate(rubric, 1))
    judge = get_llm().with_structured_output(RubricVerdicts, method="function_calling")
    verdicts = judge.invoke([
        ("system", "You grade a voice shopping assistant's conversation against a checklist. "
                   "Judge only from the transcript. A line is satisfied if the transcript does not contradict it "
                   "and shows it where it applies. Be strict about invented products, prices and actions."),
        ("human", f"Transcript:\n{transcript}\n\nChecklist:\n{lines}\n\nGive one verdict per checklist line."),
    ])
    failed = []
    for v in verdicts.verdicts:
        if not v.satisfied and 1 <= v.line <= len(rubric):
            failed.append(f"rubric: {rubric[v.line - 1]} -- {v.reason}")
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", help="comma-separated conversation ids")
    parser.add_argument("--no-judge", action="store_true", help="skip the model-judged rubric")
    args = parser.parse_args()

    wanted = set(args.only.split(",")) if args.only else None
    specs = [c for c in CONVERSATIONS if not wanted or c["id"] in wanted]
    if wanted and len(specs) != len(wanted):
        unknown = wanted - {c["id"] for c in CONVERSATIONS}
        print(f"Unknown conversation id(s): {', '.join(sorted(unknown))}")
        return 2

    print(f"Evaluating {len(specs)} conversation(s), each with its own throwaway shopper\n")
    results = []
    for spec in specs:
        try:
            shopper = Shopper()  # a new account per conversation, so one conversation's orders never leak into another
        except httpx.HTTPError as exc:
            print(f"Could not set up a shopper at {PRODUCT_SERVICE}: {exc}\nAre the services running (run-all.ps1)?")
            return 2
        try:
            result = run_conversation(shopper, spec)
        finally:
            shopper.finish()
        if not args.no_judge and not any(t.problems for t in result.turns):
            try:
                result.problems += judge_rubric(spec, result)
            except Exception as exc:  # a broken judge must not read as a pass
                result.problems.append(f"rubric could not be judged: {type(exc).__name__}: {exc}")
        results.append(result)
        print(f"{'PASS' if result.passed else 'FAIL'}  {result.id:<24} {sum(t.seconds for t in result.turns):5.1f}s  {result.title}")
        for turn in result.turns:
            for problem in turn.problems:
                print(f"        turn \"{turn.said}\": {problem}")
            if turn.problems:
                print(f"        reply: {turn.reply[:300]}")
        for problem in result.problems:
            print(f"        {problem}")

    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} conversations passed")
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps([{**r.__dict__, "passed": r.passed, "turns": [t.__dict__ for t in r.turns]} for r in results],
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Details: {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
