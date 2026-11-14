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
