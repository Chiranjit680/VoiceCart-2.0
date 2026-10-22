"""
Tests for the MCP server's recipe and display tools. Run from the repo root:  python mcp_server/test_server.py

TheMealDB is replaced by a stand-in, so nothing is fetched from the internet.
"""
import asyncio
import importlib.util
import sys
import traceback
from pathlib import Path

import httpx

spec = importlib.util.spec_from_file_location("voicecart_mcp_server", Path(__file__).resolve().parent / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def run(coro):
    return asyncio.run(coro)


class mealdb:
    """Makes the server's HTTP calls answer from `handler`; records the requests it receives."""

    def __init__(self, handler):
        self.handler, self.requests = handler, []

    def __enter__(self):
        self.real = server.httpx.AsyncClient

        def record(request):
            self.requests.append(request)
            return self.handler(request)

        server.httpx.AsyncClient = lambda **kw: self.real(transport=httpx.MockTransport(record), **kw)
        return self

    def __exit__(self, *exc):
        server.httpx.AsyncClient = self.real


def meals(count, **extra):
    return httpx.Response(200, json={"meals": [{"idMeal": str(n), "strMeal": f"Dish {n}", "strCategory": "Dessert", "strArea": "British", **extra} for n in range(count)]})


def nothing(request):
    return httpx.Response(200, json={"meals": None})


# --- the tools exist ---

def test_the_server_offers_the_recipe_and_display_tools_with_descriptions():
    tools = {tool.name: tool for tool in run(server.mcp.list_tools())}
    for name in ("search_recipes", "recipes_by_ingredient", "get_recipe", "show_products"):
        assert name in tools, name
        assert tools[name].description and len(tools[name].description) > 20, f"{name} has no description for the model"
    assert len(tools) == 32


# --- show_products ---

def test_show_products_only_acknowledges_and_counts_at_most_five():
    assert server.show_products([1, 2, 3]) == "Showing 3 product card(s) on the user's screen."
    assert server.show_products(list(range(12))) == "Showing 5 product card(s) on the user's screen."
    assert server.show_products([]) == "Showing 0 product card(s) on the user's screen."


# --- recipes ---

def test_search_recipes_returns_up_to_five_summaries():
    with mealdb(lambda r: meals(8)) as api:
        found = run(server.search_recipes("apple"))
    assert len(found) == 5 and found[0] == {"meal_id": "0", "name": "Dish 0", "category": "Dessert", "cuisine": "British"}
    assert api.requests[0].url.path.endswith("/search.php") and api.requests[0].url.params["s"] == "apple"


def test_search_recipes_says_so_when_nothing_matches():
    with mealdb(nothing):
        assert run(server.search_recipes("zzzz")) == [{"message": "No recipes found for 'zzzz'."}]


def test_recipes_by_ingredient_uses_underscores_and_returns_up_to_eight():
    with mealdb(lambda r: meals(12)) as api:
        found = run(server.recipes_by_ingredient("chicken breast"))
    assert len(found) == 8 and set(found[0]) == {"meal_id", "name"}
    assert api.requests[0].url.params["i"] == "chicken_breast"
    with mealdb(nothing):
        assert "No recipes found with" in run(server.recipes_by_ingredient("unobtainium"))[0]["message"]


def test_get_recipe_lists_ingredients_with_measures_and_skips_blank_ones():
    extra = {
        "strIngredient1": "Apples", "strMeasure1": "3",
        "strIngredient2": "Butter", "strMeasure2": " 50g ",
        "strIngredient3": "", "strMeasure3": " ",
        "strIngredient4": None, "strMeasure4": None,
        "strIngredient5": "Cinnamon", "strMeasure5": "",
        "strInstructions": "Bake. " * 400,
    }
    with mealdb(lambda r: meals(1, **extra)):
        recipe = run(server.get_recipe("0"))
    assert recipe["ingredients"] == ["3 Apples", "50g Butter", "Cinnamon"]
    assert recipe["name"] == "Dish 0" and len(recipe["instructions"]) == 1500


def test_get_recipe_for_an_unknown_id_says_so():
    with mealdb(nothing):
        assert run(server.get_recipe("999")) == {"message": "No recipe with id 999."}


def test_recipe_tools_need_no_login():
    saved = server._ensure_token

    async def refuse():
        raise AssertionError("a recipe tool asked for a login token")

    server._ensure_token = refuse
    try:
        with mealdb(lambda r: meals(1)) as api:
            run(server.search_recipes("x"))
            run(server.get_recipe("0"))
            run(server.recipes_by_ingredient("x"))
        assert all("authorization" not in r.headers for r in api.requests)
    finally:
        server._ensure_token = saved


def test_a_recipe_service_that_keeps_failing_gives_a_clear_error():
    with mealdb(lambda r: httpx.Response(503)) as api:
        try:
            run(server.search_recipes("apple"))
        except RuntimeError as error:
            assert "not answering right now" in str(error) and "TheMealDB" in str(error)
        else:
            raise AssertionError("a 503 from the recipe service was swallowed")
    assert len(api.requests) == server.MEALDB_ATTEMPTS  # tried again once before giving up


def test_a_recipe_lookup_that_fails_once_is_tried_again_and_succeeds():
    attempts = []

    def flaky(request):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectTimeout("")  # an exception with no message at all
        return meals(2)

    with mealdb(flaky):
        found = run(server.search_recipes("apple"))
    assert [m["name"] for m in found] == ["Dish 0", "Dish 1"] and len(attempts) == 2


def test_dropped_connections_and_timeouts_end_in_the_same_clear_error():
    for failure in (httpx.ConnectError(""), httpx.ReadTimeout(""), httpx.RemoteProtocolError("")):
        def always(request, failure=failure):
            raise failure

        with mealdb(always):
            try:
                run(server.get_recipe("1"))
            except RuntimeError as error:
                assert "not answering right now" in str(error), failure
            else:
                raise AssertionError(f"{failure!r} was swallowed")


def test_a_refused_request_is_not_retried():
    with mealdb(lambda r: httpx.Response(404)) as api:
        try:
            run(server.search_recipes("apple"))
        except RuntimeError as error:
            assert "refused the request (404)" in str(error)
        else:
            raise AssertionError("a 404 was swallowed")
    assert len(api.requests) == 1


def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
