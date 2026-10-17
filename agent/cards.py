"""
Product cards: the products a reply should show, as small dicts the frontend renders with their photo.

Which products to show:
- products the model picked by calling the `show_products` tool (search results, candidates to choose from);
- products from tools whose result *is* the answer: a single product, the cart, an item just added to it.
"""
from typing import Any, Dict, Iterator, List, Optional, Tuple

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from .toolresult import parse

CARD_LIMIT = 6

# Tools whose result is itself "the product(s) the user asked about", shown without the model asking.
AUTO_SHOW_TOOLS = {"get_product", "get_cart", "add_to_cart", "update_cart_item"}


def card_from(product: Dict[str, Any], quantity: Optional[int] = None) -> Dict[str, Any]:
    card = {
        "id": product["id"],
        "name": product["name"],
        "brand_name": product.get("brand_name"),
        "price": float(product["price"]),
        "avg_rating": float(product.get("avg_rating") or 0),
        "num_reviews": int(product.get("num_reviews") or 0),
        "stock": int(product.get("stock") or 0),
        "has_image": bool(product.get("has_image")),
    }
    if quantity is not None:
        card["quantity"] = int(quantity)
    return card


def _products_in(value: Any) -> Iterator[Tuple[Dict[str, Any], Optional[int]]]:
    """Every product inside a tool result, with its quantity when it came from a cart or order line."""
    if isinstance(value, list):
        for item in value:
            yield from _products_in(item)
    elif isinstance(value, dict):
        if {"id", "name", "price"} <= value.keys():
            yield value, None
        elif isinstance(value.get("product"), dict):  # a cart or order line wraps the product
            yield from ((p, value.get("quantity")) for p, _ in _products_in(value["product"]))


def collect_cards(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Cards for the products this agent step chose to show, best first, without duplicates."""
    fetched: Dict[int, Tuple[Dict[str, Any], Optional[int]]] = {}
    chosen: List[int] = []
    automatic: List[int] = []

    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                if call["name"] == "show_products":
                    chosen.extend(i for i in (call["args"].get("product_ids") or []) if isinstance(i, int))
        elif isinstance(message, ToolMessage):
            for product, quantity in _products_in(parse(message.content)):
                pid = product["id"]
                if quantity is None and pid in fetched:
                    quantity = fetched[pid][1]  # keep the quantity from an earlier cart lookup
                fetched[pid] = (product, quantity)
                if message.name in AUTO_SHOW_TOOLS:
                    automatic.append(pid)

    ids = dict.fromkeys([*chosen, *automatic])  # order kept, duplicates dropped
    return [card_from(*fetched[pid]) for pid in ids if pid in fetched][:CARD_LIMIT]


def merge_cards(existing: Optional[List[Dict[str, Any]]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add cards to the ones already shown this turn, keeping the first copy of each product."""
    merged: Dict[int, Dict[str, Any]] = {}
    for card in [*(existing or []), *new]:
        merged.setdefault(card["id"], card)
    return list(merged.values())[:CARD_LIMIT]
