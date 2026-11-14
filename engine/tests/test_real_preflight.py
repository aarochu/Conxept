from pathlib import Path

import real_eval

TEMPLATE = Path(__file__).resolve().parents[2] / "data/real/derivations.template.csv"


def test_preflight_does_not_diagnose_or_write_scores(monkeypatch, tmp_path, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("preflight must not calculate held-out diagnoses")
    monkeypatch.setattr(real_eval, "_diagnose_with_timeout", forbidden)
    output = tmp_path / "scores"
    assert real_eval.main([str(TEMPLATE), "--check", "--split", "all", "--out", str(output)]) == 0
    text = capsys.readouterr().out
    assert "Checked 3 rows" in text and "no diagnoses calculated" in text
    assert "accuracy" not in text and not output.exists()


def test_preflight_rejects_invalid_metadata(tmp_path, capsys):
    source = tmp_path / "rows.csv"
    source.write_text("id,problem_id,step1,true_step\nR1,unknown,t,1\n")
    assert real_eval.main([str(source), "--check", "--split", "all"]) == 2
    assert "unknown problem id" in capsys.readouterr().err


def test_preflight_rejects_csv_errors_even_with_valid_rows(tmp_path):
    source = tmp_path / "rows.csv"
    source.write_text("id,problem_id,step1,true_step\nR1,f3-a1,t,1\nR1,f3-a1,t,1\n")
    assert real_eval.main([str(source), "--check", "--split", "all"]) == 2


def test_preflight_rejects_step_dsl_typos_without_diagnosing(monkeypatch, tmp_path, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("preflight must not calculate held-out diagnoses")
    monkeypatch.setattr(real_eval, "_diagnose_with_timeout", forbidden)
    source = tmp_path / "rows.csv"
    source.write_text("id,problem_id,step1,step2,true_step\nR1,f1-p1-q2-n0,2/(s+2) - 1/(s+1,x,0\n")
    assert real_eval.main([str(source), "--check", "--split", "all"]) == 2
    captured = capsys.readouterr()
    assert "step 1 does not parse" in captured.err
    assert "FAILED" in captured.out
