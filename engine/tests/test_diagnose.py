"""Diagnosis: correct derivations pass, every catalog mutation is labelled at the right step."""

import pytest
import sympy as sp

from diagnose import STATUS_DIVERGED, STATUS_PARSE_ERROR, STATUS_VALID, diagnose, diagnose_exprs, equiv
from parse_step import t, to_dsl, w
from problems import DEFAULT_IDS, SPEC_CORRECT_STEPS, problem_from_id
from synthetic import rewrite


@pytest.mark.parametrize("pid", DEFAULT_IDS)
def test_spec_correct_steps_valid(pid):
    assert diagnose(problem_from_id(pid), SPEC_CORRECT_STEPS[pid]).status == STATUS_VALID


@pytest.mark.parametrize("pid", DEFAULT_IDS)
def test_generated_and_rewritten_steps_valid(pid):
    p = problem_from_id(pid)
    assert diagnose(p, [to_dsl(e) for e in p.correct_steps()]).status == STATUS_VALID
    assert diagnose(p, rewrite(p)).status == STATUS_VALID


@pytest.mark.parametrize("pid", DEFAULT_IDS)
def test_answer_key_matches_last_step(pid):
    p = problem_from_id(pid)
    assert equiv(p.correct_steps()[-1], p.answer())


def _mutation_cases():
    for pid in DEFAULT_IDS:
        p = problem_from_id(pid)
        for i, entries in p.family.catalog.items():
            for mid, _ in entries:
                yield pid, i, mid


MUTATIONS = list(_mutation_cases())


def test_32_mutation_checks():
    assert len(MUTATIONS) == 32


@pytest.mark.parametrize("pid,i,mid", MUTATIONS)
def test_catalog_mutation_detected(pid, i, mid):
    p = problem_from_id(pid)
    steps = [p.given] + p.correct_steps()
    wrong = dict(p.family.catalog[i])[mid](steps[i - 1], steps[i], p.params)
    assert not equiv(wrong, steps[i]), "mutation coincides with the truth"
    r = diagnose_exprs(p.family, p.params, steps[:i] + [wrong])
    assert r.status == STATUS_DIVERGED
    assert r.step_index == i
    assert r.misconception_ids == [mid]


def test_follow_through_blames_only_first_step():
    # Swapped residues at step 1, then a correct inverse transform of the wrong fractions.
    p = problem_from_id("f1-p1-q2-n0")
    r = diagnose(p, ["-1/(s+2) + 2/(s+1)", "(2*exp(-t) - exp(-2*t))*u(t)"])
    assert (r.status, r.step_index, r.misconception_ids) == (STATUS_DIVERGED, 1, ["residues_assigned_to_wrong_poles"])


def test_missing_u_of_t():
    r = diagnose(problem_from_id("f1-p1-q2-n0"), ["2/(s+2) - 1/(s+1)", "2*exp(-2*t) - exp(-t)"])
    assert r.step_index == 2 and r.misconception_ids == ["forgot_causality_u_of_t"]


@pytest.mark.parametrize(
    "steps,label",
    [
        (["int(exp(-t)*exp(-j*w*t),t,0,inf)", "2/(1+j*w)"], "residual:factor_2"),
        (["int(exp(-t)*exp(-j*w*t),t,0,inf)", "-1/(1+j*w)"], "residual:sign_flip"),
        (["int(exp(-t)*exp(-j*w*t),t,0,inf)", "1/(1-j*w)"], "residual:argument_negated(w)"),
        (["int(exp(-t)*exp(-j*w*t),t,0,inf)", "1/(1+j*w) + 1/3"], "unclassified"),
    ],
)
def test_residual_labels(steps, label):
    r = diagnose(problem_from_id("f3-a1"), steps)
    assert r.status == STATUS_DIVERGED and r.step_index == 2
    assert r.misconception_ids == [] and r.residual_label == label


def test_parse_error_names_step():
    r = diagnose(problem_from_id("f3-a1"), ["int(exp(-t)*exp(-j*w*t),t,0,inf)", "__import__('os')"])
    assert r.status == STATUS_PARSE_ERROR and r.parse_error_step == 2


def test_verdict_is_deterministic():
    p = problem_from_id("f2-a1-b2")
    steps = ["int(exp(-tau)*exp(-2*(t-tau)),tau,0,t)"]
    assert diagnose(p, steps).__dict__ | {"elapsed_ms": 0} == diagnose(p, steps).__dict__ | {"elapsed_ms": 0}


def test_unusual_but_valid_rewrite_does_not_crash():
    # sqrt(s^2) equals s on the sampled half-plane, so step 1 is valid; SymPy cannot split it into
    # partial fractions, so step 2's expectation must come from the correct step 1 instead.
    p = problem_from_id("f1-p1-q2-n0")
    ok = diagnose(p, ["sqrt(s^2)/((s+1)*(s+2))", "(2*exp(-2*t) - exp(-t))*u(t)"])
    assert ok.status == STATUS_VALID
    bad = diagnose(p, ["sqrt(s^2)/((s+1)*(s+2))", "2*exp(-2*t) - exp(-t)"])
    assert bad.step_index == 2 and bad.misconception_ids == ["forgot_causality_u_of_t"]


def test_unexpected_engine_error_is_contained(monkeypatch):
    import diagnose as d

    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(d, "diagnose_exprs", boom)
    r = d.diagnose(problem_from_id("f3-a1"), ["1/(1+j*w)"])
    assert r.status == STATUS_PARSE_ERROR and "could not evaluate" in r.parse_error


def test_complex_heaviside_does_not_abort_diagnosis():
    r = diagnose(problem_from_id("f3-a1"), ["u(j)"])
    assert r.status == STATUS_PARSE_ERROR
    assert r.parse_error_step == 1
