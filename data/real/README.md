# Real derivations (spec §8.4)

The synthetic evaluation only shows the engine is internally consistent. This folder is for a small
set of real derivations, which is the only data that can test the catalog against real students.

1. Run `make worksheet` to generate `data/real/worksheet.md` from the eight default problems.
   Render it with Markdown math support before printing. The sheet includes the givens and step
   prompts, with no answer keys or misconception names. Confirm the printed Fourier convention
   matches the course before collecting results. Ask classmates to solve assigned problems on
   paper; collect 10 to 20 derivations in total, rather than requiring every participant to finish
   all eight problems. Explain the evaluation and ask permission to use their anonymized work.
2. Copy `derivations.template.csv` to `derivations.csv` and type each derivation in the Step DSL,
   one row per derivation. Use anonymized labels in `student` (A01, A02, ...), never real names.
   Steps with commas, such as `int(f, t, 0, inf)`, must be in double quotes (spreadsheet apps do
   this for you when they save CSV).
3. Label `true_step` by hand: `0` if every step is correct, else the first wrong step. Optionally set
   `true_label` to a catalog id, or `other` for an error the catalog doesn't describe.
4. Run `make real-check` before scoring. It checks CSV structure, problem ids, step counts,
   and hand-label metadata across all rows without calculating diagnoses or writing scores.
   It also parses every step with the Step DSL parser, so transcription typos are caught before any
   row is scored. It returns failure for invalid input. It does not check mathematical correctness.
5. Run `make real-eval` (the `test` half) and `make real-eval SPLIT=dev` (the half you may look at
   while fixing typing mistakes).

Rows are split in half by a hash of `id`, so adding rows never moves an existing one. **Do not tune
the catalog on the test half and then report it.** Report the result whichever way it goes.

`derivations.csv` is gitignored: it is classmates' work, so keep it out of the repository unless
everyone agreed to share it.

Use stable row ids assigned before inspecting engine output. Keep participant labels anonymous
and any identity mapping outside this repository. A blank worksheet answer is unattempted work,
not a correct derivation; omit it from the evaluation CSV. Hand-label each completed derivation
before comparing it with the engine. Preserve the test split and report the sample size and
excluded rows alongside the results. The generated worksheet stays local and can be regenerated
when needed; collecting data and confirming the course convention remain manual plan gates.
