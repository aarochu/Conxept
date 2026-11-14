# Conxept — HackPrinceton Build Spec

Nov 13, 2026 · @Aaron

## 1. Overview and locked decisions

We build **Conxept**: an instructor tool that finds the exact step where each student's derivation first goes wrong, groups those errors into named misconceptions across the class, and generates verified practice problems for each one.

**Why a chat window cannot replace it.** A chat model can mark one derivation. It cannot deterministically prove which step broke, aggregate hundreds of submissions into a class heatmap, or guarantee that a generated answer key is correct. Those three things are the product.

**Scope (fixed).** Four problem families in one course domain (Linear Systems and Signals): inverse Laplace by partial fractions, causal convolution, Fourier transform with a fixed convention, and Laplace transform properties. Each family has a hand-written misconception catalog. No handwriting input, no accounts, no grading, no LMS integration.

**Non-goals.** Teaching a single student, free-form natural-language proofs, calculus outside the four families, mobile layout.

**Locked decisions.** Nothing below is open during the build.

| Layer | Choice | Reason |
| --- | --- | --- |
| Browser app | Angular + TypeScript | Stack constraint |
| Public API | Go service using connect-go, Connect protocol over HTTP | Browsers cannot speak gRPC; connect-go serves gRPC, gRPC-Web and Connect from one handler |
| Internal calls | gRPC + Protobuf, Go to Python | Stack constraint; no JSON/REST between services |
| Math engine and agent | Python, one process, SymPy for checking, Deep Agents for orchestration | SymPy is deterministic and free; Deep Agents is a prize track |
| Verifier of record | SymPy; Wolfram only as an optional second opinion and answer-key cross-check | Wolfram access depends on a license entitlement we have not confirmed |
| Database | PostgreSQL 16 in Docker for dev; Tiger Cloud Free service for the deployed demo | Free; Tiger Data is a hackathon sponsor |
| Schema and codegen | buf, one `proto/` directory | Single source of truth for all three languages |
| Not used | C++, Java, Kotlin | No component needs them; adding them costs setup time |

## 2. Architecture

The browser talks Connect to a Go gateway; the gateway talks gRPC to one Python engine; PostgreSQL holds the data. This follows the stack constraint: gRPC and Protobuf between services, TypeScript with Angular in the browser, Go and Python on the backend.

| Component | Language | Port | Talks to | Protocol |
| --- | --- | --- | --- | --- |
| Web app | Angular, TypeScript | 4200 in development; served by the gateway in production | Gateway | Connect over HTTP, same origin (a dev proxy forwards `/misconception.v1.GatewayService/` to port 8080) |
| Gateway | Go, connect-go, pgx | 8080 | Engine; PostgreSQL | gRPC (cleartext HTTP/2) to the engine; SQL to PostgreSQL |
| Engine | Python, `grpc.aio`, SymPy, Deep Agents | 50051 | PostgreSQL (read-only role); Claude API; Wolfram (optional) | SQL; HTTPS |
| Database | PostgreSQL 16 | 5432 | none | none |

**Data flow for the main path.**

1. The instructor clicks Seed in the browser. The web app calls `SeedSyntheticClass`; the gateway calls the engine's `GenerateClass` and stores the problems, submissions and ground truth.
2. The instructor clicks Process. The web app calls `ProcessClass` (a stream); the gateway calls the engine's `DiagnoseBatch` (a stream), stores each diagnosis as it arrives and forwards progress.
3. The dashboard calls `GetHeatmap` and `GetClusters`; the gateway answers from SQL (section 5) and adds names from the catalog.
4. A cluster page calls `GenerateRemediation`; the gateway forwards it to the engine, which returns verified practice problems.
5. Analyze calls `AnalyzeClass` (a stream); the gateway calls the engine's `Analyze`; the Deep Agent calls its four tools and the Claude API, and streams events back.

**Rules of the architecture (locked).**

- Only the Go gateway is reachable from the browser. The engine is internal.
- Only the gateway writes to the database.
- No JSON or REST is used between services; the browser uses the Connect protocol with Protobuf messages.
- The language model never decides correctness; the engine's mathematics does (section 3).
- Everything in the diagnosis path works with no network and no API key. The model and Wolfram are only used for the brief and the optional cross-check.

**Why one Python process holds both services.** The agent's tools call the same functions as the diagnosis RPCs, so one process avoids a second network hop and a second copy of the problem bank.

## 3. Diagnosis algorithm

The engine decides correctness with mathematics, not a language model: a step is valid when it equals the correct operation applied to the student's own previous step, and the first step that fails is the divergence.

```latex
\text{step } i \text{ is valid} \iff e_i \equiv \mathrm{op}_i(e_{i-1}), \qquad \text{divergence} = \min\{\, i : \text{step } i \text{ is not valid} \,\}
```

Here e\_0 is the given and e\_i is the student's expression at step i. Checking against the student's own previous step (follow-through) means one early mistake is not charged again at every later step. Only the first divergence per submission is reported.

**Step kinds.** The expected value of a step depends on its kind.

| Kind | Used by | Expected value op\_i(e\_{i-1}) |
| --- | --- | --- |
| equal | f1 step 1; f2 steps 2 and 3; f3 step 2; f4 step 2 | e\_{i-1} itself: a rewrite must not change the value |
| invL | f1 step 2 | Termwise inverse Laplace of the student's partial fractions: c/(s+r) becomes c·exp(-r·t)·u(t) |
| conv\_setup | f2 step 1 | u(t)·integral from 0 to t of x(tau)·h(t-tau) d tau, built from the given pair |
| ft\_integral | f3 step 1 | Integral from 0 to infinity of x(t)·exp(-j·w·t) dt |
| L\_shift | f4 step 1 | exp(-s·T)/(s+a) |

**Equivalence test.** Two expressions are equal when they agree at 6 sample points within a relative tolerance. The rule is fixed:

- Sample t and tau uniformly from ±\[0.3, 3.0\] with a random sign, so a missing u(t) is caught on negative t.
- Sample w uniformly from \[-3, 3\]. Sample s as a complex number with real part in \[0.5, 3\] and imaginary part in \[-3, 3\].
- Two values a and b agree when |a - b| ≤ 1e-6 · (1 + |a| + |b|) at every point.
- Seed the sampler with 12345 inside every call, so a verdict never changes between runs.
- Evaluate every definite integral with mpmath.quad on a lambdified integrand, never with SymPy's numeric integration. This one change cut the 400-diagnosis evaluation from 237 s to 15.7 s with identical results (section 12).

**Classification order** after a divergence at step i:

1. **Catalog.** Try every catalog entry for this family and step, in declared order. Each entry builds the wrong answer it would produce; a match means that wrong answer equals the student's step. Return all matches in catalog order, so ambiguity is shown and never hidden.
2. **Residual.** If nothing matched, test whether the student's step equals the expected value times one of -1, 2, 1/2, 2π, 1/(2π), √(2π), 1/√(2π). Then test whether it equals the expected value with s, w or t negated. Labels are `residual:sign_flip`, `residual:factor_2`, `residual:factor_1_over_2`, `residual:factor_2pi`, `residual:factor_1_over_2pi`, `residual:factor_sqrt_2pi`, `residual:factor_1_over_sqrt_2pi`, and `residual:argument_negated(s)`, `(w)`, `(t)`.
3. **Unclassified.** Otherwise the label is `unclassified`. These are grouped by family and step only (key `unclassified:<family>:<step>`), shown as "Other" with examples, and never named by the engine.

```python
def diagnose(family, ctx, steps):            # steps[0] is the given
    for i in range(1, len(steps)):
        expected = family.true_next(i, steps[i-1], ctx)
        if equiv(steps[i], expected):
            continue
        ids = [m.id for m in family.catalog[i]
               if equiv(steps[i], m.wrong_answer(steps[i-1], expected, ctx))]
        return Divergence(i, ids or [residual_label(steps[i], expected)])
    return None                                # every step valid
```

**Fourier convention (locked).** All Fourier answers use X(jw) = integral of x(t)·exp(-j·w·t) dt, angular frequency, no prefactor. Common tools disagree with it by default, which is why the catalog has an entry for copying a tool's default.

- SymPy's `fourier_transform` uses exp(-2·π·i·k·x), ordinary frequency. Run here: the transform of exp(-2t)·u(t) came back as 1/(2+2πik).
- SymPy's `fourier_transform(cos(t))` returned 0, because it has no distributions. Run here. Never call it for sinusoids.
- Wolfram's `FourierTransform` defaults to FourierParameters {0,1}, documented as the modern-physics setting. Its documentation lists {1,-1} for systems engineering and {0,-2Pi} for signal processing, so the course convention is `FourierParameters -> {1, -1}`.
- Confirm tonight that the course uses this convention. If it does not, change the f3 answer key and the four f3 catalog entries in one file and rerun the tests.

