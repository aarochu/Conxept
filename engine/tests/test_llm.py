"""Model selection for Analyze and the baseline: OpenRouter or Anthropic, no network calls."""

from types import SimpleNamespace

import pytest

import baseline
import llm
from free_models import free_tool_models


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "AGENT_MODEL", "BASELINE_MODEL"):
        monkeypatch.delenv(var, raising=False)


def test_default_follows_whichever_key_is_set(monkeypatch):
    assert llm.missing_key(llm.resolve_model()) == "ANTHROPIC_API_KEY"
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    assert llm.resolve_model() == llm.OPENROUTER_DEFAULT
    assert llm.missing_key(llm.resolve_model()) is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert llm.resolve_model() == llm.ANTHROPIC_DEFAULT


def test_explicit_model_names_its_missing_key(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "openrouter:some/model:free")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert llm.missing_key(llm.resolve_model()) == "OPENROUTER_API_KEY"


def test_openrouter_chat_model_points_at_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    model = llm.chat_model("openrouter:some/model:free")
    assert model.model_name == "some/model:free"
    assert str(model.openai_api_base).rstrip("/") == llm.OPENROUTER_BASE_URL
    assert llm.chat_model("anthropic:claude-sonnet-5-5") == "anthropic:claude-sonnet-5-5"


def test_free_model_filter():
    models = [
        {"id": "a/free:free", "supported_parameters": ["tools"], "context_length": 10},
        {"id": "b/big:free", "supported_parameters": ["tools", "tool_choice"], "context_length": 99},
        {"id": "c/notools:free", "supported_parameters": ["temperature"]},
        {"id": "d/paid", "supported_parameters": ["tools"]},
    ]
    assert [m["id"] for m in free_tool_models(models)] == ["b/big:free", "a/free:free"]


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        message = SimpleNamespace(content=reply)
        return SimpleNamespace(model=kwargs["model"], choices=[SimpleNamespace(message=message, finish_reason="stop")])


def fake_openrouter(replies):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(replies)))


def test_openrouter_answer_parsed_through_code_fences():
    client = fake_openrouter(['```json\n{"first_wrong_step": 2, "misconception": "dropped u(t)"}\n```'])
    a = baseline.ask_openrouter(client, "prompt", "openrouter:some/model:free")
    assert (a.first_wrong_step, a.misconception, a.served_by) == (2, "dropped u(t)", "some/model:free")
    assert client.chat.completions.calls[0]["model"] == "some/model:free"


def test_openrouter_rate_limit_is_retried():
    import httpx
    import openai

    response = httpx.Response(429, request=httpx.Request("POST", llm.OPENROUTER_BASE_URL))
    limited = openai.RateLimitError("rate limited", response=response, body=None)
    client = fake_openrouter([limited, '{"first_wrong_step": 0, "misconception": ""}'])
    waits = []
    a = baseline.ask_openrouter(client, "prompt", "openrouter:m:free", sleep=waits.append)
    assert a.first_wrong_step == 0 and waits == [5]


def test_baseline_defaults_to_free_model_with_only_openrouter_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    answer = '{"first_wrong_step": 1, "misconception": "x"}'
    client = fake_openrouter([answer] * 200)
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: client)
    assert baseline.main(["--out", str(tmp_path), "--runs", "2"]) == 0
    summary = (tmp_path / "summary.md").read_text()
    assert f"Model: `{llm.OPENROUTER_DEFAULT}`, effort `n/a`" in summary
    assert len(client.chat.completions.calls) == 200


def test_baseline_openrouter_model_without_key_is_rejected():
    with pytest.raises(SystemExit):
        baseline.main(["--model", "openrouter:m:free"])
