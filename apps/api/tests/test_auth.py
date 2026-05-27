from __future__ import annotations

import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import User, UserSession


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@pytest.mark.asyncio
async def test_register_success():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    user = User(
        user_id="testuser_abcd1234",
        email="new@example.com",
        password_hash="$argon2id$mock",
        display_name="New User",
        is_active=True,
    )
    mock_repo.get_by_email = AsyncMock(return_value=None)
    mock_repo.get_by_user_id = AsyncMock(return_value=None)
    mock_repo.create_user = AsyncMock(return_value=user)

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        with patch("pwdlib.PasswordHash") as mock_ph:
            mock_ph.recommended.return_value.hash.return_value = "$argon2id$mock"
            result = await service.register("new@example.com", "password123", "New User")

    assert result.user_id
    assert result.email == "new@example.com"
    assert result.password_hash != "password123"


@pytest.mark.asyncio
async def test_register_duplicate_email():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    existing = User(user_id="existing", email="dup@example.com", password_hash="x", is_active=True)
    mock_repo.get_by_email = AsyncMock(return_value=existing)

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        with pytest.raises(ValueError, match="already registered"):
            await service.register("dup@example.com", "password123")


@pytest.mark.asyncio
async def test_register_password_too_short():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_by_email = AsyncMock(return_value=None)

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        with pytest.raises(ValueError, match="at least 8"):
            await service.register("short@example.com", "1234567")


@pytest.mark.asyncio
async def test_login_success():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    user = User(user_id="testuser", email="test@example.com", password_hash="$argon2id$mock", is_active=True)
    mock_repo.get_by_email = AsyncMock(return_value=user)
    mock_repo.create_session = AsyncMock()

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        with patch("pwdlib.PasswordHash") as mock_ph:
            mock_ph.recommended.return_value.verify.return_value = True
            result_user, token = await service.login("test@example.com", "password123")

    assert result_user.email == "test@example.com"
    assert len(token) > 20


@pytest.mark.asyncio
async def test_login_wrong_password():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    user = User(user_id="testuser", email="test@example.com", password_hash="$argon2id$mock", is_active=True)
    mock_repo.get_by_email = AsyncMock(return_value=user)

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        with patch("pwdlib.PasswordHash") as mock_ph:
            mock_ph.recommended.return_value.verify.return_value = False
            with pytest.raises(ValueError, match="Invalid credentials"):
                await service.login("test@example.com", "wrongpassword")


@pytest.mark.asyncio
async def test_login_nonexistent_email():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_by_email = AsyncMock(return_value=None)

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        with pytest.raises(ValueError, match="Invalid credentials"):
            await service.login("nobody@example.com", "password123")


@pytest.mark.asyncio
async def test_logout_revokes_session():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.revoke_session = AsyncMock(return_value=True)

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        result = await service.logout("some_token")

    assert result is True


