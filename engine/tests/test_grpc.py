"""Python gRPC gate: unary and streaming calls against a real grpc.aio server."""

import os

import grpc
import pytest

import server
from misconception.v1 import common_pb2 as cpb
from misconception.v1 import engine_pb2 as pb
from misconception.v1 import engine_pb2_grpc as rpc

PORT = 50951


@pytest.fixture
async def stub():
    srv = await server.serve(PORT)
    async with grpc.aio.insecure_channel(f"localhost:{PORT}") as ch:
        yield rpc.EngineServiceStub(ch), rpc.InstructorAgentServiceStub(ch)
    await srv.stop(None)


def _steps(*exprs):
    return [cpb.Step(index=i, expr=e) for i, e in enumerate(exprs, start=1)]


async def test_diagnose_valid_diverged_parse_error(stub):
    engine, _ = stub
    ok = await engine.Diagnose(pb.DiagnoseRequest(problem_id="f1-p1-q2-n0", steps=_steps("2/(s+2) - 1/(s+1)", "(2*exp(-2*t) - exp(-t))*u(t)")))
    assert ok.diagnosis.status == cpb.DIAGNOSIS_STATUS_VALID
    bad = await engine.Diagnose(pb.DiagnoseRequest(problem_id="f1-p1-q2-n0", steps=_steps("2/(s+2) - 1/(s+1)", "2*exp(-2*t) - exp(-t)")))
    assert bad.diagnosis.status == cpb.DIAGNOSIS_STATUS_DIVERGED
    assert bad.diagnosis.divergence.step_index == 2
    assert list(bad.diagnosis.divergence.misconception_ids) == ["forgot_causality_u_of_t"]
    assert bad.diagnosis.divergence.expected_latex
    hostile = await engine.Diagnose(pb.DiagnoseRequest(problem_id="f1-p1-q2-n0", steps=_steps("__import__('os')")))
    assert hostile.diagnosis.status == cpb.DIAGNOSIS_STATUS_PARSE_ERROR
    assert hostile.diagnosis.parse_error_step == 1


async def test_unknown_problem_not_found(stub):
    engine, _ = stub
    with pytest.raises(grpc.aio.AioRpcError) as e:
        await engine.Diagnose(pb.DiagnoseRequest(problem_id="f9-x", steps=_steps("1")))
    assert e.value.code() == grpc.StatusCode.NOT_FOUND


async def test_batch_streams_one_message_per_submission(stub):
    engine, _ = stub
    subs = [
        cpb.Submission(id=f"sub{i}", problem_id="f3-a1", student_label=f"S{i:03d}",
                       steps=_steps("int(exp(-t)*exp(-j*w*t),t,0,inf)", "1/(1+j*w)" if i % 2 else "2/(1+j*w)"))
        for i in range(6)
    ]
    msgs = [m async for m in engine.DiagnoseBatch(pb.DiagnoseBatchRequest(submissions=subs))]
    assert len(msgs) == 6
    assert [m.done for m in msgs] == [1, 2, 3, 4, 5, 6] and all(m.total == 6 for m in msgs)
    assert sorted(r.submission_id for m in msgs for r in m.results) == sorted(s.id for s in subs)


async def test_lists_and_generate(stub):
    engine, _ = stub
    probs = await engine.ListProblems(pb.ListProblemsRequest())
    assert len(probs.problems) == 8 and probs.problems[0].steps[0].index == 1
    mis = await engine.ListMisconceptions(pb.ListMisconceptionsRequest())
    assert len(mis.misconceptions) == 14
    cls = await engine.GenerateClass(pb.GenerateClassRequest(num_students=2, seed=7, error_rate=0.6, heldout_share=0.25))
    assert len(cls.submissions) == 16 and len(cls.ground_truth) == 16
    rem = await engine.GenerateRemediation(pb.GenerateRemediationRequest(misconception_id="forgot_to_flip_h", count=2, seed=3))
    assert len(rem.problems) == 2 and all(p.verified for p in rem.problems)


async def test_generate_rejects_bad_count(stub):
    engine, _ = stub
    with pytest.raises(grpc.aio.AioRpcError) as e:
        await engine.GenerateClass(pb.GenerateClassRequest(num_students=500))
    assert e.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_analyze_without_key_is_failed_precondition(stub, monkeypatch):
    _, agent = stub
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(grpc.aio.AioRpcError) as e:
        async for _ in agent.Analyze(pb.AnalyzeRequest(class_id="x")):
            pass
    assert e.value.code() == grpc.StatusCode.FAILED_PRECONDITION


async def test_slow_step_times_out_and_frees_worker(stub, monkeypatch):
    engine, _ = stub
    monkeypatch.setattr(server, "TIMEOUT_S", 1.0)  # applies to the asyncio backstop in this process
    slow = _steps("int(exp(-t)*exp(-j*w*t)*sin(t^60)*cos(t^61), t, 0, inf)")
    # The worker's own timer uses the module default; the call must still return, not hang the pool.
    r = await engine.Diagnose(pb.DiagnoseRequest(problem_id="f3-a1", steps=slow))
    assert r.diagnosis.status in (cpb.DIAGNOSIS_STATUS_PARSE_ERROR, cpb.DIAGNOSIS_STATUS_DIVERGED)
    ok = await engine.Diagnose(pb.DiagnoseRequest(problem_id="f3-a1", steps=_steps("int(exp(-t)*exp(-j*w*t),t,0,inf)", "1/(1+j*w)")))
    assert ok.diagnosis.status == cpb.DIAGNOSIS_STATUS_VALID


def test_worker_timer_interrupts_a_busy_job(monkeypatch):
    import time

    import diagnose as d

    def busy(*a, **k):
        while True:
            sum(range(1000))

    monkeypatch.setattr(d, "diagnose", busy)
    monkeypatch.setattr(server, "TIMEOUT_S", 0.3)
    start = time.perf_counter()
    r = server.job_diagnose("f3-a1", ["1/(1+j*w)"])
    assert r["status"] == 3 and r["parse_error"] == "timed out"
    assert time.perf_counter() - start < 2
