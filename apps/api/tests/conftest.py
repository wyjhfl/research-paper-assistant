import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.config import settings
from app.database import get_db, Base

settings.EMBEDDING_PROVIDER = "local"
settings.EMBEDDING_MODEL = "local-hash"
settings.EMBEDDING_API_KEY = ""
settings.EMBEDDING_BASE_URL = ""
settings.LLM_PROVIDER = "local"
settings.LLM_MODEL = "local-mock"
settings.LLM_API_KEY = ""
settings.LLM_BASE_URL = ""
settings.REAL_MODEL_REQUIRED = False
settings.AUTH_ENABLED = False
settings.ALLOW_DEV_USER_HEADER = True

TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    "/research_assistant", "/research_assistant_test"
)

_root_engine = create_async_engine(
    settings.DATABASE_URL.replace("/research_assistant", "/postgres"),
    echo=False,
    poolclass=NullPool,
    isolation_level="AUTOCOMMIT",
)

_test_engine = create_async_engine(
    TEST_DATABASE_URL, echo=False, poolclass=NullPool
)
_test_session_factory = sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with _test_session_factory() as session:
        yield session


from app.main import app
app.dependency_overrides[get_db] = override_get_db

from app.mcp.tools import set_session_factory
set_session_factory(_test_session_factory)

from app.services.model_call_audit_service import set_audit_session_factory
set_audit_session_factory(_test_session_factory)

_db_available = False


async def _check_db_available():
    global _db_available
    try:
        async with _root_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _db_available = True
    except Exception:
        _db_available = False


def skip_if_no_db():
    return pytest.mark.skipif(
        not _db_available,
        reason="PostgreSQL not available for test DB"
    )


@pytest_asyncio.fixture(autouse=True, scope="session")
async def create_test_db():
    await _check_db_available()
    if not _db_available:
        yield
        return
    try:
        async with _root_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname='research_assistant_test'")
            )
            if result.scalar() is None:
                await conn.execute(text("CREATE DATABASE research_assistant_test"))
        async with _test_engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        yield
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all, checkfirst=True)
        await _test_engine.dispose()
        async with _root_engine.connect() as conn:
            await conn.execute(text("DROP DATABASE IF EXISTS research_assistant_test"))
        await _root_engine.dispose()
    except Exception:
        yield


@pytest_asyncio.fixture(autouse=True, scope="function")
async def setup_db():
    if not _db_available:
        yield
        return
    try:
        async with _test_engine.begin() as conn:
            await conn.execute(text("TRUNCATE TABLE model_call_events CASCADE"))
            await conn.execute(text("TRUNCATE TABLE job_runs CASCADE"))
            await conn.execute(text("TRUNCATE TABLE agent_runs CASCADE"))
            await conn.execute(text("TRUNCATE TABLE idea_sources CASCADE"))
            await conn.execute(text("TRUNCATE TABLE ideas CASCADE"))
            await conn.execute(text("TRUNCATE TABLE paper_chunks CASCADE"))
            await conn.execute(text("TRUNCATE TABLE papers CASCADE"))
            await conn.execute(text("TRUNCATE TABLE user_sessions CASCADE"))
            await conn.execute(text("TRUNCATE TABLE users CASCADE"))
        yield
    except Exception:
        yield
