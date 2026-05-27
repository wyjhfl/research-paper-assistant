import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from .config import settings
from .models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def get_alembic_versions() -> tuple[str | None, str | None]:
    try:
        async with engine.connect() as conn:
            current_result = await conn.execute(
                text("SELECT version_num FROM alembic_version")
            )
            current_row = current_result.fetchone()
            current = current_row[0] if current_row else None
    except Exception:
        current = None

    try:
        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory
        alembic_cfg_path = str(
            __import__("pathlib").Path(__file__).resolve().parent.parent / "alembic.ini"
        )
        alembic_cfg = AlembicConfig(alembic_cfg_path)
        script = ScriptDirectory.from_config(alembic_cfg)
        head = script.get_current_head()
    except Exception:
        head = None

    return current, head


async def _run_migrations(conn) -> None:
    result = await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='paper_chunks' AND column_name='embedding'"
    ))
    if result.scalar() is None:
        dim = settings.EMBEDDING_DIMENSION
        await conn.execute(text(
            f"ALTER TABLE paper_chunks ADD COLUMN embedding vector({dim})"
        ))
        logger.info("Added embedding column (dim=%d) to paper_chunks", dim)
    else:
        dim_result = await conn.execute(text(
            "SELECT a.atttypmod FROM pg_attribute a "
            "JOIN pg_class c ON a.attrelid = c.oid "
            "JOIN pg_namespace n ON c.relnamespace = n.oid "
            "WHERE c.relname='paper_chunks' AND a.attname='embedding' AND n.nspname='public'"
        ))
        row = dim_result.fetchone()
        if row is not None:
            db_dim = row[0]
            if db_dim != settings.EMBEDDING_DIMENSION:
                raise RuntimeError(
                    f"Embedding dimension mismatch: database has vector({db_dim}) "
                    f"but EMBEDDING_DIMENSION={settings.EMBEDDING_DIMENSION}. "
                    f"Please run 'docker compose down -v' to rebuild the database, "
                    f"or update EMBEDDING_DIMENSION to match."
                )

    idx_result = await conn.execute(text(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename='paper_chunks' AND indexname='paper_chunks_embedding_hnsw_idx'"
    ))
    if idx_result.scalar() is None:
        await conn.execute(text(
            "CREATE INDEX paper_chunks_embedding_hnsw_idx ON paper_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        ))
        logger.info("Created HNSW index on paper_chunks.embedding")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)
