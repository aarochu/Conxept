"""Engine-only evaluation on a synthetic class (spec section 8.2 metrics).

Usage: python evaluate.py [num_students] [seed]

This measures internal consistency: synthetic catalog errors are built by the
same functions the catalog uses to recognize them. It is not an accuracy claim
about real students.
"""

from __future__ import annotations

import statistics
import sys
import time
from collections import Counter

from diagnose import STATUS_DIVERGED, STATUS_PARSE_ERROR, diagnose
from problems import problem_from_id
from synthetic import generate_class


def run(num_students: int = 60, seed: int = 7) -> dict:
    t0 = time.perf_counter()
    _, subs = generate_class(num_students, seed)
    gen_s = time.perf_counter() - t0
    m = Counter()
    per_label = Counter()
    times = []
    failures = []
    for sub in subs:
        st = time.perf_counter()
        r = diagnose(problem_from_id(sub.problem_id), sub.steps)
        times.append(time.perf_counter() - st)
        m["total"] += 1
        if r.status == STATUS_PARSE_ERROR:
            m["parse_errors"] += 1
            failures.append((sub, r))
            continue
        flagged = r.status == STATUS_DIVERGED
        if sub.true_step_index == 0:
            m["correct_submissions"] += 1
            if flagged:
                m["false_alarms"] += 1
                failures.append((sub, r))
            continue
        m["divergence_step_expected"] += 1
        at_true_step = flagged and r.step_index == sub.true_step_index
        m["divergence_step_correct"] += at_true_step
        if sub.true_label.startswith("heldout:"):
            m["heldout_expected"] += 1
            m["heldout_detected"] += at_true_step
            m["heldout_named"] += bool(r.misconception_ids)
        else:
            m["label_expected"] += 1
            hit = at_true_step and sub.true_label in r.misconception_ids
            m["label_correct"] += hit
            per_label[(sub.true_label, hit)] += 1
            m["label_ambiguous"] += len(r.misconception_ids) > 1
        if not at_true_step:
            failures.append((sub, r))
    times.sort()
    return {
        "metrics": dict(m),
        "per_label": per_label,
        "generate_s": gen_s,
        "median_s": statistics.median(times),
        "p95_s": times[int(0.95 * (len(times) - 1))],
        "max_s": times[-1],
        "total_s": sum(times),
        "failures": failures,
    }


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    out = run(n, seed)
    m = out["metrics"]
    print(f"submissions           {m['total']}  (generated in {out['generate_s']:.1f} s)")
    print(f"parse errors          {m.get('parse_errors', 0)}")
    print(f"false alarms          {m.get('false_alarms', 0)} of {m.get('correct_submissions', 0)} correct")
    print(f"step accuracy         {m.get('divergence_step_correct', 0)} of {m.get('divergence_step_expected', 0)}")
    print(f"label accuracy        {m.get('label_correct', 0)} of {m.get('label_expected', 0)}"
          f"  (ambiguous: {m.get('label_ambiguous', 0)})")
    print(f"held-out detected     {m.get('heldout_detected', 0)} of {m.get('heldout_expected', 0)}")
    print(f"held-out given a name {m.get('heldout_named', 0)}")
    print(f"per-diagnosis time    median {out['median_s']:.3f} s, p95 {out['p95_s']:.3f} s, "
          f"max {out['max_s']:.3f} s, total {out['total_s']:.1f} s")
    labels = sorted({lab for lab, _ in out["per_label"]})
    print("per label:", ", ".join(
        f"{lab} {out['per_label'][(lab, True)]}/{out['per_label'][(lab, True)] + out['per_label'][(lab, False)]}"
        for lab in labels))
    for sub, r in out["failures"][:10]:
        print("FAIL", sub.problem_id, sub.true_step_index, sub.true_label, sub.steps, "->",
              r.status, r.step_index, r.misconception_ids, r.residual_label, r.parse_error)


if __name__ == "__main__":
    main()
