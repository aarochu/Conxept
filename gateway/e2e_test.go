package main

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"connectrpc.com/connect"
	"github.com/jackc/pgx/v5/pgxpool"

	v1 "misconception/gen/go/misconception/v1"
	"misconception/gen/go/misconception/v1/misconceptionv1connect"
)

// End-to-end through the gateway with the Connect protocol (what the browser speaks).
// Needs a running engine (ENGINE_ADDR) and Postgres with the schema (DATABASE_URL).
func newTestGateway(t *testing.T) (misconceptionv1connect.GatewayServiceClient, func()) {
	t.Helper()
	engineAddr, dbURL := os.Getenv("ENGINE_ADDR"), os.Getenv("DATABASE_URL")
	if engineAddr == "" || dbURL == "" {
		t.Skip("ENGINE_ADDR and DATABASE_URL not set")
	}
	pool, err := pgxpool.New(context.Background(), dbURL)
	if err != nil {
		t.Fatal(err)
	}
	store, err := NewStore(pool)
	if err != nil {
		t.Fatal(err)
	}
	gw := &Gateway{engine: newEngineClient(engineAddr), agent: newAgentClient(engineAddr), store: store}
	srv := httptest.NewServer(newMux(gw, t.TempDir()))
	client := misconceptionv1connect.NewGatewayServiceClient(http.DefaultClient, srv.URL)
	return client, func() { srv.Close(); pool.Close() }
}

func code(err error) connect.Code {
	var ce *connect.Error
	if errors.As(err, &ce) {
		return ce.Code()
	}
	return connect.CodeUnknown
}

func TestSeedProcessEvaluate(t *testing.T) {
	c, done := newTestGateway(t)
	defer done()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()

	start := time.Now()
	seeded, err := c.SeedSyntheticClass(ctx, connect.NewRequest(&v1.SeedSyntheticClassRequest{Name: "e2e"}))
	if err != nil {
		t.Fatalf("seed: %v", err)
	}
	info := seeded.Msg.ClassInfo
	if info.NumSubmissions != 480 {
		t.Fatalf("seeded %d submissions, want 480 (60 students x 8 problems)", info.NumSubmissions)
	}

	stream, err := c.ProcessClass(ctx, connect.NewRequest(&v1.ProcessClassRequest{ClassId: info.Id}))
	if err != nil {
		t.Fatal(err)
	}
	var last *v1.ProcessClassResponse
	msgs := 0
	for stream.Receive() {
		last = stream.Msg()
		msgs++
	}
	if err := stream.Err(); err != nil {
		t.Fatalf("process: %v", err)
	}
	elapsed := time.Since(start)
	if last == nil || last.Done != 480 || last.Total != 480 || msgs != 480 {
		t.Fatalf("progress: %d messages, last %+v", msgs, last)
	}
	t.Logf("seed + process 480 submissions: %s", elapsed.Round(time.Millisecond))
	if elapsed > 60*time.Second {
		t.Fatalf("class run took %s, target is 60 s", elapsed)
	}

	classes, err := c.ListClasses(ctx, connect.NewRequest(&v1.ListClassesRequest{}))
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, cl := range classes.Msg.Classes {
		if cl.Id == info.Id {
			found = cl.Processed && cl.NumSubmissions == 480
		}
	}
	if !found {
		t.Fatal("class not listed as processed with 480 submissions")
	}

	heat, err := c.GetHeatmap(ctx, connect.NewRequest(&v1.GetHeatmapRequest{ClassId: info.Id}))
	if err != nil {
		t.Fatal(err)
	}
	if len(heat.Msg.Cells) != 18 { // 2+2+3+3+2+2+2+2 steps across the eight default problems
		t.Fatalf("heatmap has %d cells, want 18", len(heat.Msg.Cells))
	}
	for _, cell := range heat.Msg.Cells {
		if cell.Failed > cell.Attempted || cell.Attempted == 0 {
			t.Fatalf("bad cell %+v", cell)
		}
	}

	clusters, err := c.GetClusters(ctx, connect.NewRequest(&v1.GetClustersRequest{ClassId: info.Id}))
	if err != nil {
		t.Fatal(err)
	}
	cl := clusters.Msg.Clusters
	if len(cl) == 0 {
		t.Fatal("no clusters")
	}
	sawOther := false
	for i, k := range cl {
		if i > 0 && cl[i-1].Count < k.Count {
			t.Fatal("clusters not sorted by count")
		}
		if len(k.ExampleSubmissionIds) == 0 || len(k.ExampleSubmissionIds) > 5 {
			t.Fatalf("cluster %s has %d examples", k.Key, len(k.ExampleSubmissionIds))
		}
		if strings.HasPrefix(k.Key, "unclassified:") {
			sawOther = true
			if k.Name != "Other" || k.InCatalog {
				t.Fatalf("unclassified cluster named %q", k.Name)
			}
		}
	}
	if !sawOther {
		t.Fatal("expected an Other cluster from held-out errors")
	}

	top := cl[0]
	sub, err := c.GetSubmission(ctx, connect.NewRequest(&v1.GetSubmissionRequest{SubmissionId: top.ExampleSubmissionIds[0]}))
	if err != nil {
		t.Fatal(err)
	}
	if sub.Msg.Diagnosis.GetStatus() != v1.DiagnosisStatus_DIAGNOSIS_STATUS_DIVERGED || sub.Msg.Diagnosis.Divergence.ExpectedLatex == "" {
		t.Fatalf("example submission diagnosis: %+v", sub.Msg.Diagnosis)
	}

	ev, err := c.GetEvaluation(ctx, connect.NewRequest(&v1.GetEvaluationRequest{ClassId: info.Id}))
	if err != nil {
		t.Fatal(err)
	}
	e := ev.Msg
	t.Logf("evaluation: total %d, false alarms %d of %d, step %d/%d, label %d/%d, held-out %d/%d",
		e.Total, e.FalseAlarms, e.CorrectSubmissions, e.DivergenceStepCorrect, e.DivergenceStepExpected,
		e.LabelCorrect, e.LabelExpected, e.HeldoutDetected, e.HeldoutExpected)
	if e.Total != 480 || e.FalseAlarms != 0 {
		t.Fatalf("evaluation %+v", e)
	}
	if float64(e.DivergenceStepCorrect) < 0.99*float64(e.DivergenceStepExpected) ||
		float64(e.LabelCorrect) < 0.95*float64(e.LabelExpected) ||
		float64(e.HeldoutDetected) < 0.99*float64(e.HeldoutExpected) {
		t.Fatalf("evaluation below target: %+v", e)
	}
	if len(e.PerLabel) == 0 {
		t.Fatal("no per-label scores")
	}

	// Reprocessing replaces diagnoses rather than duplicating them.
	again, err := c.ProcessClass(ctx, connect.NewRequest(&v1.ProcessClassRequest{ClassId: info.Id}))
	if err != nil {
		t.Fatal(err)
	}
	for again.Receive() {
	}
	if err := again.Err(); err != nil {
		t.Fatal(err)
	}
	ev2, err := c.GetEvaluation(ctx, connect.NewRequest(&v1.GetEvaluationRequest{ClassId: info.Id}))
	if err != nil || ev2.Msg.Total != 480 {
		t.Fatalf("after rerun: %v %+v", err, ev2)
	}
}

