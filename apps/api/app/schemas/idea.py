from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class IdeaCandidateItem(BaseModel):
    title: str
    summary: str
    research_question: str
    method_hint: str
    tags: list[str]
    source_chunk_ids: list[int]
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractIdeasResponse(BaseModel):
    paper_id: int
    candidates: list[IdeaCandidateItem]


class SaveIdeaRequest(BaseModel):
    paper_id: int
    title: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    research_question: str = ""
    method_hint: str = ""
    tags: list[str] = Field(default_factory=list)
    source_chunk_ids: list[int] = Field(default_factory=list, min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("title")
    @classmethod
    def trim_title(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("title must not be empty")
        return trimmed

    @field_validator("summary")
    @classmethod
    def trim_summary(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("summary must not be empty")
        return trimmed

    @field_validator("tags")
    @classmethod
    def filter_empty_tags(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v if t.strip()]


class IdeaSourceItem(BaseModel):
    paper_id: int
    chunk_id: int
    chunk_index: int
    page_start: int
    page_end: int
    text_excerpt: str


class IdeaListItem(BaseModel):
    id: int
    paper_id: int
    paper_title: str
    title: str
    summary: str
    tags: list[str]
    confidence: float
    created_at: datetime
    source_count: int


class IdeaListResponse(BaseModel):
    ideas: list[IdeaListItem]
    total: int


class IdeaDetailResponse(BaseModel):
    id: int
    paper_id: int
    title: str
    summary: str
    research_question: str
    method_hint: str
    tags: list[str]
    confidence: float
    status: str
    created_at: datetime
    updated_at: datetime
    sources: list[IdeaSourceItem]


class SaveIdeaResponse(BaseModel):
    id: int
    paper_id: int
    title: str
    summary: str
    research_question: str
    method_hint: str
    tags: list[str]
    confidence: float
    status: str
    created_at: datetime
    sources: list[IdeaSourceItem]
