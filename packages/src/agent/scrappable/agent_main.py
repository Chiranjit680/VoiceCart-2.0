import json
import operator
import uuid
from typing import TypedDict, Annotated, List, Dict

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════════
#  Shared LLM
# ═══════════════════════════════════════════════════════════════
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)


# ═══════════════════════════════════════════════════════════════
#  Agent Metadata
# ═══════════════════════════════════════════════════════════════
class AgentConfig(BaseModel):
    """Describes a registered sub-agent."""
    name: str = Field(..., description="Name of the agent.")
    description: str = Field(..., description="What the agent does.")
    tools: List[str] = Field(default_factory=list, description="Tool names.")


# ═══════════════════════════════════════════════════════════════
#  Graph State  (shared across every node)
# ═══════════════════════════════════════════════════════════════
class AgentState(TypedDict):
    """State shared across all nodes in the VoiceCart graph."""
    messages: Annotated[list, operator.add]   # conversation history (accumulates)
    current_agent: str                         # name of the active agent node
    task_type: str                             # classified intent
    context: dict                              # metadata (user_id, preferences …)
    thread_id: str                             # persistence key
    response: str                              # latest agent response text


# ═══════════════════════════════════════════════════════════════
#  Agent Registry
# ═══════════════════════════════════════════════════════════════
AGENT_REGISTRY: Dict[str, str] = {
    "shopping_list": "Generates shopping lists, checks allergies / budget / vegan status.",
    "cart":          "Manages the shopping cart — add, remove, update items, search products.",
    "order":         "Places orders, tracks order history and delivery status.",
}


# ═══════════════════════════════════════════════════════════════
#  1.  Intent-Classifier Node
# ═══════════════════════════════════════════════════════════════
INTENT_PROMPT = """\
You are an intent classifier for VoiceCart, a voice-based shopping assistant.

Classify the user message into exactly ONE intent:
  shopping_list – generating / managing a shopping list, allergy / budget / vegan checks
  cart          – adding, removing, updating, or viewing cart items; searching products
  order         – placing, tracking, or reviewing orders
  general       – greetings, chitchat, help, or anything else

Return ONLY valid JSON (no markdown fences):
{{"intent": "<shopping_list | cart | order | general>"}}"""


def intent_classifier_node(state: AgentState) -> dict:
    """Classify the latest user message and set *task_type*."""
    last_user_msg = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break

    resp = llm.invoke([
        SystemMessage(content=INTENT_PROMPT),
        HumanMessage(content=last_user_msg),
    ])

    raw = resp.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw[:-3]

    try:
        intent = json.loads(raw.strip()).get("intent", "general")
    except (json.JSONDecodeError, AttributeError):
        intent = "general"

    return {"task_type": intent, "current_agent": intent}


# ═══════════════════════════════════════════════════════════════
#  2.  Shopping-List Agent Node
# ═══════════════════════════════════════════════════════════════
def shopping_list_node(state: AgentState) -> dict:
    # Lazy import to avoid circular dependency
    from shoppinglist_agent import shopping_list_tools, SHOPPING_LIST_SYSTEM_PROMPT

    agent = create_react_agent(
        model=llm,
        tools=shopping_list_tools,
        prompt=SHOPPING_LIST_SYSTEM_PROMPT,
    )
    result = agent.invoke({"messages": state["messages"]})
    last = result["messages"][-1]
    return {
        "messages": [last],
        "response": last.content,
        "current_agent": "shopping_list",
    }


# ═══════════════════════════════════════════════════════════════
#  3.  Cart Agent Node
# ═══════════════════════════════════════════════════════════════
def cart_node(state: AgentState) -> dict:
    # Lazy import to avoid circular dependency
    from cart_agent import cart_tools, get_system_prompt

    user_id = state.get("context", {}).get("user_id", 1)
    agent = create_react_agent(
        model=llm,
        tools=cart_tools,
        prompt=get_system_prompt(user_id),
    )
    result = agent.invoke({"messages": state["messages"]})
    last = result["messages"][-1]
    return {
        "messages": [last],
        "response": last.content,
        "current_agent": "cart",
    }


# ═══════════════════════════════════════════════════════════════
#  4.  Order Agent Node  (placeholder — backend not yet wired)
# ═══════════════════════════════════════════════════════════════
ORDER_PROMPT = (
    "You are VoiceCart's Order Manager. Help the user place orders, "
    "check order status, and view order history. If the backend is not "
    "yet connected, let the user know politely and offer alternatives."
)


def order_node(state: AgentState) -> dict:
    resp = llm.invoke([SystemMessage(content=ORDER_PROMPT), *state["messages"]])
    return {
        "messages": [resp],
        "response": resp.content,
        "current_agent": "order",
    }


# ═══════════════════════════════════════════════════════════════
#  5.  General / Fallback Node
# ═══════════════════════════════════════════════════════════════
GENERAL_PROMPT = (
    "You are VoiceCart, a friendly voice-based shopping assistant. "
    "Respond helpfully to the user's general query, greeting, or question."
)


def general_node(state: AgentState) -> dict:
    resp = llm.invoke([SystemMessage(content=GENERAL_PROMPT), *state["messages"]])
    return {
        "messages": [resp],
        "response": resp.content,
        "current_agent": "general",
    }


# ═══════════════════════════════════════════════════════════════
#  Conditional Router (edge function)
# ═══════════════════════════════════════════════════════════════
def route_by_intent(state: AgentState) -> str:
    intent = state.get("task_type", "general")
    return intent if intent in AGENT_REGISTRY else "general"


# ═══════════════════════════════════════════════════════════════
#  Build & Compile the Graph
#
#         START
#           │
#           ▼
#    intent_classifier
#           │
#     ┌─────┼──────┬──────────┐
#     ▼     ▼      ▼          ▼
#  shopping cart  order     general
#   _list
#     └─────┴──────┴──────────┘
#                  │
#                 END
# ═══════════════════════════════════════════════════════════════
def build_voicecart_graph():
    graph = StateGraph(AgentState)

    # — nodes —
    graph.add_node("intent_classifier", intent_classifier_node)
    graph.add_node("shopping_list",     shopping_list_node)
    graph.add_node("cart",              cart_node)
    graph.add_node("order",             order_node)
    graph.add_node("general",           general_node)

    # — edges —
    graph.add_edge(START, "intent_classifier")

    graph.add_conditional_edges(
        "intent_classifier",
        route_by_intent,
        {
            "shopping_list": "shopping_list",
            "cart":          "cart",
            "order":         "order",
            "general":       "general",
        },
    )

    for node_name in ("shopping_list", "cart", "order", "general"):
        graph.add_edge(node_name, END)

    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


# ═══════════════════════════════════════════════════════════════
#  Compiled Application
# ═══════════════════════════════════════════════════════════════
app = build_voicecart_graph()


def run(user_input: str, thread_id: str | None = None, user_id: int = 1) -> str:
    """Send a user message through the VoiceCart graph and return the response."""
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    result = app.invoke(
        {
            "messages":      [HumanMessage(content=user_input)],
            "current_agent": "",
            "task_type":     "",
            "context":       {"user_id": user_id},
            "thread_id":     thread_id,
            "response":      "",
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    return result.get("response", "No response generated.")


# ═══════════════════════════════════════════════════════════════
#  CLI for quick testing
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("═══ VoiceCart 2.0 ═══")
    thread = str(uuid.uuid4())
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        response = run(user_input, thread_id=thread)
        print(f"\nVoiceCart: {response}")
