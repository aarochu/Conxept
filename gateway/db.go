package main

import (
	"context"
	"crypto/rand"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	v1 "misconception/gen/go/misconception/v1"
)

// queries.sql is copied from ../sql/queries.sql by `make gen` (single source of truth, spec section 5).
//
//go:embed queries.sql
var queriesSQL string

var errNotFound = errors.New("not found")

// newUUID returns a random version 4 UUID.
func newUUID() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16]), nil
}

// loadQueries splits queries.sql into named queries on "-- Q_NAME" markers.
func loadQueries(text string) map[string]string {
	out := map[string]string{}
	marker := regexp.MustCompile(`^--\s*(Q_\w+)`)
	var name string
	var buf []string
	flush := func() {
		if name != "" {
			out[name] = strings.TrimRight(strings.TrimSpace(strings.Join(buf, "\n")), ";")
		}
	}
	for _, line := range strings.Split(text, "\n") {
		if m := marker.FindStringSubmatch(line); m != nil {
			flush()
			name, buf = m[1], nil
			continue
		}
		if name != "" {
			buf = append(buf, line)
		}
	}
	flush()
	return out
}

// Store owns every database write (spec section 2: only the gateway writes).
type Store struct {
	pool *pgxpool.Pool
	q    map[string]string
}

func NewStore(pool *pgxpool.Pool) (*Store, error) {
	q := loadQueries(queriesSQL)
	for _, name := range []string{"Q_HEATMAP", "Q_CLUSTERS", "Q_EVAL", "Q_PER_LABEL"} {
		if q[name] == "" {
			return nil, fmt.Errorf("queries.sql is missing %s (run make gen)", name)
		}
	}
	return &Store{pool: pool, q: q}, nil
}

type stepSpecJSON struct {
	Index  int32  `json:"index"`
	Kind   string `json:"kind"`
	Prompt string `json:"prompt"`
}

type stepJSON struct {
	Index int32  `json:"index"`
	Expr  string `json:"expr"`
}

func stepsToJSON(steps []*v1.Step) ([]byte, error) {
	out := make([]stepJSON, len(steps))
	for i, s := range steps {
		out[i] = stepJSON{Index: s.Index, Expr: s.Expr}
	}
	return json.Marshal(out)
}

