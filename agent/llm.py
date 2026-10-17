import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


@lru_cache
def get_llm() -> ChatOpenAI:
    """Chat model behind every agent, served from the OpenAI-compatible endpoint in agent/.env."""
    return ChatOpenAI(
        base_url=os.environ["INFERENCE_BASE_URL"],
        api_key=os.environ["INFERENCE_API_KEY"],
        model=os.environ["INFERENCE_MODEL"],
        temperature=0,
        # The model's thinking mode rejects forced tool_choice (structured output) and requires
        # reasoning_content to be echoed back on tool loops, so keep it off. It is also faster for voice.
        extra_body={"thinking": {"type": "disabled"}},
    )
