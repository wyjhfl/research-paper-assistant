from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import get_user_id
from ..services.agent_run_service import AgentRunService
from ..agents.supervisor import VALID_TASK_TYPES
from ..repositories.paper_repo import PaperRepository
from ..schemas.agent import AgentRunRequest, AgentRunResponse, AgentRunDetailResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    req: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    if req.task_type not in VALID_TASK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_type: {req.task_type}. Must be one of {VALID_TASK_TYPES}",
        )

    if req.task_type in ("summarize_paper", "extract_ideas", "recommend_citations"):
        if req.paper_id is None:
            raise HTTPException(
                status_code=400,
                detail=f"paper_id is required for {req.task_type}",
            )

    if req.paper_id is not None:
        paper_repo = PaperRepository(db)
        paper = await paper_repo.get_paper(req.paper_id, user_id=user_id)
        if paper is None:
            raise HTTPException(status_code=404, detail=f"Paper {req.paper_id} not found")

    if req.task_type == "recommend_citations":
        if not req.question.strip() and not req.draft_text.strip():
            raise HTTPException(
                status_code=400,
                detail="question or draft_text is required for recommend_citations",
            )

    if req.task_type == "recommend_citations_multi":
        if not req.question.strip() and not req.draft_text.strip():
            raise HTTPException(
                status_code=400,
                detail="question or draft_text is required for recommend_citations_multi",
            )
        if req.paper_ids is not None and len(req.paper_ids) == 0:
            req.paper_ids = None
        if req.paper_ids:
            paper_repo = PaperRepository(db)
            for pid in req.paper_ids:
                paper = await paper_repo.get_paper(pid, user_id=user_id)
                if paper is None:
                    raise HTTPException(status_code=404, detail=f"Paper {pid} not found")

    service = AgentRunService(db)
    result = await service.run_agent(
        task_type=req.task_type,
        paper_id=req.paper_id,
        paper_ids=req.paper_ids,
        question=req.question,
        draft_text=req.draft_text,
        user_id=user_id,
    )

    return AgentRunResponse(**result)


@router.get("/runs/{run_id}", response_model=AgentRunDetailResponse)
async def get_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    service = AgentRunService(db)
    result = await service.get_run(run_id, user_id=user_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Agent run {run_id} not found")
    return AgentRunDetailResponse(**result)
