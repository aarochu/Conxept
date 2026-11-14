package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"strings"
	"sync"

	"connectrpc.com/connect"

	v1 "misconception/gen/go/misconception/v1"
	"misconception/gen/go/misconception/v1/misconceptionv1connect"
)

// Limits and defaults from spec section 4, enforced before any engine call.
const (
	defaultStudents     = 60
	maxStudents         = 200
	defaultSeed         = 7
	defaultErrorRate    = 0.6
	defaultHeldoutShare = 0.25
	defaultRemediation  = 3
	maxRemediation      = 5
	maxSteps            = 6
	maxExprLen          = 400
	maxInstructionLen   = 500
	maxClusterExamples  = 5
	insertBatchSize     = 50
)

type Gateway struct {
	misconceptionv1connect.UnimplementedGatewayServiceHandler
	engine misconceptionv1connect.EngineServiceClient
	agent  misconceptionv1connect.InstructorAgentServiceClient
	store  *Store

	catalogMu sync.Mutex
	catalog   map[string]*v1.Misconception
}

func invalid(format string, args ...any) error {
	return connect.NewError(connect.CodeInvalidArgument, fmt.Errorf(format, args...))
}

// engineErr keeps the engine's status code; anything that is not a status from the engine means it is unreachable.
func engineErr(err error) error {
	var ce *connect.Error
	if errors.As(err, &ce) && ce.Code() != connect.CodeUnknown {
		return err
	}
	return connect.NewError(connect.CodeUnavailable, fmt.Errorf("engine unreachable: %w", err))
}

func dbErr(err error, what string) error {
	if errors.Is(err, errNotFound) {
		return connect.NewError(connect.CodeNotFound, fmt.Errorf("unknown %s", what))
	}
	log.Printf("db error (%s): %v", what, err)
	return connect.NewError(connect.CodeInternal, errors.New("database error"))
}

func checkSteps(steps []*v1.Step) error {
	if len(steps) == 0 {
		return invalid("at least one step is required")
	}
	if len(steps) > maxSteps {
		return invalid("at most %d steps", maxSteps)
	}
	for _, s := range steps {
		if len(s.Expr) > maxExprLen {
			return invalid("step %d is longer than %d characters", s.Index, maxExprLen)
		}
	}
	return nil
}

// ------------------------------------------------------------ catalog names

func (g *Gateway) misconceptions(ctx context.Context) (map[string]*v1.Misconception, error) {
	g.catalogMu.Lock()
	defer g.catalogMu.Unlock()
	if g.catalog != nil {
		return g.catalog, nil
	}
	res, err := g.engine.ListMisconceptions(ctx, connect.NewRequest(&v1.ListMisconceptionsRequest{}))
	if err != nil {
		return nil, engineErr(err)
	}
	g.catalog = map[string]*v1.Misconception{}
	for _, m := range res.Msg.Misconceptions {
		g.catalog[m.Id] = m
	}
	return g.catalog, nil
}

var residualNames = map[string]string{
	"residual:sign_flip":              "Sign flipped",
	"residual:factor_2":               "Off by a factor of 2",
	"residual:factor_1_over_2":        "Off by a factor of 1/2",
	"residual:factor_2pi":             "Off by a factor of 2π",
	"residual:factor_1_over_2pi":      "Off by a factor of 1/(2π)",
	"residual:factor_sqrt_2pi":        "Off by a factor of √(2π)",
	"residual:factor_1_over_sqrt_2pi": "Off by a factor of 1/√(2π)",
	"residual:argument_negated(s)":    "Argument negated (s)",
	"residual:argument_negated(w)":    "Argument negated (ω)",
	"residual:argument_negated(t)":    "Argument negated (t)",
}

func clusterName(key string, catalog map[string]*v1.Misconception) (string, bool) {
	if m, ok := catalog[key]; ok {
		return m.Name, true
	}
	if strings.HasPrefix(key, "unclassified:") {
		return "Other", false
	}
	if n, ok := residualNames[key]; ok {
		return n, false
	}
	return key, false
}

// ----------------------------------------------------------------- RPCs

func (g *Gateway) ListProblems(ctx context.Context, _ *connect.Request[v1.GatewayServiceListProblemsRequest]) (*connect.Response[v1.GatewayServiceListProblemsResponse], error) {
	res, err := g.engine.ListProblems(ctx, connect.NewRequest(&v1.ListProblemsRequest{}))
	if err != nil {
		return nil, engineErr(err)
	}
	return connect.NewResponse(&v1.GatewayServiceListProblemsResponse{Problems: res.Msg.Problems}), nil
}

func (g *Gateway) ListMisconceptions(ctx context.Context, _ *connect.Request[v1.GatewayServiceListMisconceptionsRequest]) (*connect.Response[v1.GatewayServiceListMisconceptionsResponse], error) {
	res, err := g.engine.ListMisconceptions(ctx, connect.NewRequest(&v1.ListMisconceptionsRequest{}))
	if err != nil {
		return nil, engineErr(err)
	}
	return connect.NewResponse(&v1.GatewayServiceListMisconceptionsResponse{Misconceptions: res.Msg.Misconceptions}), nil
}

