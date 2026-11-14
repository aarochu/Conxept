from copy import deepcopy
import json

import pytest
import acceptance


def passing_result():
    return {"metrics": {"total": 480, "correct_submissions": 167,
        "divergence_step_correct": 313, "divergence_step_expected": 313,
        "label_correct": 235, "label_expected": 235,
        "heldout_detected": 78, "heldout_expected": 78},
        "p95_s": .5, "median_s": .1, "max_s": .7}


@pytest.mark.parametrize("key,value", [("parse_errors", 1), ("false_alarms", 1),
    ("heldout_named", 1), ("label_correct", 220), ("heldout_detected", 76),
    ("divergence_step_correct", 300), ("label_expected", 0)])
def test_metric_regressions_fail(key, value):
    result = deepcopy(passing_result())
    result["metrics"][key] = value
    assert acceptance.assess(result)


def test_latency_and_passing_boundary():
    result = passing_result()
    assert acceptance.assess(result) == []
    result["p95_s"] = .501
    assert acceptance.assess(result)


def test_cli_records_failed_run(monkeypatch, tmp_path):
    result = passing_result()
    result["metrics"]["false_alarms"] = 1
    def fake_run(students, seed, *, clear_value_cache):
        assert (students, seed, clear_value_cache) == (60, 7, True)
        return result
    monkeypatch.setattr(acceptance, "run", fake_run)
    output = tmp_path / "report.json"
    assert acceptance.main(["--out", str(output)]) == 1
    assert json.loads(output.read_text())["passed"] is False
