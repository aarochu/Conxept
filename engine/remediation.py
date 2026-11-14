"""Remediation generator (spec section 7.3).

For a misconception, return practice problems whose correct answer differs from
the wrong answer that misconception produces, with answer keys checked by two
independent routes. A problem is never returned with verified = False.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import mpmath
import sympy as sp

from diagnose import CATALOG, FAMILIES, NotComputable, equiv, values
from parse_step import s, t, tau, to_latex, w
from problems import Problem, problem_from_params

_T_SAMPLES = (0.5, 1.3, 2.7)
_W_SAMPLES = (-2.1, 0.7, 2.9)


@dataclass
class RemediationResult:
    problem: Problem
    answer_key_latex: str
    verification_routes: list[str]
    verified: bool
    why_it_discriminates: str


def _close(a, b) -> bool:
    return abs(a - b) <= 1e-6 * (1 + abs(a) + abs(b))


def _route_numeric_quad(problem: Problem, key: sp.Expr) -> bool:
    """Evaluate the defining integral with mpmath.quad at 3 points and compare with the key."""
    c = problem.params
    if problem.family.key == "f2":
        a, b = c["a"], c["b"]
        f = sp.lambdify(t, key, modules=[{"Heaviside": lambda x, *_: 1 if x > 0 else 0}, "mpmath"])
        for tv in _T_SAMPLES:
            num = mpmath.quad(lambda x: mpmath.exp(-a * x) * mpmath.exp(-b * (tv - x)), [0, tv])
            if not _close(num, f(tv)):
                return False
        return True
    a = c["a"]
    f = sp.lambdify(w, key, modules="mpmath")
    for wv in _W_SAMPLES:
        num = mpmath.quad(
            lambda x: mpmath.exp(-a * x) * mpmath.exp(-1j * wv * x), [0, 1, 2, 4, 8, 16, 32, mpmath.inf]
        )
        if not _close(num, f(wv)):
            return False
    return True


def _route_sympy_transform(problem: Problem, key: sp.Expr) -> bool:
    """f1: SymPy's inverse Laplace of the given; f4: SymPy's Laplace of the given."""
    pos_t = sp.Symbol("t", positive=True)
    if problem.family.key == "f1":
        f = sp.inverse_laplace_transform(problem.given, s, pos_t)
        return equiv(f.subs(pos_t, t) * sp.Heaviside(t), key)
    x = problem.given.subs(t, pos_t)
    F = sp.laplace_transform(x, pos_t, s, noconds=True)
    return equiv(F, key)


def _verify(problem: Problem, key: sp.Expr) -> tuple[list[str], bool]:
    if problem.family.key in ("f2", "f3"):
        route = "numeric_quad"
        ok = _route_numeric_quad(problem, key)
    else:
        route = "sympy_transform"
        try:
            ok = _route_sympy_transform(problem, key)
        except Exception:  # SymPy transform failure means the route did not agree
            ok = False
    # The formula key must also equal the last correct step reached by the step-by-step path.
    formula_ok = values(key) is not None and equiv(problem.correct_steps()[-1], key)
    return ["formula", route], ok and formula_ok


def generate_remediation(misconception_id: str, count: int = 3, seed: int = 0) -> list[RemediationResult]:
    if misconception_id not in CATALOG:
        raise KeyError(misconception_id)
    family_key, step = CATALOG[misconception_id].places[0]
    family = FAMILIES[family_key]
    build = dict(family.catalog[step])[misconception_id]
    candidates = family.grid()
    random.Random(seed).shuffle(candidates)
    out: list[RemediationResult] = []
    for params in candidates:
        if len(out) >= count:
            break
        problem = problem_from_params(family, params)
        steps = [problem.given] + problem.correct_steps()
        try:
            wrong = build(steps[step - 1], steps[step], params)
        except NotComputable:
            continue
        if wrong is None or equiv(wrong, steps[step]):
            continue
        key = problem.answer()
        routes, verified = _verify(problem, key)
        if not verified:
            continue
        out.append(
            RemediationResult(
                problem=problem,
                answer_key_latex=to_latex(key),
                verification_routes=routes,
                verified=True,
                why_it_discriminates=to_latex(wrong),
            )
        )
    return out
