"""Which language model the brief and the baseline use, and which key that needs.

Model names use a provider prefix:
  anthropic:<model>    Claude through the Anthropic API (ANTHROPIC_API_KEY)
  openrouter:<model>   any OpenRouter model, including the free ":free" ones (OPENROUTER_API_KEY)

When AGENT_MODEL is unset, the first provider with a key wins: Anthropic, then OpenRouter.
The diagnosis path never calls a model, so none of this affects correctness.
"""

from __future__ import annotations

import os

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
ANTHROPIC_DEFAULT = "anthropic:claude-sonnet-5-5"
# A free, tool-capable OpenRouter model at the time of writing; `make free-models` lists current ones.
OPENROUTER_DEFAULT = "openrouter:nvidia/nemotron-3-ultra-550b-a55b:free"

KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
MISSING_KEY_MESSAGE = (
    "Analyze needs a model key in the engine's environment: OPENROUTER_API_KEY (free models work) "
    "or ANTHROPIC_API_KEY"
)


def provider_of(model: str) -> str:
    return model.split(":", 1)[0] if ":" in model else ""


def resolve_model(env_var: str = "AGENT_MODEL") -> str:
    """The configured model, or a default for whichever provider has a key."""
    configured = os.environ.get(env_var, "").strip()
    if configured:
        return configured
    if os.environ.get(KEYS["anthropic"]):
        return ANTHROPIC_DEFAULT
    if os.environ.get(KEYS["openrouter"]):
        return OPENROUTER_DEFAULT
    return ANTHROPIC_DEFAULT


def missing_key(model: str) -> str | None:
    """The environment variable this model still needs, or None when it is ready."""
    key = KEYS.get(provider_of(model))
    if key is None:
        return None  # another LangChain provider string; its own library reports a missing key
    return None if os.environ.get(key) else key


def chat_model(model: str):
    """A LangChain chat model, or the provider string for Deep Agents to resolve itself."""
    if provider_of(model) == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model.split(":", 1)[1],
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ[KEYS["openrouter"]],
            temperature=0,
        )
    return model
