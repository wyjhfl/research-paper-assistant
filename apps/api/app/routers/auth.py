from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..dependencies import get_user_id
from ..services.auth_service import AuthService
from ..schemas.auth import RegisterRequest, LoginRequest, UserResponse, MeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
    )


@router.post("/register", status_code=201, response_model=UserResponse)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    try:
        user = await service.register(
            email=req.email,
            password=req.password,
            display_name=req.display_name,
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        if "already registered" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
    )


@router.post("/login", response_model=UserResponse)
async def login(
    req: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    try:
        user, token = await service.login(email=req.email, password=req.password)
        await db.commit()
    except ValueError:
        await db.rollback()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _set_session_cookie(response, token)
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    cookie_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_token:
        service = AuthService(db)
        await service.logout(cookie_token)
        await db.commit()
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
):
    if settings.AUTH_ENABLED:
        from ..repositories.user_repo import UserRepository
        repo = UserRepository(db)
        user = await repo.get_by_user_id(user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return MeResponse(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            auth_mode="session",
        )
    else:
        return MeResponse(
            user_id=user_id,
            email="dev@localhost",
            display_name=user_id,
            auth_mode="dev",
        )
