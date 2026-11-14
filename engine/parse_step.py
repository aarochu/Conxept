"""Step DSL parser (spec section 3).

The only accepted student input. Parsing builds a small syntax tree without
evaluating anything, checks the safety rules on that tree, and only then builds
a SymPy expression. No eval, no sympify of raw text.
"""

from __future__ import annotations

import re
from fractions import Fraction

import sympy as sp
from sympy.printing.str import StrPrinter

MAX_LEN = 400
MAX_DIGITS = 6
MAX_EXPONENT = 64
MAX_DEPTH = 60

_ALLOWED = re.compile(r"^[A-Za-z0-9+\-*/^(),. ]*$")
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_NAME = re.compile(r"[A-Za-z]+")

t, tau, w, s = sp.symbols("t tau w s")
VARIABLES = {"t": t, "tau": tau, "w": w, "s": s}
CONSTANTS = {"j": sp.I, "pi": sp.pi, "e": sp.E, "inf": sp.oo}
FUNCTIONS = {"u": 1, "step": 1, "exp": 1, "sin": 1, "cos": 1, "sqrt": 1, "int": 4}


class ParseError(ValueError):
    """Raised for any input the Step DSL does not accept."""


# ---------------------------------------------------------------- tokenizer


def _tokenize(text: str) -> list[tuple[str, str]]:
    if len(text) > MAX_LEN:
        raise ParseError(f"longer than {MAX_LEN} characters")
    if not _ALLOWED.match(text):
        bad = next(c for c in text if not _ALLOWED.match(c))
        raise ParseError(f"character {bad!r} is not allowed")
    toks: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == " ":
            i += 1
        elif c.isdigit() or c == ".":
            m = _NUMBER.match(text, i)
            if not m:
                raise ParseError("a dot must be inside a number")
            num = m.group(0)
            if sum(ch.isdigit() for ch in num) > MAX_DIGITS:
                raise ParseError(f"number {num} has more than {MAX_DIGITS} digits")
            i = m.end()
            if i < n and text[i] == ".":
                raise ParseError("a dot must be inside a number")
            toks.append(("num", num))
        elif c.isalpha():
            m = _NAME.match(text, i)
            name = m.group(0)
            if name not in VARIABLES and name not in CONSTANTS and name not in FUNCTIONS:
                raise ParseError(f"unknown name {name!r}")
            toks.append(("name", name))
            i = m.end()
        else:
            toks.append(("op", c))
            i += 1
    if not toks:
        raise ParseError("empty step")
    return toks


# ------------------------------------------------------------------- parser
# AST nodes are tuples: ("num", str) ("var", name) ("const", name)
# ("call", name, [args]) ("neg", x) ("add"|"sub"|"mul"|"div"|"pow", a, b)


