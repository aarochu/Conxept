# Submission evidence and remaining gates

## Reproduced locally — November 14, 2026

Rehearsal source: commit `afbb0b45ef3de81ba2b763f43577060330908aed` on PR #4, including the reviewed engine changes from PR #1. PostgreSQL 16 used a disposable database on port 55432, engine port 50061, gateway port 18080, and the production Angular build. The engine was warm from integration tests; timings are not cold-start benchmarks.

```bash
cd gateway
go run ./cmd/rehearse \
  -gateway http://127.0.0.1:18080 \
  -db postgres://postgres@127.0.0.1:55432/misconception \
  -reset -runs 3
```

`-reset` deletes the target database's project data. Use a disposable instance. Each run seeded 480 submissions and completed all required automated steps. All three returned false alarms `0/167`, step accuracy `313/313`, catalog label accuracy `235/235`, and held-out detection `78/78`. Analyze was skipped in all three runs because the engine had no API key. Example student selection varied because SQL orders examples by fresh submission UUIDs.

Gateway integration tests passed against that instance. The production web build passed. The engine plus baseline suite passed 144 tests; the real-evaluation and diagnosis subset passed 75 tests. GitHub CI is the authoritative check for each PR's final merged revision.

## Before recording and submitting

- [ ] Confirm the course uses `X(jw) = integral x(t) exp(-j*w*t) dt`, angular frequency, no prefactor.
- [ ] Collect 10–20 anonymized classmate derivations, label them independently, and reserve the test split before tuning. Do not present template examples as real data.
- [ ] Run `make baseline` with valid credentials; score misconception names by hand and report results even if the model wins.
- [ ] Run Analyze with a live model and inspect both the tool events and the final brief.
- [ ] Review the browser walkthrough and sub-two-minute draft recording; confirm current event timing before uploading. If Analyze is unavailable, show the fallback explicitly.
- [ ] Provision and smoke-test the hosted database and application before claiming a Tiger Cloud deployment.
- [ ] Confirm team details, prize eligibility, submission deadline, and demo slot against the current event handbook.
- [ ] Add the video and project links to the Devpost entry, review the final claims, and submit.

The local automated rehearsal gate is complete. Real-student accuracy, comparative model performance, live brief quality, and hosted operation remain unmeasured.
