from typing import Any, Dict, List
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_agents import create_agent
from dotenv import load_dotenv
import os
import json

load_dotenv()

# ── Sample Products Database ────────────────────────────────
products_db = {
    "milk":          {"price": 3.99, "vegan": False},
    "eggs":          {"price": 2.49, "vegan": False},
    "bread":         {"price": 2.99, "vegan": True},
    "cheese":        {"price": 4.99, "vegan": False},
    "butter":        {"price": 3.49, "vegan": False},
    "tofu":          {"price": 2.99, "vegan": True},
    "oat milk":      {"price": 4.49, "vegan": True},
    "chicken":       {"price": 7.99, "vegan": False},
    "rice":          {"price": 1.99, "vegan": True},
    "pasta":         {"price": 1.49, "vegan": True},
    "tomato sauce":  {"price": 2.29, "vegan": True},
    "peanut butter": {"price": 3.99, "vegan": True},
    "almond milk":   {"price": 4.99, "vegan": True},
    "yogurt":        {"price": 3.29, "vegan": False},
    "banana":        {"price": 0.59, "vegan": True},
    "apple":         {"price": 0.99, "vegan": True},
    "spinach":       {"price": 2.49, "vegan": True},
    "salmon":        {"price": 9.99, "vegan": False},
    "ground beef":   {"price": 6.99, "vegan": False},
    "olive oil":     {"price": 5.99, "vegan": True},
}

# ── Allergen Keywords ───────────────────────────────────────
allergen_keywords = {
    "nuts": ["peanut", "almond", "walnut", "cashew", "pecan", "hazelnut", "pistachio", "tree nuts"],
    "dairy": ["milk", "cheese", "butter", "cream", "lactose", "casein", "whey"],
    "gluten": ["wheat", "barley", "rye", "oats", "gluten"],
    "eggs": ["egg", "albumin", "lecithin"],
    "soy": ["soy", "soybean", "tofu", "tempeh"],
    "shellfish": ["shrimp", "crab", "lobster", "shellfish"],
    "fish": ["salmon", "tuna", "cod", "fish"],
    "sesame": ["sesame", "tahini"]
}

# ── Tools ───────────────────────────────────────────────────
@tool
def check_for_allergies(input_data: str) -> str:
    """
    Check if items in shopping list contain any known allergens.
    Args:
        input_data: JSON string with "shopping_list" and "user_allergies"
        Example: {"shopping_list": ["milk", "eggs"], "user_allergies": ["dairy"]}
    """
    try:
        # Try parsing as JSON
        data = json.loads(input_data)
        shopping_list = data.get("shopping_list", [])
        user_allergies = data.get("user_allergies", [])
    except json.JSONDecodeError:
        # Fallback: try to parse input as strings representing lists
        if isinstance(input_data, str):
            # Try to safely evaluate string representation of lists
            import ast
            parts = input_data.split(",", 1)
            if len(parts) == 2:
                try:
                    shopping_list = ast.literal_eval(parts[0].strip())
                    user_allergies = ast.literal_eval(parts[1].strip())
                except (SyntaxError, ValueError):
                    return "Error: Please provide input as JSON with shopping_list and user_allergies."
            else:
                return "Error: Please provide both shopping_list and user_allergies."
    
    if not isinstance(shopping_list, list) or not isinstance(user_allergies, list):
        return "Error: shopping_list and user_allergies must be lists."
    
    warnings = []
    
    for item in shopping_list:
        item_name = str(item).lower()
        item_warnings = []
        for allergy in user_allergies:
            allergy_keywords = allergen_keywords.get(str(allergy).lower(), [])
            for keyword in allergy_keywords:
                if keyword in item_name:
                    item_warnings.append(allergy)
                    break
        if item_warnings:
            warnings.append(f"⚠️ '{item}' may contain: {', '.join(item_warnings)}")
    
    return "ALLERGEN WARNINGS:\n" + "\n".join(warnings) if warnings else "✅ No allergens detected."


