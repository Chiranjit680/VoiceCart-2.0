"""
Tests for the scoring code (not the agent). Run from the repo root:  python -m evals.test_checks
"""
import sys
import traceback

from .checks import cart_problems, final_problems, turn_problems, voice_problems
from .conversations import CONVERSATIONS

tests = []


def test(fn):
    tests.append(fn)
    return fn


@test
def a_plain_short_reply_passes_the_voice_rules():
    assert voice_problems("Amul Butter 500g is 285 rupees. Want me to add it?") == []


@test
def markdown_lists_emoji_dollars_and_long_replies_are_flagged():
    assert voice_problems("**Milk** is nice") == ["uses markdown or a list"]
    assert voice_problems("Options:\n- Milk\n- Bread") == ["uses markdown or a list"]
    assert voice_problems("Great choice 🙂") == ["contains an emoji"]
    assert voice_problems("It costs $5") == ["quotes dollars"]
    assert "words long" in voice_problems("word " * 100)[0]
    assert voice_problems("  ") == ["the reply is empty"]


@test
def a_price_with_a_decimal_point_is_not_a_list_item():
    assert voice_problems("The kettle is 1.5 litres and costs 1599 rupees.") == []


@test
def the_cart_must_hold_exactly_the_wanted_items():
    cart = {"Amul Butter 500g": 2}
    assert cart_problems(cart, {r"butter": 2}) == []
    assert "wanted quantity 3" in cart_problems(cart, {r"butter": 3})[0]
    assert "no item matching" in cart_problems({}, {r"butter": 1})[0]
    assert "unexpected items" in cart_problems({"Amul Butter 500g": 1, "Tata Salt": 1}, {r"butter": 1})[0]


@test
def turn_expectations_are_checked_one_by_one():
    expect = {"reply_any": [r"milk"], "reply_all": [r"285"], "reply_none": [r"\$"], "cards_min": 1, "card_any": r"butter"}
    assert turn_problems(expect, "Milk and butter 285 rupees", ["Amul Butter 500g"], {}, 0) == []
    problems = turn_problems(expect, "It is $5", [], {}, 0)
    assert len(problems) == 5, problems


@test
def cards_max_cart_empty_and_orders_are_checked():
    assert turn_problems({"cards_max": 0}, "x", ["Milk"], {}, 0) != []
    assert turn_problems({"cart_empty_after": True}, "x", [], {"Milk": 1}, 0) != []
    assert turn_problems({"orders_after": 1}, "x", [], {}, 0) != []
    assert turn_problems({"orders_after": 1, "cart_empty_after": True}, "x", [], {}, 1) == []
    assert turn_problems({"cart_any_after": [r"rice", r"dal"]}, "x", [], {"Basmati Rice": 1}, 0) != []


@test
def the_stock_limit_is_enforced_at_the_end():
    final = {"cart_max_quantity": {r"tv": 20}}
    assert final_problems(final, {"OnePlus 43-inch 4K Smart TV": 20}) == []
    assert final_problems(final, {"OnePlus 43-inch 4K Smart TV": 100}) != []


@test
def the_conversation_set_is_well_formed():
    assert len(CONVERSATIONS) == 15
    ids = [c["id"] for c in CONVERSATIONS]
    assert len(set(ids)) == 15, "ids must be unique"
    known = {"reply_any", "reply_all", "reply_none", "cards_min", "cards_max", "card_any",
             "cart_after", "cart_any_after", "cart_empty_after", "orders_after"}
    for c in CONVERSATIONS:
        assert c["turns"] and c["title"], c["id"]
        for turn in c["turns"]:
            assert turn["say"].strip(), c["id"]
            assert set(turn["expect"]) <= known, (c["id"], set(turn["expect"]) - known)


if __name__ == "__main__":
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
