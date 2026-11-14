"""Model-only baseline (spec section 8.5): can a chat model alone find the first wrong step?

Same submissions and ground truth for both systems:
  1. 100 submissions from the seed-7 synthetic class: 40 correct, 40 catalog errors, 20 held-out.
  2. Each one goes to Claude with the problem, the correct answer, the student's steps and the
     fixed prompt below. The model answers {"first_wrong_step", "misconception"}.
  3. Step accuracy and false alarms are scored automatically. The misconception name is scored by
     hand: results.csv has the catalog name next to the model's name, with an empty column to fill.
  4. The model runs twice on the same 100 to count disagreements; the engine runs twice as well.

This calls the API ~200 times and costs real money. It never runs in CI.

Usage:
  python baseline.py --dry-run                 # show the sample and one prompt, no API calls
  python baseline.py --out baseline_out        # run (needs Anthropic credentials)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from diagnose import CATALOG, STATUS_DIVERGED, STATUS_VALID, diagnose
from problems import problem_from_id
from synthetic import SyntheticSubmission, generate_class

FIXED_PROMPT = (
    "Here is a signals-and-systems problem and one student's derivation. Check each step against "
    "the student's own previous step. Reply with JSON only: "
    '{"first_wrong_step": <integer, 0 if all steps are correct>, "misconception": <short name or empty>}.'
)

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "first_wrong_step": {"type": "integer"},
        "misconception": {"type": "string"},
    },
    "required": ["first_wrong_step", "misconception"],
    "additionalProperties": False,
}

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
SAMPLE_SEED = 7
CLASS_STUDENTS = 60
MIX = {"correct": 40, "catalog": 40, "heldout": 20}
REFUSED = -1


# ----------------------------------------------------------------- sample


def kind_of(sub: SyntheticSubmission) -> str:
    if sub.true_step_index == 0:
        return "correct"
    return "heldout" if sub.true_label.startswith("heldout:") else "catalog"


def select_sample(seed: int = SAMPLE_SEED, mix: dict[str, int] = MIX) -> list[SyntheticSubmission]:
    """A fixed, reproducible 100-submission sample from the seed-7 class."""
    _, subs = generate_class(CLASS_STUDENTS, seed)
    rng = random.Random(seed)
    out: list[SyntheticSubmission] = []
    for kind, n in mix.items():
        pool = [s for s in subs if kind_of(s) == kind]
        if len(pool) < n:
            raise ValueError(f"only {len(pool)} {kind} submissions in the class, need {n}")
        out.extend(rng.sample(pool, n))
    return out


def build_prompt(sub: SyntheticSubmission) -> str:
    p = problem_from_id(sub.problem_id)
    asked = "\n".join(f"  Step {i}: {p.family.prompts[i]}" for i in sorted(p.family.prompts))
    steps = "\n".join(f"  Step {i}: {expr}" for i, expr in enumerate(sub.steps, start=1))
    return (
        f"{FIXED_PROMPT}\n\n"
        f"Problem: {p.title}\n"
        f"Given (LaTeX): {p.given_latex}\n"
        f"Steps asked for:\n{asked}\n"
        f"Correct final answer (LaTeX): {p.answer_latex()}\n\n"
        "Notation: u(x) is the unit step, j is the imaginary unit, int(f, var, lo, hi) is a definite "
        "integral, ^ is power.\n"
        f"Student's derivation:\n{steps}\n"
    )


# ------------------------------------------------------------------ model


@dataclass
class ModelAnswer:
    first_wrong_step: int
    misconception: str
    served_by: str = ""
    refused: bool = False
    error: str = ""


def ask_model(client, prompt: str, model: str, effort: str, use_fallbacks: bool = True) -> ModelAnswer:
    kwargs = dict(
        model=model,
        max_tokens=16000,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if use_fallbacks:
        # Server-side refusal fallback: a policy decline is re-run on a fallback model in the same call.
        kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    response = client.beta.messages.create(**kwargs)
    if response.stop_reason == "refusal":
        return ModelAnswer(REFUSED, "", served_by=response.model, refused=True)
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
        return ModelAnswer(int(data["first_wrong_step"]), str(data.get("misconception", "")), served_by=response.model)
    except (ValueError, KeyError, TypeError) as e:
        return ModelAnswer(REFUSED, "", served_by=response.model, error=f"unparseable answer: {e}")


def run_model(client, sample, model, effort, runs, workers, use_fallbacks) -> list[list[ModelAnswer]]:
    prompts = [build_prompt(s) for s in sample]

    def one(prompt: str) -> ModelAnswer:
        import anthropic

        try:
            return ask_model(client, prompt, model, effort, use_fallbacks)
        except anthropic.APIStatusError as e:
            return ModelAnswer(REFUSED, "", error=f"API {e.status_code}: {e.message}")
        except anthropic.APIConnectionError as e:
            return ModelAnswer(REFUSED, "", error=f"connection: {e}")

    out = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for r in range(runs):
            print(f"model run {r + 1}/{runs}: {len(prompts)} requests", file=sys.stderr)
            out.append(list(pool.map(one, prompts)))
    return out


# ---------------------------------------------------------------- engine


@dataclass
class EngineAnswer:
    first_wrong_step: int
    labels: list[str] = field(default_factory=list)


def run_engine(sample, runs: int = 2) -> list[list[EngineAnswer]]:
    out = []
    for _ in range(runs):
        answers = []
        for s in sample:
            r = diagnose(problem_from_id(s.problem_id), s.steps)
            step = r.step_index if r.status == STATUS_DIVERGED else (0 if r.status == STATUS_VALID else REFUSED)
            labels = r.misconception_ids or ([r.residual_label] if r.residual_label else [])
            answers.append(EngineAnswer(step, labels))
        out.append(answers)
    return out


# ---------------------------------------------------------------- scoring


@dataclass
class Score:
    step_correct: int
    step_expected: int
    false_alarms: int
    correct_total: int
    refused_or_failed: int = 0

    @property
    def step_accuracy(self) -> float:
        return self.step_correct / self.step_expected if self.step_expected else 0.0


def score(sample, steps: list[int]) -> Score:
    s = Score(0, 0, 0, 0)
    for sub, got in zip(sample, steps):
        if got == REFUSED:
            s.refused_or_failed += 1
        if sub.true_step_index == 0:
            s.correct_total += 1
            # A refusal is reported separately; only a real "step N is wrong" counts as a false alarm.
            s.false_alarms += got > 0
        else:
            s.step_expected += 1
            s.step_correct += got == sub.true_step_index
    return s


def disagreements(a: list, b: list) -> int:
    return sum(x != y for x, y in zip(a, b))


# ----------------------------------------------------------------- report


def write_csv(path: Path, sample, model_runs, engine_runs) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        header = ["submission_id", "problem_id", "kind", "true_step", "true_label", "catalog_name"]
        for r in range(len(model_runs)):
            header += [f"model_step_run{r + 1}", f"model_misconception_run{r + 1}"]
        header += ["engine_step", "engine_labels", "model_name_matches_catalog (fill by hand: y/n)"]
        w.writerow(header)
        for i, sub in enumerate(sample):
            name = CATALOG[sub.true_label].name if sub.true_label in CATALOG else ""
            row = [sub.id, sub.problem_id, kind_of(sub), sub.true_step_index, sub.true_label, name]
            for run in model_runs:
                row += [run[i].first_wrong_step, run[i].misconception or run[i].error]
            e = engine_runs[0][i]
            row += [e.first_wrong_step, ";".join(e.labels), ""]
            w.writerow(row)


def summary_markdown(sample, model, effort, model_runs, engine_runs) -> str:
    m = [score(sample, [a.first_wrong_step for a in run]) for run in model_runs]
    e = score(sample, [a.first_wrong_step for a in engine_runs[0]])
    lines = [
        "# Model-only baseline (spec section 8.5)",
        "",
        f"Sample: {len(sample)} submissions from the seed-{SAMPLE_SEED} synthetic class "
        f"({MIX['correct']} correct, {MIX['catalog']} catalog errors, {MIX['heldout']} held-out).",
        f"Model: `{model}`, effort `{effort}`. Engine: SymPy diagnosis.",
        "",
        "| Measure | Model | Engine |",
        "| --- | --- | --- |",
        f"| Step accuracy (run 1) | {m[0].step_correct} of {m[0].step_expected} | "
        f"{e.step_correct} of {e.step_expected} |",
        f"| False alarms on correct submissions (run 1) | {m[0].false_alarms} of {m[0].correct_total} | "
        f"{e.false_alarms} of {e.correct_total} |",
        f"| Refused or failed (run 1) | {m[0].refused_or_failed} | {e.refused_or_failed} |",
        f"| Answered by a fallback model instead of `{model}` (run 1) | "
        f"{sum(1 for a in model_runs[0] if a.served_by and a.served_by != model)} | — |",
    ]
    if len(model_runs) > 1:
        steps = [[a.first_wrong_step for a in run] for run in model_runs]
        names = [[a.misconception.strip().lower() for a in run] for run in model_runs]
        eng = [[(a.first_wrong_step, tuple(a.labels)) for a in run] for run in engine_runs]
        lines += [
            f"| Run-to-run disagreements, first wrong step | {disagreements(steps[0], steps[1])} | "
            f"{disagreements(eng[0], eng[1])} |",
            f"| Run-to-run disagreements, misconception text | {disagreements(names[0], names[1])} | — |",
        ]
    lines += [
        "",
        "Misconception names are scored by hand in `results.csv`: count a match only if the model "
        "describes the same error as the catalog entry. Report the result whichever way it goes.",
    ]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------- main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="baseline_out", help="output directory")
    ap.add_argument("--model", default=os.environ.get("BASELINE_MODEL", DEFAULT_MODEL))
    ap.add_argument("--effort", default=os.environ.get("BASELINE_EFFORT", DEFAULT_EFFORT))
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-fallbacks", action="store_true", help="disable server-side refusal fallback")
    ap.add_argument("--dry-run", action="store_true", help="print the sample and one prompt; no API calls")
    args = ap.parse_args(argv)
    if not args.model.strip():
        ap.error("--model must not be blank")
    if args.runs < 1:
        ap.error("--runs must be at least 1")
    if args.workers < 1:
        ap.error("--workers must be at least 1")

    sample = select_sample()
    counts = {k: sum(kind_of(s) == k for s in sample) for k in MIX}
    print(f"sample: {len(sample)} submissions {counts}", file=sys.stderr)
    if args.dry_run:
        print(build_prompt(next(s for s in sample if kind_of(s) == "catalog")))
        print(f"would send {len(sample) * args.runs} requests to {args.model}", file=sys.stderr)
        return 0

    import anthropic

    client = anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY, an `ant auth login` profile, or WIF
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model_runs = run_model(client, sample, args.model, args.effort, args.runs, args.workers, not args.no_fallbacks)
    engine_runs = run_engine(sample, runs=max(2, args.runs))
    write_csv(out / "results.csv", sample, model_runs, engine_runs)
    report = summary_markdown(sample, args.model, args.effort, model_runs, engine_runs)
    (out / "summary.md").write_text(report)
    print(report)
    print(f"wrote {out / 'results.csv'} and {out / 'summary.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