**Step DSL.** The only accepted input. Each step is the right-hand side of the quantity being solved for, not an equation.

| Write | Meaning |
| --- | --- |
| t, tau, w, s | time, convolution variable, angular frequency, Laplace variable |
| u(x) or step(x) | unit step, Heaviside |
| j | imaginary unit |
| exp, sin, cos, sqrt, pi, e, inf | the usual functions and constants |
| int(f, var, lo, hi) | definite integral, for example `int(exp(-2*tau)*exp(-5*(t-tau)), tau, 0, t)` |
| + - \* / ^ ( ) , | operators; `^` is power, implicit multiplication such as `2 t` is accepted |

Rejected with a parse error that names the step: anything over 400 characters, any character outside letters, digits, `+ - * / ^ ( ) , .` and spaces, any name not in the table, a dot that is not inside a number, numbers longer than 6 digits, a power inside an exponent, or an exponent above 64. Parsing builds the expression without evaluating it, checks these rules on the tree, and only then evaluates. Run here: 12 of 12 valid steps parsed and 17 of 17 hostile inputs, including `__import__('os')`, `9^9^9^9` and `t**10000000`, were rejected cleanly in under 1 ms each.

**Known limits (accepted).**

- Equality is by sampling, so two different functions that agree to 1e-6 at all 6 points would pass. This is an accepted risk for integer-parameter problems.
- All problem parameters are small integers. There are no Dirac deltas in student answers, because SymPy cannot evaluate them numerically here.
- Only the first divergence is reported. A second, independent error later in the same derivation is not.
- Free-text or handwritten derivations are out of scope.

## 4. Protobuf contracts

Three files under `proto/misconception/v1/`, package `misconception.v1`, are the single source of truth for Go, Python and TypeScript; they pass `buf lint` with the STANDARD rule set and generate Python and TypeScript stubs.

| Service | Implemented in | Called by | Transport | Port |
| --- | --- | --- | --- | --- |
| GatewayService | Go | Angular app | Connect protocol over HTTP, served from the same origin as the page | 8080 |
| EngineService | Python | Go gateway | gRPC | 50051 |
| InstructorAgentService | Python, same process as EngineService | Go gateway | gRPC | 50051 |

**Limits and defaults (enforced in the gateway, in this order).**

| Field | Rule |
| --- | --- |
| SeedSyntheticClassRequest | num\_students 1 to 200, default 60; seed default 7; error\_rate default 0.6; heldout\_share default 0.25 |
| GenerateRemediationRequest | count 1 to 5, default 3 |
| Submission and DiagnoseRequest | at most 6 steps; each expr at most 400 characters |
| AnalyzeClassRequest | instruction at most 500 characters |
| Error codes | bad input is INVALID\_ARGUMENT; unknown id is NOT\_FOUND; engine unreachable is UNAVAILABLE; agent without an API key is FAILED\_PRECONDITION |

**common.proto**

```proto
syntax = "proto3";

package misconception.v1;

option go_package = "misconception/gen/go/misconception/v1;misconceptionv1";

// The four problem families supported in v1.
enum Family {
  FAMILY_UNSPECIFIED = 0;
  FAMILY_INVERSE_LAPLACE_PF = 1;
  FAMILY_CAUSAL_CONVOLUTION = 2;
  FAMILY_FOURIER_TRANSFORM = 3;
  FAMILY_LAPLACE_TIME_SHIFT = 4;
}

// What the student must produce at one step.
message StepSpec {
  int32 index = 1;     // 1-based; step 0 is the given and is never submitted
  string kind = 2;     // equal | invL | conv_setup | ft_integral | L_shift
  string prompt = 3;   // shown to the student, e.g. "Write F(s) as partial fractions"
}

message Problem {
  string id = 1;                    // stable, e.g. "f1-p1-q2-n0"
  Family family = 2;
  string title = 3;
  string given_latex = 4;
  string given_expr = 5;            // Step DSL form of the given (may be empty for f2, f3)
  repeated StepSpec steps = 6;
  map<string, int32> params = 7;    // integer parameters used to build the instance
}

// One line of a student's derivation, in the Step DSL (see spec section 3).
message Step {
  int32 index = 1;
  string expr = 2;
}

message Submission {
  string id = 1;
  string problem_id = 2;
  string student_label = 3;         // synthetic or anonymized, never a real name
  repeated Step steps = 4;
}

message Misconception {
  string id = 1;                    // snake_case, unique, e.g. "cover_up_forgot_other_factor"
  string name = 2;                  // human readable
  string description = 3;
  Family family = 4;
  int32 step_index = 5;
  string fix_hint = 6;
}

enum DiagnosisStatus {
  DIAGNOSIS_STATUS_UNSPECIFIED = 0;
  DIAGNOSIS_STATUS_VALID = 1;
  DIAGNOSIS_STATUS_DIVERGED = 2;
  DIAGNOSIS_STATUS_PARSE_ERROR = 3;
}

message Divergence {
  int32 step_index = 1;
  repeated string misconception_ids = 2;  // catalog matches; empty when only a residual label applies
  string residual_label = 3;              // "residual:factor_2pi", "residual:sign_flip", or "unclassified"
  string expected_latex = 4;              // correct move from the student's own previous step
  string student_latex = 5;
}

message Diagnosis {
  DiagnosisStatus status = 1;
  Divergence divergence = 2;              // set when status is DIVERGED
  string parse_error = 3;                 // set when status is PARSE_ERROR
  int32 parse_error_step = 4;
  int64 elapsed_ms = 5;
}
```

**engine.proto**

```proto
syntax = "proto3";

package misconception.v1;

import "misconception/v1/common.proto";

option go_package = "misconception/gen/go/misconception/v1;misconceptionv1";

// Internal service, Python. Called only by the Go gateway over gRPC.
service EngineService {
  rpc ListProblems(ListProblemsRequest) returns (ListProblemsResponse);
  rpc ListMisconceptions(ListMisconceptionsRequest) returns (ListMisconceptionsResponse);
  rpc Diagnose(DiagnoseRequest) returns (DiagnoseResponse);
  rpc DiagnoseBatch(DiagnoseBatchRequest) returns (stream DiagnoseBatchResponse);
  rpc GenerateRemediation(GenerateRemediationRequest) returns (GenerateRemediationResponse);
  rpc GenerateClass(GenerateClassRequest) returns (GenerateClassResponse);
}

// Internal service, Python (same process). The Deep Agent behind "Analyze class".
service InstructorAgentService {
  rpc Analyze(AnalyzeRequest) returns (stream AnalyzeResponse);
}

message ListProblemsRequest {}
message ListProblemsResponse {
  repeated Problem problems = 1;
}

message ListMisconceptionsRequest {}
message ListMisconceptionsResponse {
  repeated Misconception misconceptions = 1;
}

message DiagnoseRequest {
  string problem_id = 1;
  repeated Step steps = 2;
}
message DiagnoseResponse {
  Diagnosis diagnosis = 1;
}

message DiagnoseBatchRequest {
  repeated Submission submissions = 1;
}
message SubmissionResult {
  string submission_id = 1;
  Diagnosis diagnosis = 2;
}
message DiagnoseBatchResponse {
  int32 done = 1;
  int32 total = 2;
  repeated SubmissionResult results = 3;   // only the results finished since the previous message
}

message GenerateRemediationRequest {
  string misconception_id = 1;
  int32 count = 2;      // 1..5
  int64 seed = 3;
}
message RemediationProblem {
  Problem problem = 1;
  string answer_key_latex = 2;
  repeated string verification_routes = 3;   // e.g. "formula", "sympy_transform", "numeric_quad"
  bool verified = 4;                         // true only when at least two routes agree
  string why_it_discriminates = 5;           // the wrong answer this misconception would give, in LaTeX
}
message GenerateRemediationResponse {
  repeated RemediationProblem problems = 1;
}

// Synthetic class generation. Ground truth is returned so evaluation can be computed.
message GroundTruth {
  string submission_id = 1;
  int32 true_step_index = 2;       // 0 means the submission is correct
  string true_label = 3;           // misconception id, "heldout:<kind>", or "" when correct
}
message GenerateClassRequest {
  int32 num_students = 1;          // 1..200
  int64 seed = 2;
  repeated string problem_ids = 3; // empty means the default problem set
  float error_rate = 4;            // 0..1 probability a submission contains an error
  float heldout_share = 5;         // 0..1 share of errors that are NOT in the catalog
}
message GenerateClassResponse {
  repeated Problem problems = 1;
  repeated Submission submissions = 2;
  repeated GroundTruth ground_truth = 3;
}

message AnalyzeRequest {
  string class_id = 1;
  string instruction = 2;           // optional extra instruction from the instructor
}
message ToolCallEvent {
  string name = 1;
  string arguments_text = 2;        // display only
}
message ToolResultEvent {
  string name = 1;
  string summary = 2;
}
message BriefEvent {
  string brief_id = 1;
  string markdown = 2;
}
message AnalyzeResponse {
  oneof event {
    string text_delta = 1;
    ToolCallEvent tool_call = 2;
    ToolResultEvent tool_result = 3;
    BriefEvent brief = 4;
    string error = 5;
  }
}
```

