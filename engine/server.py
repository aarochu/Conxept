"""Engine gRPC server (spec section 6.1). Port 50051.

One grpc.aio process registering EngineService and InstructorAgentService.
SymPy and mpmath are CPU-bound, so diagnoses run in a 4-worker process pool
with a 5-second timeout each.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "gen"))
sys.path.insert(0, str(HERE))

import grpc  # noqa: E402
from misconception.v1 import common_pb2 as cpb  # noqa: E402
from misconception.v1 import engine_pb2 as pb  # noqa: E402
from misconception.v1 import engine_pb2_grpc as rpc  # noqa: E402

log = logging.getLogger("engine")

WORKERS = 4
TIMEOUT_S = 5.0
_pool: ProcessPoolExecutor | None = None


# ------------------------------------------------------------ worker jobs
# Module-level so they pickle into the process pool.


def _timed_out() -> dict:
    return {
        "status": 3,
        "step_index": 0,
        "misconception_ids": [],
        "residual_label": "",
        "expected_latex": "",
        "student_latex": "",
        "parse_error": "timed out",
        "parse_error_step": 0,
        "elapsed_ms": int(TIMEOUT_S * 1000),
    }


def _raise_timeout(signum, frame):
    from diagnose import DiagnosisTimeout

    raise DiagnosisTimeout()


def job_diagnose(problem_id: str, steps: list[str]) -> dict:
    """Runs in a pool worker. A real-time timer interrupts SymPy/mpmath after TIMEOUT_S,
    so a pathological step frees its worker instead of occupying it indefinitely."""
    from diagnose import DiagnosisTimeout, diagnose
    from problems import problem_from_id

    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, TIMEOUT_S)
    try:
        return diagnose(problem_from_id(problem_id), steps).__dict__
    except DiagnosisTimeout:
        return _timed_out()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def job_generate_class(num_students, seed, problem_ids, error_rate, heldout_share):
    from synthetic import generate_class

    problems, subs = generate_class(num_students, seed, problem_ids, error_rate, heldout_share)
    return [p.id for p in problems], [s.__dict__ for s in subs]


def job_remediation(misconception_id: str, count: int, seed: int):
    from remediation import generate_remediation

    return [
        {
            "problem_id": r.problem.id,
            "answer_key_latex": r.answer_key_latex,
            "verification_routes": r.verification_routes,
            "verified": r.verified,
            "why_it_discriminates": r.why_it_discriminates,
        }
        for r in generate_remediation(misconception_id, count, seed)
    ]


# --------------------------------------------------------------- mapping


def problem_pb(problem_id: str) -> cpb.Problem:
    from problems import problem_from_id

    p = problem_from_id(problem_id)
    fam = p.family
    return cpb.Problem(
        id=p.id,
        family=fam.enum,
        title=p.title,
        given_latex=p.given_latex,
        given_expr=p.given_expr,
        steps=[cpb.StepSpec(index=i, kind=fam.kinds[i], prompt=fam.prompts[i]) for i in sorted(fam.kinds)],
        params=p.params,
    )


def misconception_pb(m) -> cpb.Misconception:
    from diagnose import FAMILIES

    family_key, step = m.places[0]
    return cpb.Misconception(
        id=m.id,
        name=m.name,
        description=m.description,
        family=FAMILIES[family_key].enum,
        step_index=step,
        fix_hint=m.fix_hint,
    )


def diagnosis_pb(r: dict) -> cpb.Diagnosis:
    d = cpb.Diagnosis(
        status=r["status"],
        parse_error=r["parse_error"],
        parse_error_step=r["parse_error_step"],
        elapsed_ms=r["elapsed_ms"],
    )
    if r["status"] == 2:
        d.divergence.CopyFrom(
            cpb.Divergence(
                step_index=r["step_index"],
                misconception_ids=r["misconception_ids"],
                residual_label=r["residual_label"],
                expected_latex=r["expected_latex"],
                student_latex=r["student_latex"],
            )
        )
    return d


def _steps_text(steps) -> list[str]:
    return [st.expr for st in sorted(steps, key=lambda x: x.index)]


_slots: asyncio.Semaphore | None = None


async def run_diagnosis(problem_id: str, steps: list[str]) -> dict:
    """At most WORKERS jobs are handed to the pool at once, so the timeout measures running time,
    not time spent queued behind the rest of a batch. The worker enforces TIMEOUT_S itself; the
    asyncio timeout is only a backstop."""
    assert _slots is not None, "serve() creates the semaphore"
    loop = asyncio.get_running_loop()
    async with _slots:
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(_pool, job_diagnose, problem_id, steps), TIMEOUT_S + 2
            )
        except asyncio.TimeoutError:
            return _timed_out()


def _known_problem(problem_id: str) -> bool:
    from problems import problem_from_id

    try:
        problem_from_id(problem_id)
        return True
    except KeyError:
        return False


# --------------------------------------------------------------- services


class EngineService(rpc.EngineServiceServicer):
    async def ListProblems(self, request, context):
        from problems import DEFAULT_IDS

        return pb.ListProblemsResponse(problems=[problem_pb(pid) for pid in DEFAULT_IDS])

    async def ListMisconceptions(self, request, context):
        from diagnose import CATALOG

        return pb.ListMisconceptionsResponse(misconceptions=[misconception_pb(m) for m in CATALOG.values()])

    async def Diagnose(self, request, context):
        if not _known_problem(request.problem_id):
            await context.abort(grpc.StatusCode.NOT_FOUND, f"unknown problem {request.problem_id!r}")
        r = await run_diagnosis(request.problem_id, _steps_text(request.steps))
        return pb.DiagnoseResponse(diagnosis=diagnosis_pb(r))

    async def DiagnoseBatch(self, request, context):
        subs = list(request.submissions)
        for sub in subs:
            if not _known_problem(sub.problem_id):
                await context.abort(grpc.StatusCode.NOT_FOUND, f"unknown problem {sub.problem_id!r}")
        total = len(subs)

        async def one(sub):
            return sub.id, await run_diagnosis(sub.problem_id, _steps_text(sub.steps))

        done = 0
        for fut in asyncio.as_completed([one(s) for s in subs]):
            sid, r = await fut
            done += 1
            yield pb.DiagnoseBatchResponse(
                done=done,
                total=total,
                results=[pb.SubmissionResult(submission_id=sid, diagnosis=diagnosis_pb(r))],
            )

    async def GenerateRemediation(self, request, context):
        from diagnose import CATALOG

        if request.misconception_id not in CATALOG:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"unknown misconception {request.misconception_id!r}")
        count = request.count or 3
        if not 1 <= count <= 5:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "count must be 1 to 5")
        loop = asyncio.get_running_loop()
        items = await loop.run_in_executor(_pool, job_remediation, request.misconception_id, count, request.seed)
        return pb.GenerateRemediationResponse(
            problems=[
                pb.RemediationProblem(
                    problem=problem_pb(it["problem_id"]),
                    answer_key_latex=it["answer_key_latex"],
                    verification_routes=it["verification_routes"],
                    verified=it["verified"],
                    why_it_discriminates=it["why_it_discriminates"],
                )
                for it in items
            ]
        )

    async def GenerateClass(self, request, context):
        n = request.num_students or 60
        if not 1 <= n <= 200:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "num_students must be 1 to 200")
        for pid in request.problem_ids:
            if not _known_problem(pid):
                await context.abort(grpc.StatusCode.NOT_FOUND, f"unknown problem {pid!r}")
        # Defaults are applied by the gateway (spec section 4); the engine uses the values as sent.
        error_rate, heldout = request.error_rate, request.heldout_share
        if not (0 <= error_rate <= 1 and 0 <= heldout <= 1):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "error_rate and heldout_share must be 0 to 1")
        loop = asyncio.get_running_loop()
        pids, subs = await loop.run_in_executor(
            _pool, job_generate_class, n, request.seed, list(request.problem_ids), error_rate, heldout
        )
        return pb.GenerateClassResponse(
            problems=[problem_pb(pid) for pid in pids],
            submissions=[
                cpb.Submission(
                    id=s["id"],
                    problem_id=s["problem_id"],
                    student_label=s["student_label"],
                    steps=[cpb.Step(index=i, expr=e) for i, e in enumerate(s["steps"], start=1)],
                )
                for s in subs
            ],
            ground_truth=[
                pb.GroundTruth(
                    submission_id=s["id"], true_step_index=s["true_step_index"], true_label=s["true_label"]
                )
                for s in subs
            ],
        )


class InstructorAgentService(rpc.InstructorAgentServiceServicer):
    async def Analyze(self, request, context):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "ANTHROPIC_API_KEY is not set")
        from agent import analyze_events

        async for event in analyze_events(request.class_id, request.instruction):
            yield event


# ------------------------------------------------------------------ main


def _warm():
    from diagnose import diagnose  # noqa: F401 - import SymPy in each worker up front


async def serve(port: int = 50051) -> grpc.aio.Server:
    global _pool, _slots
    _slots = asyncio.Semaphore(WORKERS)  # bound to this server's event loop
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=WORKERS, initializer=_warm)
        # Start every worker now, before gRPC threads exist and before the first request.
        for f in [_pool.submit(_warm) for _ in range(WORKERS)]:
            f.result()
    server = grpc.aio.server()
    rpc.add_EngineServiceServicer_to_server(EngineService(), server)
    rpc.add_InstructorAgentServiceServicer_to_server(InstructorAgentService(), server)
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    log.info("engine listening on :%d", port)
    return server


async def _main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not os.environ.get("WOLFRAM_APP_ID"):
        log.info("WOLFRAM_APP_ID not set; Wolfram cross-check disabled")
    server = await serve(int(os.environ.get("ENGINE_PORT", "50051")))
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(_main())
