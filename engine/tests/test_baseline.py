"""Baseline harness (spec section 8.5) with a fake client: no API calls, no key needed."""

import json
import pytest
from types import SimpleNamespace

import baseline
from baseline import FIXED_PROMPT, REFUSED, ask_model, kind_of, score, select_sample


def test_engine_failure_is_reported_not_counted_as_valid(monkeypatch):
    from diagnose import Result, STATUS_PARSE_ERROR

    sample = select_sample()[:1]
    monkeypatch.setattr(baseline, "diagnose", lambda *args: Result(status=STATUS_PARSE_ERROR))
    engine = baseline.run_engine(sample, runs=1)
    assert engine[0][0].first_wrong_step == REFUSED
    model = [[baseline.ModelAnswer(0, "")]]
    assert "| Refused or failed (run 1) | 0 | 1 |" in baseline.summary_markdown(
        sample, "test", "medium", model, engine
    )


def test_zero_workers_rejected_before_requests():
    with pytest.raises(SystemExit):
        baseline.main(["--workers", "0"])


class FakeMessages:
    def __init__(self, answer_for):
        self.answer_for = answer_for
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["messages"][0]["content"]
        result = self.answer_for(prompt)
        if result == "refuse":
            return SimpleNamespace(stop_reason="refusal", content=[], model=kwargs["model"])
        text = SimpleNamespace(type="text", text=json.dumps(result))
        return SimpleNamespace(stop_reason="end_turn", content=[text], model=kwargs["model"])


def fake_client(answer_for):
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(answer_for)))


def test_sample_is_fixed_mix_and_reproducible():
    a, b = select_sample(), select_sample()
    assert [s.id for s in a] == [s.id for s in b]
    assert len(a) == 100
    assert {k: sum(kind_of(s) == k for s in a) for k in ("correct", "catalog", "heldout")} == {
        "correct": 40,
        "catalog": 40,
        "heldout": 20,
    }


def test_prompt_uses_fixed_text_and_includes_answer_and_steps():
    sub = next(s for s in select_sample() if kind_of(s) == "catalog")
    p = baseline.build_prompt(sub)
    assert p.startswith(FIXED_PROMPT)
    assert "Correct final answer" in p
    assert all(expr in p for expr in sub.steps)


def test_request_shape_structured_output_and_fallbacks():
    client = fake_client(lambda prompt: {"first_wrong_step": 2, "misconception": "dropped u(t)"})
    ans = ask_model(client, "prompt", "claude-opus-5-5", "medium")
    call = client.beta.messages.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["output_config"]["effort"] == "medium"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert (ans.first_wrong_step, ans.misconception) == (2, "dropped u(t)")


def test_refusal_is_recorded_not_raised():
    ans = ask_model(fake_client(lambda p: "refuse"), "prompt", "claude-opus-5-5", "medium")
    assert ans.refused and ans.first_wrong_step == REFUSED


def test_scoring_and_engine_side():
    sample = select_sample()
    truth = [s.true_step_index for s in sample]
    perfect = score(sample, truth)
    assert perfect.step_correct == perfect.step_expected == 60
    assert perfect.false_alarms == 0 and perfect.correct_total == 40
    always_one = score(sample, [1] * len(sample))
    assert always_one.false_alarms == 40
    engine = baseline.run_engine(sample, runs=2)
    e = score(sample, [a.first_wrong_step for a in engine[0]])
    assert e.false_alarms == 0 and e.step_correct == e.step_expected
    assert [(a.first_wrong_step, a.labels) for a in engine[0]] == [(a.first_wrong_step, a.labels) for a in engine[1]]


def test_end_to_end_with_fake_model(tmp_path, monkeypatch):
    monkeypatch.delenv("BASELINE_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # A "model" that always says the first step is wrong: all false alarms, no determinism issues.
    client = fake_client(lambda p: {"first_wrong_step": 1, "misconception": "x"})
    monkeypatch.setattr("anthropic.Anthropic", lambda: client)
    assert baseline.main(["--out", str(tmp_path), "--runs", "2", "--workers", "2"]) == 0
    summary = (tmp_path / "summary.md").read_text()
    assert "| False alarms on correct submissions (run 1) | 40 of 40 | 0 of 40 |" in summary
    rows = (tmp_path / "results.csv").read_text().splitlines()
    assert len(rows) == 101 and "fill by hand" in rows[0]
    assert len(client.beta.messages.calls) == 200


def test_dry_run_makes_no_calls(capsys):
    assert baseline.main(["--dry-run"]) == 0
    assert FIXED_PROMPT in capsys.readouterr().out


def test_refusal_on_correct_submission_is_not_a_false_alarm():
    sample = select_sample()
    steps = [REFUSED if s.true_step_index == 0 else s.true_step_index for s in sample]
    s = score(sample, steps)
    assert s.false_alarms == 0 and s.refused_or_failed == 40


def test_summary_counts_fallback_answers():
    sample = select_sample()[:3]
    answers = [baseline.ModelAnswer(0, "", served_by=m) for m in ("claude-opus-5-5", "claude-opus-4-8", "")]
    engine = baseline.run_engine(sample, runs=1)
    md = baseline.summary_markdown(sample, "claude-opus-5-5", "medium", [answers], engine)
    assert "| Answered by a fallback model instead of `claude-opus-5-5` (run 1) | 1 |" in md
