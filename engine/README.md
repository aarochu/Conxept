# engine (Lane A, Python)

`grpc.aio` server on port 50051 registering `EngineService` and `InstructorAgentService`.
Port `reference/engine_spike.py` and `reference/parse_step.py` — do not rewrite the math.

Planned files (spec §9): `server.py`, `parse_step.py`, `diagnose.py`, `problems.py`,
`remediation.py`, `synthetic.py`, `agent.py`, `tests/`. Generated stubs go in `engine/gen/` (not committed).