@tool 
def check_budget(input_data: str) -> str:
    """
    Check if the total cost of items in the shopping list exceeds the budget.
    Args:
        input_data: JSON string with "shopping_list" and "budget"
        Example: {"shopping_list": ["milk", "eggs"], "budget": 10.5}
    """
    try:
        # Try parsing as JSON
        data = json.loads(input_data)
        shopping_list = data.get("shopping_list", [])
        budget = float(data.get("budget", 0))
    except json.JSONDecodeError:
        # Fallback: try to parse input as strings representing list and number
        if isinstance(input_data, str):
            import ast
            parts = input_data.split(",", 1)
            if len(parts) == 2:
                try:
                    shopping_list = ast.literal_eval(parts[0].strip())
                    budget = float(parts[1].strip())
                except (SyntaxError, ValueError):
                    return "Error: Please provide input as JSON with shopping_list and budget."
            else:
                return "Error: Please provide both shopping_list and budget."
    
    if not isinstance(shopping_list, list):
        return "Error: shopping_list must be a list."
    
    # Convert all items to strings to prevent joining issues
    shopping_list = [str(item) for item in shopping_list]
    
    total_cost = 0.0
    missing_items = []

    for item in shopping_list:
        item_name = item.lower()
        if item_name in products_db:
            total_cost += products_db[item_name]["price"]
        else:
            missing_items.append(item)  # This should be a string now

    if missing_items:
        # Convert any non-string items to strings before joining
        missing_items_str = [str(item) for item in missing_items]
        return f"⚠️ Items not found: {', '.join(missing_items_str)}"

    if total_cost > budget:
        return f"❌ Budget exceeded! Limit: ${budget}, Cost: ${total_cost:.2f}"
    
    return f"✅ Within budget! Limit: ${budget}, Cost: ${total_cost:.2f}"


@tool
def check_vegan_status(input_data: str) -> str:
    """
    Check if items in shopping list are vegan-friendly.
    Args:
        input_data: JSON string or list of items
        Example: {"shopping_list": ["tofu", "oat milk"]} or ["tofu", "oat milk"]
    """
    try:
        # Try parsing as JSON
        data = json.loads(input_data)
        if isinstance(data, dict):
            shopping_list = data.get("shopping_list", [])
        else:
            shopping_list = data
    except json.JSONDecodeError:
        # Fallback: try to parse input as string representation of a list
        if isinstance(input_data, str):
            import ast
            try:
                shopping_list = ast.literal_eval(input_data)
            except (SyntaxError, ValueError):
                return "Error: Please provide input as JSON with shopping_list or as a list."
    
    if not isinstance(shopping_list, list):
        return "Error: shopping_list must be a list."
    
    non_vegan = []
    for item in shopping_list:
        item_name = str(item).lower()
        if item_name in products_db and not products_db[item_name]["vegan"]:
            non_vegan.append(item)
    
    if non_vegan:
        return f"❌ Not Vegan: {', '.join(non_vegan)}"
    return "✅ All items are vegan-friendly."


# ═══════════════════════════════════════════════════════════════
#  Exports for the main VoiceCart graph  (agent_main.py)
# ═══════════════════════════════════════════════════════════════
shopping_list_tools = [check_for_allergies, check_budget, check_vegan_status]

SHOPPING_LIST_SYSTEM_PROMPT = """You are VoiceCart's Shopping-List Agent.

You help users:
1. Generate shopping lists based on meals, dietary needs, and budgets.
2. Check for allergens in shopping items.
3. Verify whether items are vegan-friendly.
4. Ensure budget compliance.
5. Provide helpful, friendly, and concise shopping recommendations.
6. Return final answers in a clear list format.

Use the tools available to you whenever a concrete check is needed."""


class ShoppingListAgent:
    """Standalone wrapper — also usable as a LangGraph node callable."""

    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
        self.agent = create_agent(
            model=self.llm,
            tools=shopping_list_tools,
            prompt=SHOPPING_LIST_SYSTEM_PROMPT,
        )

    def __call__(self, user_input: str) -> str:
        result = self.agent.invoke(
            {"messages": [HumanMessage(content=user_input)]}
        )
        return result["messages"][-1].content


# ── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    agent = ShoppingListAgent()
    response = agent(
        "I want to buy groceries for the week — breakfast, lunch, "
        "and dinner. Budget is $50. I'm allergic to nuts and dairy "
        "and prefer vegan options."
    )
    print(response)
