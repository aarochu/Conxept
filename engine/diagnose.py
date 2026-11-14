"""Diagnosis core (spec sections 3 and 7): equivalence, families, catalog, diagnose.

A step is valid when it equals the correct operation applied to the student's
own previous step. The first step that fails is the divergence. Correctness is
decided here by sampling and mpmath quadrature, never by a language model.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

import mpmath
import sympy as sp

from parse_step import ParseError, parse_step, s, t, tau, to_dsl, to_latex, w

H = sp.Heaviside
E = sp.exp
I = sp.I

# ------------------------------------------------------------- equivalence

SEED = 12345
N_POINTS = 6
REL_TOL = 1e-6
_INF_SPLIT = [0, 1, 2, 4, 8, 16, 32]


def _heaviside(x, *_):
    x = mpmath.re(x)
    return mpmath.mpf(1) if x > 0 else (mpmath.mpf(0) if x < 0 else mpmath.mpf(0.5))


_MODULES = [{"Heaviside": _heaviside}, "mpmath"]


def sample_points() -> list[dict]:
    """The fixed 6 points. Seeded inside every call so a verdict never changes."""
    rng = random.Random(SEED)
    pts = []
    for _ in range(N_POINTS):
        tv = rng.choice((-1, 1)) * rng.uniform(0.3, 3.0)
        tauv = rng.choice((-1, 1)) * rng.uniform(0.3, 3.0)
        wv = rng.uniform(-3.0, 3.0)
        sv = mpmath.mpc(rng.uniform(0.5, 3.0), rng.uniform(-3.0, 3.0))
        pts.append({"t": mpmath.mpf(tv), "tau": mpmath.mpf(tauv), "w": mpmath.mpf(wv), "s": sv})
    return pts


_POINTS = sample_points()


def _compile(e: sp.Expr) -> Callable[[dict], object]:
    """Compile to f(env). Integrals are evaluated with mpmath.quad on a lambdified integrand."""
    if isinstance(e, sp.Integral):
        ((var, lo, hi),) = e.limits
        integrand, flo, fhi = _compile(e.function), _compile(lo), _compile(hi)
        name = str(var)

        def integral(env):
            a, b = flo(env), fhi(env)
            saved = env.get(name)

            def g(x):
                env[name] = x
                return integrand(env)

            try:
                if b == mpmath.inf:
                    pts = [a + d for d in _INF_SPLIT] + [mpmath.inf]
                else:
                    pts = mpmath.linspace(a, b, 4)
                return mpmath.quad(g, pts)
            finally:
                env[name] = saved

        return integral
    if not e.has(sp.Integral):
        syms = sorted(e.free_symbols, key=str)
        names = [str(x) for x in syms]
        f = sp.lambdify(syms, e, modules=_MODULES)
        return lambda env: f(*[env[n] for n in names])
    kids = [_compile(a) for a in e.args]
    if e.is_Add:
        return lambda env: mpmath.fsum(k(env) for k in kids)
    if e.is_Mul:
        return lambda env: mpmath.fprod(k(env) for k in kids)
    if e.is_Pow:
        return lambda env: kids[0](env) ** kids[1](env)
    if e.func == sp.Heaviside:
        return lambda env: _heaviside(kids[0](env))
    fn = getattr(mpmath, e.func.__name__)
    return lambda env: fn(*[k(env) for k in kids])


@lru_cache(maxsize=8192)
def values(e: sp.Expr) -> tuple | None:
    """Values of e at the fixed sample points, or None if it cannot be evaluated."""
    try:
        f = _compile(e)
        out = []
        for p in _POINTS:
            v = mpmath.mpc(f(dict(p)))
            if not (mpmath.isfinite(v.real) and mpmath.isfinite(v.imag)):
                return None
            out.append(v)
        return tuple(out)
    except (TypeError, ValueError, ZeroDivisionError, AttributeError, OverflowError):
        return None


def equiv(a: sp.Expr, b: sp.Expr) -> bool:
    va, vb = values(a), values(b)
    if va is None or vb is None:
        return False
    return all(abs(x - y) <= REL_TOL * (1 + abs(x) + abs(y)) for x, y in zip(va, vb))


# ------------------------------------------------------------- transforms


class NotComputable(ValueError):
    pass


def inverse_laplace_termwise(expr: sp.Expr) -> sp.Expr:
    """c/(s+r) becomes c*exp(-r*t)*u(t), term by term, after partial fractions."""
    if expr.has(t, tau, w, sp.Integral):
        raise NotComputable("not a function of s alone")
    out = sp.Integer(0)
    for term in sp.Add.make_args(sp.apart(sp.together(expr), s)):
        num, den = sp.fraction(sp.factor(term))
        if num.has(s):
            raise NotComputable("numerator depends on s")
        poly = sp.Poly(den, s)
        if poly.degree() != 1:
            raise NotComputable("only simple poles are supported")
        lead, const = poly.all_coeffs()
        out += (num / lead) * E(-(const / lead) * t) * H(t)
    return out


def ft_closed_form(expr: sp.Expr) -> sp.Expr:
    """Replace each int(c*exp(-k t), t, 0, inf) by c/k (Re k > 0 by construction)."""

    def closed(integral):
        f = integral.function
        ((var, lo, hi),) = integral.limits
        if var != t or lo != 0 or hi != sp.oo:
            raise NotComputable("unexpected Fourier integral")
        k = sp.simplify(-sp.diff(f, t) / f)
        if k.has(t):
            raise NotComputable("integrand is not a single exponential")
        return sp.simplify(f.subs(t, 0) / k)

    return expr.replace(lambda e: isinstance(e, sp.Integral), closed)


def evaluate_integrals(expr: sp.Expr) -> sp.Expr:
    out = expr.replace(lambda e: isinstance(e, sp.Integral), lambda e: e.doit())
    if out.has(sp.Integral, sp.Piecewise):
        raise NotComputable("integral did not evaluate in closed form")
    return sp.powsimp(sp.expand(out))


def drop_steps(expr: sp.Expr) -> sp.Expr:
    return expr.replace(lambda e: isinstance(e, sp.Heaviside), lambda e: sp.Integer(1))


def negate_exp_args(expr: sp.Expr) -> sp.Expr:
    return expr.replace(lambda e: isinstance(e, sp.exp), lambda e: E(-e.args[0]))


# ------------------------------------------------------------------ catalog


@dataclass(frozen=True)
class Misconception:
    id: str
    name: str
    description: str
    fix_hint: str
    places: tuple[tuple[str, int], ...]  # (family key, step); first is the primary place


CATALOG: dict[str, Misconception] = {
    m.id: m
    for m in [
        Misconception(
            "cover_up_forgot_other_factor",
            "Cover-up without the other factor",
            "Each residue is taken as the numerator at the pole, without dividing by the other denominator factor.",
            "The cover-up method divides by the remaining factors evaluated at the pole",
            (("f1", 1),),
        ),
        Misconception(
            "residues_assigned_to_wrong_poles",
            "Residues swapped between poles",
            "The two residues are computed correctly but attached to each other's poles.",
            "Match each residue to the pole it was computed at",
            (("f1", 1),),
        ),
        Misconception(
            "forgot_causality_u_of_t",
            "Dropped u(t) (causality)",
            "The unit step is dropped, so the answer is nonzero for t < 0. "
            "Applies at: inverse Laplace step 2; causal convolution steps 1 and 3.",
            "A causal signal is zero for t < 0; keep u(t)",
            (("f1", 2), ("f2", 1), ("f2", 3)),
        ),
        Misconception(
            "pole_sign_flipped_in_exponent",
            "Pole sign flipped in the exponent",
            "A pole at s = -r is turned into exp(+r t) instead of exp(-r t).",
            "A pole at s = -r gives exp(-r t), not exp(+r t)",
            (("f1", 2),),
        ),
        Misconception(
            "forgot_to_flip_h",
            "Convolution without flipping h",
            "The integrand uses x(tau)h(tau) instead of x(tau)h(t - tau).",
            "Convolution flips and shifts h: h(t - tau)",
            (("f2", 1),),
        ),
        Misconception(
            "integration_forgot_divide_by_rate",
            "Integrated an exponential without dividing by its rate",
            "The integral of exp(c tau) is written as exp(c tau), missing the 1/c factor, "
            "so the result lacks the 1/(a - b) factor.",
            "Integrating exp(c tau) gives exp(c tau)/c",
            (("f2", 3),),
        ),
        Misconception(
            "sign_of_exponent_flipped",
            "Fourier kernel sign flipped",
            "The Fourier integral uses exp(+j w t) instead of exp(-j w t).",
            "The kernel is exp(-j w t)",
            (("f3", 1),),
        ),
        Misconception(
            "ordinary_frequency_2pi_in_exponent",
            "2π in the exponent (ordinary frequency)",
            "The kernel exp(-2π j w t) from the ordinary-frequency convention is used with angular frequency w.",
            "w is angular frequency; there is no 2π in the exponent",
            (("f3", 1),),
        ),
        Misconception(
            "copied_tool_default_convention",
            "Copied a tool's default Fourier convention",
            "The integral is written as (1/√(2π))∫x(t)exp(+j w t)dt, a common software default.",
            "Tool defaults differ from the course convention; use the course definition",
            (("f3", 1),),
        ),
        Misconception(
            "unitary_1_over_sqrt_2pi_prefactor",
            "Unitary 1/√(2π) prefactor",
            "A 1/√(2π) prefactor from the unitary convention is added to the course definition.",
            "The course definition has no 1/√(2π) prefactor",
            (("f3", 1),),
        ),
        Misconception(
            "dropped_shift_exponential",
            "Dropped the time-shift exponential",
            "The delay is ignored and the transform is written as 1/(s + a).",
            "A delay of T multiplies by exp(-s T)",
            (("f4", 1),),
        ),
        Misconception(
            "shift_exponent_sign_flipped",
            "Time-shift exponential sign flipped",
            "A delay of T is written as exp(+s T) instead of exp(-s T).",
            "Delay gives exp(-s T), not exp(+s T)",
            (("f4", 1),),
        ),
        Misconception(
            "shift_added_to_pole",
            "Time shift added to the pole",
            "The shift T is placed in the pole, giving 1/(s + a + T).",
            "The time shift goes in the exponential, not in the pole",
            (("f4", 1),),
        ),
        Misconception(
            "time_shift_confused_with_freq_shift",
            "Extra exp(-aT) factor",
            "An extra exp(-a T) factor is included, mixing in a different property.",
            "exp(-a T) belongs to a different property; here the shifted signal already contains it",
            (("f4", 1),),
        ),
    ]
}

# ----------------------------------------------------------------- families

Builder = Callable[[sp.Expr, sp.Expr, dict], sp.Expr]


@dataclass
class Family:
    key: str
    enum: int
    name: str
    kinds: dict[int, str]
    prompts: dict[int, str]
    grid: Callable[[], list[dict]]
    id_of: Callable[[dict], str]
    title: Callable[[dict], str]
    given: Callable[[dict], sp.Expr | None]
    given_latex: Callable[[dict], str]
    setup: Callable[[int, dict], sp.Expr]  # expected value for non-'equal', non-'invL' kinds
    advance: Callable[[int, sp.Expr, dict], sp.Expr]  # what a correct student writes from prev
    answer: Callable[[dict], sp.Expr]  # closed-form key (verification route "formula")
    catalog: dict[int, list[tuple[str, Builder]]] = field(default_factory=dict)

    @property
    def n_steps(self) -> int:
        return len(self.kinds)

    def true_next(self, i: int, prev: sp.Expr | None, ctx: dict) -> sp.Expr:
        kind = self.kinds[i]
        if kind == "equal":
            return prev
        if kind == "invL":
            return inverse_laplace_termwise(prev)
        return self.setup(i, ctx)

    def correct_steps(self, ctx: dict) -> list[sp.Expr]:
        prev, out = self.given(ctx), []
        for i in range(1, self.n_steps + 1):
            prev = self.advance(i, prev, ctx)
            out.append(prev)
        return out


# f1: inverse Laplace by partial fractions -----------------------------------


def _f1_F(c):
    return (s + c["n"]) / ((s + c["p"]) * (s + c["q"]))


def _f1_res(c):
    p, q, n = c["p"], c["q"], c["n"]
    return sp.Rational(n - p, q - p), sp.Rational(n - q, p - q)


def _f1_advance(i, prev, c):
    return sp.apart(prev, s) if i == 1 else inverse_laplace_termwise(prev)


def _f1_answer(c):
    A, B = _f1_res(c)
    return (A * E(-c["p"] * t) + B * E(-c["q"] * t)) * H(t)


def _f1_grid():
    return [
        {"p": p, "q": q, "n": n}
        for p in range(1, 7)
        for q in range(p + 1, 7)
        for n in range(0, 7)
        if n not in (p, q)
    ]


F1 = Family(
    key="f1",
    enum=1,
    name="Inverse Laplace by partial fractions",
    kinds={1: "equal", 2: "invL"},
    prompts={1: "Write F(s) as partial fractions", 2: "Take the inverse Laplace transform f(t)"},
    grid=_f1_grid,
    id_of=lambda c: f"f1-p{c['p']}-q{c['q']}-n{c['n']}",
    title=lambda c: "Inverse Laplace transform by partial fractions",
    given=_f1_F,
    given_latex=lambda c: "F(s) = " + to_latex(_f1_F(c)),
    setup=lambda i, c: None,
    advance=_f1_advance,
    answer=_f1_answer,
    catalog={
        1: [
            (
                "cover_up_forgot_other_factor",
                lambda prev, exp, c: sp.Rational(c["n"] - c["p"]) / (s + c["p"])
                + sp.Rational(c["n"] - c["q"]) / (s + c["q"]),
            ),
            (
                "residues_assigned_to_wrong_poles",
                lambda prev, exp, c: _f1_res(c)[1] / (s + c["p"]) + _f1_res(c)[0] / (s + c["q"]),
            ),
        ],
        2: [
            ("forgot_causality_u_of_t", lambda prev, exp, c: drop_steps(exp)),
            ("pole_sign_flipped_in_exponent", lambda prev, exp, c: negate_exp_args(exp)),
        ],
    },
)

# f2: causal convolution -----------------------------------------------------


def _f2_setup(i, c):
    return H(t) * sp.Integral(E(-c["a"] * tau) * E(-c["b"] * (t - tau)), (tau, 0, t))


def _f2_advance(i, prev, c):
    if i == 1:
        return _f2_setup(1, c)
    if i == 2:
        return prev.replace(
            lambda e: isinstance(e, sp.Integral),
            lambda e: sp.Integral(sp.powsimp(sp.expand(e.function)), *e.limits),
        )
    return evaluate_integrals(prev)


def _f2_answer(c):
    a, b = c["a"], c["b"]
    return H(t) * (E(-b * t) - E(-a * t)) / (a - b)


F2 = Family(
    key="f2",
    enum=2,
    name="Causal convolution",
    kinds={1: "conv_setup", 2: "equal", 3: "equal"},
    prompts={
        1: "Set up y(t) = (x * h)(t) as an integral",
        2: "Simplify the integrand",
        3: "Evaluate the integral",
    },
    grid=lambda: [{"a": a, "b": b} for a in range(1, 7) for b in range(1, 7) if a != b],
    id_of=lambda c: f"f2-a{c['a']}-b{c['b']}",
    title=lambda c: "Causal convolution of two exponentials",
    given=lambda c: None,
    given_latex=lambda c: f"x(t) = e^{{-{c['a']} t}}u(t),\\quad h(t) = e^{{-{c['b']} t}}u(t)".replace(
        "-1 t", "-t"
    ),
    setup=_f2_setup,
    advance=_f2_advance,
    answer=_f2_answer,
    catalog={
        1: [
            ("forgot_causality_u_of_t", lambda prev, exp, c: drop_steps(exp)),
            (
                "forgot_to_flip_h",
                lambda prev, exp, c: H(t)
                * sp.Integral(E(-c["a"] * tau) * E(-c["b"] * tau), (tau, 0, t)),
            ),
        ],
        3: [
            ("forgot_causality_u_of_t", lambda prev, exp, c: drop_steps(exp)),
            (
                "integration_forgot_divide_by_rate",
                lambda prev, exp, c: H(t) * (E(-c["b"] * t) - E(-c["a"] * t)),
            ),
        ],
    },
)

# f3: Fourier transform, course convention X(jw) = int x(t) exp(-j w t) dt ----
# To change the course convention, edit only the four f3 catalog entries and _f3_answer.


def _f3_x(c):
    return E(-c["a"] * t)


def _f3_integral(c, kernel_sign=-1, two_pi=False, prefactor=1):
    k = 2 * sp.pi if two_pi else 1
    return prefactor * sp.Integral(_f3_x(c) * E(kernel_sign * k * I * w * t), (t, 0, sp.oo))


def _f3_answer(c):
    return 1 / (c["a"] + I * w)


_INV_SQRT_2PI = 1 / sp.sqrt(2 * sp.pi)

F3 = Family(
    key="f3",
    enum=3,
    name="Fourier transform",
    kinds={1: "ft_integral", 2: "equal"},
    prompts={1: "Write X(jw) as an integral", 2: "Evaluate it in closed form"},
    grid=lambda: [{"a": a} for a in range(1, 7)],
    id_of=lambda c: f"f3-a{c['a']}",
    title=lambda c: "Fourier transform of a decaying exponential",
    given=lambda c: None,
    given_latex=lambda c: (f"x(t) = e^{{-{c['a']} t}}u(t)".replace("-1 t", "-t"))
    + r",\quad X(j\omega) = \int_{-\infty}^{\infty} x(t)\,e^{-j\omega t}\,dt",
    setup=lambda i, c: _f3_integral(c),
    advance=lambda i, prev, c: _f3_integral(c) if i == 1 else ft_closed_form(prev),
    answer=_f3_answer,
    catalog={
        1: [
            ("sign_of_exponent_flipped", lambda prev, exp, c: _f3_integral(c, kernel_sign=1)),
            ("ordinary_frequency_2pi_in_exponent", lambda prev, exp, c: _f3_integral(c, two_pi=True)),
            (
                "copied_tool_default_convention",
                lambda prev, exp, c: _f3_integral(c, kernel_sign=1, prefactor=_INV_SQRT_2PI),
            ),
            (
                "unitary_1_over_sqrt_2pi_prefactor",
                lambda prev, exp, c: _f3_integral(c, prefactor=_INV_SQRT_2PI),
            ),
        ],
    },
)

# f4: Laplace time shift -----------------------------------------------------


def _f4_x(c):
    return E(-c["a"] * (t - c["T"])) * H(t - c["T"])


def _f4_answer(c):
    return E(-s * c["T"]) / (s + c["a"])


F4 = Family(
    key="f4",
    enum=4,
    name="Laplace transform: time shift",
    kinds={1: "L_shift", 2: "equal"},
    prompts={1: "Take the Laplace transform X(s)", 2: "Rewrite X(s) in simplest form"},
    grid=lambda: [{"a": a, "T": T} for a in range(1, 6) for T in range(1, 5)],
    id_of=lambda c: f"f4-a{c['a']}-T{c['T']}",
    title=lambda c: "Laplace transform of a delayed exponential",
    given=_f4_x,
    given_latex=lambda c: "x(t) = " + to_latex(_f4_x(c)),
    setup=lambda i, c: _f4_answer(c),
    advance=lambda i, prev, c: _f4_answer(c) if i == 1 else prev,
    answer=_f4_answer,
    catalog={
        1: [
            ("dropped_shift_exponential", lambda prev, exp, c: 1 / (s + c["a"])),
            ("shift_exponent_sign_flipped", lambda prev, exp, c: E(s * c["T"]) / (s + c["a"])),
            ("shift_added_to_pole", lambda prev, exp, c: 1 / (s + c["a"] + c["T"])),
            (
                "time_shift_confused_with_freq_shift",
                lambda prev, exp, c: E(-c["a"] * c["T"]) * E(-s * c["T"]) / (s + c["a"]),
            ),
        ],
    },
)

FAMILIES: dict[str, Family] = {f.key: f for f in (F1, F2, F3, F4)}

# ---------------------------------------------------------------- residuals

_FACTORS = [
    ("residual:sign_flip", sp.Integer(-1)),
    ("residual:factor_2", sp.Integer(2)),
    ("residual:factor_1_over_2", sp.Rational(1, 2)),
    ("residual:factor_2pi", 2 * sp.pi),
    ("residual:factor_1_over_2pi", 1 / (2 * sp.pi)),
    ("residual:factor_sqrt_2pi", sp.sqrt(2 * sp.pi)),
    ("residual:factor_1_over_sqrt_2pi", 1 / sp.sqrt(2 * sp.pi)),
]


def residual_label(student: sp.Expr, expected: sp.Expr) -> str:
    for label, k in _FACTORS:
        if equiv(student, k * expected):
            return label
    for var in (s, w, t):
        if expected.has(var) and equiv(student, expected.subs(var, -var)):
            return f"residual:argument_negated({var})"
    return "unclassified"


# ---------------------------------------------------------------- diagnose

STATUS_VALID, STATUS_DIVERGED, STATUS_PARSE_ERROR = 1, 2, 3


@dataclass
class Result:
    status: int
    step_index: int = 0
    misconception_ids: list[str] = field(default_factory=list)
    residual_label: str = ""
    expected_latex: str = ""
    student_latex: str = ""
    parse_error: str = ""
    parse_error_step: int = 0
    elapsed_ms: int = 0


def classify(family: Family, i: int, prev, expected, student, ctx) -> tuple[list[str], str]:
    ids = []
    for mid, build in family.catalog.get(i, []):
        try:
            wrong = build(prev, expected, ctx)
        except NotComputable:
            continue
        if wrong is not None and equiv(student, wrong):
            ids.append(mid)
    if ids:
        return ids, ""
    return [], residual_label(student, expected)


def diagnose_exprs(family: Family, ctx: dict, steps: list[sp.Expr]) -> Result:
    """steps[0] is the given (may be None); steps[1:] are the student's steps."""
    for i in range(1, len(steps)):
        try:
            expected = family.true_next(i, steps[i - 1], ctx)
        except NotComputable:
            expected = None
        if expected is not None and equiv(steps[i], expected):
            continue
        if expected is None:
            ids, label = [], "unclassified"
        else:
            ids, label = classify(family, i, steps[i - 1], expected, steps[i], ctx)
        return Result(
            status=STATUS_DIVERGED,
            step_index=i,
            misconception_ids=ids,
            residual_label=label,
            expected_latex=to_latex(expected) if expected is not None else "",
            student_latex=to_latex(steps[i]),
        )
    return Result(status=STATUS_VALID)


def diagnose(problem, step_texts: list[str]) -> Result:
    """Parse and diagnose. step_texts are the student's steps 1..k (never the given)."""
    start = time.perf_counter()
    family, ctx = problem.family, problem.params
    if len(step_texts) > family.n_steps:
        res = Result(
            status=STATUS_PARSE_ERROR,
            parse_error=f"this problem has {family.n_steps} steps",
            parse_error_step=family.n_steps + 1,
        )
    else:
        exprs, res = [], None
        for i, text in enumerate(step_texts, start=1):
            try:
                exprs.append(parse_step(text))
            except ParseError as e:
                res = Result(status=STATUS_PARSE_ERROR, parse_error=str(e), parse_error_step=i)
                break
        if res is None:
            res = diagnose_exprs(family, ctx, [family.given(ctx)] + exprs)
    res.elapsed_ms = int((time.perf_counter() - start) * 1000)
    return res


__all__ = [
    "CATALOG",
    "FAMILIES",
    "Family",
    "Misconception",
    "NotComputable",
    "Result",
    "diagnose",
    "diagnose_exprs",
    "equiv",
    "to_dsl",
]