@pytest.mark.asyncio
async def test_session_expired():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    expired_session = UserSession(
        session_token_hash=_hash_token("expired_token"),
        user_id="testuser",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    mock_repo.get_session_by_token_hash = AsyncMock(return_value=expired_session)

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        user = await service.get_user_from_session("expired_token")

    assert user is None


@pytest.mark.asyncio
async def test_revoked_session():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    revoked_session = UserSession(
        session_token_hash=_hash_token("revoked_token"),
        user_id="testuser",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        revoked_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    mock_repo.get_session_by_token_hash = AsyncMock(return_value=revoked_session)

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        user = await service.get_user_from_session("revoked_token")

    assert user is None


@pytest.mark.asyncio
async def test_valid_session():
    from app.services.auth_service import AuthService
    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    valid_session = UserSession(
        session_token_hash=_hash_token("valid_token"),
        user_id="testuser",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    user = User(user_id="testuser", email="test@example.com", password_hash="x", is_active=True)
    mock_repo.get_session_by_token_hash = AsyncMock(return_value=valid_session)
    mock_repo.get_by_user_id = AsyncMock(return_value=user)

    with patch("app.services.auth_service.UserRepository", return_value=mock_repo):
        service = AuthService(mock_db)
        result = await service.get_user_from_session("valid_token")

    assert result is not None
    assert result.user_id == "testuser"


def test_password_hash_not_plain():
    from pwdlib import PasswordHash
    ph = PasswordHash.recommended()
    hashed = ph.hash("mypassword123")
    assert hashed != "mypassword123"
    assert hashed.startswith("$")


def test_session_token_hashed():
    token = "my_secret_token_abc123"
    token_hash = _hash_token(token)
    assert token_hash != token
    assert len(token_hash) == 64


def test_production_check_auth_enabled_with_dev_header_warns():
    from scripts.production_check import _check_auth_config
    with patch("app.config.settings") as mock_settings, \
         patch("scripts.production_check.settings", mock_settings):
        mock_settings.AUTH_ENABLED = True
        mock_settings.ALLOW_DEV_USER_HEADER = True
        mock_settings.REAL_MODEL_REQUIRED = False
        mock_settings.ENV = "development"
        mock_settings.SESSION_COOKIE_SECURE = True
        mock_settings.SESSION_TTL_SECONDS = 604800
        result = _check_auth_config()
        assert result.status == "WARN"
        assert "ALLOW_DEV_USER_HEADER" in result.message


def test_production_check_auth_enabled_with_dev_header_real_model_fails():
    from scripts.production_check import _check_auth_config
    with patch("app.config.settings") as mock_settings, \
         patch("scripts.production_check.settings", mock_settings):
        mock_settings.AUTH_ENABLED = True
        mock_settings.ALLOW_DEV_USER_HEADER = True
        mock_settings.REAL_MODEL_REQUIRED = True
        mock_settings.ENV = "production"
        mock_settings.SESSION_COOKIE_SECURE = True
        mock_settings.SESSION_TTL_SECONDS = 604800
        result = _check_auth_config()
        assert result.status == "FAIL"


def test_production_check_auth_disabled_warns():
    from scripts.production_check import _check_auth_config
    with patch("app.config.settings") as mock_settings, \
         patch("scripts.production_check.settings", mock_settings):
        mock_settings.AUTH_ENABLED = False
        mock_settings.REAL_MODEL_REQUIRED = False
        mock_settings.ENV = "development"
        result = _check_auth_config()
        assert result.status == "WARN"


def test_production_check_auth_cookie_secure_false_warns():
    from scripts.production_check import _check_auth_config
    with patch("app.config.settings") as mock_settings, \
         patch("scripts.production_check.settings", mock_settings):
        mock_settings.AUTH_ENABLED = True
        mock_settings.ALLOW_DEV_USER_HEADER = False
        mock_settings.REAL_MODEL_REQUIRED = False
        mock_settings.ENV = "development"
        mock_settings.SESSION_COOKIE_SECURE = False
        mock_settings.SESSION_TTL_SECONDS = 604800
        result = _check_auth_config()
        assert result.status == "WARN"
        assert "SECURE" in result.message


def test_production_check_auth_session_ttl_zero_fails():
    from scripts.production_check import _check_auth_config
    with patch("app.config.settings") as mock_settings, \
         patch("scripts.production_check.settings", mock_settings):
        mock_settings.AUTH_ENABLED = True
        mock_settings.ALLOW_DEV_USER_HEADER = False
        mock_settings.REAL_MODEL_REQUIRED = False
        mock_settings.ENV = "development"
        mock_settings.SESSION_COOKIE_SECURE = True
        mock_settings.SESSION_TTL_SECONDS = 0
        result = _check_auth_config()
        assert result.status == "FAIL"


def test_production_check_auth_passes_when_configured():
    from scripts.production_check import _check_auth_config
    with patch("app.config.settings") as mock_settings, \
         patch("scripts.production_check.settings", mock_settings):
        mock_settings.AUTH_ENABLED = True
        mock_settings.ALLOW_DEV_USER_HEADER = False
        mock_settings.REAL_MODEL_REQUIRED = False
        mock_settings.ENV = "development"
        mock_settings.SESSION_COOKIE_SECURE = True
        mock_settings.SESSION_TTL_SECONDS = 604800
        result = _check_auth_config()
        assert result.status == "PASS"
