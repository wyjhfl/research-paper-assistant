from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    created_at: datetime


class MeResponse(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    auth_mode: str = "session"
