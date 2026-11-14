"""Evaluate the engine on real, hand-labelled derivations (spec section 8.4).

Procedure from the spec: classmates solve the eight problems on paper, you type each derivation in
the Step DSL, label the true first wrong step by hand, then report step accuracy and how many errors
fall in Other. Half of the rows are kept aside: never tune the catalog on the "test" half and then
report the same rows.

The split is decided by a hash of each row's id, so adding rows never moves an existing row
between halves.

CSV columns (see data/real/derivations.template.csv):
  id           unique row id (anything stable, e.g. R001)
  problem_id   one of the problem ids, e.g. f1-p1-q2-n0
  student      anonymized label (never a real name)
  step1..step6 the student's steps in the Step DSL; leave unused steps empty
  true_step    hand label: 0 if every step is correct, else the first wrong step
  true_label   optional: a catalog id, or "other" for an error the catalog does not describe
  notes        optional free text

Usage:
  python real_eval.py ../data/real/derivations.csv              # reports the test half
  python real_eval.py ../data/real/derivations.csv --split dev  # the half you may tune on
  python real_eval.py ../data/real/derivations.csv --split all
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import signal
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from diagnose import CATALOG, STATUS_DIVERGED, STATUS_PARSE_ERROR, STATUS_VALID, DiagnosisTimeout, diagnose
from problems import problem_from_id

MAX_STEPS = 6
TIMEOUT_S = 5.0
SPLITS = ("test", "dev", "all")


@dataclass
class Row:
    id: str
    problem_id: str
    student: str
    steps: list[str]
    true_step: int
    true_label: str
    notes: str = ""


@dataclass
class Outcome:
    row: Row
    status: int = 0
    step: int = 0
    labels: tuple[str, ...] = ()
    parse_error: str = ""
    input_error: str = ""

    @property
    def bucket(self) -> str:
        """Where a flagged error landed: catalog, residual, or other (unclassified)."""
        if self.status != STATUS_DIVERGED:
            return ""
        if any(label in CATALOG for label in self.labels):
            return "catalog"
        if any(label.startswith("residual:") for label in self.labels):
            return "residual"
        return "other"


def split_of(row_id: str) -> str:
    """Stable half split by hash: the same id always lands in the same half."""
    return "test" if hashlib.sha256(row_id.encode()).digest()[0] % 2 == 0 else "dev"


def read_rows(path: Path) -> tuple[list[Row], list[str]]:
    rows, errors, seen = [], [], set()
    with path.open(newline="") as f:
        for n, rec in enumerate(csv.DictReader(f), start=2):  # line 1 is the header
            rid = (rec.get("id") or "").strip()
            if not rid:
                errors.append(f"line {n}: missing id")
                continue
            if rid in seen:
                errors.append(f"line {n}: duplicate id {rid}")
                continue
            seen.add(rid)
            if any(v for v in rec.get(None) or []):  # DictReader puts surplus columns under None
                errors.append(f"line {n} ({rid}): too many columns; quote steps that contain commas, "
                              'e.g. "int(f, t, 0, inf)"')
                continue
            steps =[(rec.get(f"step{i}") or "").strip() for i in range(1, MAX_STEPS + 1)]
            while steps and not steps[-1]:
                steps.pop()
            try:
                true_step = int((rec.get("true_step") or "").strip())
            except ValueError:
                errors.append(f"line {n} ({rid}): true_step must be an integer")
                continue
            rows.append(
                Row(
                    id=rid,
                    problem_id=(rec.get("problem_id") or "").strip(),
                    student=(rec.get("student") or "").strip(),
                    steps=steps,
                    true_step=true_step,
                    true_label=(rec.get("true_label") or "").strip(),
                    notes=(rec.get("notes") or "").strip(),
                )
            )
    return rows, errors


def _raise_timeout(signum, frame):
    raise DiagnosisTimeout()


def _diagnose_with_timeout(problem, steps):
    """Same per-diagnosis limit as the engine server, so one pathological row can't hang the run."""
    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, TIMEOUT_S)
    try:
        return diagnose(problem, steps)
    except DiagnosisTimeout:
        return None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def evaluate_row(row: Row) -> Outcome:
    try:
        problem = problem_from_id(row.problem_id)
    except KeyError:
        return Outcome(row, input_error=f"unknown problem id {row.problem_id!r}")
    if not row.steps:
        return Outcome(row, input_error="no steps")
    if any(not s for s in row.steps):
        return Outcome(row, input_error="empty step before a filled one")
    if not 0 <= row.true_step <= len(row.steps):
        return Outcome(row, input_error=f"true_step {row.true_step} is outside 0..{len(row.steps)}")
    r = _diagnose_with_timeout(problem, row.steps)
    if r is None:
        return Outcome(row, status=STATUS_PARSE_ERROR, parse_error=f"timed out after {TIMEOUT_S:.0f} s")
    labels = tuple(r.misconception_ids) or ((r.residual_label,) if r.residual_label else ())
    step = r.step_index if r.status == STATUS_DIVERGED else (r.parse_error_step if r.status == STATUS_PARSE_ERROR else 0)
    return Outcome(row, status=r.status, step=step, labels=labels, parse_error=r.parse_error)