**gateway.proto**

```proto
syntax = "proto3";

package misconception.v1;

import "misconception/v1/common.proto";
import "misconception/v1/engine.proto";

option go_package = "misconception/gen/go/misconception/v1;misconceptionv1";

// Public service, Go + connect-go, called by the Angular app with the Connect protocol.
service GatewayService {
  rpc ListProblems(GatewayServiceListProblemsRequest) returns (GatewayServiceListProblemsResponse);
  rpc ListMisconceptions(GatewayServiceListMisconceptionsRequest) returns (GatewayServiceListMisconceptionsResponse);
  rpc SeedSyntheticClass(SeedSyntheticClassRequest) returns (SeedSyntheticClassResponse);
  rpc ListClasses(ListClassesRequest) returns (ListClassesResponse);
  rpc ProcessClass(ProcessClassRequest) returns (stream ProcessClassResponse);
  rpc GetHeatmap(GetHeatmapRequest) returns (GetHeatmapResponse);
  rpc GetClusters(GetClustersRequest) returns (GetClustersResponse);
  rpc GetSubmission(GetSubmissionRequest) returns (GetSubmissionResponse);
  rpc TryDerivation(TryDerivationRequest) returns (TryDerivationResponse);
  rpc GenerateRemediation(GatewayServiceGenerateRemediationRequest) returns (GatewayServiceGenerateRemediationResponse);
  rpc AnalyzeClass(AnalyzeClassRequest) returns (stream AnalyzeClassResponse);
  rpc GetEvaluation(GetEvaluationRequest) returns (GetEvaluationResponse);
}

message GatewayServiceListProblemsRequest {}
message GatewayServiceListProblemsResponse {
  repeated Problem problems = 1;
}

message GatewayServiceListMisconceptionsRequest {}
message GatewayServiceListMisconceptionsResponse {
  repeated Misconception misconceptions = 1;
}

message ClassInfo {
  string id = 1;
  string name = 2;
  int32 num_submissions = 3;
  bool processed = 4;
}

message SeedSyntheticClassRequest {
  string name = 1;
  int32 num_students = 2;    // 1..200, default 60
  int64 seed = 3;            // default 7
  float error_rate = 4;      // default 0.6
  float heldout_share = 5;   // default 0.25
}
message SeedSyntheticClassResponse {
  ClassInfo class_info = 1;
}

message ListClassesRequest {}
message ListClassesResponse {
  repeated ClassInfo classes = 1;
}

message ProcessClassRequest {
  string class_id = 1;
}
message ProcessClassResponse {
  int32 done = 1;
  int32 total = 2;
}

message GetHeatmapRequest {
  string class_id = 1;
}
// One cell = one (problem, step). failed counts submissions whose FIRST divergence is at this step.
message HeatmapCell {
  string problem_id = 1;
  int32 step_index = 2;
  int32 failed = 3;
  int32 attempted = 4;   // submissions that reached this step (all earlier steps valid)
}
message GetHeatmapResponse {
  repeated HeatmapCell cells = 1;
}

message GetClustersRequest {
  string class_id = 1;
}
message Cluster {
  string key = 1;                       // misconception id, "residual:<name>", or "unclassified:<family>:<step>"
  string name = 2;
  int32 count = 3;
  Family family = 4;
  int32 step_index = 5;
  bool in_catalog = 6;
  repeated string example_submission_ids = 7;   // at most 5
}
message GetClustersResponse {
  repeated Cluster clusters = 1;            // sorted by count, descending
}

message GetSubmissionRequest {
  string submission_id = 1;
}
message GetSubmissionResponse {
  Submission submission = 1;
  Diagnosis diagnosis = 2;
}

message TryDerivationRequest {
  string problem_id = 1;
  repeated Step steps = 2;
}
message TryDerivationResponse {
  Diagnosis diagnosis = 1;
}

message GatewayServiceGenerateRemediationRequest {
  string misconception_id = 1;
  int32 count = 2;
  int64 seed = 3;
}
message GatewayServiceGenerateRemediationResponse {
  repeated RemediationProblem problems = 1;
}

message AnalyzeClassRequest {
  string class_id = 1;
  string instruction = 2;
}
message AnalyzeClassResponse {
  AnalyzeResponse event = 1;
}

message GetEvaluationRequest {
  string class_id = 1;
}
message LabelScore {
  string label = 1;
  int32 true_positive = 2;
  int32 false_positive = 3;
  int32 false_negative = 4;
}
message GetEvaluationResponse {
  int32 total = 1;
  int32 correct_submissions = 2;
  int32 false_alarms = 3;                 // correct submissions flagged as wrong
  int32 divergence_step_correct = 4;      // flagged at the true step
  int32 divergence_step_expected = 5;     // submissions that truly contain an error
  int32 label_correct = 6;                // catalog errors whose id is in the returned labels
  int32 label_expected = 7;
  int32 heldout_detected = 8;
  int32 heldout_expected = 9;
  repeated LabelScore per_label = 10;
}
```

## 5. Data model

One PostgreSQL 16 database, six tables, no extensions beyond built-ins (`gen_random_uuid()` is built in from version 13). The Go gateway owns all writes. The Python engine connects with a read-only role and uses the database only to read submissions for the agent's tools. Both files below ran on PostgreSQL 16 in this build: the schema created cleanly and the four queries returned the results in the table after them.

**sql/schema.sql**

```sql
CREATE TABLE classes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz
);
CREATE TABLE problems (
  id text PRIMARY KEY,
  family smallint NOT NULL,
  title text NOT NULL,
  given_latex text NOT NULL,
  given_expr text NOT NULL DEFAULT '',
  params jsonb NOT NULL,
  steps jsonb NOT NULL
);
CREATE TABLE submissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  class_id uuid NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  problem_id text NOT NULL REFERENCES problems(id),
  student_label text NOT NULL,
  steps jsonb NOT NULL,
  UNIQUE (class_id, problem_id, student_label)
);
CREATE INDEX submissions_class_idx ON submissions (class_id);
CREATE TABLE diagnoses (
  submission_id uuid PRIMARY KEY REFERENCES submissions(id) ON DELETE CASCADE,
  status smallint NOT NULL,
  divergence_step int,
  misconception_ids text[] NOT NULL DEFAULT '{}',
  residual_label text,
  expected_latex text,
  student_latex text,
  parse_error text,
  parse_error_step int,
  elapsed_ms int NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ground_truth (
  submission_id uuid PRIMARY KEY REFERENCES submissions(id) ON DELETE CASCADE,
  true_step_index int NOT NULL,
  true_label text NOT NULL DEFAULT ''
);
CREATE TABLE briefs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  class_id uuid NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  markdown text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

`diagnoses.status` stores the `DiagnosisStatus` enum number: 1 valid, 2 diverged, 3 parse error. `problems.family` stores the `Family` enum number. `ground_truth` is filled only for synthetic classes.

**sql/queries.sql.** Each query takes the class id as parameter 1. In Go with pgx write `$1`. In Python with psycopg, `%` characters in SQL must be doubled (`'heldout:%%'`) because psycopg treats a single `%` as a placeholder; the harness here hit exactly that error and the fix was escaping.

```sql
-- Q_HEATMAP ($1 = class_id)
SELECT p.id AS problem_id,
       (st.step->>'index')::int AS step_index,
       count(*) FILTER (WHERE d.divergence_step = (st.step->>'index')::int) AS failed,
       count(*) FILTER (WHERE d.status = 1 OR d.divergence_step >= (st.step->>'index')::int) AS attempted
FROM problems p
CROSS JOIN LATERAL jsonb_array_elements(p.steps) AS st(step)
JOIN submissions sub ON sub.problem_id = p.id AND sub.class_id = $1
JOIN diagnoses d ON d.submission_id = sub.id AND d.status IN (1, 2)
GROUP BY p.id, (st.step->>'index')::int
ORDER BY p.id, step_index;

