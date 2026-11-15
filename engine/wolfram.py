"""Optional Wolfram|Alpha cross-check of remediation answer keys (spec sections 6.1 and 7.3).

Only active when WOLFRAM_APP_ID is set and the start-up probe succeeds. It adds a third
verification route, "wolfram", when Wolfram agrees with a key at two sample points. Nothing
depends on it: a disagreement, timeout, unparseable reply or missing key leaves the problem
verified by its two existing routes, exactly as without Wolfram.

Uses the Short Answers API (one plain-text result per query) with Wolfram Language input. The
Fourier queries pass FourierParameters -> {1, -1}, the course convention (spec section 3).
"""

from __future__ import annotations

import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

log = logging.getLogger("engine.wolfram")

API_URL = "https://api.wolframalpha.com/v1/result"
TIMEOUT_S = 8
REL_TOL = 1e-4  # short answers carry about six significant digits
DISABLED_ENV = "WOLFRAM_DISABLED"  # set by a failed probe so worker processes skip Wolfram too

_T = (0.5, 1.3)
_W = (0.7, 2.1)
_S = (1.5, 2.5)
_NUMBER = re.compile(r"^[^\d\-+.]*([-+]?\d*\.?\d+)(?:\s*(?:×|x|\*)\s*10\^\(?([-+]?\d+)\)?)?")


def enabled() -> bool:
    return bool(os.environ.get("WOLFRAM_APP_ID")) and not os.environ.get(DISABLED_ENV)


def parse_number(text: str) -> float | None:
    """A real number from a short answer such as '0.367879', '≈ -1.25' or '3.2×10^-5'."""
    m = _NUMBER.match(text.strip().replace("−", "-"))
    if not m:
        return None
    value = float(m.group(1))
    return value * 10 ** int(m.group(2)) if m.group(2) else value


def _fetch(expr: str) -> str:
    query = urllib.parse.urlencode({"appid": os.environ["WOLFRAM_APP_ID"], "i": expr})
    with urllib.request.urlopen(f"{API_URL}?{query}", timeout=TIMEOUT_S) as r:
        return r.read().decode("utf-8", "replace")


@lru_cache(maxsize=512)
def evaluate(expr: str) -> float | None:
    """Wolfram's numeric value of a Wolfram Language expression, or None if it gave none."""
    try:
        return parse_number(_fetch(expr))
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


def probe() -> bool:
    """One known transform at start-up; on failure, disable Wolfram for this process and its workers."""
    if not os.environ.get("WOLFRAM_APP_ID"):
        log.info("WOLFRAM_APP_ID not set; Wolfram cross-check disabled")
        return False
    got = evaluate("N[InverseLaplaceTransform[1/(s + 1), s, t] /. t -> 1]")  # exp(-1) = 0.367879...
    if got is not None and _agrees(got, 0.36787944117144233):
        log.info("Wolfram cross-check enabled")
        return True
    os.environ[DISABLED_ENV] = "1"
    log.info("Wolfram probe failed; Wolfram cross-check disabled")
    return False


def _agrees(a: float, b: float) -> bool:
    return abs(a - b) <= REL_TOL * (1 + abs(a) + abs(b))


def queries(family: str, c: dict) -> list[tuple[str, str, float]]:
    """(Wolfram expression, key part, sample point) triples; key part is 're' or 'im'."""
    if family == "f1":
        f = f"(s + {c['n']})/((s + {c['p']})(s + {c['q']}))"
        return [(f"N[InverseLaplaceTransform[{f}, s, t] /. t -> {v}]", "re", v) for v in _T]
    if family == "f2":
        a, b = c["a"], c["b"]
        return [(f"N[Integrate[Exp[-{a} x] Exp[-{b} ({v} - x)], {{x, 0, {v}}}]]", "re", v) for v in _T]
    if family == "f3":
        ft = f"FourierTransform[Exp[-{c['a']} t] UnitStep[t], t, w, FourierParameters -> {{1, -1}}]"
        return [(f"N[{part.capitalize()}[{ft} /. w -> {v}]]", part, v) for v in _W for part in ("re", "im")]
    if family == "f4":
        lt = f"LaplaceTransform[Exp[-{c['a']} (t - {c['T']})] UnitStep[t - {c['T']}], t, s]"
        return [(f"N[{lt} /. s -> {v}]", "re", v) for v in _S]
    raise ValueError(family)


def cross_check(family: str, params: dict, key_at) -> bool | None:
    """True if Wolfram agrees with the key at every sample point, False if it disagrees anywhere,
    None if Wolfram is off or did not answer every query. key_at(point) returns the key's value."""
    if not enabled():
        return None
    qs = queries(family, params)
    with ThreadPoolExecutor(max_workers=len(qs)) as pool:
        got = list(pool.map(evaluate, [q for q, _, _ in qs]))
    if any(g is None for g in got):
        return None
    for (_, part, point), g in zip(qs, got):
        v = complex(key_at(point))
        if not _agrees(g, v.real if part == "re" else v.imag):
            return False
    return True