func TestPassThroughRPCs(t *testing.T) {
	c, done := newTestGateway(t)
	defer done()
	ctx := context.Background()

	probs, err := c.ListProblems(ctx, connect.NewRequest(&v1.GatewayServiceListProblemsRequest{}))
	if err != nil || len(probs.Msg.Problems) != 8 {
		t.Fatalf("ListProblems: %v", err)
	}
	mis, err := c.ListMisconceptions(ctx, connect.NewRequest(&v1.GatewayServiceListMisconceptionsRequest{}))
	if err != nil || len(mis.Msg.Misconceptions) != 14 {
		t.Fatalf("ListMisconceptions: %v", err)
	}
	try, err := c.TryDerivation(ctx, connect.NewRequest(&v1.TryDerivationRequest{
		ProblemId: "f4-a2-T2", Steps: []*v1.Step{{Index: 1, Expr: "1/(s+2)"}},
	}))
	if err != nil {
		t.Fatal(err)
	}
	if ids := try.Msg.Diagnosis.GetDivergence().GetMisconceptionIds(); len(ids) != 1 || ids[0] != "dropped_shift_exponential" {
		t.Fatalf("TryDerivation: %+v", try.Msg.Diagnosis)
	}
	rem, err := c.GenerateRemediation(ctx, connect.NewRequest(&v1.GatewayServiceGenerateRemediationRequest{MisconceptionId: "forgot_to_flip_h"}))
	if err != nil || len(rem.Msg.Problems) != 3 {
		t.Fatalf("GenerateRemediation: %v", err)
	}
	for _, p := range rem.Msg.Problems {
		if !p.Verified {
			t.Fatal("unverified practice problem returned")
		}
	}
}

