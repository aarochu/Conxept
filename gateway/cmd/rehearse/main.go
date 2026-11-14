// Command rehearse runs the demo script (spec section 11) end to end through the gateway, several
// times in a row, each from a clean database (spec section 10 gate: "Demo runs three times in a
// row from a clean database"). Every step is asserted; the evaluation numbers must be identical
// across runs.
//
// It deletes all data in the target database when -reset is given, so it refuses any database
// host other than localhost unless -allow-remote is also passed.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"connectrpc.com/connect"
	"github.com/jackc/pgx/v5"

	v1 "misconception/gen/go/misconception/v1"
	"misconception/gen/go/misconception/v1/misconceptionv1connect"
)

type step struct {
	name string
	run  func(ctx context.Context, s *state) (string, error)
	// optional steps may fail on stage (spec: if the model call fails, skip the last row and say so)
	optional bool
}

type state struct {
	c            misconceptionv1connect.GatewayServiceClient
	base         string
	classID      string
	clusters     []*v1.Cluster
	eval         string
	classStarted time.Time
}

func main() {
	gateway := flag.String("gateway", "http://localhost:8080", "gateway base URL")
	dbURL := flag.String("db", envOr("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/misconception"), "database to reset")
	runs := flag.Int("runs", 3, "number of rehearsals")
	reset := flag.Bool("reset", false, "delete all data before each run (required for a clean-database rehearsal)")
	allowRemote := flag.Bool("allow-remote", false, "allow -reset on a database host other than localhost")
	flag.Parse()
	if *runs < 1 {
		fail(errors.New("-runs must be at least 1"))
	}

	if *reset {
		if err := checkLocal(*dbURL, *allowRemote); err != nil {
			fail(err)
		}
	}
	steps := demoSteps()
	var evals []string
	for r := 1; r <= *runs; r++ {
		fmt.Printf("\n== rehearsal %d of %d\n", r, *runs)
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		if *reset {
			if err := resetDB(ctx, *dbURL); err != nil {
				cancel()
				fail(fmt.Errorf("reset: %w", err))
			}
			fmt.Println("  database reset")
		}
		s := &state{c: misconceptionv1connect.NewGatewayServiceClient(http.DefaultClient, *gateway), base: *gateway}
		start := time.Now()
		for _, st := range steps {
			t0 := time.Now()
			detail, err := st.run(ctx, s)
			took := time.Since(t0).Round(time.Millisecond)
			switch {
			case err == nil:
				fmt.Printf("  ok    %-28s %8s  %s\n", st.name, took, detail)
			case st.optional:
				fmt.Printf("  skip  %-28s %8s  %v\n", st.name, took, err)
			default:
				cancel()
				fail(fmt.Errorf("rehearsal %d, %s: %w", r, st.name, err))
			}
		}
		cancel()
		fmt.Printf("  total %s\n", time.Since(start).Round(time.Millisecond))
		evals = append(evals, s.eval)
	}
	for i := 1; i < len(evals); i++ {
		if evals[i] != evals[0] {
			fail(fmt.Errorf("evaluation changed between runs:\n  run 1: %s\n  run %d: %s", evals[0], i+1, evals[i]))
		}
	}
	fmt.Printf("\nAll %d rehearsals passed with identical evaluation: %s\n", *runs, evals[0])
}

