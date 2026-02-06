import sys
import os
import json
import logging

# Add project root to sys.path BEFORE backend imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from dotenv import load_dotenv
load_dotenv()

from fastapi import HTTPException
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain.agents import create_agent
from langchain_core.tools import tool
from typing import TypedDict, Dict, List
from pydantic import BaseModel, Field
from schemas import ShoppingResponse, RouterOutput
from langchain_ollama import ChatOllama

try:
    from backend.app import models, schemas, database
    from backend.app.routers import cart, product, categories, search
except ImportError:
    print("Warning: Could not import backend modules. Make sure to run this script from the project root and that the backend is properly set up.")
    database = None
    schemas = None
    models = None

logger = logging.getLogger(__name__)
Ollama_llm = ChatOllama(model="llama3:8b", temperature=0)
class AgentState(TypedDict):
    user_id: int
    session_id: str
    thread_id: str
    current_agent: str
    intent: str
    next_agent: str
    messages: List[BaseMessage]
    response: str

#tools ------------------------------------------------------------------------------------------------------------>


@tool
def add_to_cart(user_id: int, product_id: int, quantity: int = 1) -> str:
    """Add a product to the user's cart.

    If the product already exists in the cart, the quantity is increased.
    If the product does not exist in the cart, a new cart entry is created.

    Args:
        user_id: The ID of the user whose cart to modify.
        product_id: The ID of the product to add.
        quantity: The number of units to add (default 1).

    Returns:
        A string message describing the result of the operation.
    """
    db = database.SessionLocal()
    try:
        cart_item = schemas.CartCreate(product_id=product_id, quantity=quantity)
        result = cart.add_product_to_cart(cart_item=cart_item, db=db, user_id=user_id)
        return f"Added product {product_id} (x{quantity}) to the cart. Current quantity: {result.quantity}."
    except HTTPException as e:
        return f"Error: {e.detail}"
    except Exception as e:
        db.rollback()
        logger.error(f"add_to_cart failed: {e}")
        return f"Error: Failed to add product to cart — {e}"
    finally:
        db.close()
        
        
@tool
def search_products(query: str) -> str:
    """Search for products based on a query string.

    Args:
        query: The search query to find matching products.
        
    Returns:
        A string representation of the search results, including product names and IDs."""
    db = database.SessionLocal()
    try:
        results = search.search_products(query=query, db=db)
        if not results:
            return f"No products found matching '{query}'."
        return json.dumps([{"id": p.id, "name": p.name, "price": float(p.price), "stock": p.stock} for p in results])
    except Exception as e:
        logger.error(f"search_products failed: {e}")
        return f"Error: Failed to search products — {e}"
    finally:
        db.close()
@tool
def remove_from_cart(user_id: int, product_id: int, quantity: int =1) -> str:
    """Remove a product from the user's cart.

    If the quantity to remove is greater than or equal to the current quantity, the item is removed entirely.
    Otherwise, the quantity is decreased by the specified amount.

    Args:
        user_id: The ID of the user whose cart to modify.
        product_id: The ID of the product to remove.
        quantity: The number of units to remove (default 1).
        """
    db = database.SessionLocal()
    try:
        result = cart.remove_product_from_cart(product_id=product_id, quantity=quantity, db=db, user_id=user_id)
        if result is None:
            return f"Product {product_id} not found in the cart."
        return f"Removed product {product_id} (x{quantity}) from the cart. Current quantity: {result.quantity}."
    except HTTPException as e:
        return f"Error: {e.detail}"
    except Exception as e:
        db.rollback()
        logger.error(f"remove_from_cart failed: {e}")
        return f"Error: Failed to remove product from cart — {e}"
    finally:
        db.close()
@tool
def get_user_cart(user_id: int) -> str:
    """Retrieve the contents of the user's cart.

    Args:
        user_id: The ID of the user whose cart to retrieve.

    Returns:
        A string representation of the cart contents, including product names, quantities, and prices.
    """
    db = database.SessionLocal()
    try:
        cart_items = cart.get_cart_items(db=db, user_id=user_id)
        if not cart_items:
            return "Your cart is empty."
        cart_details = []
        for item in cart_items:
            product = product.get_product_by_id(db=db, product_id=item.product_id)
            if product:
                cart_details.append({
                    "product_id": product.id,
                    "name": product.name,
                    "quantity": item.quantity,
                    "price_per_unit": float(product.price),
                    "total_price": float(product.price) * item.quantity
                })
        return json.dumps(cart_details)
    except Exception as e:
        logger.error(f"get_user_cart failed: {e}")
        return f"Error: Failed to retrieve cart — {e}"
    finally:
        db.close()






