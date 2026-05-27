from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PaperListItem(BaseModel):
    id: int
    title: str
    filename: str
    status: str
    chunk_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PaperDetail(BaseModel):
    id: int
    title: str
    filename: str
    status: str
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChunkExcerpt(BaseModel):
    id: int
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    section_title: str | None

    model_config = {"from_attributes": True}


class PaperDetailResponse(BaseModel):
    paper: PaperDetail
    chunks: list[ChunkExcerpt]


class PaperListResponse(BaseModel):
    papers: list[PaperListItem]
    total: int


class PaperUploadResponse(BaseModel):
    id: int
    title: str
    filename: str
    status: str
    chunk_count: int
    job_id: str | None = None

    model_config = {"from_attributes": True}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)

    @field_validator("question")
    @classmethod
    def trim_question(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("question must not be empty")
        return trimmed


class SourceItem(BaseModel):
    paper_id: int
    chunk_id: int
    chunk_index: int
    page_start: int
    page_end: int
    text_excerpt: str
    score: float


class AskResponse(BaseModel):
    answer: str
    status: Literal["answered", "insufficient_context"]
    confidence: float
    sources: list[SourceItem]


class EmbeddingRebuildResponse(BaseModel):
    paper_id: int
    chunks_embedded: int
    job_id: str | None = None


class MultiPaperAskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    paper_ids: list[int] | None = Field(default=None, max_length=50)
    top_k: int = Field(default=8, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def trim_question(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("question must not be empty")
        return trimmed


class MultiPaperSourceItem(BaseModel):
    paper_id: int
    paper_title: str
    chunk_id: int
    chunk_index: int
    page_start: int
    page_end: int
    text_excerpt: str
    score: float


class MultiPaperAskResponse(BaseModel):
    answer: str
    status: Literal["answered", "insufficient_context"]
    confidence: float
    sources: list[MultiPaperSourceItem]


class PaperSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    paper_ids: list[int] | None = Field(default=None, max_length=50)
    top_k: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def trim_query(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("query must not be empty")
        return trimmed


class PaperSearchResultItem(BaseModel):
    paper_id: int
    paper_title: str
    chunk_id: int
    chunk_index: int
    page_start: int
    page_end: int
    text_excerpt: str
    score: float


class PaperSearchResponse(BaseModel):
    results: list[PaperSearchResultItem]
