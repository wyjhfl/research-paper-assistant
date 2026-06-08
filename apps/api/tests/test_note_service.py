from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.note_service import InvalidNoteReferenceError, ResearchNoteService


class FakeNoteRepo:
    def __init__(self):
        self.notes = []
        self.deleted: list[tuple[int, str | None]] = []

    async def create_note(self, note):
        note.id = 1
        self.notes.append(note)
        return note

    async def list_notes(self, user_id=None, limit=100, note_type=None, tag=None, query=None):
        return [note for note in self.notes if note.user_id == user_id][:limit]

    async def get_note(self, note_id, user_id=None):
        for note in self.notes:
            if note.id == note_id and note.user_id == user_id:
                return note
        return None

    async def delete_note(self, note_id, user_id=None):
        self.deleted.append((note_id, user_id))
        return True


class FakePaperRepo:
    def __init__(self):
        self.papers = {
            1: SimpleNamespace(id=1, user_id="user_a", title="Alpha"),
        }
        self.chunks = {
            1: [SimpleNamespace(id=10, paper_id=1, chunk_index=0)],
        }
        self.user_ids: list[str | None] = []

    async def get_paper(self, paper_id, user_id=None):
        self.user_ids.append(user_id)
        paper = self.papers.get(paper_id)
        if paper and paper.user_id == user_id:
            return paper
        return None

    async def get_chunks_by_paper(self, paper_id, user_id=None):
        self.user_ids.append(user_id)
        paper = await self.get_paper(paper_id, user_id=user_id)
        if paper is None:
            return []
        return self.chunks.get(paper_id, [])


def test_smoke_check_includes_research_notes_table():
    import inspect
    from scripts import smoke_check

    src = inspect.getsource(smoke_check.smoke_check)
    assert '"research_notes"' in src or "'research_notes'" in src


@pytest.mark.asyncio
async def test_list_notes_passes_filters_to_repository():
    class RecordingRepo(FakeNoteRepo):
        def __init__(self):
            super().__init__()
            self.kwargs = None

        async def list_notes(self, user_id=None, limit=100, note_type=None, tag=None, query=None):
            self.kwargs = {
                "user_id": user_id,
                "limit": limit,
                "note_type": note_type,
                "tag": tag,
                "query": query,
            }
            return []

    repo = RecordingRepo()
    service = ResearchNoteService(session=None, user_id="user_a")  # type: ignore[arg-type]
    service.repo = repo

    await service.list_notes(limit=20, note_type="qa_answer", tag="qa", query=" retrieval ")

    assert repo.kwargs == {
        "user_id": "user_a",
        "limit": 20,
        "note_type": "qa_answer",
        "tag": "qa",
        "query": "retrieval",
    }


@pytest.mark.asyncio
async def test_create_note_filters_source_and_preserves_user_id():
    service = ResearchNoteService(session=None, user_id="user_a")  # type: ignore[arg-type]
    service.repo = FakeNoteRepo()
    service.paper_repo = FakePaperRepo()

    note = await service.create_note(
        title="Answer note",
        content="A concise answer with sources.",
        note_type="qa_answer",
        paper_id=1,
        chunk_id=10,
        source={
            "paper_id": 1,
            "chunk_id": 10,
            "score": 0.8,
            "api_key": "must-not-persist",
            "Authorization": "must-not-persist",
        },
        tags=["rag", "rag", "  qa  "],
    )

    assert note.user_id == "user_a"
    assert note.paper_id == 1
    assert note.chunk_id == 10
    item = await service.to_item(note)
    assert item["source"] == {"paper_id": 1, "chunk_id": 10, "score": 0.8}
    assert item["tags"] == ["rag", "qa"]
    assert "must-not-persist" not in note.source_json


@pytest.mark.asyncio
async def test_create_note_rejects_cross_user_paper():
    service = ResearchNoteService(session=None, user_id="user_b")  # type: ignore[arg-type]
    service.repo = FakeNoteRepo()
    service.paper_repo = FakePaperRepo()

    with pytest.raises(InvalidNoteReferenceError):
        await service.create_note(
            title="Bad note",
            content="Should not save",
            note_type="source_snippet",
            paper_id=1,
            chunk_id=10,
            source={"paper_id": 1, "chunk_id": 10},
            tags=[],
        )


@pytest.mark.asyncio
async def test_create_note_requires_paper_for_chunk():
    service = ResearchNoteService(session=None, user_id="user_a")  # type: ignore[arg-type]
    service.repo = FakeNoteRepo()
    service.paper_repo = FakePaperRepo()

    with pytest.raises(InvalidNoteReferenceError):
        await service.create_note(
            title="Chunk note",
            content="Missing paper.",
            note_type="source_snippet",
            paper_id=None,
            chunk_id=10,
            source={"chunk_id": 10},
            tags=[],
        )
