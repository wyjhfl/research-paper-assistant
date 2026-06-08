from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResearchNoteSource(BaseModel):
    paper_id: int | None = None
    paper_title: str | None = None
    chunk_id: int | None = None
    chunk_index: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    score: float | None = None
    source_kind: str | None = None


class ResearchNoteCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(..., min_length=1, max_length=8000)
    note_type: str = Field(default="manual", pattern="^(manual|qa_answer|source_snippet|review_matrix|idea)$")
    paper_id: int | None = None
    chunk_id: int | None = None
    source: ResearchNoteSource | dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("title must not be empty")
        return trimmed

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("content must not be empty")
        return trimmed

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            tag = item.strip()
            if not tag or tag in seen:
                continue
            cleaned.append(tag[:40])
            seen.add(tag)
        return cleaned[:20]


class ResearchNoteUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    content: str | None = Field(default=None, min_length=1, max_length=8000)
    tags: list[str] | None = Field(default=None, max_length=20)

    @field_validator("title")
    @classmethod
    def trim_optional_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("title must not be empty")
        return trimmed

    @field_validator("content")
    @classmethod
    def trim_optional_content(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("content must not be empty")
        return trimmed

    @field_validator("tags")
    @classmethod
    def clean_optional_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return ResearchNoteCreateRequest.clean_tags(value)


class ResearchNoteItem(BaseModel):
    id: int
    title: str
    content: str
    note_type: str
    paper_id: int | None
    paper_title: str | None = None
    chunk_id: int | None
    source: dict[str, Any]
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class ResearchNoteListResponse(BaseModel):
    notes: list[ResearchNoteItem]
    total: int


class ResearchNoteResponse(BaseModel):
    note: ResearchNoteItem
