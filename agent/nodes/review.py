"""Review specialist: reads product reviews and manages the shopper's own."""
from ..prompts import VOICE_RULES
from .base import tool_agent

PROMPT = (
    "You are VoiceCart's review specialist. Read a product's reviews and summarise what people say, or write, edit "
    "and delete the user's own reviews. Ratings are whole numbers from 1 to 5. If you need a product id, find it "
    "with search_products."
)

SPEC = tool_agent(
    name="review",
    prompt=PROMPT + VOICE_RULES,
    tool_names=(
        "get_product_reviews", "get_user_reviews", "create_review", "update_review", "delete_review", "search_products",
    ),
)
