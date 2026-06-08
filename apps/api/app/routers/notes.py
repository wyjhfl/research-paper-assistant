from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_user_id
from ..schemas.note import (
    ResearchNoteCreateRequest,
    ResearchNoteListResponse,
    ResearchNoteResponse,
    ResearchNoteUpdateRequest,
)
from ..services.note_service import InvalidNoteReferenceError, ResearchNoteService


router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("", status_code=201, response_model=ResearchNoteResponse)
async def create_note(
    req: ResearchNoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = ResearchNoteService(db, user_id=user_id)
    try:
        note = await service.create_note(
            title=req.title,
            content=req.content,
            note_type=req.note_type,
            paper_id=req.paper_id,
            chunk_id=req.chunk_id,
            source=req.source,
            tags=req.tags,
        )
        await db.commit()
    except InvalidNoteReferenceError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return {"note": await service.to_item(note)}


@router.get("", response_model=ResearchNoteListResponse)
async def list_notes(
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = ResearchNoteService(db, user_id=user_id)
    notes = await service.list_notes(limit=limit)
    return {
        "notes": [await service.to_item(note) for note in notes],
        "total": len(notes),
    }


@router.get("/{note_id}", response_model=ResearchNoteResponse)
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = ResearchNoteService(db, user_id=user_id)
    note = await service.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"note": await service.to_item(note)}


@router.patch("/{note_id}", response_model=ResearchNoteResponse)
async def update_note(
    note_id: int,
    req: ResearchNoteUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = ResearchNoteService(db, user_id=user_id)
    note = await service.update_note(
        note_id,
        title=req.title,
        content=req.content,
        tags=req.tags,
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.commit()
    return {"note": await service.to_item(note)}


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = ResearchNoteService(db, user_id=user_id)
    deleted = await service.delete_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.commit()