func (g *Gateway) SeedSyntheticClass(ctx context.Context, req *connect.Request[v1.SeedSyntheticClassRequest]) (*connect.Response[v1.SeedSyntheticClassResponse], error) {
	m := req.Msg
	n, seed, errRate, heldout := m.NumStudents, m.Seed, m.ErrorRate, m.HeldoutShare
	if n == 0 {
		n = defaultStudents
	}
	if n < 1 || n > maxStudents {
		return nil, invalid("num_students must be 1 to %d", maxStudents)
	}
	if seed == 0 {
		seed = defaultSeed
	}
	if errRate == 0 {
		errRate = defaultErrorRate
	}
	if heldout == 0 {
		heldout = defaultHeldoutShare
	}
	if errRate < 0 || errRate > 1 || heldout < 0 || heldout > 1 {
		return nil, invalid("error_rate and heldout_share must be 0 to 1")
	}
	name := strings.TrimSpace(m.Name)
	if name == "" {
		name = fmt.Sprintf("Synthetic class (%d students, seed %d)", n, seed)
	}
	gen, err := g.engine.GenerateClass(ctx, connect.NewRequest(&v1.GenerateClassRequest{
		NumStudents: n, Seed: seed, ErrorRate: errRate, HeldoutShare: heldout,
	}))
	if err != nil {
		return nil, engineErr(err)
	}
	info, err := g.store.SeedClass(ctx, name, gen.Msg)
	if err != nil {
		return nil, dbErr(err, "class")
	}
	return connect.NewResponse(&v1.SeedSyntheticClassResponse{ClassInfo: info}), nil
}

func (g *Gateway) ListClasses(ctx context.Context, _ *connect.Request[v1.ListClassesRequest]) (*connect.Response[v1.ListClassesResponse], error) {
	classes, err := g.store.ListClasses(ctx)
	if err != nil {
		return nil, dbErr(err, "classes")
	}
	return connect.NewResponse(&v1.ListClassesResponse{Classes: classes}), nil
}

func (g *Gateway) ProcessClass(ctx context.Context, req *connect.Request[v1.ProcessClassRequest], stream *connect.ServerStream[v1.ProcessClassResponse]) error {
	classID := req.Msg.ClassId
	if err := g.store.ClassExists(ctx, classID); err != nil {
		return dbErr(err, "class")
	}
	subs, err := g.store.ClassSubmissions(ctx, classID)
	if err != nil {
		return dbErr(err, "class")
	}
	// Rerunning replaces existing diagnoses; the class reads as unprocessed until this run finishes.
	if err := g.store.StartProcessing(ctx, classID); err != nil {
		return dbErr(err, "class")
	}
	total := int32(len(subs))
	if total == 0 {
		if err := g.store.MarkProcessed(ctx, classID); err != nil {
			return dbErr(err, "class")
		}
		return stream.Send(&v1.ProcessClassResponse{Done: 0, Total: 0})
	}
	batch, err := g.engine.DiagnoseBatch(ctx, connect.NewRequest(&v1.DiagnoseBatchRequest{Submissions: subs}))
	if err != nil {
		return engineErr(err)
	}
	defer batch.Close()
	// The engine streams one result per message; buffer them so a remote database
	// sees one round trip per insertBatchSize results instead of one per submission.
	var done int32
	pending := make([]*v1.SubmissionResult, 0, insertBatchSize)
	flush := func() error {
		if len(pending) == 0 {
			return nil
		}
		if err := g.store.InsertDiagnoses(ctx, pending); err != nil {
			return dbErr(err, "diagnosis")
		}
		pending = pending[:0]
		return nil
	}
	for batch.Receive() {
		msg := batch.Msg()
		pending = append(pending, msg.Results...)
		if len(pending) >= insertBatchSize {
			if err := flush(); err != nil {
				return err
			}
		}
		done = msg.Done
		if err := stream.Send(&v1.ProcessClassResponse{Done: msg.Done, Total: msg.Total}); err != nil {
			return err
		}
	}
	if err := batch.Err(); err != nil {
		return engineErr(err)
	}
	if err := flush(); err != nil {
		return err
	}
	if done != total {
		return connect.NewError(connect.CodeUnavailable, fmt.Errorf("engine stream ended at %d of %d", done, total))
	}
	if err := g.store.MarkProcessed(ctx, classID); err != nil {
		return dbErr(err, "class")
	}
	return nil
}

func (g *Gateway) GetHeatmap(ctx context.Context, req *connect.Request[v1.GetHeatmapRequest]) (*connect.Response[v1.GetHeatmapResponse], error) {
	if err := g.store.ClassExists(ctx, req.Msg.ClassId); err != nil {
		return nil, dbErr(err, "class")
	}
	cells, err := g.store.Heatmap(ctx, req.Msg.ClassId)
	if err != nil {
		return nil, dbErr(err, "class")
	}
	return connect.NewResponse(&v1.GetHeatmapResponse{Cells: cells}), nil
}

