from __future__ import annotations

import hashlib
import re

from fastapi import Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import async_session

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_\-.]{1,64}$")


async def get_user_id(
    request: Request,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    if settings.AUTH_ENABLED:
        cookie_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
        if cookie_token:
            from .services.auth_service import AuthService
            async with async_session() as db:
                service = AuthService(db)
                user = await service.get_user_from_session(cookie_token)
            if user is not None:
                return user.user_id

        if settings.ALLOW_DEV_USER_HEADER and x_user_id:
            x_user_id = x_user_id.strip()
            if x_user_id and _USER_ID_RE.fullmatch(x_user_id):
                return x_user_id

        raise HTTPException(status_code=401, detail="Not authenticated")
    else:
        if x_user_id is None:
            return "default"
        x_user_id = x_user_id.strip()
        if not x_user_id:
            return "default"
        if not _USER_ID_RE.fullmatch(x_user_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid X-User-Id: must be 1-64 chars, only letters, digits, underscore, hyphen, dot",
            )
        return x_user_id
