from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ResearchNote
from ..repositories.note_repo import ResearchNoteRepository
from ..repositories.paper_repo import PaperRepository


_ALLOWED_SOURCE_KEYS = {
    "paper_id",
    "paper_title",
    "chunk_id",
    "chunk_index",
    "page_start",
    "page_end",
    "score",
    "source_kind",
    "retrieval_mode",
    "matched_fields",
}


def _safe_json(value: Any) -> str:
    if value is None:
        return "{}"
    if hasattr(value, "model_dump"):
        raw = value.model_dump(exclude_none=True)
    elif isinstance(value, dict):
        raw = value
    else:
        raw = {}
    safe = {k: v for k, v in raw.items() if k in _ALLOWED_SOURCE_KEYS}
    return json.dumps(safe, ensure_ascii=False)


def _parse_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_tags(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str)]


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in tags:
        tag = item.strip()
        if not tag or tag in seen:
            continue
        cleaned.append(tag[:40])
        seen.add(tag)
    return cleaned[:20]


class InvalidNoteReferenceError(ValueError):
    pass


class ResearchNoteService:
    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id
        self.repo = ResearchNoteRepository(session)
        self.paper_repo = PaperRepository(session)

    async def _validate_refs(self, paper_id: int | None, chunk_id: int | None) -> None:
        if paper_id is None and chunk_id is None:
            return
        if paper_id is not None:
            paper = await self.paper_repo.get_paper(paper_id, user_id=self.user_id)
            if paper is None:
                raise InvalidNoteReferenceError("paper not found")
        if chunk_id is not None:
            if paper_id is None:
                raise InvalidNoteReferenceError("chunk reference requires paper_id")
            chunks = await self.paper_repo.get_chunks_by_paper(paper_id, user_id=self.user_id)
            if not any(chunk.id == chunk_id for chunk in chunks):
                raise InvalidNoteReferenceError("chunk not found under this paper")

    async def create_note(
        self,
        *,
        title: str,
        content: str,
        note_type: str,
        paper_id: int | None,
        chunk_id: int | None,
        source: Any,
        tags: list[str],
    ) -> ResearchNote:
        await self._validate_refs(paper_id, chunk_id)
        note = ResearchNote(
            user_id=self.user_id,
            title=title,
            content=content,
            note_type=note_type,
            paper_id=paper_id,
            chunk_id=chunk_id,
            source_json=_safe_json(source),
            tags=json.dumps(_clean_tags(tags), ensure_ascii=False),
        )
        return await self.repo.create_note(note)

    async def list_notes(self, limit: int = 100) -> list[ResearchNote]:
        return await self.repo.list_notes(user_id=self.user_id, limit=limit)

    async def get_note(self, note_id: int) -> ResearchNote | None:
        return await self.repo.get_note(note_id, user_id=self.user_id)

    async def update_note(
        self,
        note_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
    ) -> ResearchNote | None:
        note = await self.repo.get_note(note_id, user_id=self.user_id)
        if note is None:
            return None
        if title is not None:
            note.title = title
        if content is not None:
            note.content = content
        if tags is not None:
            note.tags = json.dumps(tags, ensure_ascii=False)
        await self.session.flush()
        await self.session.refresh(note)
        return note

    async def delete_note(self, note_id: int) -> bool:
        return await self.repo.delete_note(note_id, user_id=self.user_id)

    async def to_item(self, note: ResearchNote) -> dict[str, Any]:
        paper_title = None
        if note.paper_id is not None:
            paper = await self.paper_repo.get_paper(note.paper_id, user_id=self.user_id)
            paper_title = paper.title if paper else None
        return {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "note_type": note.note_type,
            "paper_id": note.paper_id,
            "paper_title": paper_title,
            "chunk_id": note.chunk_id,
            "source": _parse_json_object(note.source_json),
            "tags": _parse_tags(note.tags),
            "created_at": note.created_at,
            "updated_at": note.updated_at,
        }