func (g *Gateway) GetClusters(ctx context.Context, req *connect.Request[v1.GetClustersRequest]) (*connect.Response[v1.GetClustersResponse], error) {
	if err := g.store.ClassExists(ctx, req.Msg.ClassId); err != nil {
		return nil, dbErr(err, "class")
	}
	rows, err := g.store.Clusters(ctx, req.Msg.ClassId)
	if err != nil {
		return nil, dbErr(err, "class")
	}
	catalog, err := g.misconceptions(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]*v1.Cluster, 0, len(rows))
	for _, r := range rows {
		name, inCatalog := clusterName(r.Key, catalog)
		examples := r.Examples
		if len(examples) > maxClusterExamples {
			examples = examples[:maxClusterExamples]
		}
		out = append(out, &v1.Cluster{
			Key: r.Key, Name: name, Count: int32(r.Count), Family: v1.Family(r.Family),
			StepIndex: r.Step, InCatalog: inCatalog, ExampleSubmissionIds: examples,
		})
	}
	return connect.NewResponse(&v1.GetClustersResponse{Clusters: out}), nil
}

func (g *Gateway) GetSubmission(ctx context.Context, req *connect.Request[v1.GetSubmissionRequest]) (*connect.Response[v1.GetSubmissionResponse], error) {
	sub, diag, err := g.store.Submission(ctx, req.Msg.SubmissionId)
	if err != nil {
		return nil, dbErr(err, "submission")
	}
	return connect.NewResponse(&v1.GetSubmissionResponse{Submission: sub, Diagnosis: diag}), nil
}

func (g *Gateway) TryDerivation(ctx context.Context, req *connect.Request[v1.TryDerivationRequest]) (*connect.Response[v1.TryDerivationResponse], error) {
	if err := checkSteps(req.Msg.Steps); err != nil {
		return nil, err
	}
	res, err := g.engine.Diagnose(ctx, connect.NewRequest(&v1.DiagnoseRequest{ProblemId: req.Msg.ProblemId, Steps: req.Msg.Steps}))
	if err != nil {
		return nil, engineErr(err)
	}
	return connect.NewResponse(&v1.TryDerivationResponse{Diagnosis: res.Msg.Diagnosis}), nil
}

func (g *Gateway) GenerateRemediation(ctx context.Context, req *connect.Request[v1.GatewayServiceGenerateRemediationRequest]) (*connect.Response[v1.GatewayServiceGenerateRemediationResponse], error) {
	count := req.Msg.Count
	if count == 0 {
		count = defaultRemediation
	}
	if count < 1 || count > maxRemediation {
		return nil, invalid("count must be 1 to %d", maxRemediation)
	}
	res, err := g.engine.GenerateRemediation(ctx, connect.NewRequest(&v1.GenerateRemediationRequest{
		MisconceptionId: req.Msg.MisconceptionId, Count: count, Seed: req.Msg.Seed,
	}))
	if err != nil {
		return nil, engineErr(err)
	}
	return connect.NewResponse(&v1.GatewayServiceGenerateRemediationResponse{Problems: res.Msg.Problems}), nil
}

func (g *Gateway) AnalyzeClass(ctx context.Context, req *connect.Request[v1.AnalyzeClassRequest], stream *connect.ServerStream[v1.AnalyzeClassResponse]) error {
	if len(req.Msg.Instruction) > maxInstructionLen {
		return invalid("instruction is longer than %d characters", maxInstructionLen)
	}
	if err := g.store.ClassExists(ctx, req.Msg.ClassId); err != nil {
		return dbErr(err, "class")
	}
	events, err := g.agent.Analyze(ctx, connect.NewRequest(&v1.AnalyzeRequest{
		ClassId: req.Msg.ClassId, Instruction: req.Msg.Instruction,
	}))
	if err != nil {
		return engineErr(err)
	}
	defer events.Close()
	for events.Receive() {
		ev := events.Msg()
		// The engine never writes to the database; the gateway stores the brief.
		if b := ev.GetBrief(); b != nil {
			if err := g.store.SaveBrief(ctx, b.BriefId, req.Msg.ClassId, b.Markdown); err != nil {
				return dbErr(err, "brief")
			}
		}
		if err := stream.Send(&v1.AnalyzeClassResponse{Event: ev}); err != nil {
			return err
		}
	}
	if err := events.Err(); err != nil {
		return engineErr(err)
	}
	return nil
}

func (g *Gateway) GetEvaluation(ctx context.Context, req *connect.Request[v1.GetEvaluationRequest]) (*connect.Response[v1.GetEvaluationResponse], error) {
	if err := g.store.ClassExists(ctx, req.Msg.ClassId); err != nil {
		return nil, dbErr(err, "class")
	}
	res, err := g.store.Evaluation(ctx, req.Msg.ClassId)
	if err != nil {
		return nil, dbErr(err, "class")
	}
	return connect.NewResponse(res), nil
}
