"""Step DSL parser gate: 12 of 12 valid steps parse, 17 of 17 hostile inputs are rejected."""

import time

import pytest
import sympy as sp

from parse_step import ParseError, parse_step, to_dsl

VALID = [
    "2/(s+2) - 1/(s+1)",
    "(2*exp(-2*t) - exp(-t))*u(t)",
    "u(t)*int(exp(-tau)*exp(-2*(t-tau)),tau,0,t)",
    "u(t)*int(exp(-2*t)*exp(tau),tau,0,t)",
    "u(t)*(exp(-t) - exp(-2*t))",
    "int(exp(-t)*exp(-j*w*t),t,0,inf)",
    "1/(1+j*w)",
    "exp(-2*s)/(s+2)",
    "2 t + 3 step(t)",
    "e^(-2 t) u(t)",
    "sqrt(2*pi)*cos(w*t) + sin(t)",
    "0.5*exp(-1.25*t)",
]

HOSTILE = [
    "__import__('os')",
    "9^9^9^9",
    "t**10000000",
    "exec(t)",
    "t; import os",
    "lambda: 1",
    "1234567*t",
    ".5*t",
    "t.real",
    "t^65",
    "x + 1",
    "s" * 401,
    "exp(t",
    "int(t, 2, 0, 1)",
    "exp(t, s)",
    "(t^2)^3",
    "1/0",
]


def test_counts():
    assert len(VALID) == 12 and len(HOSTILE) == 17


@pytest.mark.parametrize("text", VALID)
def test_valid_parses_and_round_trips(text):
    e = parse_step(text)
    back = parse_step(to_dsl(e))
    assert back == e or sp.simplify(back - e) == 0


@pytest.mark.parametrize("text", HOSTILE)
def test_hostile_rejected_fast(text):
    start = time.perf_counter()
    with pytest.raises(ParseError):
        parse_step(text)
    assert time.perf_counter() - start < 0.05
