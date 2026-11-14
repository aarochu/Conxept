"""Deep Agent behind "Analyze class" (spec section 6.3).

The agent writes the instructor brief; it never decides correctness. Every
number comes from a tool that reads the database (read-only role) or calls the
engine, and a number check rejects any brief containing an integer that no tool
returned. The engine never writes to the database: it streams the brief with a
fresh id and the gateway stores it.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Protocol

from diagnose import CATALOG, FAMILIES

SYSTEM_PROMPT = (
    "You are an assistant for a signals-and-systems instructor. Use only numbers returned by tools; "
    "never compute or estimate a count yourself. Name a cluster only if it has in_catalog true. "
    "Describe unclassified clusters as Other and do not guess their cause. For the top three "
    "misconceptions by count, call generate_remediation and include only problems with verified true. "
    "Write a brief in Markdown with: one-sentence overview, a table of the top misconceptions with "
    "counts, and the practice problems."
)

DEFAULT_MODEL = "anthropic:claude-sonnet-5-5"
SUMMARY_CHARS = 60
_FAMILY_BY_ENUM = {f.enum: f for f in FAMILIES.values()}

# ------------------------------------------------------------------ data


class ClassData(Protocol):
    def heatmap(self, class_id: str) -> list[dict]: ...
    def clusters(self, class_id: str) -> list[dict]: ...
    def examples(self, class_id: str, key: str, limit: int = 3) -> list[dict]: ...


def cluster_name(key: str) -> str:
    if key in CATALOG:
        return CATALOG[key].name
    if key.startswith("unclassified:"):
        return "Other"
    return key


def _load_queries() -> dict[str, str]:
    """Read named queries from sql/queries.sql, converted to psycopg placeholders."""
    text = (Path(__file__).resolve().parent.parent / "sql" / "queries.sql").read_text()
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"--\s*(Q_\w+)", line)
        if m:
            if name:
                out[name] = "\n".join(buf)
            name, buf = m.group(1), []
        elif name:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf)
    # psycopg treats % as a placeholder marker, so literal % must be doubled.
    return {k: v.replace("%", "%%").replace("$1", "%(class_id)s").strip().rstrip(";") for k, v in out.items()}


_CLUSTER_KEY_SQL = """
CASE WHEN cardinality(d.misconception_ids) > 0 THEN d.misconception_ids[1]
     WHEN d.residual_label = 'unclassified' THEN 'unclassified:' || p.family || ':' || d.divergence_step
     ELSE d.residual_label END
"""

_EXAMPLES_SQL = f"""
SELECT sub.id::text, sub.problem_id, sub.student_label, sub.steps, d.divergence_step,
       d.expected_latex, d.student_latex
FROM diagnoses d
JOIN submissions sub ON sub.id = d.submission_id
JOIN problems p ON p.id = sub.problem_id
WHERE sub.class_id = %(class_id)s AND d.status = 2 AND ({_CLUSTER_KEY_SQL}) = %(key)s
ORDER BY sub.id
LIMIT %(limit)s
"""


class PostgresClassData:
    """Read-only access using DATABASE_URL (the engine's read-only role)."""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ.get(
            "DATABASE_URL", "postgres://postgres:postgres@localhost:5432/misconception"
        )
        self.q = _load_queries()

    def _rows(self, sql: str, params: dict) -> list[tuple]:
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def heatmap(self, class_id):
        return [
            {"problem": r[0], "step": r[1], "failed": r[2], "attempted": r[3]}
            for r in self._rows(self.q["Q_HEATMAP"], {"class_id": class_id})
        ]

    def clusters(self, class_id):
        out = []
        for key, n, family, step, _examples in self._rows(self.q["Q_CLUSTERS"], {"class_id": class_id}):
            fam = _FAMILY_BY_ENUM.get(family)
            out.append(
                {
                    "key": key,
                    "name": cluster_name(key),
                    "count": n,
                    "step": step,
                    "family": fam.name if fam else str(family),
                    "in_catalog": key in CATALOG,
                }
            )
        return out

    def examples(self, class_id, key, limit=3):
        rows = self._rows(_EXAMPLES_SQL, {"class_id": class_id, "key": key, "limit": limit})
        return [
            {
                "submission_id": r[0],
                "problem": r[1],
                "student": r[2],
                "steps": r[3],
                "divergence_step": r[4],
                "expected": r[5],
                "student_step": r[6],
            }
            for r in rows
        ]


