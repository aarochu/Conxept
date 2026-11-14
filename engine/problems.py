"""Problem bank (spec section 7.1): families, parameter grids, the eight default problems."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import sympy as sp

from diagnose import FAMILIES, Family
from parse_step import to_dsl, to_latex


@dataclass(frozen=True)
class Problem:
    id: str
    family: Family
    params: dict

    @property
    def title(self) -> str:
        return self.family.title(self.params)

    @property
    def given(self) -> sp.Expr | None:
        return self.family.given(self.params)

    @property
    def given_expr(self) -> str:
        g = self.given
        return "" if g is None else to_dsl(g)

    @property
    def given_latex(self) -> str:
        return self.family.given_latex(self.params)

    def correct_steps(self) -> list[sp.Expr]:
        return self.family.correct_steps(self.params)

    def answer(self) -> sp.Expr:
        return self.family.answer(self.params)

    def answer_latex(self) -> str:
        return to_latex(self.answer())

    def __hash__(self):
        return hash(self.id)


_ID_PATTERNS = {
    "f1": re.compile(r"^f1-p(\d)-q(\d)-n(\d)$"),
    "f2": re.compile(r"^f2-a(\d)-b(\d)$"),
    "f3": re.compile(r"^f3-a(\d)$"),
    "f4": re.compile(r"^f4-a(\d)-T(\d)$"),
}
_PARAM_NAMES = {"f1": ("p", "q", "n"), "f2": ("a", "b"), "f3": ("a",), "f4": ("a", "T")}


@lru_cache(maxsize=1024)
def problem_from_id(pid: str) -> Problem:
    """Build a problem from its stable id. Raises KeyError for unknown or out-of-grid ids."""
    key = pid[:2]
    pat = _ID_PATTERNS.get(key)
    m = pat.match(pid) if pat else None
    if not m:
        raise KeyError(pid)
    params = {name: int(v) for name, v in zip(_PARAM_NAMES[key], m.groups())}
    family = FAMILIES[key]
    if params not in family.grid():
        raise KeyError(pid)
    return Problem(pid, family, params)


def problem_from_params(family: Family, params: dict) -> Problem:
    return problem_from_id(family.id_of(params))


DEFAULT_IDS = [
    "f1-p1-q2-n0",
    "f1-p2-q3-n1",
    "f2-a1-b2",
    "f2-a2-b3",
    "f3-a1",
    "f3-a2",
    "f4-a1-T1",
    "f4-a2-T2",
]

# Correct step values from the spec's default problem table (Step DSL).
SPEC_CORRECT_STEPS = {
    "f1-p1-q2-n0": ["2/(s+2) - 1/(s+1)", "(2*exp(-2*t) - exp(-t))*u(t)"],
    "f1-p2-q3-n1": ["2/(s+3) - 1/(s+2)", "(2*exp(-3*t) - exp(-2*t))*u(t)"],
    "f2-a1-b2": [
        "u(t)*int(exp(-tau)*exp(-2*(t-tau)),tau,0,t)",
        "u(t)*int(exp(-2*t)*exp(tau),tau,0,t)",
        "u(t)*(exp(-t) - exp(-2*t))",
    ],
    "f2-a2-b3": [
        "u(t)*int(exp(-2*tau)*exp(-3*(t-tau)),tau,0,t)",
        "u(t)*int(exp(-3*t)*exp(tau),tau,0,t)",
        "u(t)*(exp(-2*t) - exp(-3*t))",
    ],
    "f3-a1": ["int(exp(-t)*exp(-j*w*t),t,0,inf)", "1/(1+j*w)"],
    "f3-a2": ["int(exp(-2*t)*exp(-j*w*t),t,0,inf)", "1/(2+j*w)"],
    "f4-a1-T1": ["exp(-s)/(s+1)", "exp(-s)/(s+1)"],
    "f4-a2-T2": ["exp(-2*s)/(s+2)", "exp(-2*s)/(s+2)"],
}


def default_problems() -> list[Problem]:
    return [problem_from_id(pid) for pid in DEFAULT_IDS]


def all_misconceptions():
    from diagnose import CATALOG

    return list(CATALOG.values())