-- Q_CLUSTERS ($1 = class_id)
SELECT CASE WHEN cardinality(d.misconception_ids) > 0 THEN d.misconception_ids[1]
            WHEN d.residual_label = 'unclassified' THEN 'unclassified:' || p.family || ':' || d.divergence_step
            ELSE d.residual_label END AS key,
       count(*) AS n, p.family, d.divergence_step,
       (array_agg(sub.id ORDER BY sub.id))[1:5] AS examples
FROM diagnoses d
JOIN submissions sub ON sub.id = d.submission_id
JOIN problems p ON p.id = sub.problem_id
WHERE sub.class_id = $1 AND d.status = 2
GROUP BY 1, p.family, d.divergence_step
ORDER BY n DESC, key;

-- Q_EVAL ($1 = class_id)
SELECT count(*) AS total,
  count(*) FILTER (WHERE g.true_step_index = 0) AS correct_submissions,
  count(*) FILTER (WHERE g.true_step_index = 0 AND d.status = 2) AS false_alarms,
  count(*) FILTER (WHERE g.true_step_index > 0) AS divergence_step_expected,
  count(*) FILTER (WHERE g.true_step_index > 0 AND d.divergence_step = g.true_step_index) AS divergence_step_correct,
  count(*) FILTER (WHERE g.true_label <> '' AND g.true_label NOT LIKE 'heldout:%') AS label_expected,
  count(*) FILTER (WHERE g.true_label <> '' AND g.true_label NOT LIKE 'heldout:%'
                   AND d.divergence_step = g.true_step_index AND g.true_label = ANY(d.misconception_ids)) AS label_correct,
  count(*) FILTER (WHERE g.true_label LIKE 'heldout:%') AS heldout_expected,
  count(*) FILTER (WHERE g.true_label LIKE 'heldout:%' AND d.divergence_step = g.true_step_index) AS heldout_detected
FROM submissions sub
JOIN ground_truth g ON g.submission_id = sub.id
JOIN diagnoses d ON d.submission_id = sub.id
WHERE sub.class_id = $1;

-- Q_PER_LABEL ($1 = class_id)
WITH j AS (
  SELECT g.true_label, g.true_step_index, d.divergence_step, d.misconception_ids
  FROM submissions sub JOIN ground_truth g ON g.submission_id = sub.id JOIN diagnoses d ON d.submission_id = sub.id
  WHERE sub.class_id = $1)
SELECT l.label,
  count(*) FILTER (WHERE j.true_label = l.label AND j.divergence_step = j.true_step_index AND l.label = ANY(j.misconception_ids)) AS true_positive,
  count(*) FILTER (WHERE j.true_label <> l.label AND l.label = ANY(j.misconception_ids)) AS false_positive,
  count(*) FILTER (WHERE j.true_label = l.label AND NOT (j.divergence_step = j.true_step_index AND l.label = ANY(j.misconception_ids))) AS false_negative
FROM (SELECT DISTINCT true_label AS label FROM j WHERE true_label <> '' AND true_label NOT LIKE 'heldout:%') l, j
GROUP BY l.label ORDER BY l.label;
```

**Query-to-RPC mapping.** Q\_HEATMAP backs GetHeatmap, Q\_CLUSTERS backs GetClusters, Q\_EVAL backs the totals in GetEvaluation, and Q\_PER\_LABEL fills `per_label`. The cluster `name` comes from the catalog (or the residual label text), joined in Go, not in SQL.

**Verified on PostgreSQL 16 with an 8-row fixture** (3 submissions wrong at step 1 of one problem, 3 wrong at step 2, 2 correct):

| Query | Result on the fixture |
| --- | --- |
| Q\_HEATMAP | step 1: 3 failed of 8 attempted; step 2: 3 failed of 5 attempted |
| Q\_EVAL | total 8, correct submissions 2, false alarms 0, divergence step 6 of 6, label 3 of 4, held-out 2 of 2 |

The fixture is small by design: it checks that the SQL counts what the definitions say, not the engine's accuracy (that is section 8). Running Q\_HEATMAP needs `problems.steps` populated with the `StepSpec` list as JSON objects containing an `index` key.

## 6. Service specs

Three deployable pieces: the Python engine, the Go gateway, the Angular app. Build them in that order; each is testable alone against the contracts in section 4.

### 6.1 Python engine (port 50051)

One process, `grpc.aio` server, registers `EngineService` and `InstructorAgentService`. The reference implementation is `reference/engine_spike.py` and `reference/parse_step.py`; port them, do not rewrite the mathematics.

| RPC | Behavior |
| --- | --- |
| ListProblems, ListMisconceptions | Return the problem bank and catalog from section 7, built in memory at start-up |
| Diagnose | Parse every step with the Step DSL parser; a parse failure returns status PARSE\_ERROR with the step index and message. Otherwise run `diagnose` and map the result to a `Diagnosis`: ids that do not start with `residual` and are not `unclassified` go to `misconception_ids`; otherwise the first label goes to `residual_label` |
| DiagnoseBatch | Server stream, one message per submission, `done` counting up to `total`, each message carrying only the results finished since the previous one |
| GenerateRemediation | Section 7 generator; returns `verified=true` only when two verification routes agree |
| GenerateClass | Section 8 synthetic generator; returns problems, submissions and ground truth |
| Analyze (agent) | Section 6.3 |

Verified here: a `grpc.aio` server built from the generated stubs answered Diagnose for a correct derivation (VALID), a derivation missing u(t) (DIVERGED at step 2), and a hostile input `__import__('os')` (PARSE\_ERROR), and streamed a 6-submission DiagnoseBatch as 6 messages (`reference/tests/grpc_roundtrip.py`).

**Wolfram probe (optional, never required).** At start-up, if the environment variable `WOLFRAM_APP_ID` is set, the engine may call the Wolfram|Alpha Full Results or LLM API once with a known transform to confirm the key works, and then use Wolfram only to cross-check answer keys in GenerateRemediation as a third route. If the variable is unset or the probe fails, the engine logs one line and continues; no code path may depend on Wolfram. Not verified here: we have no confirmed Wolfram entitlement, so this path is built last and is cut first.

**Concurrency.** SymPy and mpmath are CPU-bound. Run each diagnosis in a `ProcessPoolExecutor` with 4 workers via `loop.run_in_executor`, so one slow step never blocks the event loop. Per-diagnosis timeout is 5 seconds; on timeout return PARSE\_ERROR with message `timed out`.

### 6.2 Go gateway (port 8080)

The only service the browser talks to. Responsibilities, in order of build:

1. Serve the `GatewayService` handler from connect-go at `/misconception.v1.GatewayService/`, and the built Angular files from `./web` on every other path, with a fallback to `index.html` for client routes.
2. Own all database writes with pgx (`pgxpool`), using the queries in section 5 with `$1` parameters.
3. Call the engine with a generated `EngineServiceClient` created with `connect.WithGRPC()` against `http://engine:50051` over cleartext HTTP/2 (h2c). If that combination fails at first integration, the fallback is the generated `grpc-go` client against the same address; the call sites do not change because both implement the same method names.
4. Enforce the limits table in section 4 before any engine call.

```go
// main.go (outline; names are fixed, bodies are straightforward)
mux := http.NewServeMux()
path, handler := misconceptionv1connect.NewGatewayServiceHandler(gw)
mux.Handle(path, handler)
mux.Handle("/", spaFileServer("./web"))

engine := misconceptionv1connect.NewEngineServiceClient(
    &http.Client{Transport: &http2.Transport{
        AllowHTTP: true,
        DialTLSContext: func(ctx context.Context, network, addr string, _ *tls.Config) (net.Conn, error) {
            return (&net.Dialer{}).DialContext(ctx, network, addr)
        },
    }},
    "http://engine:50051",
    connect.WithGRPC(),
)

srv := &http.Server{Addr: ":8080", Handler: h2c.NewHandler(mux, &http2.Server{})}
log.Fatal(srv.ListenAndServe())
```

**Status: not run.** The Go module proxy was unreachable from the build sandbox, so no Go code, connect-go, or h2c wiring in this document has been compiled. The proto contracts, Python server and SQL are verified; the Go gateway is the first integration gate. Do this first when you start the gateway: generate the Go stubs, compile an empty handler, and make one Diagnose call to the Python engine. If that fails, use the grpc-go fallback above before writing anything else.

**ProcessClass.** Reads the class's submissions, calls `DiagnoseBatch`, inserts each result into `diagnoses` as it streams, forwards `done` and `total` to the browser, and sets `classes.processed_at` at the end. Rerunning it replaces existing diagnoses for that class.

**SeedSyntheticClass.** Calls the engine's `GenerateClass`, inserts the problems (skip ones that exist), submissions and ground truth in one transaction, and returns the `ClassInfo`.

### 6.3 Deep Agent (inside the engine process)