# ----------------------------------------------------------------- tools


def make_tools(data: ClassData):
    def get_heatmap(class_id: str) -> str:
        """Per (problem, step): how many submissions first went wrong there (failed) out of those that reached it (attempted)."""
        return json.dumps(data.heatmap(class_id))

    def get_clusters(class_id: str) -> str:
        """Error clusters for the class, sorted by count. Only clusters with in_catalog true may be named."""
        return json.dumps(data.clusters(class_id))

    def get_examples(class_id: str, key: str) -> str:
        """Up to 3 example submissions for one cluster key, with the student's steps and the expected value."""
        return json.dumps(data.examples(class_id, key, 3))

    def generate_remediation(misconception_id: str, count: int = 3) -> str:
        """Verified practice problems for a catalog misconception. Only include problems with verified true."""
        from remediation import generate_remediation as gen

        count = max(1, min(5, int(count)))
        try:
            items = gen(misconception_id, count, seed=0)
        except KeyError:
            return json.dumps({"error": f"{misconception_id} is not a catalog misconception"})
        return json.dumps(
            [
                {
                    "problem_id": r.problem.id,
                    "title": r.problem.title,
                    "given": r.problem.given_latex,
                    "answer_key": r.answer_key_latex,
                    "verified": r.verified,
                    "verification_routes": r.verification_routes,
                }
                for r in items
            ]
        )

    return [get_heatmap, get_clusters, get_examples, generate_remediation]


# ---------------------------------------------------------- number check

_INT = re.compile(r"\d+")


def unverified_numbers(brief: str, tool_outputs: list[str]) -> set[int]:
    """Integers in the brief that appear in no tool result of this run (1 to 3 allowed as ordinals)."""
    seen = {int(n) for out in tool_outputs for n in _INT.findall(out)}
    return {int(n) for n in _INT.findall(brief) if int(n) not in seen and not 1 <= int(n) <= 3}


# ----------------------------------------------------------------- stream


def _text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts)


async def analyze_events(class_id: str, instruction: str = "", model=None, data: ClassData | None = None):
    """Run the agent and yield AnalyzeResponse messages."""
    from deepagents import create_deep_agent
    from misconception.v1 import engine_pb2 as pb

    agent = create_deep_agent(
        model=model or os.environ.get("AGENT_MODEL", DEFAULT_MODEL),
        tools=make_tools(data or PostgresClassData()),
        system_prompt=SYSTEM_PROMPT,
    )
    prompt = f"Analyze class {class_id} and write the instructor brief."
    if instruction:
        prompt += f"\nInstructor's extra instruction: {instruction}"

    tool_outputs: list[str] = []
    brief = None
    try:
        async for update in agent.astream({"messages": [{"role": "user", "content": prompt}]}, stream_mode="updates"):
            for node in (update or {}).values():
                for msg in (node or {}).get("messages", []) if isinstance(node, dict) else []:
                    mtype = getattr(msg, "type", "")
                    if mtype == "ai" and getattr(msg, "tool_calls", None):
                        for call in msg.tool_calls:
                            yield pb.AnalyzeResponse(
                                tool_call=pb.ToolCallEvent(
                                    name=call["name"], arguments_text=json.dumps(call.get("args", {}))
                                )
                            )
                    elif mtype == "tool":
                        content = _text(msg.content)
                        tool_outputs.append(content)
                        yield pb.AnalyzeResponse(
                            tool_result=pb.ToolResultEvent(name=msg.name or "", summary=content[:SUMMARY_CHARS])
                        )
                    elif mtype == "ai":
                        text = _text(msg.content)
                        if text.strip():
                            brief = text
    except Exception as e:  # model or tool failure is reported to the instructor, not raised
        yield pb.AnalyzeResponse(error=f"agent failed: {type(e).__name__}: {e}")
        return

    if brief is None:
        yield pb.AnalyzeResponse(error="agent produced no brief")
        return
    if unverified_numbers(brief, tool_outputs):
        yield pb.AnalyzeResponse(error="brief contained an unverified number")
        return
    yield pb.AnalyzeResponse(brief=pb.BriefEvent(brief_id=str(uuid.uuid4()), markdown=brief))
