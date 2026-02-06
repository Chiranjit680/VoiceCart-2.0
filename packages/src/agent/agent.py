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
from typing import TypedDict, Dict, List, Optional
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from sqlalchemy.orm import joinedload
from sqlalchemy import or_

try:
    from backend.app import models, database
    from backend.app.models import Product, Cart, Orders, OrderItem, User, Category, ProductCategory
except ImportError:
    print("Warning: Could not import backend modules. Make sure to run this script from the project root and that the backend is properly set up.")
    database = None
    models = None

# --- Pydantic schemas for structured LLM output ---
class ShoppingResponse(BaseModel):
    """Structured output for shopping list agent."""
    products: List[Dict] = Field(default_factory=list, description="List of product results")
    message: str = Field(default="", description="Response message to the user")

class RouterOutput(BaseModel):
    """Structured output for the router node."""
    next_agent: str = Field(description="The next agent to route to: SHOPPING_LIST_AGENT, CART_AGENT, or END")
    reasoning: str = Field(default="", description="Brief reasoning for the routing decision")

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
        # Check product exists and has stock
        prod = db.query(Product).filter(Product.id == product_id).first()
        if not prod:
            return f"Error: Product {product_id} not found."
        if prod.stock < quantity:
            return f"Error: Insufficient stock for product {product_id}. Available: {prod.stock}."

        # Check if already in cart
        existing = db.query(Cart).filter(
            Cart.product_id == product_id,
            Cart.user_id == user_id
        ).first()

        if existing:
            existing.quantity += quantity
            db.commit()
            db.refresh(existing)
            return f"Added product '{prod.name}' (x{quantity}) to the cart. Current quantity: {existing.quantity}."

        new_item = Cart(user_id=user_id, product_id=product_id, quantity=quantity)
        db.add(new_item)
        db.commit()
        db.refresh(new_item)
        return f"Added product '{prod.name}' (x{quantity}) to the cart. Current quantity: {new_item.quantity}."
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
        words = query.strip().split()
        conditions = []
        for word in words:
            term = f"%{word}%"
            conditions.append(Product.name.ilike(term))
            conditions.append(Product.brand_name.ilike(term))
            conditions.append(Product.description.ilike(term))

        results = db.query(Product).filter(or_(*conditions)).limit(50).all() if conditions else []
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
        cart_item = db.query(Cart).filter(
            Cart.product_id == product_id,
            Cart.user_id == user_id
        ).first()

        if not cart_item:
            return f"Product {product_id} not found in the cart."

        if quantity >= cart_item.quantity:
            db.delete(cart_item)
            db.commit()
            return f"Removed product {product_id} entirely from the cart."
        else:
            cart_item.quantity -= quantity
            db.commit()
            db.refresh(cart_item)
            return f"Removed {quantity} unit(s) of product {product_id}. Remaining quantity: {cart_item.quantity}."
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
        cart_items = db.query(Cart)\
            .options(joinedload(Cart.product))\
            .filter(Cart.user_id == user_id)\
            .all()
        if not cart_items:
            return "Your cart is empty."
        cart_details = []
        for item in cart_items:
            prod = item.product
            if prod:
                cart_details.append({
                    "product_id": prod.id,
                    "name": prod.name,
                    "quantity": item.quantity,
                    "price_per_unit": float(prod.price),
                    "total_price": float(prod.price) * item.quantity
                })
        return json.dumps(cart_details)
    except Exception as e:
        logger.error(f"get_user_cart failed: {e}")
        return f"Error: Failed to retrieve cart — {e}"
    finally:
        db.close()


@tool
def checkout_cart(user_id: int) -> str:
    """Simulate the checkout process for the user's cart.

    Args:
        user_id: The ID of the user whose cart to checkout.
    Returns:
        A string message confirming the checkout and providing a summary of the order.
    """
    
    db = database.SessionLocal()
    try:
        cart_items = db.query(Cart)\
            .options(joinedload(Cart.product))\
            .filter(Cart.user_id == user_id)\
            .all()
        if not cart_items:
            return "Your cart is empty. Add items before checking out."
        
        order_summary = []
        total_cost = 0.0
        
        for item in cart_items:
            prod = item.product
            if prod:
                item_total = float(prod.price) * item.quantity
                total_cost += item_total
                order_summary.append({
                    "product_id": prod.id,
                    "name": prod.name,
                    "quantity": item.quantity,
                    "price_per_unit": float(prod.price),
                    "total_price": item_total
                })
        
        return f"Checkout successful! Order summary: {json.dumps(order_summary)}, Total cost: ${total_cost:.2f}"
    except Exception as e:
        logger.error(f"checkout_cart failed: {e}")
        return f"Error: Failed to checkout — {e}"
    finally:
        db.close()

@tool
def view_orders(user_id: int) -> str:
    """View past orders for the user.

    Args:
        user_id: The ID of the user whose orders to view.
    Returns:
        A string representation of the user's past orders, including order details and statuses.
    """
    db = database.SessionLocal()
    try:
        user_orders = db.query(Orders)\
            .options(
                joinedload(Orders.items).joinedload(OrderItem.product)
            )\
            .filter(Orders.user_id == user_id)\
            .all()
        if not user_orders:
            return "You have no past orders."
        
        order_details = []
        for order in user_orders:
            order_items = []
            for item in order.items:
                prod = item.product
                if prod:
                    order_items.append({
                        "product_id": prod.id,
                        "name": prod.name,
                        "quantity": item.quantity,
                        "price_per_unit": float(item.price),
                        "total_price": float(item.price) * item.quantity
                    })
            order_details.append({
                "order_id": order.id,
                "items": order_items,
                "total_cost": float(order.total_amount),
                "status": order.status
            })
        
        return json.dumps(order_details)
    except Exception as e:
        logger.error(f"view_orders failed: {e}")
        return f"Error: Failed to retrieve orders — {e}"
    finally:
        db.close()
@tool
def create_order(user_id: int) -> str:
    """Create an order from the user's current cart.

    Args:
        user_id: The ID of the user whose order to create.
    Returns:
        A string message confirming the order creation and providing order details.
    """
    db = database.SessionLocal()
    try:
        # 1. Fetch cart items
        cart_items = db.query(Cart).filter(Cart.user_id == user_id).all()
        if not cart_items:
            return "Your cart is empty. Add items before creating an order."

        # 2. Get user address
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return f"Error: User {user_id} not found."
        address = user.address or "No address on file"

        # 3. Calculate total & verify stock
        total_amount = 0.0
        for item in cart_items:
            prod = db.query(Product).filter(Product.id == item.product_id).first()
            if not prod:
                return f"Error: Product {item.product_id} not found."
            if prod.stock < item.quantity:
                return f"Error: Insufficient stock for '{prod.name}'. Available: {prod.stock}."
            total_amount += float(prod.price) * item.quantity

        # 4. Create order
        new_order = Orders(
            user_id=user_id,
            address=address,
            total_amount=total_amount,
            status="Pending"
        )
        db.add(new_order)
        db.flush()  # Get order ID

        # 5. Create order items & reduce stock
        for item in cart_items:
            prod = db.query(Product).filter(Product.id == item.product_id).first()
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price=prod.price
            )
            db.add(order_item)
            prod.stock -= item.quantity
            prod.num_sold += item.quantity

        # 6. Clear cart
        db.query(Cart).filter(Cart.user_id == user_id).delete()

        db.commit()
        return f"Order #{new_order.id} created successfully! Total: ${total_amount:.2f}."
    except Exception as e:
        db.rollback()
        logger.error(f"create_order failed: {e}")
        return f"Error: Failed to create order — {e}"
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