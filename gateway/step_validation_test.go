package main

import (
	"context"
	"testing"

	"connectrpc.com/connect"
	v1 "misconception/gen/go/misconception/v1"
)

func TestTryRejectsInvalidStepIndicesBeforeEngineCall(t *testing.T) {
	for _, indices := range [][]int32{{0}, {-1}, {2}, {1, 1}, {1, 3}, {2, 1}} {
		steps := make([]*v1.Step, len(indices))
		for i, index := range indices {
			steps[i] = &v1.Step{Index: index, Expr: "t"}
		}
		// An unset engine would panic if invalid input reached it.
		_, err := (&Gateway{}).TryDerivation(context.Background(), connect.NewRequest(&v1.TryDerivationRequest{Steps: steps}))
		if connect.CodeOf(err) != connect.CodeInvalidArgument {
			t.Errorf("indices %v: got %v", indices, err)
		}
	}
	if err := checkSteps([]*v1.Step{nil}); err == nil {
		t.Fatal("nil step accepted")
	}
	if err := checkSteps([]*v1.Step{{Index: 1, Expr: "t"}, {Index: 2, Expr: "t"}}); err != nil {
		t.Fatal(err)
	}
}
