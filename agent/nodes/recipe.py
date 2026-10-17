"""Recipe specialist: finds recipes and their ingredients (the recipe tools are served by the MCP server)."""
from ..prompts import VOICE_RULES
from .base import tool_agent

PROMPT = (
    "You are VoiceCart's recipe specialist. Find recipes with your tools. search_recipes matches words in dish "
    "names, so search with one or two keywords (e.g. \"apple\", \"crumble\", \"curry\"), not a whole sentence. If "
    "that finds nothing, try recipes_by_ingredient with the main ingredient, then other keywords; make up to 4 "
    "attempts before giving up. Once you pick a recipe, fetch it with get_recipe and tell the user the dish name "
    "and its main ingredients, then offer to build a shopping list for it."
)

SPEC = tool_agent(
    name="recipe",
    prompt=PROMPT + VOICE_RULES,
    tool_names=("search_recipes", "recipes_by_ingredient", "get_recipe"),
)
