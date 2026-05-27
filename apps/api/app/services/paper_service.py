from __future__ import annotations

import logging
import os
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Paper, PaperChunk
from ..repositories.paper_repo import PaperRepository
from ..services.embedding_service import EmbeddingService
from ..services.pdf_parser import parse_pdf

logger = logging.getLogger(__name__)


class PaperService:
    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id
        self.repo = PaperRepository(session)
        self.embedding_service = EmbeddingService(session, user_id=user_id)

    async def upload_paper(
        self, filename: str, file_content: bytes
    ) -> Paper:
        uid = self.user_id
        storage_base = settings.STORAGE_PATH
        upload_dir = os.path.join(storage_base, "uploads", uid)
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = _safe_filename(filename)
        unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
        file_path = os.path.join(upload_dir, unique_name)
        with open(file_path, "wb") as f:
            f.write(file_content)

        paper = Paper(
            title=filename,
            filename=filename,
            file_path=file_path,
            status="pending",
            user_id=uid,
        )
        paper = await self.repo.create_paper(paper)
        await self.session.commit()
        return paper

    async def list_papers(self, user_id: str = "default") -> list[Paper]:
        return await self.repo.list_papers(user_id=user_id)

    async def get_paper(self, paper_id: int, user_id: str = "default") -> Paper | None:
        return await self.repo.get_paper(paper_id, user_id=user_id)

    async def process_paper(self, paper_id: int) -> Paper:
        paper = await self.repo.get_paper(paper_id, user_id=self.user_id)
        if paper is None:
            raise ValueError(f"Paper {paper_id} not found for user {self.user_id}")

        try:
            await self.repo.update_paper_status(paper_id, "processing", user_id=self.user_id)
            await self.session.commit()

            chunks_data = parse_pdf(
                paper.file_path,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
            )

            all_text = " ".join(c.text for c in chunks_data)
            if not all_text.strip():
                await self.repo.update_paper_status(
                    paper_id, "failed", "No text could be extracted from the PDF",
                    user_id=self.user_id,
                )
                await self.session.commit()
                return await self.repo.get_paper(paper_id, user_id=self.user_id)

            for chunk_data in chunks_data:
                chunk = PaperChunk(
                    paper_id=paper_id,
                    chunk_index=chunk_data.chunk_index,
                    text=chunk_data.text,
                    page_start=chunk_data.page_start,
                    page_end=chunk_data.page_end,
                    section_title=chunk_data.section_title,
                )
                self.session.add(chunk)
            await self.session.flush()

            try:
                await self.embedding_service.embed_chunks_for_paper(paper_id)
            except Exception as emb_exc:
                logger.warning(
                    "Embedding failed for paper %d (paper still marked completed): %s",
                    paper_id, type(emb_exc).__name__,
                )

            await self.repo.update_paper_status(paper_id, "completed", user_id=self.user_id)
            await self.session.commit()

        except Exception as e:
            logger.exception("Failed to process paper %d", paper_id)
            await self.repo.update_paper_status(paper_id, "failed", str(e)[:500], user_id=self.user_id)
            await self.session.commit()

        return await self.repo.get_paper(paper_id, user_id=self.user_id)

    async def rebuild_embeddings(self, paper_id: int) -> int:
        paper = await self.repo.get_paper(paper_id, user_id=self.user_id)
        if paper is None:
            raise ValueError(f"Paper {paper_id} not found for user {self.user_id}")

        await self.repo.clear_embeddings(paper_id)
        await self.session.commit()

        count = await self.embedding_service.embed_chunks_for_paper(paper_id)
        await self.session.commit()
        return count


def _safe_filename(filename: str) -> str:
    base = os.path.basename(filename)
    safe = base.replace("..", "").replace(os.sep, "").replace("/", "")
    if not safe or safe.startswith("."):
        safe = "upload"
    return safe
