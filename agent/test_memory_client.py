"""
Tests for how the agent uses long-term memory. Run from the repo root:  python -m agent.test_memory_client

No services, model or database are needed: the HTTP calls and the graph are replaced by stand-ins.
"""
import asyncio
import sys
import traceback
from types import SimpleNamespace

import httpx
from langchain_core.messages import AIMessage, HumanMessage

from . import main as agent_main
from .memory_client import MAX_MEMORY_CHARS, recall

KEY = "test-key"


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run(coro):
    return asyncio.run(coro)


# --- recall ---

def test_recall_asks_for_the_shoppers_own_memories_with_the_key():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(method=request.method, path=request.url.path, key=request.headers.get("x-memory-key"), body=request.read())
        return httpx.Response(200, json=[{"id": "a", "text": "Is vegetarian.", "kind": "dietary", "created_at": 1.0}])

    memories = run(recall(5, "what's for dinner", key=KEY, url="http://memory", client=mock_client(handler)))
    assert memories == ["Is vegetarian."]
    assert (seen["method"], seen["path"], seen["key"]) == ("POST", "/users/5/search", KEY)
    assert b"what's for dinner" in seen["body"] and b'"k":5' in seen["body"].replace(b" ", b"")


def test_recall_does_nothing_when_memory_is_not_set_up():
    def handler(request):
        raise AssertionError("no request should be made without a key")

    assert run(recall(5, "x", key="", url="http://memory", client=mock_client(handler))) == []


def test_recall_never_breaks_a_reply():
    def server_error(request):
        return httpx.Response(500, text="boom")

    def refused(request):
        raise httpx.ConnectError("refused")

    def timed_out(request):
        raise httpx.ReadTimeout("slow")

    def not_json(request):
        return httpx.Response(200, text="<html>")

    def wrong_key(request):
        return httpx.Response(401, json={"detail": "Missing or wrong memory service key"})

    for handler in (server_error, refused, timed_out, not_json, wrong_key):
        assert run(recall(5, "x", key=KEY, url="http://memory", client=mock_client(handler))) == [], handler.__name__
    assert run(recall("not-a-number", "x", key=KEY, url="http://memory", client=mock_client(server_error))) == []


def test_recall_trims_long_memories_and_drops_blank_ones():
    def handler(request):
        return httpx.Response(200, json=[{"text": "x" * 1000}, {"text": "   "}, {"text": ""}, {}, {"text": " ok "}])

    memories = run(recall(5, "x", key=KEY, url="http://memory", client=mock_client(handler)))
    assert memories == ["x" * MAX_MEMORY_CHARS, "ok"]


# --- check_session ---

class patched_httpx:
    """Makes the agent's own HTTP client answer from `handler` instead of the network."""

    def __init__(self, handler):
        self.handler = handler

    def __enter__(self):
        self.real = agent_main.httpx.AsyncClient
        agent_main.httpx.AsyncClient = lambda **kw: self.real(transport=httpx.MockTransport(self.handler), **kw)

    def __exit__(self, *exc):
        agent_main.httpx.AsyncClient = self.real


def check(handler):
    with patched_httpx(handler):
        return run(agent_main.check_session("sid", "Bearer t"))


def test_check_session_returns_the_verified_owner():
    assert check(lambda r: httpx.Response(200, json={"id": "sid", "ended": False, "user_id": 5})) == (5, None)


def test_check_session_explains_each_refusal_and_gives_no_user():
    for status, words in ((401, "expired"), (404, "no longer available"), (500, "went wrong")):
        user, problem = check(lambda r, s=status: httpx.Response(s, json={"detail": "x"}))
        assert user is None and words in problem, status

    def refused(request):
        raise httpx.ConnectError("refused")

    user, problem = check(refused)
    assert user is None and "not reachable" in problem


def test_check_session_without_an_owner_means_no_memory_but_the_conversation_continues():
    assert check(lambda r: httpx.Response(200, json={"id": "sid", "ended": False})) == (None, None)  # an older Product Service
    assert check(lambda r: httpx.Response(200, json={"id": "sid", "ended": False, "user_id": "5"})) == (None, None)  # not a number


# --- the scoping rule ---

class FakeGraph:
    def __init__(self):
        self.received = None
        self.config = None

    async def aget_state(self, config):
        return SimpleNamespace(values={"messages": []})

    async def ainvoke(self, payload, config):
        self.received, self.config = payload, config
        return {"messages": [HumanMessage("hi"), AIMessage("Hello!", name="product")], "products": []}


class FakeMcp:
    def __init__(self, *args, **kwargs):
        pass

    async def get_tools(self):
        return []


def drive(verified_user, url_user="2", problem=None):
    """Run the real run_agent with stand-ins; returns (response, the fake graph that was run)."""
    graph = FakeGraph()

    async def fake_check(session_id, authorization):
        return verified_user, problem

    async def fake_save(*args, **kw):
        return None

    saved = {name: getattr(agent_main, name) for name in ("check_session", "save_turns", "build_graph", "MultiServerMCPClient", "new_turn_trace")}
    agent_main.check_session, agent_main.save_turns = fake_check, fake_save
    agent_main.build_graph, agent_main.MultiServerMCPClient = (lambda tools, saver, trace=None: graph), FakeMcp
    agent_main.new_turn_trace = lambda session_id: None
    try:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(checkpointer=object())))
        response = run(
            agent_main.run_agent(
                user_id=url_user, body=agent_main.AgentRequest(msg="what's for dinner"), request=request,
                authorization="Bearer t", x_session_id="sid",
            )
        )
    finally:
        for name, value in saved.items():
            setattr(agent_main, name, value)
    return response, graph


def test_the_graph_is_given_the_verified_shopper_not_the_one_in_the_url():
    response, graph = drive(verified_user=5, url_user="2")  # the URL claims shopper 2
    assert graph.config["configurable"]["user_id"] == 5  # the memory node will look up shopper 5's memories only
    assert graph.config["configurable"]["thread_id"] == "sid"
    assert "memories" not in graph.received  # fetching them is the memory node's job, inside the graph
    assert response["response"] == "Hello!"


def test_no_verified_user_means_the_graph_gets_no_shopper():
    response, graph = drive(verified_user=None)
    assert graph.config["configurable"]["user_id"] is None
    assert response["response"] == "Hello!"  # the conversation still works


def test_a_refused_session_stops_before_any_graph_work():
    response, graph = drive(verified_user=None, problem="Your login has expired. Please log in again.")
    assert response == {"response": "Your login has expired. Please log in again."}
    assert graph.received is None


def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
