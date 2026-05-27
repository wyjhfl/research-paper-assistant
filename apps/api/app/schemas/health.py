from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


class ReadyResponse(BaseModel):
    ready: bool
    database: str
    alembic_current: str | None = None
    alembic_head: str | None = None
