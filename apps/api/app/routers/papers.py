from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_user_id
from ..services.paper_service import PaperService
from ..services.rag_service import RAGService, PaperNotFoundError, PaperNotReadyError
from ..services.multi_paper_rag_service import MultiPaperRAGService
from ..services.idea_service import IdeaService
from ..services.ai_provider import ProviderConfigurationError, ProviderRequestError, ProviderResponseError
from ..repositories.paper_repo import PaperRepository
from ..schemas.paper import (
    PaperListResponse,
    PaperUploadResponse,
    PaperDetailResponse,
    AskRequest,
    AskResponse,
    EmbeddingRebuildResponse,
    MultiPaperAskRequest,
    MultiPaperAskResponse,
    PaperSearchRequest,
    PaperSearchResponse,
)
from ..schemas.idea import ExtractIdeasResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("", response_model=PaperListResponse)
async def list_papers(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = PaperService(db, user_id=user_id)
    papers = await service.list_papers(user_id=user_id)
    return {
        "papers": [
            {
                "id": p.id,
                "title": p.title,
                "filename": p.filename,
                "status": p.status,
                "chunk_count": await PaperRepository(db).get_chunk_count(p.id),
                "created_at": p.created_at,
            }
            for p in papers
        ],
        "total": len(papers),
    }


@router.post("/upload", status_code=201, response_model=PaperUploadResponse)
async def upload_paper(
    file: UploadFile = File(...),
    async_mode: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = PaperService(db, user_id=user_id)
    content = await file.read()
    paper = await service.upload_paper(file.filename or "unknown.pdf", content)

    job_id = None
    if async_mode:
        from ..services.job_service import JobService
        job_svc = JobService(db)
        job = await job_svc.create_job(
            user_id=user_id,
            job_type="process_paper",
            input_data={"paper_id": paper.id},
        )
        job_id = job.job_id
        await db.commit()
    else:
        try:
            paper = await service.process_paper(paper.id)
        except Exception:
            logger.exception("Paper processing failed for id=%d", paper.id)

    return {
        "id": paper.id,
        "title": paper.title,
        "filename": paper.filename,
        "status": paper.status,
        "chunk_count": await PaperRepository(db).get_chunk_count(paper.id),
        "job_id": job_id,
    }


@router.get("/{paper_id}", response_model=PaperDetailResponse)
async def get_paper(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = PaperService(db, user_id=user_id)
    paper = await service.get_paper(paper_id, user_id=user_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    repo = PaperRepository(db)
    chunks = await repo.get_chunks_by_paper(paper_id)
    return {
        "paper": {
            "id": paper.id,
            "title": paper.title,
            "filename": paper.filename,
            "status": paper.status,
            "error_message": paper.error_message,
            "chunk_count": len(chunks),
            "created_at": paper.created_at,
            "updated_at": paper.updated_at,
        },
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "text": c.text,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "section_title": c.section_title,
            }
            for c in chunks
        ],
    }


@router.post("/{paper_id}/ask", response_model=AskResponse)
async def ask_paper(
    paper_id: int,
    req: AskRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    repo = PaperRepository(db)
    paper = await repo.get_paper(paper_id, user_id=user_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    rag = RAGService(db, user_id=user_id)
    try:
        result = await rag.ask(paper_id, req.question)
    except PaperNotFoundError:
        raise HTTPException(status_code=404, detail="Paper not found")
    except PaperNotReadyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError):
        logger.exception("AI provider failed for paper %d ask", paper_id)
        raise HTTPException(status_code=503, detail="AI provider unavailable")

    return {
        "answer": result.answer,
        "status": result.status,
        "confidence": result.confidence,
        "sources": [
            {
                "paper_id": paper_id,
                "chunk_id": s.chunk_id,
                "chunk_index": s.chunk_index,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "text_excerpt": s.text_excerpt,
                "score": s.score,
            }
            for s in result.sources
        ],
    }


@router.post("/{paper_id}/embeddings/rebuild", response_model=EmbeddingRebuildResponse)
async def rebuild_embeddings(
    paper_id: int,
    async_mode: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    repo = PaperRepository(db)
    paper = await repo.get_paper(paper_id, user_id=user_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    if async_mode:
        from ..services.job_service import JobService
        job_svc = JobService(db)
        job = await job_svc.create_job(
            user_id=user_id,
            job_type="rebuild_embeddings",
            input_data={"paper_id": paper_id},
        )
        await db.commit()
        return {"paper_id": paper_id, "chunks_embedded": 0, "job_id": job.job_id}

    service = PaperService(db, user_id=user_id)
    try:
        count = await service.rebuild_embeddings(paper_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Paper not found")

    return {"paper_id": paper_id, "chunks_embedded": count}


@router.post("/{paper_id}/ideas/extract", response_model=ExtractIdeasResponse)
async def extract_ideas(
    paper_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    repo = PaperRepository(db)
    paper = await repo.get_paper(paper_id, user_id=user_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")

    idea_service = IdeaService(db)
    try:
        candidates = await idea_service.extract_ideas(paper_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "paper_id": paper_id,
        "candidates": [
            {
                "title": c.title,
                "summary": c.summary,
                "research_question": c.research_question,
                "method_hint": c.method_hint,
                "tags": c.tags,
                "source_chunk_ids": c.source_chunk_ids,
                "confidence": c.confidence,
            }
            for c in candidates
        ],
    }


@router.post("/ask", response_model=MultiPaperAskResponse)
async def multi_paper_ask(
    req: MultiPaperAskRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    paper_ids = req.paper_ids

    if paper_ids:
        repo = PaperRepository(db)
        for pid in paper_ids:
            p = await repo.get_paper(pid, user_id=user_id)
            if p is None:
                raise HTTPException(status_code=404, detail=f"Paper {pid} not found")

    rag = MultiPaperRAGService(db, user_id=user_id)
    try:
        result = await rag.ask(question=req.question, paper_ids=paper_ids, top_k=req.top_k)
    except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError):
        logger.exception("AI provider failed for multi-paper ask")
        raise HTTPException(status_code=503, detail="AI provider unavailable")

    return {
        "answer": result.answer,
        "status": result.status,
        "confidence": result.confidence,
        "sources": [
            {
                "paper_id": s.paper_id,
                "paper_title": s.paper_title,
                "chunk_id": s.chunk_id,
                "chunk_index": s.chunk_index,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "text_excerpt": s.text_excerpt,
                "score": s.score,
            }
            for s in result.sources
        ],
    }


@router.post("/search", response_model=PaperSearchResponse)
async def search_papers(
    req: PaperSearchRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    paper_ids = req.paper_ids

    if paper_ids:
        repo = PaperRepository(db)
        for pid in paper_ids:
            p = await repo.get_paper(pid, user_id=user_id)
            if p is None:
                raise HTTPException(status_code=404, detail=f"Paper {pid} not found")

    rag = MultiPaperRAGService(db, user_id=user_id)
    try:
        results = await rag.search(query=req.query, paper_ids=paper_ids, top_k=req.top_k)
    except (ProviderConfigurationError, ProviderRequestError, ProviderResponseError):
        logger.exception("AI provider failed for paper search")
        raise HTTPException(status_code=503, detail="AI provider unavailable")

    return {
        "results": [
            {
                "paper_id": r.paper_id,
                "paper_title": r.paper_title,
                "chunk_id": r.chunk_id,
                "chunk_index": r.chunk_index,
                "page_start": r.page_start,
                "page_end": r.page_end,
                "text_excerpt": r.text_excerpt,
                "score": r.score,
            }
            for r in results
        ],
    }
