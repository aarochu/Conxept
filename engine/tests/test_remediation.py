"""Remediation: every returned problem is verified and separates the misconception from the key."""

import pytest
import sympy as sp

from diagnose import CATALOG, equiv
from parse_step import t, w, s
from problems import problem_from_id
from remediation import _verify, generate_remediation


@pytest.mark.parametrize("mid", list(CATALOG))
def test_verified_and_discriminating(mid):
    items = generate_remediation(mid, 3, seed=1)
    assert len(items) == 3
    family_key, step = CATALOG[mid].places[0]
    for r in items:
        assert r.verified and len(r.verification_routes) == 2
        p = r.problem
        steps = [p.given] + p.correct_steps()
        wrong = dict(p.family.catalog[step])[mid](steps[step - 1], steps[step], p.params)
        assert not equiv(wrong, steps[step])


def test_seed_changes_order_deterministically():
    a = [r.problem.id for r in generate_remediation("forgot_to_flip_h", 3, seed=1)]
    b = [r.problem.id for r in generate_remediation("forgot_to_flip_h", 3, seed=1)]
    assert a == b


@pytest.mark.parametrize("pid", ["f1-p1-q2-n0", "f2-a1-b2", "f3-a2", "f4-a2-T2"])
def test_wrong_key_fails_verification(pid):
    p = problem_from_id(pid)
    _, ok = _verify(p, p.answer())
    assert ok
    _, bad = _verify(p, 2 * p.answer())
    assert not bad


def test_unknown_misconception():
    with pytest.raises(KeyError):
        generate_remediation("residual:factor_2")
