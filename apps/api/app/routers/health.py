from fastapi import APIRouter

from ..schemas.health import HealthResponse, ReadyResponse
from ..database import check_db_connection, get_alembic_versions
from ..config import settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    db_connected = await check_db_connection()
    return HealthResponse(
        status="ok" if db_connected else "degraded",
        version=settings.APP_VERSION,
        database="connected" if db_connected else "disconnected",
    )


@router.get("/health/ready", response_model=ReadyResponse)
async def readiness_check():
    db_connected = await check_db_connection()
    alembic_current, alembic_head = await get_alembic_versions()

    db_ok = db_connected
    alembic_ok = (
        alembic_current is not None
        and alembic_head is not None
        and alembic_current == alembic_head
    )
    ready = db_ok and alembic_ok

    return ReadyResponse(
        ready=ready,
        database="connected" if db_ok else "disconnected",
        alembic_current=alembic_current,
        alembic_head=alembic_head,
    )
