"""
VoiceCart MCP server.

Exposes the Product Service REST routes (user, product, cart, orders, search,
reviews, categories) as MCP tools. Every tool is a thin HTTP call to the
running Product Service, so business rules (auth, admin checks, stock) stay
in one place.

Auth: over HTTP transports each request must carry the end user's
`Authorization: Bearer <jwt>` header, which is forwarded to the Product
Service (this is how the agent service acts as the logged-in user). Over
stdio, the `login` tool or the env credentials below are used instead.

Config (env vars or mcp_server/.env):
    PRODUCT_SERVICE_URL       base URL of the Product Service (default http://localhost:8000)
    PRODUCT_SERVICE_TOKEN     optional pre-issued JWT (stdio only)
    PRODUCT_SERVICE_USERNAME  optional email/phone used to log in automatically (stdio only)
    PRODUCT_SERVICE_PASSWORD  optional password used to log in automatically (stdio only)
    MCP_TRANSPORT             stdio (default) or streamable-http
    MCP_HOST / MCP_PORT       bind address for streamable-http (default 127.0.0.1:8004, path /mcp)
"""
import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BASE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8000").rstrip("/")

mcp = FastMCP(
    "voicecart-product-service",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8004")),
)

# Bearer token for authenticated routes; set by `login` or from the environment.
_token: Optional[str] = os.getenv("PRODUCT_SERVICE_TOKEN")


async def _login(username: str, password: str) -> Dict[str, Any]:
    global _token
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # /user/login uses OAuth2PasswordRequestForm, so it expects form data, not JSON.
        response = await client.post("/user/login", data={"username": username, "password": password})
    if response.status_code >= 400:
        raise RuntimeError(f"Login failed ({response.status_code}): {_detail(response)}")
    _token = response.json()["access_token"]
    return response.json()


def _caller_headers() -> Optional[Any]:
    """Headers of the incoming MCP HTTP request, or None when running over stdio."""
    try:
        request = mcp.get_context().request_context.request
    except (LookupError, ValueError):
        return None
    return getattr(request, "headers", None)


async def _ensure_token() -> str:
    headers = _caller_headers()
    if headers is not None:
        # HTTP callers act as their own user; never fall back to the shared stdio login.
        auth_header = headers.get("authorization", "")
        if auth_header.lower().startswith("bearer ") and auth_header[7:].strip():
            return auth_header[7:].strip()
        raise RuntimeError("Not authenticated. The user needs to log in.")

    if _token:
        return _token
    username = os.getenv("PRODUCT_SERVICE_USERNAME")
    password = os.getenv("PRODUCT_SERVICE_PASSWORD")
    if username and password:
        await _login(username, password)
        return _token
    raise RuntimeError("Not authenticated. Call the `login` tool first.")


def _detail(response: httpx.Response) -> Any:
    try:
        return response.json().get("detail", response.text)
    except Exception:
        return response.text


async def _request(
    method: str,
    path: str,
    *,
    auth: bool = False,
    params: Optional[Dict[str, Any]] = None,
    json: Any = None,
) -> Any:
    headers = {"Authorization": f"Bearer {await _ensure_token()}"} if auth else {}
    if params:
        params = {k: v for k, v in params.items() if v is not None}

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        response = await client.request(method, path, headers=headers, params=params, json=json)

    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed ({response.status_code}): {_detail(response)}")
    if response.status_code == 204 or not response.content:
        return {"status": "success"}
    return response.json()


# --- User ---

@mcp.tool()
async def login(username: str, password: str) -> Dict[str, Any]:
    """Log in with email or phone number and password. Stores the access token for later tool calls."""
    result = await _login(username, password)
    return {"status": "logged_in", "token_type": result.get("token_type")}