def summarize(outcomes: list[Outcome]) -> dict:
    m = Counter()
    buckets = Counter()
    for o in outcomes:
        if o.input_error:
            m["input_errors"] += 1
            continue
        m["rows"] += 1
        if o.status == STATUS_PARSE_ERROR:
            m["parse_errors"] += 1  # a typing problem in the DSL, not a verdict; fix the row
            continue
        if o.row.true_step == 0:
            m["correct"] += 1
            m["false_alarms"] += o.status == STATUS_DIVERGED
            continue
        m["wrong"] += 1
        at_step = o.status == STATUS_DIVERGED and o.step == o.row.true_step
        m["step_correct"] += at_step
        m["missed"] += o.status == STATUS_VALID
        if at_step:
            buckets[o.bucket] += 1
            label = o.row.true_label
            if label and label != "other":
                m["labelled_catalog"] += 1
                m["label_correct"] += label in o.labels
            elif label == "other":
                m["labelled_other"] += 1
                m["other_named"] += o.bucket == "catalog"  # should stay 0
    return {"counts": dict(m), "buckets": dict(buckets)}


def report(summary: dict, split: str, source: str) -> str:
    c, b = summary["counts"], summary["buckets"]
    g = c.get

    def frac(n, d):
        return f"{n} of {d}" + (f" ({100 * n / d:.0f}%)" if d else "")

    lines = [
        f"# Real derivations: `{split}` half" if split != "all" else "# Real derivations: all rows",
        "",
        f"Source: `{source}`. Rows evaluated: {g('rows', 0)}"
        + (f"; skipped for input errors: {g('input_errors')}" if g("input_errors") else "")
        + (f"; DSL parse errors (fix and rerun): {g('parse_errors')}" if g("parse_errors") else "")
        + ".",
        "",
        "| Measure | Result |",
        "| --- | --- |",
        f"| False alarms on correct derivations | {frac(g('false_alarms', 0), g('correct', 0))} |",
        f"| Flagged at the hand-labelled first wrong step | {frac(g('step_correct', 0), g('wrong', 0))} |",
        f"| Wrong derivations the engine called valid | {g('missed', 0)} |",
        f"| Of errors found at the right step: in the catalog / residual / Other | "
        f"{b.get('catalog', 0)} / {b.get('residual', 0)} / {b.get('other', 0)} |",
    ]
    if g("labelled_catalog"):
        lines.append(f"| Catalog label matches your hand label | {frac(g('label_correct', 0), g('labelled_catalog'))} |")
    if g("labelled_other"):
        lines.append(f"| Errors you labelled \"other\" that got a catalog name | {g('other_named', 0)} (should be 0) |")
    lines += [
        "",
        "Real-student results, small sample. Report them whichever way they come out; "
        "do not tune the catalog on the test half.",
    ]
    return "\n".join(lines) + "\n"


def write_rows(path: Path, outcomes: list[Outcome]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "split", "problem_id", "true_step", "true_label", "engine_status", "engine_step",
                    "engine_labels", "bucket", "agrees", "error"])
        status_names = {STATUS_VALID: "valid", STATUS_DIVERGED: "diverged", STATUS_PARSE_ERROR: "parse_error"}
        for o in outcomes:
            agrees = "" if (o.input_error or o.status == STATUS_PARSE_ERROR) else (
                "y" if (o.step if o.status == STATUS_DIVERGED else 0) == o.row.true_step else "n")
            w.writerow([o.row.id, split_of(o.row.id), o.row.problem_id, o.row.true_step, o.row.true_label,
                        status_names.get(o.status, ""), o.step, ";".join(o.labels), o.bucket, agrees,
                        o.input_error or o.parse_error])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--split", choices=SPLITS, default="test")
    ap.add_argument("--out", type=Path, default=Path("real_eval_out"))
    args = ap.parse_args(argv)

    rows, errors = read_rows(args.csv)
    for e in errors:
        print(f"skipped: {e}", file=sys.stderr)
    chosen = [r for r in rows if args.split == "all" or split_of(r.id) == args.split]
    outcomes = [evaluate_row(r) for r in chosen]
    for o in outcomes:
        if o.input_error:
            print(f"skipped {o.row.id}: {o.input_error}", file=sys.stderr)
        elif o.status == STATUS_PARSE_ERROR:
            print(f"parse error {o.row.id} step {o.step}: {o.parse_error}", file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)
    text = report(summarize(outcomes), args.split, str(args.csv))
    (args.out / f"summary_{args.split}.md").write_text(text)
    write_rows(args.out / f"rows_{args.split}.csv", outcomes)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