#______________________________________________________________________________________________
def cart_agent(state: AgentState):
    """LangGraph node for managing the shopping cart.

    Reads user_input from state messages, invokes the cart agent,
    and returns a state update dict.
    """
    user_id = state["user_id"]
    messages = state["messages"]
    user_input = messages[-1].content if messages else ""

    llm = Ollama_llm
    system_prompt = """You are a shopping cart management agent. Your task is to help users manage their shopping carts by adding, removing, and viewing products. Use the provided tools to perform actions on the cart.

    Available tools:
    1. add_to_cart(user_id: int, product_id: int, quantity: int = 1) -> str
       - Adds a specified quantity of a product to the user's cart.
    2. remove_from_cart(user_id: int, product_id: int, quantity: int = 1) -> str
       - Removes a specified quantity of a product from the user's cart.
    3. get_user_cart(user_id: int) -> str
       - Retrieves the current contents of the user's cart.
    4. search_products(query: str) -> str
       - Searches for products based on a query string.

    Always respond in JSON format:
    {{
        "action": "add_to_cart" | "remove_from_cart" | "get_user_cart" | "search_products",
        "parameters": {{
            // parameters required for the action
        }}
    }}
    """
    agent = create_agent(llm, system_prompt=system_prompt, tools=[add_to_cart, remove_from_cart, get_user_cart, search_products])
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]}
    )

    # Extract the response from the last AI message
    result_messages = result.get("messages", [])
    response = ""
    if result_messages:
        response = result_messages[-1].content if hasattr(result_messages[-1], 'content') else str(result_messages[-1])

    return {"current_agent": "cart_agent", "response": response}

def shopping_list_agent(state: AgentState):
    """LangGraph node for generating shopping lists based on user input.

    Reads user_input from state messages, invokes the shopping list agent,
    and returns a state update dict.
    """
    user_id = state["user_id"]
    messages = state["messages"]
    user_input = messages[-1].content if messages else ""

    llm = Ollama_llm
    system_prompt = """You are a shopping list generation agent. Your task is to help users create shopping lists based on their preferences and needs. Use the provided tools to perform actions related to product search and cart management.

    Available tools:
    1. search_products(query: str) -> str
       - Searches for products based on a query string.

    """
    output_parser = JsonOutputParser(pydantic_object=ShoppingResponse)
    agent = create_agent(llm, system_prompt=system_prompt, tools=[search_products, add_to_cart])
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]}
    )

    # Extract the response from the last AI message
    result_messages = result.get("messages", [])
    response = ""
    if result_messages:
        response = result_messages[-1].content if hasattr(result_messages[-1], 'content') else str(result_messages[-1])

    return {"current_agent": "shopping_list_agent", "response": response}
def router_node(state: AgentState):
    """
    Router Node: Classifies intent and directs traffic.
    """
    messages = state["messages"]
    last_message = messages[-1].content
    
    llm = Ollama_llm
    
    # Use structured output for reliability (Native Gemini feature)
    structured_llm = llm.with_structured_output(RouterOutput)
    
    system_prompt = """You are a request routing agent. Classify user intents.
    
    Available agents:
    1. SHOPPING_LIST_AGENT: Searching products, finding items, browsing.
    2. CART_AGENT: Adding/Removing items, viewing cart, checkout.
    3. END: If the conversation is just a greeting or already finished.
    """
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}")
    ])
    
    chain = prompt | structured_llm
    
    try:
        response: RouterOutput = chain.invoke({"input": last_message})
        next_agent = response.next_agent
        reasoning = response.reasoning
    except Exception as e:
        logger.error(f"Router parsing failed: {e}")
        next_agent = "CART_AGENT" # Default fallback
        reasoning = "Error parsing"

    logger.info(f"🚦 Router: {next_agent} ({reasoning})")
    
    return {"next_agent": next_agent}

def route_from_router(state: AgentState) -> str:
    """Route from router to the correct specialized agent."""
    next_agent = state["next_agent"]
    if next_agent == "SHOPPING_LIST_AGENT":
        return "shopping_list_agent"
    elif next_agent == "CART_AGENT":
        return "cart_agent"
    return "END"


workflow = StateGraph(AgentState)
workflow.add_node("router", router_node)
workflow.add_node("shopping_list_agent", shopping_list_agent)
workflow.add_node("cart_agent", cart_agent)
workflow.add_edge(START, "router")
workflow.add_conditional_edges(
    "router",
    route_from_router,
    {
        "shopping_list_agent": "shopping_list_agent",
        "cart_agent": "cart_agent",
        "END": END
    }
)
workflow.add_edge("shopping_list_agent", "router")
workflow.add_edge("cart_agent", "router")
app = workflow.compile()

class AgentExecutor:
    def __init__(self, user_id: int = 0):
        self.app = app  # reuse the already-compiled graph
        self.user_id = user_id

    def invoke(self, user_input: str) -> str:
        """Run the full agent graph for a single user message.

        LangGraph's app.invoke() drives the graph from START to END
        automatically — no manual loop needed.
        """
        initial_state: AgentState = {
            "user_id": self.user_id,
            "session_id": "",
            "thread_id": "",
            "current_agent": "router",
            "intent": "",
            "next_agent": "",
            "messages": [HumanMessage(content=user_input)],
            "response": "",
        }
        # invoke() runs the entire graph and returns the final state
        final_state = self.app.invoke(initial_state)
        return final_state["response"]
# Example usage:
if __name__ == "__main__":
    agent_executor = AgentExecutor(user_id=123)
    user_input = "I want to buy some fruits and add them to my cart."
    response = agent_executor.invoke(user_input)
    print("Final Response:", response)