func demoSteps() []step {
	return []step{
		{"class list", func(ctx context.Context, s *state) (string, error) {
			res, err := s.c.ListClasses(ctx, connect.NewRequest(&v1.ListClassesRequest{}))
			if err != nil {
				return "", err
			}
			return fmt.Sprintf("%d classes", len(res.Msg.Classes)), nil
		}, false},
		{"seed 60 students", func(ctx context.Context, s *state) (string, error) {
			s.classStarted = time.Now()
			res, err := s.c.SeedSyntheticClass(ctx, connect.NewRequest(&v1.SeedSyntheticClassRequest{NumStudents: 60, Seed: 7}))
			if err != nil {
				return "", err
			}
			s.classID = res.Msg.ClassInfo.Id
			if n := res.Msg.ClassInfo.NumSubmissions; n != 480 {
				return "", fmt.Errorf("%d submissions, want 480", n)
			}
			return "480 submissions", nil
		}, false},
		{"process (stream)", func(ctx context.Context, s *state) (string, error) {
			stream, err := s.c.ProcessClass(ctx, connect.NewRequest(&v1.ProcessClassRequest{ClassId: s.classID}))
			if err != nil {
				return "", err
			}
			var last *v1.ProcessClassResponse
			for stream.Receive() {
				last = stream.Msg()
			}
			if err := stream.Err(); err != nil {
				return "", err
			}
			if last == nil || last.Done != last.Total || last.Total != 480 {
				return "", fmt.Errorf("progress ended at %+v", last)
			}
			if err := checkClassDuration(time.Since(s.classStarted)); err != nil {
				return "", err
			}
			return fmt.Sprintf("480 / 480; seed + process %s", time.Since(s.classStarted).Round(time.Millisecond)), nil
		}, false},
		{"heatmap", func(ctx context.Context, s *state) (string, error) {
			res, err := s.c.GetHeatmap(ctx, connect.NewRequest(&v1.GetHeatmapRequest{ClassId: s.classID}))
			if err != nil {
				return "", err
			}
			var darkest *v1.HeatmapCell
			for _, c := range res.Msg.Cells {
				if darkest == nil || c.Failed*darkest.Attempted > darkest.Failed*c.Attempted {
					darkest = c
				}
			}
			if darkest == nil {
				return "", errors.New("no cells")
			}
			return fmt.Sprintf("%d cells; darkest %s step %d (%d/%d)", len(res.Msg.Cells), darkest.ProblemId,
				darkest.StepIndex, darkest.Failed, darkest.Attempted), nil
		}, false},
		{"clusters", func(ctx context.Context, s *state) (string, error) {
			res, err := s.c.GetClusters(ctx, connect.NewRequest(&v1.GetClustersRequest{ClassId: s.classID}))
			if err != nil {
				return "", err
			}
			s.clusters = res.Msg.Clusters
			var catalog, other *v1.Cluster
			for _, c := range s.clusters {
				if c.InCatalog && catalog == nil {
					catalog = c
				}
				if strings.HasPrefix(c.Key, "unclassified:") && other == nil {
					other = c
				}
			}
			if catalog == nil || other == nil {
				return "", errors.New("need a catalog cluster and an Other cluster to show")
			}
			if other.Name != "Other" {
				return "", fmt.Errorf("unclassified cluster named %q", other.Name)
			}
			return fmt.Sprintf("top catalog: %s (%d); Other: %d", catalog.Name, catalog.Count, other.Count), nil
		}, false},
		{"one submission", func(ctx context.Context, s *state) (string, error) {
			top := firstCatalog(s.clusters)
			res, err := s.c.GetSubmission(ctx, connect.NewRequest(&v1.GetSubmissionRequest{SubmissionId: top.ExampleSubmissionIds[0]}))
			if err != nil {
				return "", err
			}
			d := res.Msg.Diagnosis.GetDivergence()
			if d == nil || d.ExpectedLatex == "" || d.StudentLatex == "" {
				return "", errors.New("example has no highlighted step with an expected value")
			}
			return fmt.Sprintf("%s, first wrong step %d", res.Msg.Submission.StudentLabel, d.StepIndex), nil
		}, false},
		{"generate practice (3)", func(ctx context.Context, s *state) (string, error) {
			top := firstCatalog(s.clusters)
			res, err := s.c.GenerateRemediation(ctx, connect.NewRequest(&v1.GatewayServiceGenerateRemediationRequest{
				MisconceptionId: top.Key, Count: 3,
			}))
			if err != nil {
				return "", err
			}
			if len(res.Msg.Problems) != 3 {
				return "", fmt.Errorf("%d problems, want 3", len(res.Msg.Problems))
			}
			for _, p := range res.Msg.Problems {
				if !p.Verified || len(p.VerificationRoutes) < 2 {
					return "", fmt.Errorf("problem %s not verified by two routes", p.Problem.GetId())
				}
			}
			return "3 verified by two routes", nil
		}, false},
		{"evaluation", func(ctx context.Context, s *state) (string, error) {
			res, err := s.c.GetEvaluation(ctx, connect.NewRequest(&v1.GetEvaluationRequest{ClassId: s.classID}))
			if err != nil {
				return "", err
			}
			e := res.Msg
			s.eval = fmt.Sprintf("false alarms %d/%d, step %d/%d, label %d/%d, held-out %d/%d",
				e.FalseAlarms, e.CorrectSubmissions, e.DivergenceStepCorrect, e.DivergenceStepExpected,
				e.LabelCorrect, e.LabelExpected, e.HeldoutDetected, e.HeldoutExpected)
			if err := checkEvaluation(e); err != nil {
				return "", fmt.Errorf("%w: %s", err, s.eval)
			}
			return s.eval, nil
		}, false},
		{"analyze class (model)", func(ctx context.Context, s *state) (string, error) {
			stream, err := s.c.AnalyzeClass(ctx, connect.NewRequest(&v1.AnalyzeClassRequest{ClassId: s.classID}))
			if err != nil {
				return "", err
			}
			calls := 0
			for stream.Receive() {
				ev := stream.Msg().GetEvent()
				switch {
				case ev.GetToolCall() != nil:
					calls++
				case ev.GetBrief() != nil:
					return fmt.Sprintf("brief after %d tool calls", calls), nil
				case ev.GetError() != "":
					return "", errors.New(ev.GetError())
				}
			}
			if err := stream.Err(); err != nil {
				var ce *connect.Error
				if errors.As(err, &ce) && ce.Code() == connect.CodeFailedPrecondition {
					return "", errors.New("no ANTHROPIC_API_KEY on the engine; skip this row on stage")
				}
				return "", err
			}
			return "", errors.New("stream ended without a brief")
		}, true},
		{"dashboard page served", func(ctx context.Context, s *state) (string, error) {
			req, _ := http.NewRequestWithContext(ctx, http.MethodGet, s.base+"/class/"+s.classID, nil)
			res, err := http.DefaultClient.Do(req)
			if err != nil {
				return "", err
			}
			defer res.Body.Close()
			body, _ := io.ReadAll(res.Body)
			if res.StatusCode != http.StatusOK || !strings.Contains(string(body), "<app-root") {
				return "", fmt.Errorf("GET /class/<id>: %d (is the web app built? make web-build)", res.StatusCode)
			}
			return "200", nil
		}, false},
	}
}

