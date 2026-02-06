# agent/orchestrator.py

import sys
import os
import json
import logging
import uuid

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage, AIMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_agent
from typing import TypedDict, List, Dict, Any
from pydantic import BaseModel, Field

# Import your existing tools
from tools import (
    add_to_cart,
    search_products,
    remove_from_cart,
    get_user_cart,
    checkout_cart,
    view_orders,
    create_order
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  Pydantic Schemas
# ═══════════════════════════════════════════════════════════════

class RouterOutput(BaseModel):
    """Router decision output"""
    next_agent: str = Field(description="SHOPPING_LIST_AGENT, CART_AGENT, or END")
    reasoning: str = Field(default="", description="Routing reasoning")


class ShoppingResponse(BaseModel):
    """Shopping agent response"""
    products: List[Dict] = Field(default_factory=list)
    message: str = Field(default="")


# ═══════════════════════════════════════════════════════════════
#  Agent State
# ═══════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    """Shared state across all agents"""
    user_id: int
    session_id: str
    thread_id: str
    current_agent: str
    intent: str
    next_agent: str
    messages: List
    response: str
    products: List[Dict] | None
    cart: Dict | None


# ═══════════════════════════════════════════════════════════════
#  Agent Nodes
# ═══════════════════════════════════════════════════════════════

def router_node(state: AgentState) -> AgentState:
    """Router: Classifies intent and directs traffic"""
    messages = state["messages"]
    last_message = messages[-1].content if messages else ""
    
    try:
        llm = ChatOllama(model="mistral:7b", temperature=0)
        structured_llm = llm.with_structured_output(RouterOutput)
    except Exception as e:
        logger.warning(f"Ollama failed: {e}")
        # Fallback: manual parsing
        llm = ChatOllama(model="llama3:8b", temperature=0)
        structured_llm = None
    
    system_prompt = """You are a routing agent for an e-commerce assistant.

Available agents:
1. SHOPPING_LIST_AGENT: Product search, browsing, finding items
2. CART_AGENT: Add/remove items, view cart, checkout, orders
3. END: Greeting or finished conversation

Classify the user's intent and route accordingly."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}")
    ])
    
    try:
        if structured_llm:
            chain = prompt | structured_llm
            response: RouterOutput = chain.invoke({"input": last_message})
            next_agent = response.next_agent
            reasoning = response.reasoning
        else:
            # Fallback parsing
            chain = prompt | llm
            response = chain.invoke({"input": last_message})
            content = response.content.upper()
            
            if "SHOPPING" in content or "SEARCH" in content:
                next_agent = "SHOPPING_LIST_AGENT"
                reasoning = "Detected search intent"
            elif "CART" in content or "ADD" in content or "CHECKOUT" in content:
                next_agent = "CART_AGENT"
                reasoning = "Detected cart intent"
            else:
                next_agent = "SHOPPING_LIST_AGENT"
                reasoning = "Default routing"
    except Exception as e:
        logger.error(f"Router error: {e}")
        next_agent = "SHOPPING_LIST_AGENT"
        reasoning = f"Error fallback: {str(e)}"
    
    logger.info(f"🚦 Router → {next_agent} ({reasoning})")
    
    state["next_agent"] = next_agent
    state["current_agent"] = "router"
    
    return state


def shopping_list_agent_node(state: AgentState) -> AgentState:
    """Shopping List Agent: Product search and discovery"""
    user_id = state["user_id"]
    messages = state["messages"]
    user_input = messages[-1].content if messages else ""
    
    llm = ChatOllama(model="mistral:7b", temperature=0)
    
    system_prompt = """You are a shopping assistant helping users find products.

Available tools:
- search_products(query: str) -> Returns JSON list of products
- add_to_cart(user_id: int, product_id: int, quantity: int) -> Adds to cart

Be friendly and helpful. Show product details clearly."""

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=[search_products, add_to_cart]
    )
    
    try:
        result = agent.invoke({"messages": [HumanMessage(content=user_input)]})
        
        # Extract response
        result_messages = result.get("messages", [])
        response = ""
        products = []
        
        if result_messages:
            last_msg = result_messages[-1]
            response = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
            
            # Try to extract product data from tool results
            for msg in result_messages:
                content = msg.content if hasattr(msg, 'content') else str(msg)
                if isinstance(content, str) and content.strip().startswith('['):
                    try:
                        products = json.loads(content)
                    except:
                        pass
        
        state["response"] = response or "I found some products for you!"
        state["current_agent"] = "shopping_list_agent"
        if products:
            state["products"] = products
        
        logger.info(f"🛍️ Shopping Agent: Found {len(products)} products")
        
    except Exception as e:
        logger.error(f"Shopping agent error: {e}")
        state["response"] = "I had trouble searching. Please try again."
        state["current_agent"] = "shopping_list_agent"
    
    return state


def cart_agent_node(state: AgentState) -> AgentState:
    """Cart Agent: Manages shopping cart operations"""
    user_id = state["user_id"]
    messages = state["messages"]
    user_input = messages[-1].content if messages else ""
    
    llm = ChatOllama(model="mistral:7b", temperature=0)
    
    system_prompt = f"""You are a cart management assistant. User ID: {user_id}

Available tools:
- add_to_cart(user_id, product_id, quantity) -> Adds product
- remove_from_cart(user_id, product_id, quantity) -> Removes product
- get_user_cart(user_id) -> Returns cart as JSON
- search_products(query) -> Finds products
- checkout_cart(user_id) -> Processes checkout
- create_order(user_id) -> Creates order from cart

Always confirm actions clearly."""

    agent = create_agent(
        llm,
        system_prompt=system_prompt,
        tools=[
            add_to_cart,
            remove_from_cart,
            get_user_cart,
            search_products,
            checkout_cart,
            create_order
        ]
    )
    
    try:
        result = agent.invoke({"messages": [HumanMessage(content=user_input)]})
        
        # Extract response
        result_messages = result.get("messages", [])
        response = ""
        cart_data = None
        
        if result_messages:
            last_msg = result_messages[-1]
            response = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
            
            # Try to extract cart data
            for msg in result_messages:
                content = msg.content if hasattr(msg, 'content') else str(msg)
                if isinstance(content, str) and '"product_id"' in content:
                    try:
                        cart_data = json.loads(content)
                    except:
                        pass
        
        state["response"] = response or "Cart operation completed!"
        state["current_agent"] = "cart_agent"
        if cart_data:
            state["cart"] = cart_data
        
        logger.info(f"🛒 Cart Agent: {response[:100]}...")
        
    except Exception as e:
        logger.error(f"Cart agent error: {e}")
        state["response"] = "I had trouble with your cart. Please try again."
        state["current_agent"] = "cart_agent"
    
    return state


# ═══════════════════════════════════════════════════════════════
#  Routing Function
# ═══════════════════════════════════════════════════════════════

def route_from_router(state: AgentState) -> str:
    """Route from router to appropriate agent"""
    next_agent = state.get("next_agent", "SHOPPING_LIST_AGENT")
    
    if next_agent == "SHOPPING_LIST_AGENT":
        return "shopping_list_agent"
    elif next_agent == "CART_AGENT":
        return "cart_agent"
    elif next_agent == "END":
        return "END"
    
    return "shopping_list_agent"


# ═══════════════════════════════════════════════════════════════
#  Build Workflow
# ═══════════════════════════════════════════════════════════════

def build_workflow() -> StateGraph:
    """Build the LangGraph workflow"""
    
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("shopping_list_agent", shopping_list_agent_node)
    workflow.add_node("cart_agent", cart_agent_node)
    
    # Entry point
    workflow.add_edge(START, "router")
    
    # Router routes to agents
    workflow.add_conditional_edges(
        "router",
        route_from_router,
        {
            "shopping_list_agent": "shopping_list_agent",
            "cart_agent": "cart_agent",
            "END": END
        }
    )
    
    # Agents can loop back to router or end
    workflow.add_edge("shopping_list_agent", END)
    workflow.add_edge("cart_agent", END)
    
    return workflow.compile(checkpointer=MemorySaver())


# Compile the workflow once
app = build_workflow()


# ═══════════════════════════════════════════════════════════════
#  Agent Executor (for voice API)
# ═══════════════════════════════════════════════════════════════

class VoiceCartOrchestrator:
    """Orchestrator for voice interactions"""
    
    def __init__(self):
        self.app = app
    
    async def process_message(
        self,
        message: str,
        session_id: str,
        user_id: int = 100000,
        thread_id: str = None
    ) -> Dict[str, Any]:
        """Process user message and return response"""
        
        if not thread_id:
            thread_id = str(uuid.uuid4())
        
        logger.info(f"📥 Processing: {message} (session: {session_id})")
        
        initial_state: AgentState = {
            "user_id": user_id,
            "session_id": session_id,
            "thread_id": thread_id,
            "current_agent": "router",
            "intent": "",
            "next_agent": "",
            "messages": [HumanMessage(content=message)],
            "response": "",
            "products": None,
            "cart": None
        }
        
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            # Run workflow (async invoke)
            result = await self.app.ainvoke(initial_state, config)
            
            response_text = result.get("response", "")
            if not response_text:
                response_text = "I'm here to help! What would you like?"
            
            return {
                "response": response_text,
                "session_id": session_id,
                "thread_id": thread_id,
                "agent_used": result.get("current_agent"),
                "intent": result.get("intent"),
                "products": result.get("products"),
                "cart": result.get("cart"),
                "state": result
            }
            
        except Exception as e:
            logger.error(f"❌ Orchestrator error: {e}", exc_info=True)
            return {
                "response": "I apologize, I encountered an error. Please try again.",
                "session_id": session_id,
                "thread_id": thread_id,
                "error": str(e)
            }


# ═══════════════════════════════════════════════════════════════
#  CLI Executor (for testing)
# ═══════════════════════════════════════════════════════════════

class AgentExecutor:
    """CLI executor for testing without voice"""
    
    def __init__(self, user_id: int = 100000):
        self.app = app
        self.user_id = user_id
    
    def invoke(self, user_input: str) -> str:
        """Synchronous invoke for CLI"""
        initial_state: AgentState = {
            "user_id": self.user_id,
            "session_id": str(uuid.uuid4()),
            "thread_id": str(uuid.uuid4()),
            "current_agent": "router",
            "intent": "",
            "next_agent": "",
            "messages": [HumanMessage(content=user_input)],
            "response": "",
            "products": None,
            "cart": None
        }
        
        final_state = self.app.invoke(
            initial_state,
            config={"configurable": {"thread_id": initial_state["thread_id"]}}
        )
        return final_state.get("response", "No response")


# ═══════════════════════════════════════════════════════════════
#  CLI Testing
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 VoiceCart Agent Test")
    print("="*60)
    
    executor = AgentExecutor(user_id=123)
    
    tests = [
        "Show me laptops",
        "Add product 1 to my cart",
        "What's in my cart?",
    ]
    
    for msg in tests:
        print(f"\n👤 User: {msg}")
        response = executor.invoke(msg)
        print(f"🤖 Agent: {response}")
        print("-"*60)