// SeedClass inserts the class, its problems (skipping existing ones), submissions and ground truth in one transaction.
func (s *Store) SeedClass(ctx context.Context, name string, gen *v1.GenerateClassResponse) (*v1.ClassInfo, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	for _, p := range gen.Problems {
		specs := make([]stepSpecJSON, len(p.Steps))
		for i, st := range p.Steps {
			specs[i] = stepSpecJSON{Index: st.Index, Kind: st.Kind, Prompt: st.Prompt}
		}
		stepsJSON, _ := json.Marshal(specs)
		paramsJSON, _ := json.Marshal(p.Params)
		if _, err := tx.Exec(ctx,
			`INSERT INTO problems (id, family, title, given_latex, given_expr, params, steps)
			 VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (id) DO NOTHING`,
			p.Id, int16(p.Family), p.Title, p.GivenLatex, p.GivenExpr, paramsJSON, stepsJSON); err != nil {
			return nil, fmt.Errorf("insert problem: %w", err)
		}
	}

	var classID string
	if err := tx.QueryRow(ctx, `INSERT INTO classes (name) VALUES ($1) RETURNING id::text`, name).Scan(&classID); err != nil {
		return nil, fmt.Errorf("insert class: %w", err)
	}

	// Engine ids are derived from the seed, so two classes seeded alike would collide.
	// Each stored submission gets a fresh id; ground truth is remapped to it.
	idMap := make(map[string]string, len(gen.Submissions))
	subRows := make([][]any, 0, len(gen.Submissions))
	for _, sub := range gen.Submissions {
		stepsJSON, err := stepsToJSON(sub.Steps)
		if err != nil {
			return nil, err
		}
		id, err := newUUID()
		if err != nil {
			return nil, err
		}
		idMap[sub.Id] = id
		subRows = append(subRows, []any{id, classID, sub.ProblemId, sub.StudentLabel, stepsJSON})
	}
	if _, err := tx.CopyFrom(ctx, pgx.Identifier{"submissions"},
		[]string{"id", "class_id", "problem_id", "student_label", "steps"}, pgx.CopyFromRows(subRows)); err != nil {
		return nil, fmt.Errorf("insert submissions: %w", err)
	}

	gtRows := make([][]any, 0, len(gen.GroundTruth))
	for _, g := range gen.GroundTruth {
		id, ok := idMap[g.SubmissionId]
		if !ok {
			return nil, fmt.Errorf("ground truth for unknown submission %s", g.SubmissionId)
		}
		gtRows = append(gtRows, []any{id, g.TrueStepIndex, g.TrueLabel})
	}
	if _, err := tx.CopyFrom(ctx, pgx.Identifier{"ground_truth"},
		[]string{"submission_id", "true_step_index", "true_label"}, pgx.CopyFromRows(gtRows)); err != nil {
		return nil, fmt.Errorf("insert ground truth: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return &v1.ClassInfo{Id: classID, Name: name, NumSubmissions: int32(len(gen.Submissions))}, nil
}

func (s *Store) ListClasses(ctx context.Context) ([]*v1.ClassInfo, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT c.id::text, c.name, count(sub.id), c.processed_at IS NOT NULL
		FROM classes c LEFT JOIN submissions sub ON sub.class_id = c.id
		GROUP BY c.id ORDER BY c.created_at DESC`)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(r pgx.CollectableRow) (*v1.ClassInfo, error) {
		var c v1.ClassInfo
		var n int64
		err := r.Scan(&c.Id, &c.Name, &n, &c.Processed)
		c.NumSubmissions = int32(n)
		return &c, err
	})
}

var uuidRe = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

func (s *Store) ClassExists(ctx context.Context, classID string) error {
	if !uuidRe.MatchString(classID) {
		return errNotFound
	}
	var ok bool
	if err := s.pool.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM classes WHERE id = $1)`, classID).Scan(&ok); err != nil {
		return err
	}
	if !ok {
		return errNotFound
	}
	return nil
}

func scanSteps(raw []byte) ([]*v1.Step, error) {
	var steps []stepJSON
	if err := json.Unmarshal(raw, &steps); err != nil {
		return nil, err
	}
	out := make([]*v1.Step, len(steps))
	for i, st := range steps {
		out[i] = &v1.Step{Index: st.Index, Expr: st.Expr}
	}
	return out, nil
}

func (s *Store) ClassSubmissions(ctx context.Context, classID string) ([]*v1.Submission, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id::text, problem_id, student_label, steps FROM submissions WHERE class_id = $1 ORDER BY student_label, problem_id`,
		classID)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(r pgx.CollectableRow) (*v1.Submission, error) {
		var sub v1.Submission
		var raw []byte
		if err := r.Scan(&sub.Id, &sub.ProblemId, &sub.StudentLabel, &raw); err != nil {
			return nil, err
		}
		var err error
		sub.Steps, err = scanSteps(raw)
		return &sub, err
	})
}

func (s *Store) ClearDiagnoses(ctx context.Context, classID string) error {
	_, err := s.pool.Exec(ctx,
		`DELETE FROM diagnoses d USING submissions sub WHERE d.submission_id = sub.id AND sub.class_id = $1`, classID)
	return err
}

func nullInt(v int32, set bool) any {
	if !set {
		return nil
	}
	return v
}

func nullText(v string) any {
	if v == "" {
		return nil
	}
	return v
}

func (s *Store) InsertDiagnoses(ctx context.Context, results []*v1.SubmissionResult) error {
	batch := &pgx.Batch{}
	for _, r := range results {
		d := r.Diagnosis
		div := d.GetDivergence()
		diverged := d.Status == v1.DiagnosisStatus_DIAGNOSIS_STATUS_DIVERGED
		ids := div.GetMisconceptionIds()
		if ids == nil {
			ids = []string{}
		}
		batch.Queue(`
			INSERT INTO diagnoses (submission_id, status, divergence_step, misconception_ids, residual_label,
			                       expected_latex, student_latex, parse_error, parse_error_step, elapsed_ms)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
			ON CONFLICT (submission_id) DO UPDATE SET
			  status = EXCLUDED.status, divergence_step = EXCLUDED.divergence_step,
			  misconception_ids = EXCLUDED.misconception_ids, residual_label = EXCLUDED.residual_label,
			  expected_latex = EXCLUDED.expected_latex, student_latex = EXCLUDED.student_latex,
			  parse_error = EXCLUDED.parse_error, parse_error_step = EXCLUDED.parse_error_step,
			  elapsed_ms = EXCLUDED.elapsed_ms, created_at = now()`,
			r.SubmissionId, int16(d.Status), nullInt(div.GetStepIndex(), diverged), ids,
			nullText(div.GetResidualLabel()), nullText(div.GetExpectedLatex()), nullText(div.GetStudentLatex()),
			nullText(d.ParseError), nullInt(d.ParseErrorStep, d.ParseErrorStep != 0), int32(d.ElapsedMs))
	}
	return s.pool.SendBatch(ctx, batch).Close()
}

func (s *Store) MarkProcessed(ctx context.Context, classID string) error {
	_, err := s.pool.Exec(ctx, `UPDATE classes SET processed_at = now() WHERE id = $1`, classID)
	return err
}

func (s *Store) Heatmap(ctx context.Context, classID string) ([]*v1.HeatmapCell, error) {
	rows, err := s.pool.Query(ctx, s.q["Q_HEATMAP"], classID)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(r pgx.CollectableRow) (*v1.HeatmapCell, error) {
		var c v1.HeatmapCell
		var failed, attempted int64
		err := r.Scan(&c.ProblemId, &c.StepIndex, &failed, &attempted)
		c.Failed, c.Attempted = int32(failed), int32(attempted)
		return &c, err
	})
}

type clusterRow struct {
	Key      string
	Count    int64
	Family   int16
	Step     int32
	Examples []string
}

func (s *Store) Clusters(ctx context.Context, classID string) ([]clusterRow, error) {
	rows, err := s.pool.Query(ctx, s.q["Q_CLUSTERS"], classID)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(r pgx.CollectableRow) (clusterRow, error) {
		var c clusterRow
		err := r.Scan(&c.Key, &c.Count, &c.Family, &c.Step, &c.Examples)
		return c, err
	})
}

func (s *Store) Evaluation(ctx context.Context, classID string) (*v1.GetEvaluationResponse, error) {
	var total, correct, falseAlarms, stepExp, stepOK, labelExp, labelOK, heldExp, heldOK int64
	err := s.pool.QueryRow(ctx, s.q["Q_EVAL"], classID).Scan(
		&total, &correct, &falseAlarms, &stepExp, &stepOK, &labelExp, &labelOK, &heldExp, &heldOK)
	if err != nil {
		return nil, err
	}
	out := &v1.GetEvaluationResponse{
		Total: int32(total), CorrectSubmissions: int32(correct), FalseAlarms: int32(falseAlarms),
		DivergenceStepCorrect: int32(stepOK), DivergenceStepExpected: int32(stepExp),
		LabelCorrect: int32(labelOK), LabelExpected: int32(labelExp),
		HeldoutDetected: int32(heldOK), HeldoutExpected: int32(heldExp),
	}
	rows, err := s.pool.Query(ctx, s.q["Q_PER_LABEL"], classID)
	if err != nil {
		return nil, err
	}
	out.PerLabel, err = pgx.CollectRows(rows, func(r pgx.CollectableRow) (*v1.LabelScore, error) {
		var l v1.LabelScore
		var tp, fp, fn int64
		err := r.Scan(&l.Label, &tp, &fp, &fn)
		l.TruePositive, l.FalsePositive, l.FalseNegative = int32(tp), int32(fp), int32(fn)
		return &l, err
	})
	return out, err
}

func (s *Store) Submission(ctx context.Context, id string) (*v1.Submission, *v1.Diagnosis, error) {
	if !uuidRe.MatchString(id) {
		return nil, nil, errNotFound
	}
	var sub v1.Submission
	var raw []byte
	var status *int16
	var divStep, peStep, elapsed *int32
	var ids []string
	var residual, expected, student, parseErr *string
	err := s.pool.QueryRow(ctx, `
		SELECT sub.id::text, sub.problem_id, sub.student_label, sub.steps,
		       d.status, d.divergence_step, d.misconception_ids, d.residual_label,
		       d.expected_latex, d.student_latex, d.parse_error, d.parse_error_step, d.elapsed_ms
		FROM submissions sub LEFT JOIN diagnoses d ON d.submission_id = sub.id
		WHERE sub.id = $1`, id).Scan(
		&sub.Id, &sub.ProblemId, &sub.StudentLabel, &raw,
		&status, &divStep, &ids, &residual, &expected, &student, &parseErr, &peStep, &elapsed)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil, errNotFound
	}
	if err != nil {
		return nil, nil, err
	}
	if sub.Steps, err = scanSteps(raw); err != nil {
		return nil, nil, err
	}
	if status == nil {
		return &sub, nil, nil
	}
	deref := func(p *string) string {
		if p == nil {
			return ""
		}
		return *p
	}
	d := &v1.Diagnosis{Status: v1.DiagnosisStatus(*status), ParseError: deref(parseErr)}
	if peStep != nil {
		d.ParseErrorStep = *peStep
	}
	if elapsed != nil {
		d.ElapsedMs = int64(*elapsed)
	}
	if d.Status == v1.DiagnosisStatus_DIAGNOSIS_STATUS_DIVERGED && divStep != nil {
		d.Divergence = &v1.Divergence{
			StepIndex: *divStep, MisconceptionIds: ids, ResidualLabel: deref(residual),
			ExpectedLatex: deref(expected), StudentLatex: deref(student),
		}
	}
	return &sub, d, nil
}

func (s *Store) SaveBrief(ctx context.Context, briefID, classID, markdown string) error {
	_, err := s.pool.Exec(ctx,
		`INSERT INTO briefs (id, class_id, markdown) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING`,
		briefID, classID, markdown)
	return err
}