func checkClassDuration(elapsed time.Duration) error {
	if elapsed > time.Minute {
		return fmt.Errorf("seed + process took %s; plan target is at most 60s", elapsed.Round(time.Millisecond))
	}
	return nil
}

func checkEvaluation(e *v1.GetEvaluationResponse) error {
	if e.Total != 480 || e.CorrectSubmissions <= 0 || e.FalseAlarms != 0 {
		return errors.New("evaluation must cover 480 submissions with correct examples and zero false alarms")
	}
	for _, metric := range []struct {
		name                   string
		got, expected, minimum int32
	}{
		{"step accuracy", e.DivergenceStepCorrect, e.DivergenceStepExpected, 99},
		{"label accuracy", e.LabelCorrect, e.LabelExpected, 95},
		{"held-out detection", e.HeldoutDetected, e.HeldoutExpected, 99},
	} {
		if metric.expected <= 0 || metric.got < 0 || metric.got > metric.expected || int64(metric.got)*100 < int64(metric.expected)*int64(metric.minimum) {
			return fmt.Errorf("%s below %d%% or invalid denominator", metric.name, metric.minimum)
		}
	}
	return nil
}

func firstCatalog(clusters []*v1.Cluster) *v1.Cluster {
	for _, c := range clusters {
		if c.InCatalog {
			return c
		}
	}
	return clusters[0]
}

func checkLocal(dbURL string, allowRemote bool) error {
	cfg, err := pgx.ParseConfig(dbURL)
	if err != nil {
		return fmt.Errorf("bad database URL: %w", err)
	}
	if allowRemote {
		return nil
	}
	hosts := []string{cfg.Host}
	for _, fallback := range cfg.Fallbacks {
		hosts = append(hosts, fallback.Host)
	}
	for _, host := range hosts {
		if host != "localhost" && host != "127.0.0.1" && host != "::1" && !strings.HasPrefix(host, "/") {
			return fmt.Errorf("refusing to delete data on %q; pass -allow-remote if that is really what you want", host)
		}
	}
	return nil
}

func resetDB(ctx context.Context, dbURL string) error {
	conn, err := pgx.Connect(ctx, dbURL)
	if err != nil {
		return err
	}
	defer conn.Close(ctx)
	_, err = conn.Exec(ctx, `TRUNCATE briefs, ground_truth, diagnoses, submissions, classes, problems`)
	return err
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func fail(err error) {
	fmt.Fprintf(os.Stderr, "\nFAILED: %v\n", err)
	os.Exit(1)
}
