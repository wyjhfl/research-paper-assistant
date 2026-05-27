from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session
from ..models import ModelCallEvent

logger = logging.getLogger(__name__)

_METADATA_ALLOWED_KEYS = frozenset({
    "paper_id", "agent_task_type", "eval_case_id",
    "chunk_count", "query_length", "context_count",
    "paper_ids", "idea_count",
})

_SANITIZE_PATTERNS = [
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer ***REDACTED***"),
    (re.compile(r"\bsk-[A-Za-z0-9]{8,}"), "sk-***REDACTED***"),
    (re.compile(r"\btp-[A-Za-z0-9]{8,}"), "tp-***REDACTED***"),
    (re.compile(r"postgresql\+asyncpg://\S+", re.IGNORECASE), "postgresql+asyncpg://***REDACTED***"),
    (re.compile(r"\bapi_key\s*[=:]\s*\S+", re.IGNORECASE), "api_key=***REDACTED***"),
    (re.compile(r"\bauthorization\s*[=:]\s*\S+", re.IGNORECASE), "authorization=***REDACTED***"),
    (re.compile(r"\bsecret\s*[=:]\s*\S+", re.IGNORECASE), "secret=***REDACTED***"),
    (re.compile(r"\btoken\s*[=:]\s*\S+", re.IGNORECASE), "token=***REDACTED***"),
    (re.compile(r"\bdatabase_url\s*[=:]\s*\S+", re.IGNORECASE), "database_url=***REDACTED***"),
]

_MAX_ERROR_MESSAGE_LEN = 300

_session_factory = async_session


def set_audit_session_factory(factory):
    global _session_factory
    _session_factory = factory


def get_audit_session_factory():
    return _session_factory


def safe_error_message(error: BaseException | str) -> str:
    msg = str(error)
    for pattern, replacement in _SANITIZE_PATTERNS:
        msg = pattern.sub(replacement, msg)
    if len(msg) > _MAX_ERROR_MESSAGE_LEN:
        msg = msg[:_MAX_ERROR_MESSAGE_LEN - 3] + "..."
    return msg


def safe_metadata(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    filtered = {k: v for k, v in metadata.items() if k in _METADATA_ALLOWED_KEYS}
    if not filtered:
        return None
    return json.dumps(filtered, ensure_ascii=False, default=str)


async def _write_audit_event(event: ModelCallEvent) -> None:
    factory = get_audit_session_factory()
    async with factory() as session:
        session.add(event)
        await session.commit()


async def record_model_call(
    *,
    user_id: str | None = "default",
    operation: str,
    provider: str,
    model: str,
    status: str,
    duration_ms: int,
    input_count: int = 0,
    input_chars: int = 0,
    output_chars: int = 0,
    error_type: str | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        sanitized_error = safe_error_message(error_message) if error_message else None
        event = ModelCallEvent(
            user_id=user_id,
            operation=operation,
            provider=provider,
            model=model,
            status=status,
            duration_ms=duration_ms,
            input_count=input_count,
            input_chars=input_chars,
            output_chars=output_chars,
            error_type=error_type,
            error_message=sanitized_error,
            metadata_json=safe_metadata(metadata),
        )
        await _write_audit_event(event)
    except Exception as exc:
        logger.warning(
            "Failed to record model call audit event: %s: %s",
            type(exc).__name__,
            safe_error_message(exc),
        )
