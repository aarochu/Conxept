"""Real-derivation evaluation (spec section 8.4): parsing, split, scoring, report."""

import csv
from pathlib import Path

import real_eval
from real_eval import read_rows, split_of, summarize, evaluate_row

TEMPLATE = Path(__file__).resolve().parents[2] / "data" / "real" / "derivations.template.csv"
HEADER = ["id", "problem_id", "student", "step1", "step2", "step3", "step4", "step5", "step6",
          "true_step", "true_label", "notes"]


def write(path, rows):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for r in rows:
            w.writerow(r + [""] * (len(HEADER) - len(r)))


def test_template_rows_score_as_labelled():
    rows, errors = read_rows(TEMPLATE)
    assert errors == [] and len(rows) == 3
    out = {r.id: evaluate_row(r) for r in rows}
    assert out["EX01"].status == 1
    assert out["EX02"].step == 2 and "forgot_causality_u_of_t" in out["EX02"].labels
    assert out["EX03"].step == 2 and out["EX03"].bucket == "other"
    s = summarize(list(out.values()))
    assert s["counts"]["step_correct"] == 2 and s["counts"].get("false_alarms", 0) == 0
    assert s["counts"]["label_correct"] == 1 and s["counts"].get("other_named", 0) == 0


def test_split_is_stable_and_roughly_half():
    ids = [f"R{i:03d}" for i in range(400)]
    first = [split_of(i) for i in ids]
    assert first == [split_of(i) for i in ids]
    assert 150 < first.count("test") < 250


def test_bad_rows_are_reported_not_fatal(tmp_path):
    p = tmp_path / "d.csv"
    write(p, [
        ["", "f3-a1", "A", "1/(1+j*w)", "", "", "", "", "", "0"],
        ["R1", "f3-a1", "A", "int(exp(-t)*exp(-j*w*t),t,0,inf)", "", "", "", "", "", "x"],
        ["R2", "f3-a1", "A", "int(exp(-t)*exp(-j*w*t),t,0,inf)", "", "", "", "", "", "0"],
        ["R2", "f3-a1", "A", "dup", "", "", "", "", "", "0"],
        ["R3", "f9-nope", "A", "t", "", "", "", "", "", "0"],
        ["R4", "f3-a1", "A", "int(exp(-t)*exp(-j*w*t),t,0,inf)", "", "", "", "", "", "5"],
        ["R5", "f3-a1", "A", "__import__('os')", "", "", "", "", "", "1"],
    ])
    rows, errors = read_rows(p)
    assert len(errors) == 3  # missing id, non-integer true_step, duplicate id
    outs = {r.id: evaluate_row(r) for r in rows}
    assert "unknown problem" in outs["R3"].input_error
    assert "outside" in outs["R4"].input_error
    assert outs["R5"].status == 3
    s = summarize(list(outs.values()))["counts"]
    assert s["input_errors"] == 2 and s["parse_errors"] == 1 and s["correct"] == 1


def test_main_writes_report_for_all_split(tmp_path):
    assert real_eval.main([str(TEMPLATE), "--split", "all", "--out", str(tmp_path)]) == 0
    md = (tmp_path / "summary_all.md").read_text()
    assert "| Flagged at the hand-labelled first wrong step | 2 of 2 (100%) |" in md
    assert "in the catalog / residual / Other | 1 / 0 / 1 |" in md
    rows = (tmp_path / "rows_all.csv").read_text().splitlines()
    assert len(rows) == 4


def test_unquoted_comma_is_explained(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text(",".join(HEADER) + "\nR1,f3-a1,A,int(exp(-t)*exp(-j*w*t),t,0,inf),1/(1+j*w),,,,,0,,\n")
    rows, errors = read_rows(p)
    assert rows == [] and "quote steps that contain commas" in errors[0]


def test_misspelled_label_is_an_input_error(tmp_path):
    p = tmp_path / "d.csv"
    write(p, [["R1", "f1-p1-q2-n0", "A", "2/(s+2) - 1/(s+1)", "2*exp(-2*t) - exp(-t)", "", "", "", "", "2",
               "forgot_causality"]])
    rows, _ = read_rows(p)
    assert "not a catalog id" in evaluate_row(rows[0]).input_error
