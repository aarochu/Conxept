"""Agent wiring with a scripted stand-in model (no API key): tool calls run, the number check guards the brief."""

import json

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent import analyze_events, unverified_numbers


class ScriptedModel(BaseChatModel):
    script: list

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        n_ai = sum(1 for m in messages if m.type == "ai")
        return ChatResult(generations=[ChatGeneration(message=self.script[min(n_ai, len(self.script) - 1)])])


class FakeData:
    def heatmap(self, class_id):
        return [{"problem": "f1-p1-q2-n0", "step": 1, "failed": 7, "attempted": 60}]

    def clusters(self, class_id):
        return [{"key": "forgot_to_flip_h", "name": "Convolution without flipping h", "count": 12,
                 "step": 1, "family": "Causal convolution", "in_catalog": True}]

    def examples(self, class_id, key, limit=3):
        return []


def _script(final_text):
    return [
        AIMessage(content="", tool_calls=[{"name": "get_heatmap", "args": {"class_id": "c1"}, "id": "a"}]),
        AIMessage(content="", tool_calls=[{"name": "get_clusters", "args": {"class_id": "c1"}, "id": "b"}]),
        AIMessage(content=final_text),
    ]


async def _run(final_text):
    events = []
    async for e in analyze_events("c1", model=ScriptedModel(script=_script(final_text)), data=FakeData()):
        events.append(e)
    return events


async def test_tool_calls_then_brief():
    events = await _run("Overview: 12 students did not flip h; 7 of 60 failed step 1 of f1-p1-q2-n0.")
    kinds = [e.WhichOneof("event") for e in events]
    assert kinds.count("tool_call") == 2 and kinds.count("tool_result") == 2
    assert kinds[-1] == "brief" and events[-1].brief.brief_id


async def test_invented_number_rejected():
    events = await _run("Overview: 45 students did not flip h.")
    assert events[-1].WhichOneof("event") == "error"
    assert events[-1].error == "brief contained an unverified number"


def test_number_check_allows_ordinals():
    assert unverified_numbers("1. first 2. second 3. third", []) == set()
    assert unverified_numbers("4 items", ["[1, 2]"]) == {4}


async def _run_script(script, class_id="c1"):
    model = ScriptedModel(script=script)
    events = [e async for e in analyze_events(class_id, model=model, data=FakeData())]
    return events, model


async def test_one_revision_fixes_an_invented_number():
    script = _script("Overview: 45 students did not flip h.") + [
        AIMessage(content="Overview: 12 students did not flip h.")
    ]
    events, _ = await _run_script(script)
    assert events[-1].WhichOneof("event") == "brief"
    assert events[-1].brief.markdown == "Overview: 12 students did not flip h."


async def test_revision_happens_once_then_rejects():
    calls = []

    class CountingModel(ScriptedModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            calls.append([m.content for m in messages if m.type == "human"])
            return super()._generate(messages, stop, run_manager, **kwargs)

    model = CountingModel(script=_script("Overview: 45 students did not flip h."))
    events = [e async for e in analyze_events("c1", model=model, data=FakeData())]
    assert events[-1].error == "brief contained an unverified number"
    revision_prompts = {p for human in calls for p in human if "no tool returned: 45" in p}
    assert len(revision_prompts) == 1


async def test_brief_may_repeat_the_class_id():
    class_id = "3f2b9c61-0a47-4e85-9d2c-7b1e5a604c19"
    events, _ = await _run_script(_script(f"Class {class_id}: 12 students did not flip h."), class_id)
    assert events[-1].WhichOneof("event") == "brief"


def test_number_check_accepts_given_text():
    assert unverified_numbers("class 61 has 12", ["12"], given="class-61") == set()
    assert unverified_numbers("class 61 has 12", ["12"]) == {61}