@mcp.tool()
async def register_user(
    name: str,
    email: str,
    password: str,
    phone: Optional[str] = None,
    address: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a new VoiceCart user account."""
    body = {"name": name, "email": email, "password": password, "phone": phone, "address": address}
    return await _request("POST", "/user/register", json=body)


@mcp.tool()
async def get_user(user_id: int) -> Dict[str, Any]:
    """Get a user's profile by ID. Requires login."""
    return await _request("GET", f"/user/{user_id}", auth=True)


# --- Products ---

@mcp.tool()
async def list_products(limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
    """List products (lightweight details, no images), paginated with limit/skip."""
    return await _request("GET", "/product/", params={"limit": limit, "skip": skip})


@mcp.tool()
async def get_product(product_id: int) -> Dict[str, Any]:
    """Get full details for one product, including categories, rating and stock."""
    return await _request("GET", f"/product/{product_id}")


@mcp.tool()
async def get_product_stock(product_id: int) -> Dict[str, Any]:
    """Get the current stock count for a product. Requires login."""
    return await _request("GET", f"/product/stock/{product_id}", auth=True)


@mcp.tool()
async def create_product(
    name: str,
    price: float,
    description: Optional[str] = None,
    specs: Optional[Dict[str, Any]] = None,
    for_sale: bool = True,
    stock: int = 0,
    brand_name: Optional[str] = None,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a product, optionally tagged with category names (created if missing). Admin only."""
    body = {
        "product": {
            "name": name,
            "price": price,
            "description": description,
            "specs": specs,
            "for_sale": for_sale,
            "stock": stock,
            "brand_name": brand_name,
        },
        "categories": [{"name": c} for c in (categories or [])],
    }
    return await _request("POST", "/product/", auth=True, json=body)


@mcp.tool()
async def update_product(
    product_id: int,
    name: Optional[str] = None,
    price: Optional[float] = None,
    description: Optional[str] = None,
    specs: Optional[Dict[str, Any]] = None,
    for_sale: Optional[bool] = None,
    stock: Optional[int] = None,
    brand_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Update fields of a product; only the fields given are changed. Admin only."""
    body = {
        "name": name,
        "price": price,
        "description": description,
        "specs": specs,
        "for_sale": for_sale,
        "stock": stock,
        "brand_name": brand_name,
    }
    body = {k: v for k, v in body.items() if v is not None}
    return await _request("PATCH", f"/product/{product_id}", auth=True, json=body)


@mcp.tool()
async def delete_product(product_id: int) -> Dict[str, Any]:
    """Delete a product. Admin only."""
    return await _request("DELETE", f"/product/{product_id}", auth=True)


# --- Search ---

@mcp.tool()
async def search_products(
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    categories: Optional[List[str]] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Search products by free-text query, with optional filters and category names. Returns the `limit` most relevant products, each with a relevance score.

    filters keys are a product field (price, stock, brand_name, avg_rating, ...) or a specs key, with a suffix:
    `_low` = below the value, `_high` = above it, `_exact`, `_contains`. Example: {"price_low": 100} for under $100.
    """
    body = {"query": query, "filters": filters, "categories": categories}
    results = await _request("POST", "/search/products", json=body)
    return results[:limit]


# --- Categories ---

@mcp.tool()
async def list_categories() -> List[Dict[str, Any]]:
    """List top-level product categories."""
    return await _request("GET", "/categories/")


@mcp.tool()
async def create_category(name: str, parent_id: Optional[int] = None) -> Dict[str, Any]:
    """Create a category, optionally under a parent category. Admin only."""
    return await _request("POST", "/categories/", auth=True, json={"name": name, "parent_id": parent_id})


# --- Cart ---

@mcp.tool()
async def get_cart() -> List[Dict[str, Any]]:
    """Get the logged-in user's cart items with product details."""
    return await _request("GET", "/cart/", auth=True)


@mcp.tool()
async def get_cart_total() -> float:
    """Get the total cost of the logged-in user's cart."""
    return await _request("GET", "/cart/cost", auth=True)


@mcp.tool()
async def add_to_cart(product_id: int, quantity: int = 1) -> Dict[str, Any]:
    """Add a product to the cart (or increase its quantity). Fails if stock is insufficient."""
    return await _request("POST", "/cart/", auth=True, json={"product_id": product_id, "quantity": quantity})


@mcp.tool()
async def update_cart_item(product_id: int, quantity: int) -> Dict[str, Any]:
    """Set the quantity of a product already in the cart."""
    return await _request("PATCH", f"/cart/{product_id}", auth=True, json={"quantity": quantity})


@mcp.tool()
async def remove_from_cart(product_id: int) -> Dict[str, Any]:
    """Remove a product from the cart."""
    return await _request("DELETE", f"/cart/{product_id}", auth=True)


@mcp.tool()
async def clear_cart() -> Dict[str, Any]:
    """Remove every item from the cart."""
    return await _request("DELETE", "/cart/clear", auth=True)


@mcp.tool()
async def checkout(address: Optional[str] = None) -> Dict[str, Any]:
    """Place an order for everything in the cart. Uses the user's saved address if none is given."""
    return await _request("POST", "/cart/checkout", auth=True, params={"address": address})


# --- Orders ---

@mcp.tool()
async def list_orders() -> List[Dict[str, Any]]:
    """List the logged-in user's orders with their items."""
    return await _request("GET", "/orders/", auth=True)


@mcp.tool()
async def get_order(order_id: int) -> Dict[str, Any]:
    """Get one of the logged-in user's orders by ID."""
    return await _request("GET", f"/orders/{order_id}", auth=True)


@mcp.tool()
async def create_order(address: str, total_amount: Optional[float] = None) -> Dict[str, Any]:
    """Create an order from the current cart, shipped to the given address."""
    return await _request(
        "POST", "/orders/", auth=True, params={"address": address, "total_amount": total_amount}
    )


@mcp.tool()
async def update_order(order_id: int, status: Optional[str] = None, address: Optional[str] = None) -> Dict[str, Any]:
    """Update an order's status (e.g. Pending, Shipped, Delivered, Cancelled) and/or address."""
    return await _request("PATCH", f"/orders/{order_id}", auth=True, json={"status": status, "address": address})


# --- Reviews ---

@mcp.tool()
async def get_product_reviews(product_id: int) -> List[Dict[str, Any]]:
    """List reviews for a product."""
    return await _request("GET", f"/reviews/product/{product_id}")


@mcp.tool()
async def get_user_reviews(user_id: int) -> List[Dict[str, Any]]:
    """List reviews written by a user."""
    return await _request("GET", f"/reviews/user/{user_id}")


@mcp.tool()
async def create_review(product_id: int, rating: int, comment: Optional[str] = None) -> Dict[str, Any]:
    """Write a review (rating 1-5) for a product as the logged-in user."""
    body = {"product_id": product_id, "rating": rating, "comment": comment}
    return await _request("POST", "/reviews/", auth=True, json=body)


@mcp.tool()
async def update_review(review_id: int, product_id: int, rating: int, comment: Optional[str] = None) -> Dict[str, Any]:
    """Replace one of the logged-in user's reviews."""
    body = {"product_id": product_id, "rating": rating, "comment": comment}
    return await _request("PUT", f"/reviews/{review_id}", auth=True, json=body)


@mcp.tool()
async def delete_review(review_id: int) -> Dict[str, Any]:
    """Delete one of the logged-in user's reviews."""
    return await _request("DELETE", f"/reviews/{review_id}", auth=True)


# --- Recipes (TheMealDB's free public API: no login needed) ---

MEALDB_URL = "https://www.themealdb.com/api/json/v1/1"


MEALDB_TIMEOUT = 8.0  # seconds per attempt; the free service is sometimes slow, and a shopper is waiting
MEALDB_ATTEMPTS = 2


async def _mealdb(endpoint: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    """One TheMealDB lookup. Timeouts, dropped connections and 5xx answers are tried once more; if it still
    fails, the error says so in words the agent can pass on (an exception with an empty message tells it nothing)."""
    for attempt in range(MEALDB_ATTEMPTS):
        try:
            async with httpx.AsyncClient(base_url=MEALDB_URL, timeout=MEALDB_TIMEOUT) as client:
                response = await client.get(endpoint, params=params)
            if response.status_code >= 500:
                raise httpx.HTTPError(f"server error {response.status_code}")
            if response.status_code >= 400:
                raise RuntimeError(f"The recipe service (TheMealDB) refused the request ({response.status_code}).")
            # TheMealDB answers {"meals": null} when nothing matches.
            return response.json().get("meals") or []
        except httpx.HTTPError:  # timeouts, dropped connections, 5xx: worth another try
            if attempt + 1 < MEALDB_ATTEMPTS:
                continue
    raise RuntimeError("The recipe service (TheMealDB) is not answering right now. Try again in a moment.")


def _meal_summary(meal: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "meal_id": meal["idMeal"],
        "name": meal["strMeal"],
        "category": meal.get("strCategory"),
        "cuisine": meal.get("strArea"),
    }


@mcp.tool()
async def search_recipes(query: str) -> List[Dict[str, Any]]:
    """Search recipes by dish name, e.g. "chicken curry" or "lasagne". Use one or two keywords, not a sentence."""
    meals = await _mealdb("search.php", {"s": query})
    return [_meal_summary(m) for m in meals[:5]] or [{"message": f"No recipes found for '{query}'."}]


@mcp.tool()
async def recipes_by_ingredient(ingredient: str) -> List[Dict[str, Any]]:
    """Find recipes that use a main ingredient, e.g. "chicken_breast" or "salmon" (use underscores for spaces)."""
    meals = await _mealdb("filter.php", {"i": ingredient.replace(" ", "_")})
    found = [{"meal_id": m["idMeal"], "name": m["strMeal"]} for m in meals[:8]]
    return found or [{"message": f"No recipes found with '{ingredient}'."}]


@mcp.tool()
async def get_recipe(meal_id: str) -> Dict[str, Any]:
    """Get a recipe's full ingredient list (with measures) and instructions by its meal_id."""
    meals = await _mealdb("lookup.php", {"i": meal_id})
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
        **_meal_summary(meal),
        "ingredients": ingredients,
        "instructions": (meal.get("strInstructions") or "")[:1500],
    }


# --- Display ---

@mcp.tool()
def show_products(product_ids: List[int]) -> str:
    """Show photo cards on the user's screen for products you are recommending or asking them to choose between.

    Call it once, after you have found products, with the ids of up to 5 of them, best match first.
    Only include products that really answer the request; never show unrelated search results.

    The tool only acknowledges the request: the agent reads the ids from the call and sends the cards to the screen.
    """
    return f"Showing {min(len(product_ids), 5)} product card(s) on the user's screen."


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
