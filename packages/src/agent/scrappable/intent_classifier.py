from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
import json
import logging
import sys
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


INTENT_SYSTEM_PROMPT = """You are a voice-based shopping cart assistant.
Your job is to classify user intents based on their input.

Classify into exactly ONE of these intents:
- add_to_cart: User wants to add a product to their cart.
- remove_from_cart: User wants to remove a product from their cart.
- update_cart: User wants to update the quantity of a product in their cart.
- search_product: User wants to search for a product.
- generate_shopping_list: User wants to generate a shopping list.

Return ONLY valid JSON (no markdown fences):
{{"intent": "<intent_name>"}}"""


def classify_intent(user_input: str) -> Dict[str, str]:
    """Classify the user's intent based on their input.

    Args:
        user_input: The raw input from the user.

    Returns:
        A dictionary containing the classified intent.
    """
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
    resp = llm.invoke([
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=user_input),
    ])
    try:
        return json.loads(_strip_code_fences(resp.content))
    except json.JSONDecodeError:
        return {"intent": resp.content.strip()}


class IntentClassifier:
    """Reusable intent classifier (keeps a warm LLM handle)."""

    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)

    def __call__(self, user_input: str) -> Dict[str, str]:
        """Classify the user's intent based on their input."""
        resp = self.llm.invoke([
            SystemMessage(content=INTENT_SYSTEM_PROMPT),
            HumanMessage(content=user_input),
        ])
        try:
            return json.loads(_strip_code_fences(resp.content))
        except json.JSONDecodeError:
            return {"intent": resp.content.strip()}


# Keep old name as alias for backward compat
Intent_classifier = IntentClassifier


if __name__ == "__main__":
    classifier = IntentClassifier()
    user_input = "I want to add a new phone to my cart."
    intent = classifier(user_input)
    print(intent.get("intent"))