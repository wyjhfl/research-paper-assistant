from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text as sql_text

from app.config import settings
from app.database import async_session, init_db
from app.models import Paper

_SENSITIVE_KEYS = {
    "api_key", "authorization", "database_url", "secret", "token",
    "file_path", "postgresql", "asyncpg", "traceback",
}
_SENSITIVE_PATTERNS = [
    "DATABASE_URL", "Authorization", "file_path",
    "postgresql+asyncpg://", "Traceback",
]
_MAX_PREVIEW_LEN = 200

_DEFAULT_CASES_PATH = Path(__file__).resolve().parent.parent / "evals" / "real_model_cases.json"

_VALID_CASE_TYPES = {"single_rag", "multi_rag", "agent", "mcp", "idea"}
_VALID_SEVERITIES = {"blocker", "warning"}


def _get_report_dir() -> Path:
    env_dir = os.environ.get("EVAL_REPORT_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return Path.cwd() / "artifacts" / "evals"


def _get_report_file() -> Path:
    return _get_report_dir() / "real_model_eval_latest.json"


def _get_history_dir() -> Path:
    return _get_report_dir() / "history"


def _get_history_file() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return _get_history_dir() / f"real_model_eval_{ts}.json"


def _get_sensitive_values() -> set[str]:
    return {v for v in [settings.DATABASE_URL, settings.LLM_API_KEY, settings.EMBEDDING_API_KEY] if v}


def _sanitize_value(val: Any) -> Any:
    if isinstance(val, (int, float, bool)):
        return val
    s = str(val) if val is not None else ""
    for secret in _get_sensitive_values():
        if secret and secret in s:
            s = s.replace(secret, "***REDACTED***")
    return s


def _sanitize_dict(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        kl = k.lower()
        if any(sk in kl for sk in _SENSITIVE_KEYS):
            out[k] = "***REDACTED***"
        elif isinstance(v, dict):
            out[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            out[k] = [_sanitize_dict(i) if isinstance(i, dict) else _sanitize_value(i) for i in v]
        else:
            sanitized = _sanitize_value(v)
            sanitized_str = str(sanitized)
            if any(pat in sanitized_str for pat in _SENSITIVE_PATTERNS):
                out[k] = "***REDACTED***"
            else:
                out[k] = sanitized
    return out


def _truncate_preview(text: str | None) -> str:
    if not text:
        return ""
    if isinstance(text, dict):
        text = json.dumps(text, ensure_ascii=False, default=str)
    s = str(text).strip()
    return s[:_MAX_PREVIEW_LEN] + ("..." if len(s) > _MAX_PREVIEW_LEN else "")


def _check_no_sensitive_output(data: Any) -> bool:
    raw = json.dumps(data, default=str)
    for secret in _get_sensitive_values():
        if secret and secret in raw:
            return False
    for sk in _SENSITIVE_KEYS:
        if f'"{sk}"' in raw.lower() or f"'{sk}'" in raw.lower():
            val_start = raw.lower().find(f'"{sk}"')
            if val_start >= 0:
                return False
    for pat in _SENSITIVE_PATTERNS:
        if pat.lower() in raw.lower():
            return False
    return True


def load_eval_cases(path: Path | str | None = None) -> list[dict[str, Any]]:
    if path is None:
        path = _DEFAULT_CASES_PATH
    path = Path(path)
    if not path.exists():
        print(f"  FAIL: eval cases file not found: {path}")
        sys.exit(1)
    try:
        with open(path, encoding="utf-8") as f:
            cases = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  FAIL: eval cases file is not valid JSON: {e}")
        sys.exit(1)
    if not isinstance(cases, list):
        print("  FAIL: eval cases file must contain a JSON array")
        sys.exit(1)
    for i, case in enumerate(cases):
        validate_eval_case_schema(case, index=i)
    return cases


def validate_eval_case_schema(case: dict[str, Any], index: int = 0) -> None:
    if "case_id" not in case:
        print(f"  FAIL: case at index {index} missing 'case_id'")
        sys.exit(1)
    cid = case["case_id"]
    if "type" not in case:
        print(f"  FAIL: case '{cid}' missing 'type'")
        sys.exit(1)
    if case["type"] not in _VALID_CASE_TYPES:
        print(f"  FAIL: case '{cid}' has invalid type '{case['type']}', must be one of {_VALID_CASE_TYPES}")
        sys.exit(1)
    if "severity" not in case:
        print(f"  FAIL: case '{cid}' missing 'severity'")
        sys.exit(1)
    if case["severity"] not in _VALID_SEVERITIES:
        print(f"  FAIL: case '{cid}' has invalid severity '{case['severity']}', must be one of {_VALID_SEVERITIES}")
        sys.exit(1)
    if "input" not in case:
        print(f"  FAIL: case '{cid}' missing 'input'")
        sys.exit(1)
    if "expected" not in case:
        print(f"  FAIL: case '{cid}' missing 'expected'")
        sys.exit(1)


def assert_eval_result(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    checks: dict[str, bool] = {}
    warnings: list[str] = []

    if "error" in result:
        error_msg = result["error"]
        severity = case.get("severity", "blocker")
        case_status = "warning" if severity == "warning" else "failed"
        return {
            "case_id": case["case_id"],
            "type": case["type"],
            "severity": severity,
            "status": case_status,
            "rag_status": None,
            "confidence": 0.0,
            "source_count": 0,
            "paper_count": 0,
            "checks": {"no_error": False},
            "sanitized_preview": _truncate_preview(str(error_msg)),
            "warnings": [f"error: {error_msg}"],
            "duration_ms": result.get("duration_ms", 0),
        }

    rag_status = result.get("rag_status")
    source_count = result.get("source_count", 0)
    paper_count = result.get("paper_count", 0)
    sources = result.get("sources", [])
    source_paper_ids = set(s.get("paper_id") for s in sources if s.get("paper_id") is not None)

    allowed_rag = expected.get("allowed_rag_status")
    if allowed_rag is not None:
        checks["rag_status_allowed"] = rag_status in allowed_rag
        if rag_status not in allowed_rag:
            warnings.append(f"rag_status={rag_status} not in {allowed_rag}")

    expected_status = expected.get("expected_status")
    if expected_status is not None:
        actual_status = result.get("status")
        checks["status_matches"] = actual_status == expected_status
        if actual_status != expected_status:
            warnings.append(f"status={actual_status}, expected={expected_status}")

    min_sources = expected.get("min_sources")
    if min_sources is not None:
        checks["min_sources"] = source_count >= min_sources
        if source_count < min_sources:
            warnings.append(f"sources={source_count} < min_sources={min_sources}")

    min_distinct_papers = expected.get("min_distinct_papers")
    if min_distinct_papers is not None:
        checks["min_distinct_papers"] = paper_count >= min_distinct_papers
        if paper_count < min_distinct_papers:
            warnings.append(f"distinct_papers={paper_count} < min_distinct_papers={min_distinct_papers}")

    forbidden_ids = expected.get("forbidden_source_paper_ids")
    if forbidden_ids == "auto":
        allowed_input_ids = result.get("allowed_paper_ids", set())
        violated = source_paper_ids - allowed_input_ids
        checks["paper_filter_respected"] = len(violated) == 0
        if violated:
            warnings.append(f"sources contain forbidden paper_ids: {violated}")
    elif isinstance(forbidden_ids, list):
        forbidden_set = set(forbidden_ids)
        violated = source_paper_ids & forbidden_set
        checks["paper_filter_respected"] = len(violated) == 0
        if violated:
            warnings.append(f"sources contain forbidden paper_ids: {violated}")

    if expected.get("require_paper_title"):
        has_title = any(s.get("paper_title") for s in sources if s)
        checks["require_paper_title"] = has_title
        if not has_title:
            warnings.append("no source has paper_title")

    if expected.get("require_source_chunk_ids"):
        has_chunk_ids = result.get("has_source_chunk_ids", False)
        checks["require_source_chunk_ids"] = has_chunk_ids
        if not has_chunk_ids:
            warnings.append("missing source_chunk_ids")

    if expected.get("min_candidates") is not None:
        candidate_count = result.get("candidate_count", 0)
        min_cand = expected["min_candidates"]
        checks["min_candidates"] = candidate_count >= min_cand
        if candidate_count < min_cand:
            warnings.append(f"candidates={candidate_count} < min_candidates={min_cand}")

    if expected.get("require_no_sensitive_output"):
        raw_output = result.get("raw_output")
        no_sensitive = _check_no_sensitive_output(raw_output) if raw_output else True
        checks["no_sensitive_output"] = no_sensitive
        if not no_sensitive:
            warnings.append("output contains sensitive information")

    all_checks_pass = all(checks.values())
    severity = case.get("severity", "blocker")

    if all_checks_pass:
        case_status = "passed"
    elif severity == "warning":
        case_status = "warning"
    else:
        case_status = "failed"

    return {
        "case_id": case["case_id"],
        "type": case["type"],
        "severity": severity,
        "status": case_status,
        "rag_status": rag_status,
        "confidence": round(result.get("confidence", 0.0), 4),
        "source_count": source_count,
        "paper_count": paper_count,
        "checks": checks,
        "sanitized_preview": _truncate_preview(result.get("answer_preview", "")),
        "warnings": warnings,
        "duration_ms": result.get("duration_ms", 0),
    }


def aggregate_results(cases: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    total = len(cases)
    passed = sum(1 for c in cases if c["status"] == "passed")
    warned = sum(1 for c in cases if c["status"] == "warning")
    failed = sum(1 for c in cases if c["status"] == "failed")
    blocker_failed = sum(
        1 for c in cases
        if c["status"] == "failed" and c.get("severity") == "blocker"
    )
    failed_details = [
        {"case_id": c["case_id"], "severity": c.get("severity"), "reason": "; ".join(c["warnings"])}
        for c in cases
        if c["status"] == "failed"
    ]
    return {
        "metadata": metadata,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "total": total,
            "passed": passed,
            "warning": warned,
            "failed": failed,
            "blocker_failed": blocker_failed,
        },
        "failed_details": failed_details,
        "can_proceed": blocker_failed == 0,
        "cases": cases,
    }


def _load_previous_history_reports(
    report_dir: Path, limit: int = 5
) -> list[dict[str, Any]]:
    history_dir = report_dir / "history"
    if not history_dir.exists():
        return []
    files = sorted(
        history_dir.glob("real_model_eval_*.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    reports: list[dict[str, Any]] = []
    for f in files:
        if len(reports) >= limit:
            break
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and "timestamp" in data:
                reports.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return reports


def _build_trend_summary(
    current_report: dict[str, Any],
    previous_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    if not previous_reports:
        return {
            "previous_report_count": 0,
            "previous_latest_timestamp": None,
            "passed_delta": 0,
            "warning_delta": 0,
            "failed_delta": 0,
            "case_status_changes": [],
        }

    prev = previous_reports[0]
    cur_totals = current_report.get("totals", {})
    prev_totals = prev.get("totals", prev)
    passed_delta = cur_totals.get("passed", 0) - prev_totals.get("passed", 0)
    warning_delta = cur_totals.get("warning", 0) - prev_totals.get("warning", 0)
    failed_delta = cur_totals.get("failed", 0) - prev_totals.get("failed", 0)

    current_cases = {
        c["case_id"]: c["status"]
        for c in current_report.get("cases", [])
        if "case_id" in c and "status" in c
    }
    prev_cases = {
        c["case_id"]: c["status"]
        for c in prev.get("cases", [])
        if "case_id" in c and "status" in c
    }

    changes: list[dict[str, str]] = []
    for cid, cur_status in current_cases.items():
        prev_status = prev_cases.get(cid)
        if prev_status is not None and prev_status != cur_status:
            changes.append({
                "case_id": cid,
                "previous": prev_status,
                "current": cur_status,
            })

    return {
        "previous_report_count": len(previous_reports),
        "previous_latest_timestamp": prev.get("timestamp"),
        "passed_delta": passed_delta,
        "warning_delta": warning_delta,
        "failed_delta": failed_delta,
        "case_status_changes": changes,
    }


async def _get_demo_papers(session) -> dict[str, Paper]:
    result = await session.execute(
        select(Paper).where(Paper.filename.in_([
            "demo_transformer.pdf",
            "demo_rag.pdf",
            "demo_multi_agent.pdf",
        ]))
    )
    papers = result.scalars().all()
    return {p.filename: p for p in papers}


async def _check_demo_embeddings(session, paper_id: int) -> bool:
    result = await session.execute(
        sql_text(
            "SELECT COUNT(*) FROM paper_chunks "
            "WHERE paper_id = :pid AND embedding IS NOT NULL"
        ).bindparams(pid=paper_id)
    )
    return result.scalar() > 0


async def run_eval_case(
    case: dict[str, Any], papers: dict[str, Paper]
) -> dict[str, Any]:
    case_type = case["type"]
    case_input = case["input"]
    start = time.monotonic()

    try:
        if case_type == "single_rag":
            raw = await _run_single_rag(case_input, papers)
        elif case_type == "multi_rag":
            raw = await _run_multi_rag(case_input, papers)
        elif case_type == "agent":
            raw = await _run_agent(case_input, papers)
        elif case_type == "mcp":
            raw = await _run_mcp(case_input)
        elif case_type == "idea":
            raw = await _run_idea(case_input, papers)
        else:
            raw = {"error": f"unknown case type: {case_type}"}
    except Exception as exc:
        raw = {"error": f"internal_error: {type(exc).__name__}: {_sanitize_value(str(exc))}"}

    elapsed_ms = int((time.monotonic() - start) * 1000)
    raw["duration_ms"] = elapsed_ms
    return assert_eval_result(case, raw)


async def _run_single_rag(case_input: dict, papers: dict[str, Paper]) -> dict[str, Any]:
    from app.services.rag_service import RAGService

    paper_filename = case_input.get("paper_filename", "demo_transformer.pdf")
    question = case_input.get("question", "")
    paper = papers.get(paper_filename)
    if paper is None:
        return {"error": f"{paper_filename} not found"}

    async with async_session() as session:
        rag = RAGService(session)
        result = await rag.ask(paper.id, question)

    sources_data = []
    for s in result.sources:
        src = {
            "chunk_id": s.chunk_id,
            "page_start": s.page_start,
            "text_excerpt": s.text_excerpt,
            "paper_id": paper.id,
            "paper_title": paper.title,
        }
        sources_data.append(src)

    return {
        "status": result.status,
        "rag_status": result.status,
        "confidence": result.confidence,
        "source_count": len(result.sources),
        "paper_count": 1,
        "sources": sources_data,
        "answer_preview": result.answer,
        "raw_output": {"answer": result.answer, "status": result.status},
    }


async def _run_multi_rag(case_input: dict, papers: dict[str, Paper]) -> dict[str, Any]:
    from app.services.multi_paper_rag_service import MultiPaperRAGService

    question = case_input.get("question", "")
    top_k = case_input.get("top_k", 5)
    paper_filename = case_input.get("paper_filename")
    paper_ids = None
    allowed_paper_ids: set[int] = set()

    if paper_filename:
        paper = papers.get(paper_filename)
        if paper is None:
            return {"error": f"{paper_filename} not found"}
        paper_ids = [paper.id]
        allowed_paper_ids = {paper.id}

    async with async_session() as session:
        rag = MultiPaperRAGService(session)
        result = await rag.ask(
            question=question,
            paper_ids=paper_ids,
            top_k=top_k,
        )

    source_paper_ids = set(s.paper_id for s in result.sources)
    return {
        "status": result.status,
        "rag_status": result.status,
        "confidence": result.confidence,
        "source_count": len(result.sources),
        "paper_count": len(source_paper_ids),
        "sources": [
            {"paper_id": s.paper_id, "paper_title": getattr(s, "paper_title", None), "page_start": s.page_start, "text_excerpt": s.text_excerpt}
            for s in result.sources
        ],
        "answer_preview": result.answer,
        "raw_output": {"answer": result.answer, "status": result.status},
        "allowed_paper_ids": allowed_paper_ids,
    }


async def _run_agent(case_input: dict, papers: dict[str, Paper]) -> dict[str, Any]:
    from app.services.agent_run_service import AgentRunService

    task_type = case_input.get("task_type", "recommend_citations_multi")
    question = case_input.get("question", "")
    paper_filename = case_input.get("paper_filename")
    paper_ids = [p.id for p in papers.values()]
    paper_id = None

    if paper_filename:
        paper = papers.get(paper_filename)
        if paper is None:
            return {"error": f"{paper_filename} not found"}
        paper_id = paper.id
        paper_ids = [paper.id]

    async with async_session() as session:
        service = AgentRunService(session)
        result = await service.run_agent(
            task_type=task_type,
            paper_id=paper_id,
            paper_ids=paper_ids,
            question=question,
        )

    output = result.get("output", {})
    rag_status = output.get("rag_status")
    sources = output.get("sources", [])
    summary = output.get("summary", "")
    retrieved_chunks = output.get("retrieved_chunks", [])

    has_source_chunk_ids = False
    if task_type == "summarize_paper":
        has_source_chunk_ids = len(retrieved_chunks) > 0
    elif "ideas" in output:
        ideas = output.get("ideas", [])
        has_source_chunk_ids = any(
            bool(getattr(idea, "source_chunk_ids", []) if hasattr(idea, "source_chunk_ids") else idea.get("source_chunk_ids", []) if isinstance(idea, dict) else [])
            for idea in ideas
        )

    answer_preview = output.get("answer", summary)
    if isinstance(answer_preview, dict):
        answer_preview = json.dumps(answer_preview, ensure_ascii=False, default=str)
    if not isinstance(answer_preview, str):
        answer_preview = str(answer_preview) if answer_preview else ""

    return {
        "status": result.get("status"),
        "rag_status": rag_status,
        "confidence": result.get("confidence", 0.0),
        "source_count": len(sources),
        "paper_count": len(set(s.get("paper_id") for s in sources if s.get("paper_id"))) if sources else 0,
        "sources": sources,
        "answer_preview": answer_preview,
        "raw_output": output,
        "has_source_chunk_ids": has_source_chunk_ids,
    }


async def _run_mcp(case_input: dict) -> dict[str, Any]:
    tool_name = case_input.get("tool", "search_paper_chunks")
    query = case_input.get("query", "")
    limit = case_input.get("limit", 10)

    if tool_name == "search_paper_chunks":
        from app.mcp.tools import tool_search_paper_chunks
        result = await tool_search_paper_chunks(query=query, limit=limit)
        results = result.get("results", [])
        return {
            "source_count": len(results),
            "paper_count": len(set(r.get("paper_id") for r in results if r.get("paper_id"))),
            "sources": results,
            "answer_preview": "",
            "raw_output": result,
        }
    elif tool_name == "recommend_citations":
        from app.mcp.tools import tool_recommend_citations
        draft_text = case_input.get("draft_text", "")
        paper_id = case_input.get("paper_id")
        paper_ids = case_input.get("paper_ids")
        result = await tool_recommend_citations(
            draft_text=draft_text,
            paper_id=paper_id,
            paper_ids=paper_ids,
            limit=limit,
        )
        sources = result.get("sources", [])
        return {
            "rag_status": result.get("rag_status"),
            "confidence": result.get("confidence", 0.0),
            "source_count": len(sources),
            "paper_count": len(set(s.get("paper_id") for s in sources if s.get("paper_id"))),
            "sources": sources,
            "answer_preview": result.get("answer", ""),
            "raw_output": result,
        }
    else:
        return {"error": f"unknown MCP tool: {tool_name}"}


async def _run_idea(case_input: dict, papers: dict[str, Paper]) -> dict[str, Any]:
    from app.services.idea_service import IdeaService

    paper_filename = case_input.get("paper_filename", "demo_transformer.pdf")
    paper = papers.get(paper_filename)
    if paper is None:
        return {"error": f"{paper_filename} not found"}

    async with async_session() as session:
        service = IdeaService(session)
        candidates = await service.extract_ideas(paper.id)

    has_source_chunk_ids = any(
        bool(c.source_chunk_ids) for c in candidates
    )

    return {
        "candidate_count": len(candidates),
        "has_source_chunk_ids": has_source_chunk_ids,
        "source_count": 0,
        "paper_count": 1,
        "sources": [],
        "answer_preview": "",
        "raw_output": {
            "candidate_count": len(candidates),
            "has_source_chunk_ids": has_source_chunk_ids,
        },
    }


def _write_report(report: dict[str, Any]) -> tuple[Path, Path]:
    report_dir = _get_report_dir()
    report_file = _get_report_file()
    history_file = _get_history_file()

    report_dir.mkdir(parents=True, exist_ok=True)
    history_file.parent.mkdir(parents=True, exist_ok=True)

    sanitized = _sanitize_dict(report)

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(sanitized, f, ensure_ascii=False, indent=2, default=str)

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(sanitized, f, ensure_ascii=False, indent=2, default=str)

    return report_file, history_file


async def run_eval() -> int:
    print("=" * 60)
    print("Real Model Evaluation")
    print("=" * 60)

    print("\n--- Pre-flight Checks ---")

    if not settings.REAL_MODEL_REQUIRED:
        print("  FAIL: REAL_MODEL_REQUIRED is not true. This script requires real model providers.")
        print("  ACTION: Set REAL_MODEL_REQUIRED=true in .env")
        return 1

    if settings.LLM_PROVIDER != "openai_compatible":
        print("  FAIL: LLM_PROVIDER is not openai_compatible")
        return 1

    if settings.EMBEDDING_PROVIDER != "openai_compatible":
        print("  FAIL: EMBEDDING_PROVIDER is not openai_compatible")
        return 1

    print("  PASS: REAL_MODEL_REQUIRED=true")
    print("  PASS: LLM_PROVIDER=openai_compatible")
    print("  PASS: EMBEDDING_PROVIDER=openai_compatible")

    cases_path = _DEFAULT_CASES_PATH
    print(f"\n--- Loading Eval Cases ---")
    print(f"  Case file: {cases_path}")
    eval_cases = load_eval_cases(cases_path)
    print(f"  Loaded {len(eval_cases)} cases")

    await init_db()

    async with async_session() as session:
        dim_result = await session.execute(sql_text(
            "SELECT a.atttypmod FROM pg_attribute a "
            "JOIN pg_class c ON a.attrelid = c.oid "
            "JOIN pg_namespace n ON c.relnamespace = n.oid "
            "WHERE c.relname='paper_chunks' AND a.attname='embedding' AND n.nspname='public'"
        ))
        dim_row = dim_result.fetchone()
        if dim_row is not None:
            db_dim = dim_row[0]
            if db_dim != settings.EMBEDDING_DIMENSION:
                print(f"  FAIL: DB vector dimension ({db_dim}) != EMBEDDING_DIMENSION ({settings.EMBEDDING_DIMENSION})")
                return 1
            print(f"  PASS: DB vector dimension matches EMBEDDING_DIMENSION ({db_dim})")

        papers = await _get_demo_papers(session)
        if len(papers) < 3:
            print(f"  FAIL: Found {len(papers)}/3 demo papers. Run seed_demo.py first.")
            return 1
        print(f"  PASS: Demo papers found ({len(papers)})")

        for fname, paper in papers.items():
            has_emb = await _check_demo_embeddings(session, paper.id)
            if not has_emb:
                print(f"  FAIL: {fname} has no embeddings. Run rebuild_demo_embeddings.py first.")
                return 1
        print("  PASS: All demo papers have embeddings")

    print("\n--- Running Evaluation Cases ---")
    case_results: list[dict[str, Any]] = []

    for case in eval_cases:
        cid = case["case_id"]
        print(f"\n  [{cid}] running...")
        result = await run_eval_case(case, papers)
        case_results.append(result)
        status_icon = {"passed": "PASS", "warning": "WARN", "failed": "FAIL"}.get(result["status"], "?")
        print(f"  [{cid}] {status_icon}: status={result['status']}, rag_status={result.get('rag_status')}, sources={result['source_count']}, duration={result['duration_ms']}ms")

    metadata = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_model": settings.LLM_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
        "case_file": str(cases_path),
    }

    report = aggregate_results(case_results, metadata)

    report_dir = _get_report_dir()
    previous_reports = _load_previous_history_reports(report_dir, limit=5)
    trend = _build_trend_summary(report, previous_reports)
    report["trend"] = trend

    latest_path, history_path = _write_report(report)

    totals = report["totals"]
    print("\n" + "=" * 60)
    print("Evaluation Summary")
    print("=" * 60)
    print(f"  Total:          {totals['total']}")
    print(f"  Passed:         {totals['passed']}")
    print(f"  Warning:        {totals['warning']}")
    print(f"  Failed:         {totals['failed']}")
    print(f"  Blocker Failed: {totals['blocker_failed']}")
    if report["failed_details"]:
        print("\n  Failed cases:")
        for fd in report["failed_details"]:
            print(f"    - {fd['case_id']} [{fd.get('severity', '?')}]: {fd['reason']}")
    print(f"\n  Latest:  {latest_path}")
    print(f"  History: {history_path}")
    if trend["previous_report_count"] > 0:
        print(f"  Trend:   vs {trend['previous_report_count']} previous report(s)")
        if trend["case_status_changes"]:
            print("  Status changes:")
            for ch in trend["case_status_changes"]:
                print(f"    - {ch['case_id']}: {ch['previous']} -> {ch['current']}")
    else:
        print("  Trend:   first run (no previous history)")
    print(f"\n  Can proceed to next phase: {'YES' if report['can_proceed'] else 'NO'}")
    print("=" * 60)

    return 0 if report["can_proceed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_eval()))
