"""Repeatable synthetic acceptance gates from the build plan, spec section 8.2."""

import argparse
import json
from pathlib import Path

from evaluate import run


def assess(result):
    metrics = result["metrics"]
    failures = []
    for key in ("parse_errors", "false_alarms", "heldout_named"):
        if metrics.get(key, 0):
            failures.append(f"{key} must be zero")
    for name, numerator, denominator, threshold in (
        ("step accuracy", "divergence_step_correct", "divergence_step_expected", .99),
        ("label accuracy", "label_correct", "label_expected", .95),
        ("held-out detection", "heldout_detected", "heldout_expected", .99),
    ):
        total, correct = metrics.get(denominator, 0), metrics.get(numerator, 0)
        if total <= 0 or not 0 <= correct <= total or correct / total < threshold:
            failures.append(f"{name} must be at least {threshold:.0%} with a nonempty denominator")
    if metrics.get("total", 0) != 480 or metrics.get("correct_submissions", 0) <= 0:
        failures.append("expected 480 submissions including correct derivations")
    if not 0 <= result["p95_s"] <= .5:
        failures.append("per-diagnosis p95 must be at most 0.5 seconds")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="optional JSON report path")
    args = parser.parse_args(argv)
    result = run(60, 7, clear_value_cache=True)
    failures = assess(result)
    report = {
        "students": 60, "seed": 7, "metrics": result["metrics"],
        "p95_s": result["p95_s"], "median_s": result["median_s"],
        "max_s": result["max_s"], "passed": not failures, "failures": failures,
        "timing": "numerical value cache cleared before each diagnosis",
        "limitation": "Synthetic internal consistency; not real-student accuracy.",
    }
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
