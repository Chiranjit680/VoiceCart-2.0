"""Pure scoring of one turn and of the end state. No network, so it is unit-tested (test_checks.py)."""
import re
from typing import Dict, List, Optional

MAX_SPOKEN_WORDS = 90  # the prompt asks for 1-3 short sentences; this leaves room for a few product names
_MARKDOWN = re.compile(r"(\*\*|__|`|^\s*#|^\s*[-*•]\s|^\s*\d+[.)]\s)", re.MULTILINE)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")


def _search(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.MULTILINE) is not None


def voice_problems(reply: str) -> List[str]:
    """Rules every reply must follow because it is spoken aloud."""
    problems = []
    if not reply.strip():
        return ["the reply is empty"]
    if _MARKDOWN.search(reply):
        problems.append("uses markdown or a list")
    if _EMOJI.search(reply):
        problems.append("contains an emoji")
    if "$" in reply:
        problems.append("quotes dollars")
    words = len(reply.split())
    if words > MAX_SPOKEN_WORDS:
        problems.append(f"is {words} words long (limit {MAX_SPOKEN_WORDS})")
    return problems


def cart_problems(cart: Dict[str, int], wanted: Dict[str, int]) -> List[str]:
    """`cart` is {product name: quantity}. It must hold exactly the wanted items (names are regexes)."""
    problems, matched = [], set()
    for pattern, quantity in wanted.items():
        hits = {name: q for name, q in cart.items() if _search(pattern, name)}
        if not hits:
            problems.append(f"cart has no item matching /{pattern}/ (cart: {cart})")
            continue
        matched.update(hits)
        if quantity not in hits.values():
            problems.append(f"cart has {hits} for /{pattern}/, wanted quantity {quantity}")
    extra = set(cart) - matched
    if extra:
        problems.append(f"cart holds unexpected items: {sorted(extra)}")
    return problems


def turn_problems(expect: dict, reply: str, card_names: List[str], cart: Dict[str, int], order_count: int) -> List[str]:
    problems = []
    if any_of := expect.get("reply_any"):
        if not any(_search(p, reply) for p in any_of):
            problems.append(f"reply matches none of {any_of}")
    for pattern in expect.get("reply_all", []):
        if not _search(pattern, reply):
            problems.append(f"reply does not match /{pattern}/")
    for pattern in expect.get("reply_none", []):
        if _search(pattern, reply):
            problems.append(f"reply must not match /{pattern}/")
    if "cards_min" in expect and len(card_names) < expect["cards_min"]:
        problems.append(f"{len(card_names)} product card(s), wanted at least {expect['cards_min']}")
    if "cards_max" in expect and len(card_names) > expect["cards_max"]:
        problems.append(f"{len(card_names)} product card(s), wanted at most {expect['cards_max']}")
    if pattern := expect.get("card_any"):
        if not any(_search(pattern, n) for n in card_names):
            problems.append(f"no product card matches /{pattern}/ (cards: {card_names})")
    if "cart_after" in expect:
        problems += cart_problems(cart, expect["cart_after"])
    for pattern in expect.get("cart_any_after", []):
        if not any(_search(pattern, n) for n in cart):
            problems.append(f"cart has nothing matching /{pattern}/ (cart: {cart})")
    if expect.get("cart_empty_after") and cart:
        problems.append(f"cart should be empty but holds {cart}")
    if "orders_after" in expect and order_count != expect["orders_after"]:
        problems.append(f"{order_count} order(s) placed, wanted {expect['orders_after']}")
    return problems


def final_problems(final: Optional[dict], cart: Dict[str, int]) -> List[str]:
    problems = []
    for pattern, most in (final or {}).get("cart_max_quantity", {}).items():
        for name, quantity in cart.items():
            if _search(pattern, name) and quantity > most:
                problems.append(f"cart holds {quantity} x {name}, at most {most} allowed")
    return problems