class _Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0
        self.depth = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, op=None):
        tok = self.peek()
        if tok[0] is None:
            raise ParseError("unexpected end of step")
        if op is not None and tok != ("op", op):
            raise ParseError(f"expected {op!r}")
        self.i += 1
        return tok

    def enter(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ParseError("expression is nested too deeply")

    def parse(self):
        node = self.expr()
        if self.peek()[0] is not None:
            raise ParseError(f"unexpected {self.peek()[1]!r}")
        return node

    def expr(self):
        self.enter()
        node = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            node = ("add" if op == "+" else "sub", node, self.term())
        self.depth -= 1
        return node

    def term(self):
        node = self.unary()
        while True:
            tok = self.peek()
            if tok in (("op", "*"), ("op", "/")):
                self.take()
                node = ("mul" if tok[1] == "*" else "div", node, self.unary())
            elif tok[0] in ("num", "name") or tok == ("op", "("):
                node = ("mul", node, self.power())  # implicit multiplication
            else:
                return node

    def unary(self):
        tok = self.peek()
        if tok in (("op", "-"), ("op", "+")):
            self.take()
            self.enter()
            inner = self.unary()
            self.depth -= 1
            return ("neg", inner) if tok[1] == "-" else inner
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek() == ("op", "^"):
            self.take()
            return ("pow", base, self.unary())
        return base

    def atom(self):
        kind, val = self.take()
        if kind == "num":
            return ("num", val)
        if kind == "name":
            if val in FUNCTIONS:
                self.take("(")
                args = [self.expr()]
                while self.peek() == ("op", ","):
                    self.take()
                    args.append(self.expr())
                self.take(")")
                if len(args) != FUNCTIONS[val]:
                    raise ParseError(f"{val} takes {FUNCTIONS[val]} argument(s)")
                if val == "int" and args[1][0] != "var":
                    raise ParseError("int needs a variable as its second argument")
                return ("call", val, args)
            return ("var", val) if val in VARIABLES else ("const", val)
        if (kind, val) == ("op", "("):
            node = self.expr()
            self.take(")")
            return node
        raise ParseError(f"unexpected {val!r}")


# --------------------------------------------------------------- validation


def _children(node):
    if node[0] in ("num", "var", "const"):
        return []
    if node[0] == "call":
        return node[2]
    return node[1:]


def _contains_pow(node) -> bool:
    if node[0] == "pow":
        return True
    return any(_contains_pow(c) for c in _children(node))


def _numeric_value(node):
    """Exact value of a purely numeric subtree, or None."""
    k = node[0]
    if k == "num":
        return Fraction(node[1])
    if k == "neg":
        v = _numeric_value(node[1])
        return None if v is None else -v
    if k in ("add", "sub", "mul", "div"):
        a, b = _numeric_value(node[1]), _numeric_value(node[2])
        if a is None or b is None:
            return None
        if k == "add":
            return a + b
        if k == "sub":
            return a - b
        if k == "mul":
            return a * b
        return None if b == 0 else a / b
    return None


def _validate(node):
    if node[0] == "pow":
        base, exponent = node[1], node[2]
        if _contains_pow(exponent):
            raise ParseError("a power inside an exponent is not allowed")
        if _contains_pow(base):
            raise ParseError("nested powers are not allowed")
        v = _numeric_value(exponent)
        if v is not None and abs(v) > MAX_EXPONENT:
            raise ParseError(f"exponent above {MAX_EXPONENT}")
    for c in _children(node):
        _validate(c)


# ------------------------------------------------------------------ builder

_UNARY = {
    "u": sp.Heaviside,
    "step": sp.Heaviside,
    "exp": sp.exp,
    "sin": sp.sin,
    "cos": sp.cos,
    "sqrt": sp.sqrt,
}


def _build(node):
    k = node[0]
    if k == "num":
        return sp.Rational(node[1])
    if k == "var":
        return VARIABLES[node[1]]
    if k == "const":
        return CONSTANTS[node[1]]
    if k == "neg":
        return -_build(node[1])
    if k == "add":
        return _build(node[1]) + _build(node[2])
    if k == "sub":
        return _build(node[1]) - _build(node[2])
    if k == "mul":
        return _build(node[1]) * _build(node[2])
    if k == "div":
        return _build(node[1]) / _build(node[2])
    if k == "pow":
        return sp.Pow(_build(node[1]), _build(node[2]))
    name, args = node[1], node[2]
    if name == "int":
        f, var, lo, hi = args
        return sp.Integral(_build(f), (VARIABLES[var[1]], _build(lo), _build(hi)))
    return _UNARY[name](_build(args[0]))


def parse_step(text: str) -> sp.Expr:
    """Parse one Step DSL string into a SymPy expression or raise ParseError."""
    tree = _Parser(_tokenize(text)).parse()
    _validate(tree)
    expr = _build(tree)
    if expr.has(sp.zoo, sp.nan):
        raise ParseError("expression is undefined (division by zero)")
    return expr


# ----------------------------------------------------------------- printers


class _DslPrinter(StrPrinter):
    def _print_Integral(self, expr):
        ((var, lo, hi),) = expr.limits
        return f"int({self._print(expr.function)}, {var}, {self._print(lo)}, {self._print(hi)})"

    def _print_Heaviside(self, expr):
        return f"u({self._print(expr.args[0])})"

    def _print_ImaginaryUnit(self, expr):
        return "j"

    def _print_Exp1(self, expr):
        return "e"

    def _print_Infinity(self, expr):
        return "inf"


_DSL = _DslPrinter()


def to_dsl(expr: sp.Expr) -> str:
    """Print a SymPy expression back as a Step DSL string."""
    return _DSL.doprint(expr).replace("**", "^")


def to_latex(expr: sp.Expr) -> str:
    return sp.latex(
        expr, symbol_names={w: r"\omega", tau: r"\tau"}, imaginary_unit="j"
    ).replace(r"\theta", "u")
