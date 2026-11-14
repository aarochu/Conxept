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