The agent writes the instructor brief; it never decides correctness. All numbers come from tools that read the database or call the engine.

| Tool | Returns |
| --- | --- |
| `get_heatmap(class_id)` | JSON list of `{problem, step, failed, attempted}` from Q\_HEATMAP |
| `get_clusters(class_id)` | JSON list of `{key, name, count, step, family, in_catalog}` from Q\_CLUSTERS |
| `get_examples(class_id, key)` | up to 3 submissions for a cluster, with steps and expected value |
| `generate_remediation(misconception_id, count)` | the engine's verified problems, with `verified` flag |

**System prompt (fixed text):** "You are an assistant for a signals-and-systems instructor. Use only numbers returned by tools; never compute or estimate a count yourself. Name a cluster only if it has in\_catalog true. Describe unclassified clusters as Other and do not guess their cause. For the top three misconceptions by count, call generate\_remediation and include only problems with verified true. Write a brief in Markdown with: one-sentence overview, a table of the top misconceptions with counts, and the practice problems."

**Wiring (verified with a scripted stand-in model, no API key):** `create_deep_agent(model=..., tools=[...], system_prompt=...)` accepted the tools, ran the loop, executed both tool functions, and `agent.astream({"messages": [...]}, stream_mode="updates")` yielded the tool calls, tool results and final text. Map events as follows: an AI message with `tool_calls` becomes `ToolCallEvent`; a message of type `tool` becomes `ToolResultEvent` with the first 60 characters of content as `summary`; an AI message with text and no tool calls becomes `BriefEvent` (save to `briefs`, return its id). Streamed `text_delta` events are optional.

**Model.** Read the model name from environment variable `AGENT_MODEL` (suggested value `anthropic:claude-sonnet-5-5`) and require `ANTHROPIC_API_KEY`; without the key `Analyze` returns FAILED\_PRECONDITION. Not verified here: a live call to the model, since no key was available.

**Number check (required).** After the brief is produced, extract every integer in the Markdown and confirm each appears in some tool result of that run (or is 1 to 3 as a list ordinal). If any does not, replace the brief with an `error` event saying `brief contained an unverified number`. This is the guard that keeps the language model from inventing counts.

### 6.4 Angular app

Angular with TypeScript, standalone components, served by the Go gateway in production and by `ng serve` in development with a proxy sending `/misconception.v1.GatewayService/` to `http://localhost:8080`. The client is generated by `protoc-gen-es` (verified to generate TypeScript here) and called with `@connectrpc/connect-web` using the Connect protocol.

| Route | Component | Content |
| --- | --- | --- |
| `/` | ClassListComponent | Lists classes; button Seed synthetic class (60 students); button Process |
| `/class/:id` | ClassDashboardComponent | Heatmap (problems as rows, steps as columns, cell shade = failed / attempted, number inside), cluster list sorted by count, Analyze button |
| `/class/:id/cluster/:key` | ClusterComponent | Misconception name and description, fix hint, 5 example submissions, button Generate practice (3) |
| `/class/:id/submission/:sid` | SubmissionComponent | The student's steps with the first wrong step highlighted, expected value next to it |
| `/try` | TryComponent | Pick a problem, type steps, see the diagnosis live |
| `/class/:id/evaluation` | EvaluationComponent | GetEvaluation figures and the per-label table |

Math is rendered with KaTeX from the `*_latex` fields. Streams (ProcessClass, AnalyzeClass) are shown as a progress bar and a live event log. Heatmap cells use one sequential colour ramp and always show the number, never colour alone. Not verified here: the Angular build itself (no Angular project was compiled in the sandbox); the generated TypeScript types were checked, the components were not.

**Environment variables (all services).**

| Variable | Used by | Default |
| --- | --- | --- |
| `DATABASE_URL` | gateway, engine (read-only role) | `postgres://postgres:postgres@localhost:5432/misconception` |
| `ENGINE_ADDR` | gateway | `http://localhost:50051` |
| `PORT` | gateway | `8080` |
| `ANTHROPIC_API_KEY` | engine agent | none; required for Analyze |
| `AGENT_MODEL` | engine agent | `anthropic:claude-sonnet-5-5` |
| `WOLFRAM_APP_ID` | engine, optional | unset |

## 7. Misconception catalog and problem bank

### 7.1 Problem families and parameters

| Family | Given | Steps (kind) | Correct answer | Parameters |
| --- | --- | --- | --- | --- |
| f1 inverse Laplace by partial fractions | F(s) = (s+n) / ((s+p)(s+q)) | 1 partial fractions (equal); 2 inverse transform (invL) | sum of residue·exp(-pole·t)·u(t) | p, q distinct in 1..6; n in 0..6 and not equal to p or q |
| f2 causal convolution | x(t) = exp(-a t)u(t), h(t) = exp(-b t)u(t) | 1 setup integral (conv\_setup); 2 simplify integrand (equal); 3 evaluate (equal) | u(t)·(exp(-b t) − exp(-a t)) / (a − b) | a, b distinct in 1..6 |
| f3 Fourier transform | x(t) = exp(-a t)u(t), X(jw) = integral of x(t)exp(-jwt) dt | 1 integral (ft\_integral); 2 closed form (equal) | 1/(a + j·w) | a in 1..6 |
| f4 Laplace time shift | x(t) = exp(-a(t−T))u(t−T) | 1 transform (L\_shift); 2 rewrite (equal) | exp(-s·T)/(s + a) | a in 1..5, T in 1..4 |

Problem id format: `f1-p{p}-q{q}-n{n}`, `f2-a{a}-b{b}`, `f3-a{a}`, `f4-a{a}-T{T}`.

**Default problem set (fixed, eight problems).**

| id | Correct step values (Step DSL) |
| --- | --- |
| f1-p1-q2-n0 | 1: `2/(s+2) - 1/(s+1)`; 2: `(2*exp(-2*t) - exp(-t))*u(t)` |
| f1-p2-q3-n1 | 1: `2/(s+3) - 1/(s+2)`; 2: `(2*exp(-3*t) - exp(-2*t))*u(t)` |
| f2-a1-b2 | 1: `u(t)*int(exp(-tau)*exp(-2*(t-tau)),tau,0,t)`; 2: `u(t)*int(exp(-2*t)*exp(tau),tau,0,t)`; 3: `u(t)*(exp(-t) - exp(-2*t))` |
| f2-a2-b3 | 1: `u(t)*int(exp(-2*tau)*exp(-3*(t-tau)),tau,0,t)`; 2: `u(t)*int(exp(-3*t)*exp(tau),tau,0,t)`; 3: `u(t)*(exp(-2*t) - exp(-3*t))` |
| f3-a1 | 1: `int(exp(-t)*exp(-j*w*t),t,0,inf)`; 2: `1/(1+j*w)` |
| f3-a2 | 1: `int(exp(-2*t)*exp(-j*w*t),t,0,inf)`; 2: `1/(2+j*w)` |
| f4-a1-T1 | given `exp(-(t-1))*u(t-1)`; 1: `exp(-s)/(s+1)`; 2: same |
| f4-a2-T2 | given `exp(-2*(t-2))*u(t-2)`; 1: `exp(-2*s)/(s+2)`; 2: same |

Run here: for every one of these eight problems, every catalog mutation below differs from the correct value and `diagnose` returns that mutation's id at the right step (32 of 32 mutation checks, listed by problem in the run output, none coincided with the truth).

### 7.2 Catalog (14 entries, final)

Each entry is a function that builds the wrong answer from the student's previous step, the expected value and the parameters. Step numbers are where the entry applies. A hint is the text shown to the instructor on the cluster page.

