"""Helpers for reading what MCP tools return."""
import json
from typing import Any


def text(content: Any) -> str:
    """Flatten message or MCP tool content (a string or a list of content blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(text(block) for block in content)
    if isinstance(content, dict):
        return content.get("text") or json.dumps(content)
    return str(getattr(content, "text", content))


def parse(result: Any) -> Any:
    """Decode an MCP tool result to JSON values; anything that isn't JSON (e.g. an error) stays a string."""
    blocks = result if isinstance(result, list) else [result]
    values = []
    for block in blocks:
        try:
            values.append(json.loads(text(block)))
        except (TypeError, ValueError):
            values.append(text(block))
    return values[0] if len(values) == 1 else values
