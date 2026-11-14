# Browser walkthrough and remaining inputs — November 14, 2026

The local synthetic-data walkthrough passed. A silent captioned draft recording
was produced and checked with ffprobe: **117.000 seconds**. It has not been
uploaded or submitted. Reproduce it with `npm run record:demo` from `web/` after
starting the disposable stack; recordings are written under `web/demo-results/`.

## Tested flow

| Step | Observed result |
| --- | --- |
| Seed and Process | 60 students, eight problems, 480 submissions; completes through the browser |
| Dashboard | 18 heatmap cells and catalog/Other clusters render |
| Other | No invented misconception name; examples remain inspectable |
| Catalog cluster | Description, fix hint, and example links work |
| Submission | First wrong step and expected expression render; later steps remain unchecked |
| Practice | Three problems, each marked verified by two routes |
| Evaluation | False alarms 0/167; steps 313/313; labels 235/235; held-out detection 78/78 |
| Analyze without a key | Explicit unavailable message; not counted as a live-model success |
| Try response race | Deterministic test fails on the old build and passes with immediate invalidation |
| Keyboard | Header navigation reaches Try; the problem select and both step fields are reachable |

The recording used a local integration of PRs #36–#39. It includes the MathML,
stale-verdict, and contrast fixes; it does not imply those PRs are all merged.
The observed evaluation remains synthetic internal consistency, not accuracy on
real students. No comparison against a live model has been measured.

## Accessibility and visual checks

The walkthrough exposed visual-only equations, unreadable heatmap counts, faded
unchecked-step labels, and low-contrast light-theme success badges. Fixes are in
PRs #36, #37, and #39. Semantic math exposure was checked in the accessibility tree.

After the contrast fixes, axe-core 4.14.0 reported zero violations for the selected
WCAG-tagged checks across seven page states in both light and dark themes:
classes, Try, dashboard, evaluation, catalog cluster, Other cluster, and submission.
Some checks remain incomplete; no full screen-reader or accessibility-conformance
claim is made. The tested desktop dashboard's Lighthouse accessibility score
changed from 93 to 100.

Reference screenshots were captured at widths 375, 768, and 1440; document width
matched viewport width in each capture. Mobile is outside the locked product
scope. There is no committed visual baseline, so visual-regression comparison is
**inconclusive**. These checks are not a Core Web Vitals benchmark.

## Inputs still needed

- **Model credentials:** no `ANTHROPIC_API_KEY`, Anthropic CLI, or repository `.env`
  was available. Run the baseline and strict live-Analyze gate when credentials exist.
- **Real derivations:** neither the integration checkout nor the original Desktop
  checkout has `data/real/derivations.csv`. Collect and hand-label the sample first.
- **Course materials:** confirm the Fourier convention; do not infer it from the checker.
- **Deployment access:** provide the intended Tiger Cloud service and application host.
  Prepared Compose configuration is not evidence of a hosted deployment.
- **Submission ownership:** confirm team/registration details, current handbook,
  event timing, prize eligibility, and final public repository/video/project links.
  See [event-checks.md](event-checks.md) for the timing discrepancy.

These inputs block the remaining plan gates. The optional Wolfram cross-check
remains cut; no entitlement has been supplied. The draft video still needs owner
review before upload and final submission.
