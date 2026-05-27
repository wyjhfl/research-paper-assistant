from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_user_id
from ..services.idea_service import IdeaService, DuplicateIdeaError, InvalidChunkIdsError
from ..repositories.idea_repo import IdeaRepository
from ..repositories.paper_repo import PaperRepository
from ..schemas.idea import (
    SaveIdeaRequest,
    SaveIdeaResponse,
    IdeaListResponse,
    IdeaDetailResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ideas", tags=["ideas"])


@router.post("", status_code=201, response_model=SaveIdeaResponse)
async def save_idea(
    req: SaveIdeaRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = IdeaService(db)
    try:
        idea = await service.save_idea(
            paper_id=req.paper_id,
            title=req.title,
            summary=req.summary,
            research_question=req.research_question,
            method_hint=req.method_hint,
            tags=req.tags,
            source_chunk_ids=req.source_chunk_ids,
            confidence=req.confidence,
            user_id=user_id,
        )
        await db.commit()
    except DuplicateIdeaError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate idea title under this paper")
    except InvalidChunkIdsError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    idea_repo = IdeaRepository(db)
    idea_sources = await idea_repo.get_idea_sources(idea.id)

    return {
        "id": idea.id,
        "paper_id": idea.paper_id,
        "title": idea.title,
        "summary": idea.summary,
        "research_question": idea.research_question,
        "method_hint": idea.method_hint,
        "tags": json.loads(idea.tags) if isinstance(idea.tags, str) else idea.tags,
        "confidence": idea.confidence,
        "status": idea.status,
        "created_at": idea.created_at,
        "sources": [
            {
                "paper_id": s.paper_id,
                "chunk_id": s.chunk_id,
                "chunk_index": s.chunk_index,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "text_excerpt": s.text_excerpt,
            }
            for s in idea_sources
        ],
    }


@router.get("", response_model=IdeaListResponse)
async def list_ideas(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = IdeaService(db)
    ideas = await service.list_ideas(user_id=user_id)

    idea_repo = IdeaRepository(db)
    paper_repo = PaperRepository(db)

    result = []
    for idea in ideas:
        source_count = await idea_repo.get_source_count(idea.id)
        paper = await paper_repo.get_paper(idea.paper_id, user_id=user_id)
        paper_title = paper.title if paper else "Unknown"

        tags_list = []
        if idea.tags:
            try:
                tags_list = json.loads(idea.tags) if isinstance(idea.tags, str) else idea.tags
            except (json.JSONDecodeError, TypeError):
                tags_list = []

        result.append({
            "id": idea.id,
            "paper_id": idea.paper_id,
            "paper_title": paper_title,
            "title": idea.title,
            "summary": idea.summary,
            "tags": tags_list,
            "confidence": idea.confidence,
            "created_at": idea.created_at,
            "source_count": source_count,
        })

    return {"ideas": result, "total": len(result)}


@router.get("/{idea_id}", response_model=IdeaDetailResponse)
async def get_idea(
    idea_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = IdeaService(db)
    idea = await service.get_idea(idea_id, user_id=user_id)
    if idea is None:
        raise HTTPException(status_code=404, detail="Idea not found")

    idea_repo = IdeaRepository(db)
    idea_sources = await idea_repo.get_idea_sources(idea.id)

    tags_list = []
    if idea.tags:
        try:
            tags_list = json.loads(idea.tags) if isinstance(idea.tags, str) else idea.tags
        except (json.JSONDecodeError, TypeError):
            tags_list = []

    return {
        "id": idea.id,
        "paper_id": idea.paper_id,
        "title": idea.title,
        "summary": idea.summary,
        "research_question": idea.research_question,
        "method_hint": idea.method_hint,
        "tags": tags_list,
        "confidence": idea.confidence,
        "status": idea.status,
        "created_at": idea.created_at,
        "updated_at": idea.updated_at,
        "sources": [
            {
                "paper_id": s.paper_id,
                "chunk_id": s.chunk_id,
                "chunk_index": s.chunk_index,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "text_excerpt": s.text_excerpt,
            }
            for s in idea_sources
        ],
    }


@router.delete("/{idea_id}", status_code=204)
async def delete_idea(
    idea_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = IdeaService(db)
    deleted = await service.delete_idea(idea_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Idea not found")
    await db.commit()
