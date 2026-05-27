from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def generate_manifest(
    db_backup_file: str,
    storage_backup_file: str,
    eval_backup_file: str,
    app_version: str,
    embedding_dimension: int,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "Z"
    return {
        "timestamp": timestamp,
        "db_backup_file": db_backup_file,
        "storage_backup_file": storage_backup_file,
        "eval_backup_file": eval_backup_file,
        "app_version": app_version,
        "embedding_dimension": embedding_dimension,
    }


_SENSITIVE_KEYS = {
    "api_key", "secret", "token", "authorization",
    "database_url", "password",
}


def manifest_has_secrets(manifest: dict[str, Any]) -> bool:
    for key, value in manifest.items():
        key_lower = key.lower()
        for sk in _SENSITIVE_KEYS:
            if sk in key_lower:
                return True
        if isinstance(value, str):
            for pattern in ("postgresql+asyncpg://", "sk-", "tp-"):
                if pattern in value:
                    return True
    return False