| id | Family, step | Wrong answer it builds | Fix hint |
| --- | --- | --- | --- |
| cover\_up\_forgot\_other\_factor | f1, 1 | Each residue is the numerator at the pole, without dividing by the other denominator factor | The cover-up method divides by the remaining factors evaluated at the pole |
| residues\_assigned\_to\_wrong\_poles | f1, 1 | Residues swapped between the two poles | Match each residue to the pole it was computed at |
| forgot\_causality\_u\_of\_t | f1, 2; f2, 1; f2, 3 | The correct value with every u(.) replaced by 1 | A causal signal is zero for t < 0; keep u(t) |
| pole\_sign\_flipped\_in\_exponent | f1, 2 | Every exp argument negated | A pole at s = −r gives exp(−r t), not exp(+r t) |
| forgot\_to\_flip\_h | f2, 1 | Integrand x(tau)·h(tau) instead of x(tau)·h(t − tau) | Convolution flips and shifts h: h(t − tau) |
| integration\_forgot\_divide\_by\_rate | f2, 3 | u(t)·(exp(-b t) − exp(-a t)) without dividing by (a − b) | Integrating exp(c·tau) gives exp(c·tau)/c |
| sign\_of\_exponent\_flipped | f3, 1 | Integral with exp(+j·w·t) | The kernel is exp(−j·w·t) |
| ordinary\_frequency\_2pi\_in\_exponent | f3, 1 | Integral with exp(−2·π·j·w·t) | w is angular frequency; there is no 2π in the exponent |
| copied\_tool\_default\_convention | f3, 1 | (1/√(2π))·integral with exp(+j·w·t) | Tool defaults differ from the course convention; use the course definition |
| unitary\_1\_over\_sqrt\_2pi\_prefactor | f3, 1 | (1/√(2π))·integral with exp(−j·w·t) | The course definition has no 1/√(2π) prefactor |
| dropped\_shift\_exponential | f4, 1 | 1/(s + a) | A delay of T multiplies by exp(−s·T) |
| shift\_exponent\_sign\_flipped | f4, 1 | exp(+s·T)/(s + a) | Delay gives exp(−s·T), not exp(+s·T) |
| shift\_added\_to\_pole | f4, 1 | 1/(s + a + T) | The time shift goes in the exponential, not in the pole |
| time\_shift\_confused\_with\_freq\_shift | f4, 1 | exp(−a·T)·exp(−s·T)/(s + a) | exp(−a·T) belongs to a different property; here the shifted signal already contains it |

A misconception may apply at several (family, step) pairs; its id is global. In `Misconception.step_index` store the first listed step for ids that appear in more than one place and list all places in `description`. Do not add, rename or remove an entry during the build; to change the course convention, edit only the four f3 entries and the f3 answer key.

Measured across 188 catalog-error submissions in the evaluation run, the engine returned the injected id in every one (section 8). That is a self-consistency result, not an accuracy claim about real students.

### 7.3 Remediation generator (GenerateRemediation)

Goal: for a misconception id, return `count` practice problems whose correct answer differs from the wrong answer that misconception produces, with answer keys checked by two independent routes.

1. Look up the entry's family and step.
2. Build the candidate list: every parameter combination allowed in the table in 7.1, in the order produced by `random.Random(seed).shuffle`.
3. For each candidate, build the correct steps and the entry's wrong answer. Discard the candidate if the wrong answer is missing or equals the correct step by the equivalence test, so every returned problem separates the misconception from the correct answer. Put the wrong answer in `why_it_discriminates`.
4. Verify the answer key by two routes and record their names in `verification_routes`:
   - `formula`: the closed-form key from the family definition in 7.1.
   - `numeric_quad`: evaluate the defining integral numerically with `mpmath.quad` at 3 sample points and compare with the key (f2 and f3), or compare with the sampled value of the key from the problem's given (f1 and f4 use the transform pair from SymPy as the second route, named `sympy_transform`).
5. Set `verified = true` only when both routes agree within the tolerance of section 3; otherwise drop the candidate.
6. Stop at `count` problems. Never return a problem with `verified = false`.

What is verified here: the closed-form answer keys for f3 against numeric quadrature, and the correct step values for all eight default problems, by running the reference code. Not run here: the generator loop itself (steps 2 to 6) and the f1/f4 SymPy transform route; build it as the first task of the engine's remediation module and cover it with the test in section 8 that every returned problem has `verified = true` and a wrong answer that is not equivalent to the key.

## 8. Synthetic data and evaluation

### 8.1 Synthetic class generator (GenerateClass)

Inputs: `num_students`, `seed`, `error_rate`, `heldout_share`, and the problem list (default: the eight problems in section 7). Use one `random.Random(seed)` for everything so a seed reproduces the class exactly.

For each student and each problem:

