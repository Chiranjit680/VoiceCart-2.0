"""
Tests for how the graph is wired. Run from the repo root:  python -m agent.test_graph

No services or model are used: the tools and the model are stand-ins. The one real thing here is the MCP
server's list of tools, read straight from mcp_server/server.py.
"""
import asyncio
import importlib.util
import os
import sys
import traceback
from pathlib import Path

os.environ["AGENT_TRACE"] = "off"

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from . import graph as graph_module
from .nodes import base, memory
from .nodes.supervisor import SPECIALIST_NAMES, Route

SERVER_FILE = Path(__file__).resolve().parent.parent / "mcp_server" / "server.py"

# MCP tools that exist but are deliberately NOT given to any agent: admin and account tools, and create_order
# (the order agent uses checkout instead).
NOT_FOR_AGENTS = {
    "login", "register_user", "get_user",
    "create_product", "update_product", "delete_product", "create_category",
    "create_order",
}


def run(coro):
    return asyncio.run(coro)


def mcp_tool_names() -> set:
    spec = importlib.util.spec_from_file_location("voicecart_mcp_server", SERVER_FILE)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    return {tool.name for tool in asyncio.run(server.mcp.list_tools())}


def stub_tool(name: str) -> StructuredTool:
    return StructuredTool.from_function(
        coroutine=lambda **kw: "ok", name=name, description=name, args_schema={"type": "object", "properties": {}}
    )


def needed_tool_names() -> set:
    return {name for spec in graph_module.SPECIALISTS for name in spec.tool_names}


class ScriptedLLM:
    """Stands in for the chat model: the supervisor's structured answers are scripted."""

    def __init__(self, *routes):
        self.routes = list(routes)

    def with_structured_output(self, schema, method=None):
        outer = self

        class Scripted:
            async def ainvoke(self, messages, config=None):
                return outer.routes.pop(0)

        return Scripted()


class patched_graph_parts:
    """Gives build_graph a scripted model, and tool-agents that answer without any model."""

    def __init__(self, llm, answer="Here you go."):
        self.llm, self.answer, self.system_prompts = llm, answer, []

    def __enter__(self):
        self.saved = (graph_module.get_llm, base.create_agent, memory.recall)
        outer = self

        def fake_create(llm, tools):
            class Agent:
                async def ainvoke(self, payload, config=None):
                    outer.system_prompts.append(payload["messages"][0].content)
                    return {"messages": [*payload["messages"], AIMessage(outer.answer)]}

            return Agent()

        async def fake_recall(user_id, query, **kw):
            outer.recalled = (user_id, query)
            return ["Is vegetarian."]

        graph_module.get_llm, base.create_agent, memory.recall = (lambda: self.llm), fake_create, fake_recall
        return self

    def __exit__(self, *exc):
        graph_module.get_llm, base.create_agent, memory.recall = self.saved


def build(llm=None):
    return graph_module.build_graph([stub_tool(n) for n in sorted(needed_tool_names())], InMemorySaver())


# --- structure ---

def test_the_graph_starts_with_the_memory_node_then_the_supervisor():
    with patched_graph_parts(ScriptedLLM()):
        drawn = build().get_graph()
    edges = {(e.source, e.target) for e in drawn.edges}
    assert ("__start__", "memory") in edges and ("memory", "supervisor") in edges
    assert not any(src == "__start__" and dst != "memory" for src, dst in edges)  # nothing runs before memory


def test_the_supervisor_and_every_specialist_are_separate_nodes_wired_to_each_other():
    with patched_graph_parts(ScriptedLLM()):
        drawn = build().get_graph()
    assert set(drawn.nodes) == {"__start__", "__end__", "memory", "supervisor", *SPECIALIST_NAMES}
    edges = {(e.source, e.target) for e in drawn.edges}
    for name in SPECIALIST_NAMES:
        assert ("supervisor", name) in edges, f"supervisor cannot reach {name}"
        assert (name, "supervisor") in edges, f"{name} does not report back to the supervisor"
    assert ("supervisor", "__end__") in edges
    assert not any(src in SPECIALIST_NAMES and dst in SPECIALIST_NAMES for src, dst in edges)  # no direct hand-offs


