"""
One module per graph node.

    memory.py         first node of every turn: fetches what this shopper has told us before
    supervisor.py     decides which specialist handles the next step (or that the turn is finished)
    product.py  cart.py  order.py  review.py  recipe.py     tool-calling specialists
    shopping_list.py  the specialist that builds and confirms shopping lists
    base.py           what the tool-calling specialists share

Each specialist module exposes `SPEC`: its name, the MCP tools it may call, and how to build its node.
graph.py wires them together.
"""
