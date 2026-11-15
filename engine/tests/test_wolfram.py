"""Optional Wolfram cross-check with a fake Wolfram: no App ID or network needed."""

import math

import pytest

import remediation
import wolfram
from problems import problem_from_id


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("WOLFRAM_APP_ID", raising=False)
    monkeypatch.delenv(wolfram.DISABLED_ENV, raising=False)


@pytest.mark.parametrize(
    "text,value",
    [("0.367879", 0.367879), ("≈ -1.25", -1.25), ("3.2×10^-5", 3.2e-5), ("−0.5", -0.5), ("2 x 10^(3)", 2000.0)],
)
def test_parse_number(text, value):
    assert wolfram.parse_number(text) == pytest.approx(value)


def test_parse_number_rejects_prose():
    assert wolfram.parse_number("Wolfram|Alpha did not understand your input") is None


def test_fourier_queries_use_the_course_convention():
    qs = wolfram.queries("f3", {"a": 2})
    assert all("FourierParameters -> {1, -1}" in q for q, _, _ in qs)
    assert {part for _, part, _ in qs} == {"re", "im"}


# f1-p1-q2-n0: F(s) = s/((s+1)(s+2)), f(t) = 2e^{-2t} - e^{-t}, computed by hand.
TRUE_F1 = {0.5: 2 * math.exp(-1.0) - math.exp(-0.5), 1.3: 2 * math.exp(-2.6) - math.exp(-1.3)}


def fake_wolfram(answers):
    def evaluate(expr):
        for point, value in answers.items():
            if f"t -> {point}]" in expr:
                return value
        return None
    return evaluate


def _f1_key_at():
    p = problem_from_id("f1-p1-q2-n0")
    return p, remediation._key_at(p, p.answer())


def test_cross_check_agrees_disagrees_or_abstains(monkeypatch):
    p, key_at = _f1_key_at()
    assert wolfram.cross_check("f1", p.params, key_at) is None  # no App ID: no opinion, no calls
    monkeypatch.setenv("WOLFRAM_APP_ID", "test")
    monkeypatch.setattr(wolfram, "evaluate", fake_wolfram(TRUE_F1))
    assert wolfram.cross_check("f1", p.params, key_at) is True
    monkeypatch.setattr(wolfram, "evaluate", fake_wolfram({k: -v for k, v in TRUE_F1.items()}))
    assert wolfram.cross_check("f1", p.params, key_at) is False
    monkeypatch.setattr(wolfram, "evaluate", fake_wolfram({0.5: TRUE_F1[0.5]}))  # one query unanswered
    assert wolfram.cross_check("f1", p.params, key_at) is None


def test_probe(monkeypatch):
    assert wolfram.probe() is False and not wolfram.enabled()
    monkeypatch.setenv("WOLFRAM_APP_ID", "test")
    monkeypatch.setattr(wolfram, "evaluate", lambda expr: 0.367879)
    assert wolfram.probe() is True and wolfram.enabled()
    monkeypatch.setattr(wolfram, "evaluate", lambda expr: None)
    assert wolfram.probe() is False and not wolfram.enabled()


def _routes(monkeypatch, verdict):
    if verdict is not None:
        monkeypatch.setenv("WOLFRAM_APP_ID", "test")
    monkeypatch.setattr(wolfram, "cross_check", lambda *a: verdict)
    out = remediation.generate_remediation("forgot_to_flip_h", count=2, seed=3)
    assert len(out) == 2 and all(r.verified for r in out)
    return [r.verification_routes for r in out]


def test_remediation_lists_wolfram_only_when_it_agrees(monkeypatch):
    assert _routes(monkeypatch, True) == [["formula", "numeric_quad", "wolfram"]] * 2


def test_remediation_disagreement_keeps_problem_on_two_routes(monkeypatch):
    assert _routes(monkeypatch, False) == [["formula", "numeric_quad"]] * 2


def test_remediation_unchanged_without_wolfram(monkeypatch):
    assert _routes(monkeypatch, None) == [["formula", "numeric_quad"]] * 2
