package main

import (
	v1 "misconception/gen/go/misconception/v1"
	"testing"
)

func TestEvaluationGates(t *testing.T) {
	good := func() *v1.GetEvaluationResponse {
		return &v1.GetEvaluationResponse{Total: 480, CorrectSubmissions: 167,
			DivergenceStepCorrect: 313, DivergenceStepExpected: 313,
			LabelCorrect: 235, LabelExpected: 235, HeldoutDetected: 78, HeldoutExpected: 78}
	}
	if err := checkEvaluation(good()); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*v1.GetEvaluationResponse){
		"empty":               func(e *v1.GetEvaluationResponse) { e.Total = 0 },
		"false alarm":         func(e *v1.GetEvaluationResponse) { e.FalseAlarms = 1 },
		"step regression":     func(e *v1.GetEvaluationResponse) { e.DivergenceStepCorrect = 300 },
		"label regression":    func(e *v1.GetEvaluationResponse) { e.LabelCorrect = 220 },
		"heldout regression":  func(e *v1.GetEvaluationResponse) { e.HeldoutDetected = 76 },
		"missing denominator": func(e *v1.GetEvaluationResponse) { e.LabelExpected = 0 },
		"impossible count":    func(e *v1.GetEvaluationResponse) { e.HeldoutDetected = 79 },
	} {
		t.Run(name, func(t *testing.T) {
			e := good()
			mutate(e)
			if checkEvaluation(e) == nil {
				t.Fatal("regression accepted")
			}
		})
	}
}

func TestResetChecksEffectiveDatabaseHost(t *testing.T) {
	for _, dsn := range []string{
		"postgres://localhost/demo?host=remote.example",
		"postgres://localhost,remote.example/demo",
		"host=remote.example dbname=demo",
	} {
		if err := checkLocal(dsn, false); err == nil {
			t.Errorf("accepted remote reset: %s", dsn)
		}
	}
	for _, dsn := range []string{"postgres://localhost/demo", "host=/tmp dbname=demo"} {
		if err := checkLocal(dsn, false); err != nil {
			t.Errorf("rejected local reset: %v", err)
		}
	}
	if err := checkLocal("postgres://remote.example/demo", true); err != nil {
		t.Fatal(err)
	}
}
