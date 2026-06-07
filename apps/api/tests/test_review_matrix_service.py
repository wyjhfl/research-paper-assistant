from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.review_matrix_service import ReviewMatrixService


class FakePaperRepo:
    def __init__(self):
        self.user_ids: list[str | None] = []
        self.papers = {
            1: SimpleNamespace(id=1, title="Alpha Paper", status="completed"),
            2: SimpleNamespace(id=2, title="Beta Paper", status="failed"),
        }
        self.chunks = {
            1: [
                SimpleNamespace(
                    id=10,
                    chunk_index=0,
                    page_start=1,
                    page_end=1,
                    text=(
                        "The problem is retrieval quality. "
                        "We propose a hybrid workflow method. "
                        "Experiments on a dataset report accuracy as the main metric. "
                        "A limitation is cross-language matching. "
                        "Future work will improve semantic retrieval."
                    ),
                )
            ],
            2: [],
        }

    async def get_completed_paper_ids(self, user_id=None):
        self.user_ids.append(user_id)
        return [1]

    async def get_paper(self, paper_id: int, user_id=None):
        self.user_ids.append(user_id)
        return self.papers.get(paper_id)

    async def get_chunks_by_paper(self, paper_id: int, user_id=None):
        self.user_ids.append(user_id)
        return self.chunks.get(paper_id, [])


@pytest.mark.asyncio
async def test_review_matrix_extracts_fields_and_sources():
    repo = FakePaperRepo()
    service = ReviewMatrixService(session=None, user_id="user_a")  # type: ignore[arg-type]
    service.repo = repo

    result = await service.generate(paper_ids=[1], max_chunks_per_paper=4)

    assert result.generated_by == "heuristic"
    assert result.total_papers == 1
    row = result.rows[0]
    assert row.paper_id == 1
    assert row.paper_title == "Alpha Paper"
    assert "retrieval quality" in row.problem
    assert "hybrid workflow" in row.method
    assert "dataset" in row.evidence
    assert "accuracy" in row.metric
    assert "cross-language" in row.limitation
    assert "semantic retrieval" in row.future_work
    assert row.source_chunk_ids == [10]
    assert row.sources[0].chunk_id == 10
    assert "problem" in row.sources[0].matched_fields
    assert all(user_id == "user_a" for user_id in repo.user_ids)


@pytest.mark.asyncio
async def test_review_matrix_skips_missing_and_non_completed_papers():
    repo = FakePaperRepo()
    service = ReviewMatrixService(session=None, user_id="user_a")  # type: ignore[arg-type]
    service.repo = repo

    result = await service.generate(paper_ids=[1, 2, 999], max_chunks_per_paper=4)

    assert result.total_papers == 1
    assert result.rows[0].paper_id == 1
    assert "paper_id=2 status=failed skipped" in (result.warnings or [])
    assert "paper_id=999 not found" in (result.warnings or [])
