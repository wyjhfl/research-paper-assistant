from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


DEFAULT_API_BASE = "http://localhost:8091"
DEFAULT_QUESTION = "What method or contribution does this paper propose?"
SMOKE_NOTE_TITLE = "Personal workflow smoke note"
SMOKE_NOTE_TAG = "local-workflow-smoke"


@dataclass
class Check:
    name: str
    ok: bool
    message: str


def _request_json(
    api_base: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    user_id: str = "default",
    timeout: int = 30,
) -> tuple[bool, dict[str, Any]]:
    data = None
    headers = {
        "Accept": "application/json",
        "X-User-Id": user_id,
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{api_base}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return 200 <= resp.status < 300, payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, {"error": type(exc).__name__}


def _select_paper(papers: list[dict[str, Any]]) -> dict[str, Any] | None:
    completed = [
        paper for paper in papers
        if paper.get("status") == "completed" and int(paper.get("chunk_count") or 0) > 0
    ]
    if not completed:
        return None
    return sorted(
        completed,
        key=lambda paper: (-int(paper.get("chunk_count") or 0), int(paper.get("id") or 0)),
    )[0]


def _source_count(payload: dict[str, Any]) -> int:
    sources = payload.get("sources")
    return len(sources) if isinstance(sources, list) else 0


def _note_markdown(title: str, content: str, tags: list[str]) -> str:
    tag_line = ", ".join(tags)
    return f"# {title}\n\n{content}\n\nTags: {tag_line}\n"


def _find_existing_smoke_note(notes_payload: dict[str, Any]) -> int | None:
    notes = notes_payload.get("notes")
    if not isinstance(notes, list):
        return None
    for note in notes:
        if not isinstance(note, dict):
            continue
        tags = note.get("tags")
        if note.get("title") == SMOKE_NOTE_TITLE and isinstance(tags, list) and SMOKE_NOTE_TAG in tags:
            note_id = note.get("id")
            return int(note_id) if isinstance(note_id, int) else None
    return None


def run_smoke(api_base: str, user_id: str, write_note: bool) -> dict[str, Any]:
    checks: list[Check] = []
    selected_paper_id: int | None = None

    ok, ready = _request_json(api_base, "GET", "/health/ready", user_id=user_id, timeout=20)
    ready_ok = ok and ready.get("ready") is True
    checks.append(Check("readiness", ready_ok, "ready=true" if ready_ok else "not ready"))

    ok, papers_payload = _request_json(api_base, "GET", "/papers", user_id=user_id, timeout=30)
    papers = papers_payload.get("papers") if ok else None
    papers = papers if isinstance(papers, list) else []
    selected = _select_paper(papers)
    papers_ok = selected is not None
    if selected:
        selected_paper_id = int(selected["id"])
    checks.append(
        Check(
            "papers available",
            papers_ok,
            f"completed={sum(1 for p in papers if p.get('status') == 'completed')}; selected_paper_id={selected_paper_id}",
        )
    )

    qa_ok = False
    qa_status = "skipped"
    qa_confidence = 0.0
    qa_sources = 0
    if selected_paper_id is not None:
        ok, qa_payload = _request_json(
            api_base,
            "POST",
            f"/papers/{selected_paper_id}/ask",
            {
                "question": DEFAULT_QUESTION,
                "allow_low_confidence_answer": True,
            },
            user_id=user_id,
            timeout=120,
        )
        qa_status = str(qa_payload.get("status", "unknown")) if ok else "request_failed"
        qa_confidence = float(qa_payload.get("confidence") or 0.0) if ok else 0.0
        qa_sources = _source_count(qa_payload) if ok else 0
        qa_ok = ok and qa_status in {"answered", "low_confidence_answer"} and qa_sources > 0
    checks.append(
        Check(
            "single paper qa",
            qa_ok,
            f"status={qa_status}; confidence={qa_confidence:.4f}; sources={qa_sources}",
        )
    )

    review_ok = False
    review_rows = 0
    if selected_paper_id is not None:
        ok, review_payload = _request_json(
            api_base,
            "POST",
            "/papers/review-matrix",
            {"paper_ids": [selected_paper_id], "max_chunks_per_paper": 5},
            user_id=user_id,
            timeout=60,
        )
        rows = review_payload.get("rows") if ok else None
        review_rows = len(rows) if isinstance(rows, list) else 0
        review_ok = ok and review_rows > 0
    checks.append(Check("review matrix", review_ok, f"rows={review_rows}"))

    if write_note:
        ok, existing_notes = _request_json(api_base, "GET", "/notes", user_id=user_id, timeout=30)
        existing_note_id = _find_existing_smoke_note(existing_notes) if ok else None
        if existing_note_id is not None:
            checks.append(Check("research note save", True, f"existing_note_id={existing_note_id}; markdown=rendered"))
            return {
                "ok": all(check.ok for check in checks),
                "selected_paper_id": selected_paper_id,
                "checks": [asdict(check) for check in checks],
            }

        title = SMOKE_NOTE_TITLE
        content = (
            "Local workflow smoke verified paper selection, single-paper QA, "
            "review matrix generation, and research note save."
        )
        tags = [SMOKE_NOTE_TAG]
        ok, note_payload = _request_json(
            api_base,
            "POST",
            "/notes",
            {
                "title": title,
                "content": content,
                "note_type": "manual",
                "tags": tags,
            },
            user_id=user_id,
            timeout=30,
        )
        note = note_payload.get("note") if ok else None
        note_id = note.get("id") if isinstance(note, dict) else None
        markdown = _note_markdown(title, content, tags)
        note_ok = ok and note_id is not None and markdown.startswith("# Personal workflow smoke note")
        checks.append(Check("research note save", note_ok, f"note_id={note_id}; markdown=rendered" if note_ok else "failed"))

        ok, notes_payload = _request_json(api_base, "GET", "/notes", user_id=user_id, timeout=30)
        total = notes_payload.get("total") if ok else None
        list_ok = ok and isinstance(total, int) and total >= 1
        checks.append(Check("research note list", list_ok, f"total={total}" if list_ok else "failed"))
    else:
        checks.append(Check("research note save", True, "skipped; pass --write-note to create a local smoke note"))

    return {
        "ok": all(check.ok for check in checks),
        "selected_paper_id": selected_paper_id,
        "checks": [asdict(check) for check in checks],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Personal local end-to-end workflow smoke check.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="Backend API base URL.")
    parser.add_argument("--user-id", default="default", help="Local user id header for dev-mode user isolation.")
    parser.add_argument("--write-note", action="store_true", help="Create one local research note to verify note save.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_smoke(args.api_base.rstrip("/"), args.user_id, args.write_note)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
