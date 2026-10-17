"""Product specialist: finds and describes products."""
from ..prompts import CARDS_RULES, VOICE_RULES
from .base import tool_agent

PROMPT = (
    "You are VoiceCart's product specialist. Help the user find products and answer questions about them using the "
    "catalog tools. Prefer search_products for anything the user describes in words, using price filters when they "
    "give a budget; use get_product for details and get_product_stock for availability. You only look things up: "
    "don't say you can't add to the cart, because another specialist does that. Just describe what you found."
)

SPEC = tool_agent(
    name="product",
    prompt=PROMPT + CARDS_RULES + VOICE_RULES,
    tool_names=("search_products", "list_products", "get_product", "get_product_stock", "list_categories", "show_products"),
)