func TestLimitsAndErrorCodes(t *testing.T) {
	c, done := newTestGateway(t)
	defer done()
	ctx := context.Background()
	long := strings.Repeat("t", 401)
	cases := []struct {
		name string
		call func() error
		want connect.Code
	}{
		{"too many students", func() error {
			_, err := c.SeedSyntheticClass(ctx, connect.NewRequest(&v1.SeedSyntheticClassRequest{NumStudents: 201}))
			return err
		}, connect.CodeInvalidArgument},
		{"bad error rate", func() error {
			_, err := c.SeedSyntheticClass(ctx, connect.NewRequest(&v1.SeedSyntheticClassRequest{ErrorRate: 1.5}))
			return err
		}, connect.CodeInvalidArgument},
		{"too many practice problems", func() error {
			_, err := c.GenerateRemediation(ctx, connect.NewRequest(&v1.GatewayServiceGenerateRemediationRequest{MisconceptionId: "forgot_to_flip_h", Count: 6}))
			return err
		}, connect.CodeInvalidArgument},
		{"seven steps", func() error {
			steps := make([]*v1.Step, 7)
			for i := range steps {
				steps[i] = &v1.Step{Index: int32(i + 1), Expr: "t"}
			}
			_, err := c.TryDerivation(ctx, connect.NewRequest(&v1.TryDerivationRequest{ProblemId: "f3-a1", Steps: steps}))
			return err
		}, connect.CodeInvalidArgument},
		{"long step", func() error {
			_, err := c.TryDerivation(ctx, connect.NewRequest(&v1.TryDerivationRequest{ProblemId: "f3-a1", Steps: []*v1.Step{{Index: 1, Expr: long}}}))
			return err
		}, connect.CodeInvalidArgument},
		{"long instruction", func() error {
			s, err := c.AnalyzeClass(ctx, connect.NewRequest(&v1.AnalyzeClassRequest{ClassId: "x", Instruction: strings.Repeat("a", 501)}))
			if err != nil {
				return err
			}
			for s.Receive() {
			}
			return s.Err()
		}, connect.CodeInvalidArgument},
		{"unknown problem", func() error {
			_, err := c.TryDerivation(ctx, connect.NewRequest(&v1.TryDerivationRequest{ProblemId: "f9-nope", Steps: []*v1.Step{{Index: 1, Expr: "t"}}}))
			return err
		}, connect.CodeNotFound},
		{"unknown class", func() error {
			_, err := c.GetHeatmap(ctx, connect.NewRequest(&v1.GetHeatmapRequest{ClassId: "00000000-0000-4000-8000-000000000000"}))
			return err
		}, connect.CodeNotFound},
		{"malformed class id", func() error {
			_, err := c.GetClusters(ctx, connect.NewRequest(&v1.GetClustersRequest{ClassId: "not-a-uuid"}))
			return err
		}, connect.CodeNotFound},
		{"unknown submission", func() error {
			_, err := c.GetSubmission(ctx, connect.NewRequest(&v1.GetSubmissionRequest{SubmissionId: "00000000-0000-4000-8000-000000000000"}))
			return err
		}, connect.CodeNotFound},
		{"unknown misconception", func() error {
			_, err := c.GenerateRemediation(ctx, connect.NewRequest(&v1.GatewayServiceGenerateRemediationRequest{MisconceptionId: "nope"}))
			return err
		}, connect.CodeNotFound},
	}
	for _, tc := range cases {
		if got := code(tc.call()); got != tc.want {
			t.Errorf("%s: code %v, want %v", tc.name, got, tc.want)
		}
	}
}

func TestEngineDownIsUnavailable(t *testing.T) {
	gw := &Gateway{engine: newEngineClient("localhost:1"), agent: newAgentClient("localhost:1")}
	srv := httptest.NewServer(newMux(gw, t.TempDir()))
	defer srv.Close()
	c := misconceptionv1connect.NewGatewayServiceClient(http.DefaultClient, srv.URL)
	_, err := c.ListProblems(context.Background(), connect.NewRequest(&v1.GatewayServiceListProblemsRequest{}))
	if code(err) != connect.CodeUnavailable {
		t.Fatalf("code %v, want unavailable (%v)", code(err), err)
	}
}

func TestSPAFallback(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(dir+"/index.html", []byte("<app-root></app-root>"), 0o644); err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(newMux(&Gateway{}, dir))
	defer srv.Close()
	for path, want := range map[string]int{"/": 200, "/class/abc/cluster/x": 200, "/missing.js": 404} {
		res, err := http.Get(srv.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		res.Body.Close()
		if res.StatusCode != want {
			t.Errorf("%s: %d, want %d", path, res.StatusCode, want)
		}
	}
}