def test_the_supervisor_can_route_to_exactly_the_specialists_that_exist():
    assert set(SPECIALIST_NAMES) == {spec.name for spec in graph_module.SPECIALISTS}
    assert len(SPECIALIST_NAMES) == len(set(SPECIALIST_NAMES))


# --- tools ---

def test_every_tool_an_agent_needs_is_served_by_the_mcp_server():
    missing = needed_tool_names() - mcp_tool_names()
    assert not missing, f"agents list tools the MCP server does not have: {sorted(missing)}"


def test_no_agent_can_call_admin_or_account_tools():
    forbidden = NOT_FOR_AGENTS & needed_tool_names()
    assert not forbidden, f"agents were given tools they must not have: {sorted(forbidden)}"


def test_every_mcp_tool_is_either_given_to_an_agent_or_deliberately_withheld():
    forgotten = mcp_tool_names() - needed_tool_names() - NOT_FOR_AGENTS
    assert not forgotten, f"new MCP tools no agent can use and nobody decided to withhold: {sorted(forgotten)}"


def test_only_the_product_and_cart_specialists_can_show_cards():
    users = {spec.name for spec in graph_module.SPECIALISTS if "show_products" in spec.tool_names}
    assert users == {"product", "cart"}


def test_no_tool_is_defined_inside_the_agent_package():
    # Every tool an agent can call is served by the MCP server; the agent package only picks from them.
    offenders = []
    for source in sorted(Path(__file__).resolve().parent.rglob("*.py")):
        if source.name.startswith("test_"):
            continue
        text = source.read_text(encoding="utf-8")
        if "@tool" in text or "StructuredTool" in text or "langchain_core.tools import tool" in text:
            offenders.append(source.name)
    assert not offenders, f"tools defined locally in: {offenders}"


def test_a_missing_mcp_tool_is_an_error_not_a_silent_gap():
    with patched_graph_parts(ScriptedLLM()):
        tools = [stub_tool(n) for n in sorted(needed_tool_names() - {"get_recipe"})]
        try:
            graph_module.build_graph(tools, InMemorySaver())
        except graph_module.MissingToolsError as error:
            assert "get_recipe" in str(error) and "Restart the MCP server" in str(error)
        else:
            raise AssertionError("built a graph with a tool missing")


# --- a whole turn through the real graph ---

def test_a_turn_runs_memory_then_supervisor_then_a_specialist_then_the_supervisor_again():
    llm = ScriptedLLM(Route(next="product", task="Find butter."), Route(next="FINISH"))
    with patched_graph_parts(llm, answer="Amul Butter is 285 rupees.") as parts:
        compiled = build()
        config = {"configurable": {"thread_id": "t1", "user_id": 5}}

        async def go():
            order = []
            async for update in compiled.astream(
                {"messages": [HumanMessage("do you have butter")], "hops": 0, "visited": [], "products": []}, config, stream_mode="updates"
            ):
                order.extend(update.keys())
            return order, await compiled.aget_state(config)

        order, final = run(go())

    assert order == ["memory", "supervisor", "product", "supervisor"]
    assert parts.recalled == (5, "do you have butter")  # the verified id from the config, what was just said
    assert "Is vegetarian." in parts.system_prompts[0]  # the specialist was told the memory
    assert "Find butter." in parts.system_prompts[0]  # ...and the supervisor's task
    assert final.values["memories"] == ["Is vegetarian."]
    assert [(m.name, m.content) for m in final.values["messages"] if isinstance(m, AIMessage)] == [("product", "Amul Butter is 285 rupees.")]


def test_a_turn_without_a_verified_shopper_still_works_with_no_memories():
    llm = ScriptedLLM(Route(next="FINISH", reply="Hello!"))
    with patched_graph_parts(llm) as parts:
        compiled = build()
        result = run(compiled.ainvoke(
            {"messages": [HumanMessage("hi")], "hops": 0, "visited": [], "products": []},
            {"configurable": {"thread_id": "t2", "user_id": None}},
        ))
    assert result["memories"] == [] and not hasattr(parts, "recalled")
    assert result["messages"][-1].content == "Hello!"


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
