package main

import (
	"context"
	"os"
	"testing"
	"time"

	"connectrpc.com/connect"

	v1 "misconception/gen/go/misconception/v1"
)

// First integration gate (spec section 6.2): one Diagnose call through connect-go WithGRPC over h2c.
func TestEngineGate(t *testing.T) {
	addr := os.Getenv("ENGINE_ADDR")
	if addr == "" {
		t.Skip("ENGINE_ADDR not set")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	c := newEngineClient(addr)
	steps := func(exprs ...string) []*v1.Step {
		out := make([]*v1.Step, len(exprs))
		for i, e := range exprs {
			out[i] = &v1.Step{Index: int32(i + 1), Expr: e}
		}
		return out
	}
	cases := []struct {
		steps []*v1.Step
		want  v1.DiagnosisStatus
	}{
		{steps("2/(s+2) - 1/(s+1)", "(2*exp(-2*t) - exp(-t))*u(t)"), v1.DiagnosisStatus_DIAGNOSIS_STATUS_VALID},
		{steps("2/(s+2) - 1/(s+1)", "2*exp(-2*t) - exp(-t)"), v1.DiagnosisStatus_DIAGNOSIS_STATUS_DIVERGED},
		{steps("__import__('os')"), v1.DiagnosisStatus_DIAGNOSIS_STATUS_PARSE_ERROR},
	}
	for _, tc := range cases {
		res, err := c.Diagnose(ctx, connect.NewRequest(&v1.DiagnoseRequest{ProblemId: "f1-p1-q2-n0", Steps: tc.steps}))
		if err != nil {
			t.Fatalf("Diagnose: %v", err)
		}
		if got := res.Msg.Diagnosis.Status; got != tc.want {
			t.Fatalf("status = %v, want %v", got, tc.want)
		}
	}
	stream, err := c.DiagnoseBatch(ctx, connect.NewRequest(&v1.DiagnoseBatchRequest{Submissions: []*v1.Submission{
		{Id: "a", ProblemId: "f3-a1", Steps: steps("int(exp(-t)*exp(-j*w*t),t,0,inf)", "1/(1+j*w)")},
		{Id: "b", ProblemId: "f3-a1", Steps: steps("int(exp(-t)*exp(-j*w*t),t,0,inf)", "2/(1+j*w)")},
	}}))
	if err != nil {
		t.Fatal(err)
	}
	n := 0
	for stream.Receive() {
		n++
	}
	if err := stream.Err(); err != nil || n != 2 {
		t.Fatalf("batch: %d messages, err %v", n, err)
	}
}
