"""Synthetic class generator and the spec section 8.2 targets on a seeded class."""

import pytest

from evaluate import run
from parse_step import parse_step
from problems import problem_from_id
from synthetic import generate_class


def test_seed_reproduces_class():
    _, a = generate_class(5, seed=11)
    _, b = generate_class(5, seed=11)
    assert [x.__dict__ for x in a] == [x.__dict__ for x in b]


def test_labels_and_shape():
    problems, subs = generate_class(3, seed=7)
    assert len(problems) == 8 and len(subs) == 24
    assert {s.student_label for s in subs} == {"S001", "S002", "S003"}
    for s in subs:
        for text in s.steps:
            parse_step(text)
        assert len(s.steps) == problem_from_id(s.problem_id).family.n_steps


@pytest.fixture(scope="module")
def evaluation():
    return run(num_students=30, seed=7)


def test_targets(evaluation):
    m = evaluation["metrics"]
    assert m.get("parse_errors", 0) == 0
    assert m.get("false_alarms", 0) == 0
    assert m["divergence_step_correct"] >= 0.99 * m["divergence_step_expected"]
    assert m["label_correct"] >= 0.95 * m["label_expected"]
    assert m["heldout_detected"] >= 0.99 * m["heldout_expected"]
    assert m.get("heldout_named", 0) == 0
    assert evaluation["p95_s"] <= 0.5


def test_mix_has_every_kind(evaluation):
    m = evaluation["metrics"]
    assert m["correct_submissions"] > 0 and m["label_expected"] > 0 and m["heldout_expected"] > 0
