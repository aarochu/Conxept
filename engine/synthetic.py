"""Synthetic class generator (spec section 8.1).

One random.Random(seed) drives everything, so a seed reproduces the class exactly.
Student labels are S001, S002, ...; no real names are ever generated.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from functools import lru_cache

import sympy as sp

from diagnose import H, I, NotComputable, equiv
from parse_step import ParseError, parse_step, s, t, tau, to_dsl, w
from problems import Problem, default_problems, problem_from_id

HELDOUT_KINDS = ("additive_constant", "dropped_term", "perturbed_constant")
MAX_ATTEMPTS = 25


@dataclass
class SyntheticSubmission:
    id: str
    problem_id: str
    student_label: str
    steps: list[str]
    true_step_index: int
    true_label: str


@lru_cache(maxsize=512)
def _correct(problem: Problem) -> tuple:
    return tuple(problem.correct_steps())


def _dsl_ok(expr: sp.Expr) -> str:
    """Print to DSL and confirm it parses back to the same value."""
    text = to_dsl(expr)
    if not equiv(parse_step(text), expr):
        raise NotComputable("DSL round trip changed the value")
    return text


def rewrite(problem: Problem) -> list[str]:
    """An equivalent but differently written correct derivation."""
    c, steps = problem.params, _correct(problem)
    key = problem.family.key
    if key == "f1":
        return [to_dsl(sp.together(steps[0])), to_dsl(sp.collect(sp.expand(steps[1]), H(t)))]
    if key == "f2":
        a, b = c["a"], c["b"]
        return [
            to_dsl(H(t) * sp.Integral(sp.exp(-a * tau - b * t + b * tau), (tau, 0, t))),
            to_dsl(H(t) * sp.exp(-b * t) * sp.Integral(sp.exp((b - a) * tau), (tau, 0, t))),
            to_dsl(sp.factor_terms(steps[2])),
        ]
    if key == "f3":
        a = c["a"]
        return [
            to_dsl(sp.Integral(sp.exp(-(a + I * w) * t), (t, 0, sp.oo))),
            to_dsl((a - I * w) / (a**2 + w**2)),
        ]
    a, T = c["a"], c["T"]
    return [f"exp(-{T}*s)*(s+{a})^(-1)", f"1/(exp({T}*s)*(s+{a}))"]


def _catalog_wrongs(problem: Problem, i: int) -> list[tuple[str, sp.Expr]]:
    steps = [problem.given] + list(_correct(problem))
    out = []
    for mid, build in problem.family.catalog.get(i, []):
        try:
            out.append((mid, build(steps[i - 1], steps[i], problem.params)))
        except NotComputable:
            pass
    return out


def _heldout(expected: sp.Expr, kind: str, rng: random.Random, problem: Problem, i: int):
    if kind == "additive_constant":
        # A constant term in F(s) would need a Dirac delta later; never at f1 step 1.
        if problem.family.key == "f1" and i == 1:
            return None
        return expected + sp.Rational(1, 3)
    if kind == "dropped_term":
        if not expected.is_Add:
            return None
        terms = list(expected.args)
        terms.pop(rng.randrange(len(terms)))
        return sp.Add(*terms)
    ints = sorted({int(n) for n in expected.atoms(sp.Integer) if abs(int(n)) >= 2})
    if not ints:
        return None
    v = rng.choice(ints)
    return expected.xreplace({sp.Integer(v): sp.Integer(v + 1)})


def _finish(problem: Problem, i: int, wrong: sp.Expr) -> list[str]:
    """Steps 1..n with the error at step i and consistent follow-through after it."""
    fam, c = problem.family, problem.params
    correct = _correct(problem)
    steps = [to_dsl(e) for e in correct[: i - 1]]
    steps.append(_dsl_ok(wrong))
    prev = wrong
    for j in range(i + 1, fam.n_steps + 1):
        prev = fam.advance(j, prev, c)
        steps.append(_dsl_ok(prev))
    return steps


def _catalog_error(problem: Problem, i: int, rng: random.Random):
    expected = _correct(problem)[i - 1]
    entries = _catalog_wrongs(problem, i)
    for mid, wrong in rng.sample(entries, len(entries)):
        if equiv(wrong, expected):
            continue  # the mutation coincides with the truth for these parameters
        try:
            return _finish(problem, i, wrong), mid
        except (NotComputable, ParseError):
            continue
    return None


def _heldout_error(problem: Problem, i: int, rng: random.Random):
    expected = _correct(problem)[i - 1]
    catalog = [wrong for _, wrong in _catalog_wrongs(problem, i)]
    for _ in range(MAX_ATTEMPTS):
        kind = rng.choice(HELDOUT_KINDS)
        wrong = _heldout(expected, kind, rng, problem, i)
        if wrong is None or equiv(wrong, expected) or any(equiv(wrong, cw) for cw in catalog):
            continue
        try:
            return _finish(problem, i, wrong), f"heldout:{kind}"
        except (NotComputable, ParseError):
            continue
    return None


def make_submission(problem: Problem, rng: random.Random, error_rate: float, heldout_share: float):
    """Returns (steps, true_step_index, true_label)."""
    if rng.random() >= error_rate:
        if rng.random() < 0.5:
            return rewrite(problem), 0, ""
        return [to_dsl(e) for e in _correct(problem)], 0, ""
    i = rng.choice(sorted(problem.family.catalog))
    use_heldout = rng.random() < heldout_share
    made = _heldout_error(problem, i, rng) if use_heldout else _catalog_error(problem, i, rng)
    if made is None:
        made = _catalog_error(problem, i, rng) if use_heldout else _heldout_error(problem, i, rng)
    if made is None:
        return [to_dsl(e) for e in _correct(problem)], 0, ""
    steps, label = made
    return steps, i, label


def generate_class(
    num_students: int,
    seed: int,
    problem_ids: list[str] | None = None,
    error_rate: float = 0.6,
    heldout_share: float = 0.25,
) -> tuple[list[Problem], list[SyntheticSubmission]]:
    rng = random.Random(seed)
    problems = [problem_from_id(p) for p in problem_ids] if problem_ids else default_problems()
    subs = []
    for k in range(num_students):
        label = f"S{k + 1:03d}"
        for p in problems:
            sid = str(uuid.UUID(int=rng.getrandbits(128), version=4))
            steps, true_step, true_label = make_submission(p, rng, error_rate, heldout_share)
            subs.append(SyntheticSubmission(sid, p.id, label, steps, true_step, true_label))
    return problems, subs
