"""Recipe tools backed by TheMealDB's free public API (https://www.themealdb.com/api.php)."""
from typing import Any, Dict, List

import httpx
from langchain_core.tools import tool

MEALDB_URL = "https://www.themealdb.com/api/json/v1/1"


async def _get(endpoint: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(base_url=MEALDB_URL, timeout=15.0) as client:
        response = await client.get(endpoint, params=params)
    response.raise_for_status()
    # TheMealDB returns {"meals": null} when nothing matches.
    return response.json().get("meals") or []


def _summary(meal: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "meal_id": meal["idMeal"],
        "name": meal["strMeal"],
        "category": meal.get("strCategory"),
        "cuisine": meal.get("strArea"),
    }


@tool
async def search_recipes(query: str) -> List[Dict[str, Any]]:
    """Search recipes by dish name, e.g. "chicken curry" or "lasagne"."""
    meals = await _get("search.php", {"s": query})
    return [_summary(m) for m in meals[:5]] or [{"message": f"No recipes found for '{query}'."}]


@tool
async def recipes_by_ingredient(ingredient: str) -> List[Dict[str, Any]]:
    """Find recipes that use a main ingredient, e.g. "chicken_breast" or "salmon" (use underscores for spaces)."""
    meals = await _get("filter.php", {"i": ingredient.replace(" ", "_")})
    found = [{"meal_id": m["idMeal"], "name": m["strMeal"]} for m in meals[:8]]
    return found or [{"message": f"No recipes found with '{ingredient}'."}]


@tool
async def get_recipe(meal_id: str) -> Dict[str, Any]:
    """Get a recipe's full ingredient list (with measures) and instructions by its meal_id."""
    meals = await _get("lookup.php", {"i": meal_id})
    if not meals:
        return {"message": f"No recipe with id {meal_id}."}
    meal = meals[0]
    ingredients = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        if name:
            measure = (meal.get(f"strMeasure{i}") or "").strip()
            ingredients.append(f"{measure} {name}".strip())
    return {
        **_summary(meal),
        "ingredients": ingredients,
        "instructions": (meal.get("strInstructions") or "")[:1500],
    }


RECIPE_TOOLS = [search_recipes, recipes_by_ingredient, get_recipe]
