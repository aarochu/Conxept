# Real derivations (spec §8.4)

The synthetic evaluation only shows the engine is internally consistent. This folder is for a small
set of real derivations, which is the only data that can test the catalog against real students.

1. Ask classmates to solve the eight default problems on paper (10 to 20 derivations is enough).
2. Copy `derivations.template.csv` to `derivations.csv` and type each derivation in the Step DSL,
   one row per derivation. Use anonymized labels in `student` (A01, A02, ...), never real names.
   Steps with commas, such as `int(f, t, 0, inf)`, must be in double quotes (spreadsheet apps do
   this for you when they save CSV).
3. Label `true_step` by hand: `0` if every step is correct, else the first wrong step. Optionally set
   `true_label` to a catalog id, or `other` for an error the catalog doesn't describe.
4. Run `make real-eval` (the `test` half) and `make real-eval SPLIT=dev` (the half you may look at
   while fixing typing mistakes).

Rows are split in half by a hash of `id`, so adding rows never moves an existing one. **Do not tune
the catalog on the test half and then report it.** Report the result whichever way it goes.

`derivations.csv` is gitignored: it is classmates' work, so keep it out of the repository unless
everyone agreed to share it.
