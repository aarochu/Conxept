"""List OpenRouter models that are free and support tool calling, for AGENT_MODEL / --model.

Reads OpenRouter's public model list; no key is needed and nothing about this project is sent.
"""

from __future__ import annotations

import json
import sys
import urllib.request

MODELS_URL = "https://openrouter.ai/api/v1/models"


def free_tool_models(models: list[dict]) -> list[dict]:
    """Free (":free") models whose supported parameters include tools, largest context first."""
    free = [
        m for m in models
        if m.get("id", "").endswith(":free") and "tools" in (m.get("supported_parameters") or [])
    ]
    return sorted(free, key=lambda m: (-(m.get("context_length") or 0), m["id"]))


def main() -> int:
    try:
        with urllib.request.urlopen(MODELS_URL, timeout=20) as r:
            models = json.load(r)["data"]
    except (OSError, ValueError, KeyError) as e:
        print(f"could not read {MODELS_URL}: {e}", file=sys.stderr)
        return 1
    found = free_tool_models(models)
    if not found:
        print("no free tool-capable models listed right now", file=sys.stderr)
        return 1
    for m in found:
        print(f"openrouter:{m['id']}")
    print("\nSet one as AGENT_MODEL (Analyze) or pass it to baseline.py --model.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
