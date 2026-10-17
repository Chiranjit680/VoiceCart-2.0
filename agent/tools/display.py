"""A tool that lets the model put product cards on the user's screen."""
from typing import List

from langchain_core.tools import tool


@tool
def show_products(product_ids: List[int]) -> str:
    """Show photo cards on the user's screen for products you are recommending or asking them to choose between.

    Call it once, after you have found products, with the ids of up to 5 of them, best match first.
    Only include products that really answer the request; never show unrelated search results.
    """
    return f"Showing {min(len(product_ids), 5)} product card(s) on the user's screen."
