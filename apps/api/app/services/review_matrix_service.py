from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.paper_repo import PaperRepository


_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "problem": [
        "problem", "challenge", "limitation", "limitations", "gap", "open problem",
        "motivation", "issue", "barrier", "难点", "问题", "挑战", "局限",
    ],
    "method": [
        "method", "approach", "propose", "proposed", "framework", "model",
        "algorithm", "architecture", "pipeline", "workflow", "方法", "提出", "框架",
    ],
    "evidence": [
        "experiment", "experiments", "evaluation", "evidence", "dataset", "study",
        "benchmark", "case study", "source", "实验", "评估", "数据集", "证据",
    ],
    "metric": [
        "accuracy", "precision", "recall", "f1", "auc", "score", "metric",
        "result", "performance", "latency", "throughput", "指标", "结果", "性能",
    ],
    "limitation": [
        "limitation", "limitations", "threat", "weakness", "fail", "failure",
        "insufficient", "shortcoming", "局限", "不足", "失败",
    ],
    "future_work": [
        "future work", "future", "next step", "direction", "extend", "extension",
        "improve", "improvement", "open problem", "未来", "方向", "改进", "扩展",
    ],
}


@dataclass
class ReviewMatrixSource:
    paper_id: int
    paper_title: str
    chunk_id: int
    chunk_index: int
    page_start: int
    page_end: int
    text_excerpt: str
    matched_fields: list[str]


@dataclass
class ReviewMatrixRow:
    paper_id: int
    paper_title: str
    problem: str
    method: str
    evidence: str
    metric: str
    limitation: str
    future_work: str
    source_chunk_ids: list[int]
    sources: list[ReviewMatrixSource]


@dataclass
class ReviewMatrixResult:
    rows: list[ReviewMatrixRow]
    total_papers: int
    generated_by: str = "heuristic"
    warnings: list[str] | None = None


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+", _normalize_ws(text))
    return [part.strip() for part in parts if part.strip()]


def _matches(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def _shorten(text: str, limit: int = 220) -> str:
    clean = _normalize_ws(text)
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _extract_field(chunk_texts: list[tuple[int, str]], field_name: str, fallback: str) -> tuple[str, list[int]]:
    keywords = _CATEGORY_KEYWORDS[field_name]
    matched: list[tuple[int, str]] = []
    for chunk_id, text in chunk_texts:
        for sentence in _sentences(text):
            if _matches(sentence, keywords):
                matched.append((chunk_id, sentence))
                break
        if len(matched) >= 2:
            break

    if not matched:
        return fallback, []

    summary = " ".join(_shorten(sentence, 160) for _, sentence in matched)
    return _shorten(summary, 260), [chunk_id for chunk_id, _ in matched]


class ReviewMatrixService:
    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id
        self.repo = PaperRepository(session)

    async def generate(
        self,
        paper_ids: list[int] | None = None,
        max_chunks_per_paper: int = 8,
    ) -> ReviewMatrixResult:
        max_chunks_per_paper = max(1, min(max_chunks_per_paper, 20))

        if paper_ids:
            requested_ids = list(dict.fromkeys(paper_ids))
        else:
            requested_ids = await self.repo.get_completed_paper_ids(user_id=self.user_id)

        rows: list[ReviewMatrixRow] = []
        warnings: list[str] = []

        for paper_id in requested_ids[:50]:
            paper = await self.repo.get_paper(paper_id, user_id=self.user_id)
            if paper is None:
                warnings.append(f"paper_id={paper_id} not found")
                continue
            if paper.status != "completed":
                warnings.append(f"paper_id={paper_id} status={paper.status} skipped")
                continue

            chunks = await self.repo.get_chunks_by_paper(paper_id, user_id=self.user_id)
            selected_chunks = chunks[:max_chunks_per_paper]
            if not selected_chunks:
                warnings.append(f"paper_id={paper_id} has no chunks skipped")
                continue
            chunk_texts = [(chunk.id, chunk.text) for chunk in selected_chunks]

            fields: dict[str, str] = {}
            field_sources: dict[str, list[int]] = {}
            for field_name, fallback in [
                ("problem", "未在片段中发现明确的问题描述"),
                ("method", "未在片段中发现明确的方法描述"),
                ("evidence", "未在片段中发现明确的数据或证据"),
                ("metric", "未在片段中发现明确的指标或结果"),
                ("limitation", "未在片段中发现明确的局限"),
                ("future_work", "未在片段中发现明确的未来工作"),
            ]:
                value, chunk_ids = _extract_field(chunk_texts, field_name, fallback)
                fields[field_name] = value
                field_sources[field_name] = chunk_ids

            source_ids = sorted({chunk_id for ids in field_sources.values() for chunk_id in ids})
            if not source_ids and selected_chunks:
                source_ids = [selected_chunks[0].id]

            sources: list[ReviewMatrixSource] = []
            for chunk in selected_chunks:
                matched_fields = [
                    field_name for field_name, ids in field_sources.items() if chunk.id in ids
                ]
                if chunk.id not in source_ids:
                    continue
                sources.append(
                    ReviewMatrixSource(
                        paper_id=paper.id,
                        paper_title=paper.title,
                        chunk_id=chunk.id,
                        chunk_index=chunk.chunk_index,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        text_excerpt=_shorten(chunk.text, 260),
                        matched_fields=matched_fields,
                    )
                )

            rows.append(
                ReviewMatrixRow(
                    paper_id=paper.id,
                    paper_title=paper.title,
                    problem=fields["problem"],
                    method=fields["method"],
                    evidence=fields["evidence"],
                    metric=fields["metric"],
                    limitation=fields["limitation"],
                    future_work=fields["future_work"],
                    source_chunk_ids=source_ids,
                    sources=sources,
                )
            )

        return ReviewMatrixResult(
            rows=rows,
            total_papers=len(rows),
            warnings=warnings,
        )
