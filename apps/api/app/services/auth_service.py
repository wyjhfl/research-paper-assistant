from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import User, UserSession
from ..repositories.user_repo import UserRepository

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_\-.]{1,64}$")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _generate_user_id(email: str) -> str:
    prefix = re.sub(r"[^A-Za-z0-9_.\-]", "", email.split("@")[0])[:40]
    suffix = secrets.token_hex(4)
    uid = f"{prefix}_{suffix}"
    if not _USER_ID_RE.fullmatch(uid):
        uid = f"user_{suffix}"
    return uid


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)

    async def register(self, email: str, password: str, display_name: str | None = None) -> User:
        from pwdlib import PasswordHash

        ph = PasswordHash.recommended()
        email = email.strip().lower()
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        existing = await self.repo.get_by_email(email)
        if existing is not None:
            raise ValueError("Email already registered")

        user_id = _generate_user_id(email)
        while await self.repo.get_by_user_id(user_id) is not None:
            user_id = _generate_user_id(email)

        user = User(
            user_id=user_id,
            email=email,
            password_hash=ph.hash(password),
            display_name=display_name or email.split("@")[0],
            is_active=True,
        )
        return await self.repo.create_user(user)

    async def login(self, email: str, password: str) -> tuple[User, str]:
        from pwdlib import PasswordHash

        ph = PasswordHash.recommended()
        email = email.strip().lower()
        user = await self.repo.get_by_email(email)
        if user is None or not user.is_active:
            raise ValueError("Invalid credentials")
        if not ph.verify(password, user.password_hash):
            raise ValueError("Invalid credentials")

        token = secrets.token_urlsafe(48)
        token_hash = _hash_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.SESSION_TTL_SECONDS)
        session_obj = UserSession(
            session_token_hash=token_hash,
            user_id=user.user_id,
            expires_at=expires_at,
        )
        await self.repo.create_session(session_obj)
        return user, token

    async def get_user_from_session(self, token: str) -> User | None:
        token_hash = _hash_token(token)
        session_obj = await self.repo.get_session_by_token_hash(token_hash)
        if session_obj is None:
            return None
        now = datetime.now(timezone.utc)
        if session_obj.expires_at < now:
            return None
        if session_obj.revoked_at is not None:
            return None
        user = await self.repo.get_by_user_id(session_obj.user_id)
        if user is None or not user.is_active:
            return None
        return user

    async def logout(self, token: str) -> bool:
        token_hash = _hash_token(token)
        return await self.repo.revoke_session(token_hash)