1. With probability `1 - error_rate`, write the correct derivation. Half of these (chosen by the same generator) use an equivalent but differently written form of the correct steps, such as `together(...)` for partial fractions, so the checker is tested on valid rewrites. Ground truth: `true_step_index = 0`, `true_label = ""`.
2. Otherwise choose the step to break uniformly among the catalog steps of the family. With probability `heldout_share` apply a held-out error, otherwise apply a catalog entry for that step.
3. Catalog error: apply the entry's function to the student's previous step. If the result equals the correct value (the mutation coincides for these parameters) pick another entry. Ground truth: that step and the entry id.
4. Held-out error: one of additive constant (+1/3), dropped term (only when the correct value is a sum), or one perturbed integer constant. These are not in the catalog on purpose. Ground truth: that step and `heldout:<kind>`.
5. Later steps are what a consistent student would write after the wrong step (the reference code's `propagate`), so the first divergence is the only one.
6. `student_label` is `S001`, `S002`, ... and no real names are ever generated.

### 8.2 Metrics (computed by GetEvaluation from section 5 queries)

| Metric | Definition | Target |
| --- | --- | --- |
| False alarms | correct submissions flagged as wrong | 0 |
| Step accuracy | flagged at the true first wrong step, over submissions that truly contain an error | at least 99% |
| Label accuracy | catalog errors whose injected id is among the returned ids at the true step | at least 95% |
| Held-out detection | held-out errors flagged at the true step | at least 99% |
| Held-out naming | held-out errors given a catalog name | 0 (they must stay unclassified) |
| Latency | per-diagnosis time, 95th percentile | at most 0.5 s |
| Class run | 60 students × 8 problems = 480 submissions, end to end through the gateway | at most 60 s |

### 8.3 What was measured here

The reference engine on a synthetic set of 12 instances per family (the fixed seed in `engine_spike.py`) produced:

| Measure | Result |
| --- | --- |
| Correct derivations flagged | 0 of 48 |
| Valid rewrites flagged | 0 of 48 |
| Catalog errors flagged at the true step | 188 of 188 |
| Catalog errors with the injected id returned | 188 of 188, and the returned id set had exactly one id each time |
| Held-out errors flagged at the true step | 164 of 164 |
| Held-out errors left unclassified | 164 of 164 (0 given a catalog name) |
| Per-diagnosis time, 400 diagnoses | median 0.012 s, 95th percentile 0.117 s, maximum 0.164 s |

Before the quadrature fast path the same 400-diagnosis run took 237 s; after it, 15.7 s, with identical results. At that rate 480 submissions take roughly 19 s sequentially; this is arithmetic from the measurement, not a run, so the 60 s class-run target is checked only when the gateway exists.

Per-label results (all matched): cover\_up\_forgot\_other\_factor 12/12, residues\_assigned\_to\_wrong\_poles 11/11, forgot\_causality\_u\_of\_t 36/36, pole\_sign\_flipped\_in\_exponent 12/12, forgot\_to\_flip\_h 12/12, integration\_forgot\_divide\_by\_rate 9/9, sign\_of\_exponent\_flipped 12/12, ordinary\_frequency\_2pi\_in\_exponent 12/12, copied\_tool\_default\_convention 12/12, unitary\_1\_over\_sqrt\_2pi\_prefactor 12/12, dropped\_shift\_exponential 12/12, shift\_exponent\_sign\_flipped 12/12, shift\_added\_to\_pole 12/12, time\_shift\_confused\_with\_freq\_shift 12/12.

### 8.4 What these numbers do not show

- **The catalog check is circular.** The synthetic errors are built by the same functions the catalog uses to recognize them, so 188 of 188 shows the machinery is consistent, not that real students make these errors in these forms. Only real derivations can test that.
- **There is no real student data.** Before the demo, ask classmates to solve the eight problems on paper (10 to 20 derivations is enough), type them in the Step DSL yourself, label the true first wrong step by hand, and report step accuracy and how many errors fall in Other. Do not tune the catalog on these and then report the same data as a test; keep half aside.
- **The Fourier convention is unconfirmed** for the course (section 3).
- **Sampling equality** can accept two functions that agree at the 6 sample points (section 3).

### 8.5 Baseline: a chat model alone (designed, not run)

The claim in section 1 is that a chat model alone cannot do this reliably. Test it rather than assert it, using the same submissions and ground truth:

1. Take 100 submissions from a synthetic class (seed 7) with the evaluation mix: 40 correct, 40 catalog errors, 20 held-out errors.
2. For each, send the problem, the correct answer and the student's steps to Claude through the API, with this fixed prompt: "Here is a signals-and-systems problem and one student's derivation. Check each step against the student's own previous step. Reply with JSON only: {"first\_wrong\_step": \<integer, 0 if all steps are correct>, "misconception": \<short name or empty>}."
3. Score first\_wrong\_step against ground truth (step accuracy, false alarms on the 40 correct ones). Score the misconception name by hand against the catalog entry's name and count it a match only if the same error is described.
4. Report the two systems side by side in the demo: engine and model, same 100 submissions. Also report determinism: run the model twice on the same 100 and count disagreements; the engine gives zero by construction (fixed seed).
5. Report the result whichever way it goes. If the model matches the engine on step accuracy, the remaining difference is aggregation across a class, determinism and verified answer keys, and the demo should say so.

Not run here: no API key was available in the build environment, so there is no measured baseline yet. Do not state a number for the model before running this.

## 9. Repository layout, setup and environment

**Versions the reference code ran on.** Use these or newer; if something breaks on a newer version, pin back to this table.

| Tool | Version run here |
| --- | --- |
| Python | 3.13 |
| SymPy / mpmath | 1.14.0 / 1.3.0 |
| grpcio, grpcio-tools | 1.85.1 |
| protobuf (Python) | 7.36.1 |
| deepagents | 0.7.38 (with langchain-core 1.8.0) |
| psycopg | 3.3.9 |
| Node | 22 |
| buf | 1.75.0 |
| protoc-gen-es, @bufbuild/protobuf | 2.17.0 |
| @connectrpc/connect, connect-web | 2.3.0 |
| PostgreSQL | 16.15 |
| Go | 1.24.7 installed; no Go package was downloaded or compiled (module proxy unreachable) |

**Layout (fixed).**

```
misconception/
  buf.yaml                 # lint STANDARD, breaking FILE
  buf.gen.yaml             # Go, TypeScript outputs
  proto/misconception/v1/  # common.proto engine.proto gateway.proto (section 4)
  sql/                     # schema.sql queries.sql (section 5)
  engine/                  # Python
    server.py              # grpc.aio server, registers both services
    parse_step.py          # from reference/
    diagnose.py            # from reference/engine_spike.py: families, catalog, equiv, diagnose
    problems.py            # the eight default problems and parameter grids (section 7)
    remediation.py         # section 7.3
    synthetic.py           # section 8.1
    agent.py               # section 6.3
    tests/                 # reference tests, ported
  gateway/                 # Go
    go.mod                 # module misconception
    main.go  service.go  db.go
    gen/go/                # generated, not committed
  web/                     # Angular app, section 6.4
    src/gen/               # generated TypeScript, not committed
  docker-compose.yml       # postgres:16, engine, gateway
  Makefile
  README.md
```

**Generated code is never committed.** `make gen` recreates it.

**buf.gen.yaml (final).**

```yaml
version: v2
plugins:
  - local: protoc-gen-go
    out: gateway/gen/go
    opt: paths=source_relative
  - local: protoc-gen-connect-go
    out: gateway/gen/go
    opt: paths=source_relative
  - local: node_modules/.bin/protoc-gen-es
    out: web/src/gen
    opt: target=ts
```

The TypeScript entry ran here. The two Go entries did not run (no network access to the Go proxy); they need `go install google.golang.org/protobuf/cmd/protoc-gen-go@latest` and `go install connectrpc.com/connect/cmd/protoc-gen-connect-go@latest`, and are the first things to check when scaffolding.

**Python stubs (ran here).**

```
mkdir -p engine/gen && python3 -m grpc_tools.protoc -I proto --python_out=engine/gen --grpc_python_out=engine/gen --pyi_out=engine/gen proto/misconception/v1/*.proto
```

**Setup commands.**

```
pip install sympy mpmath grpcio grpcio-tools protobuf deepagents "psycopg[binary]"
npm i -D @bufbuild/buf @bufbuild/protoc-gen-es @bufbuild/protobuf
npm i @connectrpc/connect @connectrpc/connect-web
npx buf lint            # no output means pass
```

**Makefile targets (fixed names).**

| Target | Does |
| --- | --- |
| `make gen` | buf generate plus the Python stub command above |
| `make db` | start postgres:16 and apply sql/schema.sql |
| `make engine` | run the Python server on 50051 |
| `make gateway` | run the Go server on 8080 |
| `make web` | `ng serve` with the proxy to 8080 |
| `make test` | run the engine tests and `npx buf lint` |
| `make demo` | seed the default synthetic class and process it through the gateway |

**Environment variables** are in section 6.4. For the deployed demo, run Postgres on a Tiger Cloud Free service and set `DATABASE_URL` to its connection string; the schema uses no extension, so it should apply unchanged. Not verified here: Tiger Cloud Free limits and sign-up steps; read the sponsor's page before relying on it, and keep the Docker Postgres as the fallback.

**Acceptance gates before moving on** (each is a command with an expected result):

| Gate | Command | Expected |
| --- | --- | --- |
| Contracts | `npx buf lint` | no output |
| Library claims | `PYTHONPATH=reference python3 reference/tests/verify_claims.py` | 10 passed, 0 failed |
| Parser | `PYTHONPATH=reference python3 reference/tests/test_parse.py` | 12 of 12 valid parsed, 17 of 17 hostile rejected |
| Engine evaluation | `PYTHONPATH=reference python3 reference/engine_spike.py 12` | 0 false alarms; results as in section 8.3 |
| Python gRPC | `PYTHONPATH=reference:. python3 reference/tests/grpc_roundtrip.py` | VALID, DIVERGED, PARSE\_ERROR and a 6-message stream |
| Agent wiring | `python3 reference/tests/agent_fake.py` | 2 tool calls executed, then final text |
| Go to Python call | first Diagnose through the gateway | same Diagnosis as the Python test (not yet run) |

## 10. Build plan and work split

Times are hours from the moment a lane starts building (H0). The opening-ceremony deck says final submissions are due Sunday, November 15 at 8:00 AM, Devpost only, and that the entire project must be built inside the 36-hour window, starting at the end of the opening ceremony. When this plan was written it was 12:04 AM on Saturday, November 14, which leaves about 32 hours. Plan to be code-complete 3 hours before the deadline (Saturday 11 PM is a safe target if the lanes start by 1 AM) and use the last hours only for the demo, the submission text and sleep. The demo or judging time slot is not in the decks we have; read it from the Hacker Onsite Handbook.

Three lanes run in parallel because the contracts in section 4 let each side build against generated stubs. A lane is one engineer or one agent session with its own branch.

| Lane | Owns | Starts with | Done when |
| --- | --- | --- | --- |
| A: Engine (Python) | `engine/` | Port `reference/` into the layout in section 9; run the acceptance gates in section 9 | Diagnose, DiagnoseBatch, ListProblems, ListMisconceptions, GenerateClass and GenerateRemediation pass their tests and the evaluation in section 8.3 reproduces |
| B: Gateway and data (Go, SQL) | `gateway/`, `sql/` | Generate Go stubs; compile an empty handler; one Diagnose call to the engine (the first integration gate, section 6.2) | All twelve GatewayService RPCs work against the real engine and Postgres; ProcessClass streams progress |
| C: Web (Angular) | `web/` | Generate TypeScript stubs; build the six routes against a mock gateway returning fixed data | Every route works against the real gateway, with the seeded class |

| Hours | What happens | Gate |
| --- | --- | --- |
| H0 to H1 | Everyone: repo scaffold from section 9, run the six acceptance gates, confirm the Fourier convention with the course materials | All gates in section 9 green except the Go-to-Python call |
| H1 to H4 | A: engine server, problem bank, catalog. B: stubs, schema, first engine call, SeedSyntheticClass. C: shell, routes, mock data | B's first Diagnose call returns the same result as the Python test |
| H4 to H8 | A: remediation generator, synthetic generator, evaluation reproduces. B: ProcessClass, GetHeatmap, GetClusters, GetEvaluation. C: heatmap, clusters, submission view | Seed and process a 60-student class end to end in under 60 s |
| H8 to H12 | A: Deep Agent and number check. B: AnalyzeClass stream, GenerateRemediation. C: Try page, cluster page with practice problems, evaluation page | Analyze produces a brief with a real model and the number check passes (needs an API key) |
| H12 to H16 | Run the baseline in section 8.5; collect and label the real classmate derivations; write the Devpost text from the measured results only | Baseline and real-data numbers recorded, whichever way they come out |
| H16 to deadline minus 3 | Bug fixing only; freeze the catalog; record the demo run once | Demo runs three times in a row from a clean database |
| Last 3 hours | Demo rehearsal, Devpost submission, sleep | Submitted |

**Rules for agents building in parallel.**

1. Do not edit `proto/` or `sql/` in a lane branch. A contract change goes to the repository owner, who edits it, runs `npx buf lint` and regenerates for everyone.
2. Do not change the catalog, the Step DSL or the equivalence rules (section 3 and 7). They are locked.
3. Every claim in the Devpost text and the demo must come from a number shown by the evaluation page or by a run you can repeat on stage.
4. If a gate fails and the fix is not obvious in 30 minutes, use the documented fallback (grpc-go client; Docker Postgres) and move on.

**Cut list, in the order to cut when behind:** Wolfram cross-check, the `/try` page, the per-label table, streaming `text_delta` events from the agent, the Tiger Cloud deployment. Never cut the heatmap, the clusters, the verified practice problems or the evaluation page.

## 11. Demo script, rules and prize mapping

**Event rules from the opening-ceremony deck (read them before submitting).** The project must be built inside the 36-hour window; at least 85% of the code must be written during the event; no crossposting; at most 4 members per team; submissions only through Devpost, due Sunday, November 15 at 8:00 AM; track-specific and plagiarism rules are on the Devpost page and in the Hacker Onsite Handbook, which the deck calls the most updated document. Keep a git history from the first commit so the 85% rule can be shown, and cite the SymPy, mpmath, Deep Agents, connect-go, Angular and KaTeX libraries in the README.

**Prizes this project can reasonably target.** The track list below is read from the deck. Eligibility rules for each prize were not in the deck, so the last column is what to check in the handbook, not a promise.

| Prize (from the deck) | Why this project fits | Check in the handbook |
| --- | --- | --- |
| Best Overall Hack | Whole pipeline, measured evaluation | Judging criteria |
| Best Education Hack | Instructor tool for a signals course | Whether it is judged by impact or by demo |
| Best Science & Discovery Hack | Verified mathematics, deterministic checking | Whether education projects can also enter this track |
| Best Practical AI Innovation | The model writes the brief and never decides correctness | Whether a model is required to be central |
| Best use of Deep Agents | The instructor brief runs on Deep Agents with deterministic tools | What "best use" is scored on; the deck says to see the handbook |
| Best Use of Tiger Data (MLH) | Postgres, deployed on Tiger Cloud Free | Whether a deployed Tiger Cloud database is required |

Best Use of Gemini API, MongoDB Atlas, Vultr and the other MLH prizes are not targeted: the design uses Claude and Postgres. Do not add a sponsor technology only to enter its prize. Whether Best Rookie Hack applies depends on the team's members; check the rule.

**Demo script (3 minutes, in this order, same words every run).**

| Time | Screen | Say |
| --- | --- | --- |
| 0:00 | Class list | "An instructor with 60 students and 8 problems has 480 derivations to read. This tool reads them in seconds and tells the instructor where the class is stuck." |
| 0:20 | Click Process on the seeded class | "Each step is checked by mathematics, not by a language model: a step is right if it follows from the student's own previous step." The progress bar fills. |
| 0:50 | Heatmap | "Each cell is a problem step; the number is students whose first mistake is here." Point at the darkest cell. |
| 1:15 | Clusters, then the top one | "The mistakes group into named misconceptions with counts." Show one catalog cluster and the Other cluster: "Anything outside the catalog is shown as Other; the tool never invents a name." |
| 1:45 | One submission | The first wrong step is highlighted with the expected value next to it. "Later steps are not blamed for an earlier mistake." |
| 2:05 | Generate practice | "Three practice problems for this misconception. Each answer key was checked by two independent routes." |
| 2:25 | Evaluation page | Read the numbers on screen: false alarms, step accuracy, held-out detection. Then say: "This is a synthetic class, built from our own error catalog, so it tests consistency, not real students." |
| 2:45 | Analyze class | The agent's tool calls stream, then the brief. "The agent writes the summary; every number in it comes from a tool, and we check that." |

If the model call fails on stage, skip the last row and say so. If a baseline was run (section 8.5), add one sentence after the evaluation page with its measured result, whichever way it came out. Rehearse from a clean database three times before the demo.

## 12. Verified-claims log

Every factual claim in this spec is in one of three groups. If a claim is not here, it is a design decision, not a fact.

### 12.1 Verified by running code in the build environment

| Claim | Evidence |
| --- | --- |
| SymPy's `fourier_transform` uses exp(-2·π·i·k·x); FT of exp(-2t)u(t) is 1/(2+2πik); `fourier_transform(cos t)` is 0 | `verify_claims.py`, 10 of 10 checks pass |
| The course-convention key 1/(a+jw) equals the defining integral | `verify_claims.py`, compared with `mpmath.quad` at two (a, w) pairs |
| The Step DSL parser accepts 12 of 12 valid steps and rejects 17 of 17 hostile inputs, each in under 1 ms | `test_parse.py` |
| Diagnosis results in section 8.3 (0 false alarms in 96 correct or rewritten derivations; 188 of 188 catalog errors; 164 of 164 held-out errors flagged and unnamed; p95 0.117 s) | `engine_spike.py 12` |
| The quadrature fast path cut the 400-diagnosis run from 237 s to 15.7 s with identical results | Before and after runs of the same evaluation |
| All 32 catalog mutations on the eight default problems differ from the truth and are labelled correctly | Bank check run during this write-up |
| The three proto files pass `buf lint` (STANDARD) and generate Python and TypeScript | `buf lint`; `grpc_tools.protoc`; `protoc-gen-es` |
| A `grpc.aio` Python server answers unary and streaming calls built from the generated stubs | `grpc_roundtrip.py` |
| `create_deep_agent` accepts our tools, runs the tool loop, and `astream(stream_mode="updates")` yields tool calls, results and text | `agent_fake.py`, scripted model, no API key |
| The schema and four queries run on PostgreSQL 16 and give the fixture results in section 5 | `sql_test.py` |

The starter package contains all of these files. Run them with the commands in its README.

### 12.2 Taken from documentation or the event decks, not run here

| Claim | Source |
| --- | --- |
| A connect-go client built with `connect.WithGRPC()` can call a gRPC server, and over cleartext HTTP/2 it needs an HTTP client configured for h2c (`http2.Transport` with `AllowHTTP`); the server side uses `h2c.NewHandler` | [Connect: common errors](https://connectrpc.com/docs/go/common-errors/), [Connect: gRPC compatibility](https://connectrpc.com/docs/go/grpc-compatibility/), [Connect: deployment and h2c](https://connectrpc.com/docs/go/deployment/) |
| Wolfram `FourierTransform` defaults to FourierParameters {0,1} (modern physics); {1,-1} is listed for pure mathematics and systems engineering; {0,-2Pi} for signal processing | [Wolfram: FourierTransform](https://reference.wolfram.com/language/ref/FourierTransform) |
| `create_deep_agent` takes a `model` string in `provider:model` form and a `tools` list | [Deep Agents docs](https://docs.langchain.com/oss/python/deepagents), [customization](https://docs.langchain.com/oss/python/deepagents/customization.md) |
| Submissions are due Sunday, November 15 at 8:00 AM on Devpost; the project must be built in the 36-hour window; at least 85% of code written during the event; at most 4 team members; no crossposting | Opening-ceremony deck (the PDF you attached) |
| The deck lists nine main tracks including Best Overall, Best Education and Best Science & Discovery, plus special tracks including Best Practical AI Innovation and Best use of Deep Agents; MLH lists Best Use of Tiger Data | Opening-ceremony deck and MLH deck (the PDFs you attached) |

### 12.3 Not verified, with the fallback

| Item | Why not verified | Fallback or check |
| --- | --- | --- |
| Every Go component: connect-go server, generated Go stubs, `pgx`, h2c client to the Python engine | The Go module proxy was unreachable from the build environment, so nothing was downloaded or compiled | First integration gate (section 6.2); fallback is a generated `grpc-go` client. Also check the current module path and major version of `connectrpc.com/connect` when you run `go get`; the docs index lists a v2 page |
| `protoc-gen-go` and `protoc-gen-connect-go` through buf | Same reason | Install commands in section 9 |
| The Angular app and the Connect web client in a browser | No Angular project was built | Build the `/` and `/class/:id` routes first and call one RPC |
| A live Claude call from the Deep Agent, and the model name `anthropic:claude-sonnet-5-5` | No API key in the build environment | Set `AGENT_MODEL` to any model string your key accepts; `Analyze` returns FAILED\_PRECONDITION without a key |
| The Wolfram probe and any Wolfram entitlement | Not confirmed | The path is optional and cut first |
| Tiger Cloud Free service limits and sign-up | Not read | Docker Postgres is the fallback |
| The remediation generator loop (section 7.3) and the f1/f4 SymPy transform route | Designed, not run | Build and test it first in the engine's remediation module |
| The model-alone baseline (section 8.5) | Needs an API key | Run it before stating any number about the model |
| Judging criteria, prize eligibility, and the demo time slot | Not in the decks | Read the Hacker Onsite Handbook |
| The course's Fourier convention | Needs the course materials | Section 3: change one answer key and four catalog entries |
| Accuracy on real student derivations | There is no real data | Section 8.4 |

### 12.4 Limits of the evaluation, stated once

The 188 of 188 and 164 of 164 results come from errors the code itself generated. They show the checker is internally consistent and fast, not that it matches what real students write.
