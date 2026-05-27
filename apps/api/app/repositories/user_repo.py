from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User, UserSession


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        result = await self.session.execute(
            select(UserSession).where(UserSession.session_token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def create_session(self, session_obj: UserSession) -> UserSession:
        self.session.add(session_obj)
        await self.session.flush()
        await self.session.refresh(session_obj)
        return session_obj

    async def revoke_session(self, token_hash: str) -> bool:
        sess = await self.get_session_by_token_hash(token_hash)
        if sess is None:
            return False
        from datetime import datetime, timezone
        sess.revoked_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True
