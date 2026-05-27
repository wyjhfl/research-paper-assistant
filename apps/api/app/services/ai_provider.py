from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from abc import ABC, abstractmethod

import httpx
import numpy as np

from ..config import settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_SENSITIVE_KEYS = {"api_key", "secret", "token", "database_url"}


class ProviderConfigurationError(Exception):
    pass


class ProviderRequestError(Exception):
    pass


class ProviderResponseError(Exception):
    pass


class EmbeddingDimensionError(Exception):
    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Embedding dimension mismatch: expected {expected}, got {actual}"
        )


def _sanitize_error_message(msg: str) -> str:
    msg = re.sub(
        r'(Bearer\s+)\S+',
        r'\1***REDACTED***',
        msg,
        flags=re.IGNORECASE,
    )
    msg = re.sub(
        r'\bsk-[A-Za-z0-9]{8,}',
        'sk-***REDACTED***',
        msg,
    )
    msg = re.sub(
        r'\btp-[A-Za-z0-9]{8,}',
        'tp-***REDACTED***',
        msg,
    )
    msg = re.sub(
        r'postgresql\+asyncpg://\S+',
        'postgresql+asyncpg://***REDACTED***',
        msg,
        flags=re.IGNORECASE,
    )
    for key in _SENSITIVE_KEYS:
        pattern = re.compile(
            rf'\b{re.escape(key)}\s*[=:]\s*\S+', re.IGNORECASE
        )
        msg = pattern.sub(f'{key}=***REDACTED***', msg)
    return msg


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def get_dimension(self) -> int:
        ...


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    lowered = text.lower()
    ascii_words = re.findall(r"[a-z0-9]+", lowered)
    tokens.extend(ascii_words)
    non_ascii = re.sub(r"[a-z0-9\s]", "", lowered)
    for i in range(len(non_ascii) - 1):
        tokens.append(non_ascii[i] + non_ascii[i + 1])
    if len(non_ascii) == 1:
        tokens.append(non_ascii[0])
    return tokens


class LocalHashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 384):
        self._dimension = dimension

    def get_dimension(self) -> int:
        return self._dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            vec = np.zeros(self._dimension, dtype=np.float32)
            tokens = _tokenize(text)
            for token in tokens:
                h = hashlib.md5(token.encode("utf-8")).digest()
                idx = int.from_bytes(h[:4], "big") % self._dimension
                sign_bit = h[4] & 1
                vec[idx] += 1.0 if sign_bit else -1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(vec.tolist())
        return results


async def _request_with_retry(
    *,
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    payload: dict,
    provider_name: str,
    model: str,
    max_retries: int | None = None,
    backoff_seconds: float | None = None,
) -> httpx.Response:
    if max_retries is None:
        max_retries = settings.PROVIDER_MAX_RETRIES
    if backoff_seconds is None:
        backoff_seconds = settings.PROVIDER_RETRY_BACKOFF_SECONDS

    last_status_code: int | None = None

    for attempt in range(1 + max_retries):
        try:
            resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code in _RETRYABLE_STATUS_CODES:
                last_status_code = resp.status_code
                if attempt < max_retries:
                    logger.warning(
                        "provider request retryable error",
                        extra={
                            "provider": provider_name,
                            "model": model,
                            "status_code": resp.status_code,
                            "attempt": attempt + 1,
                            "error_type": "retryable_http",
                        },
                    )
                    await asyncio.sleep(backoff_seconds * (attempt + 1))
                    continue
                logger.error(
                    "provider request retryable error, max retries exceeded",
                    extra={
                        "provider": provider_name,
                        "model": model,
                        "status_code": resp.status_code,
                        "attempt": attempt + 1,
                        "error_type": "retryable_http_exhausted",
                    },
                )
                raise ProviderRequestError(
                    _sanitize_error_message(
                        f"{provider_name} API retryable error exhausted: "
                        f"provider={provider_name}, status_code={resp.status_code}, "
                        f"attempts={attempt + 1}"
                    )
                )

            if resp.status_code in (401, 403):
                logger.warning(
                    "provider request auth error",
                    extra={
                        "provider": provider_name,
                        "model": model,
                        "status_code": resp.status_code,
                        "attempt": attempt + 1,
                        "error_type": "auth_error",
                    },
                )
                raise ProviderRequestError(
                    _sanitize_error_message(
                        f"{provider_name} API auth error: status {resp.status_code}"
                    )
                )

            if resp.status_code == 400:
                raise ProviderRequestError(
                    _sanitize_error_message(
                        f"{provider_name} API bad request: status {resp.status_code}"
                    )
                )

            if resp.status_code == 404:
                raise ProviderRequestError(
                    _sanitize_error_message(
                        f"{provider_name} API not found: status {resp.status_code}"
                    )
                )

            return resp

        except httpx.TimeoutException as exc:
            if attempt < max_retries:
                logger.warning(
                    "provider request timeout, retrying",
                    extra={
                        "provider": provider_name,
                        "model": model,
                        "status_code": None,
                        "attempt": attempt + 1,
                        "error_type": "timeout",
                    },
                )
                await asyncio.sleep(backoff_seconds * (attempt + 1))
                continue
            logger.error(
                "provider request timeout, max retries exceeded",
                extra={
                    "provider": provider_name,
                    "model": model,
                    "status_code": None,
                    "attempt": attempt + 1,
                    "error_type": "timeout",
                },
            )
            raise ProviderRequestError(
                _sanitize_error_message(
                    f"{provider_name} API request timed out: "
                    f"provider={provider_name}, attempts={attempt + 1}"
                )
            ) from exc

        except httpx.RequestError as exc:
            if attempt < max_retries:
                logger.warning(
                    "provider request connection error, retrying",
                    extra={
                        "provider": provider_name,
                        "model": model,
                        "status_code": None,
                        "attempt": attempt + 1,
                        "error_type": "connection_error",
                    },
                )
                await asyncio.sleep(backoff_seconds * (attempt + 1))
                continue
            logger.error(
                "provider request failed, max retries exceeded",
                extra={
                    "provider": provider_name,
                    "model": model,
                    "status_code": None,
                    "attempt": attempt + 1,
                    "error_type": "connection_error",
                },
            )
            raise ProviderRequestError(
                _sanitize_error_message(
                    f"{provider_name} API request failed: "
                    f"provider={provider_name}, attempts={attempt + 1}"
                )
            ) from exc

    raise ProviderRequestError(
        _sanitize_error_message(
            f"{provider_name} API request failed: "
            f"provider={provider_name}, status_code={last_status_code}, "
            f"attempts={1 + max_retries}"
        )
    )


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        dimension: int = 384,
        timeout: int = 30,
        max_retries: int | None = None,
        backoff_seconds: float | None = None,
    ):
        if not api_key:
            raise ProviderConfigurationError(
                "EMBEDDING_API_KEY is required for openai_compatible provider"
            )
        if not base_url:
            raise ProviderConfigurationError(
                "EMBEDDING_BASE_URL is required for openai_compatible provider"
            )
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._dimension = dimension
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    def get_dimension(self) -> int:
        return self._dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "input": texts,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await _request_with_retry(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                provider_name="Embedding",
                model=self._model,
                max_retries=self._max_retries,
                backoff_seconds=self._backoff_seconds,
            )

        if resp.status_code != 200:
            raise ProviderRequestError(
                _sanitize_error_message(
                    f"Embedding API returned status {resp.status_code}"
                )
            )

        try:
            data = resp.json()
        except Exception:
            raise ProviderResponseError("Embedding API returned invalid JSON")

        try:
            embedding_data = data["data"]
        except (KeyError, TypeError):
            raise ProviderResponseError("Embedding API response missing 'data' field")

        if len(embedding_data) != len(texts):
            raise ProviderResponseError(
                f"Embedding API returned {len(embedding_data)} embeddings for {len(texts)} inputs"
            )

        results: list[list[float]] = []
        for item in embedding_data:
            emb = item.get("embedding", [])
            if len(emb) != self._dimension:
                raise EmbeddingDimensionError(self._dimension, len(emb))
            results.append(emb)

        return results


class LLMProvider(ABC):
    @abstractmethod
    async def generate_answer(self, question: str, contexts: list[str]) -> str:
        ...


class LocalMockLLMProvider(LLMProvider):
    async def generate_answer(self, question: str, contexts: list[str]) -> str:
        if not contexts:
            return "未找到与问题相关的论文内容，无法生成回答。"
        context_summary = "\n---\n".join(contexts[:3])
        return (
            f"基于检索到的 {len(contexts)} 个相关片段，以下是参考信息摘要：\n\n"
            f"{context_summary}\n\n"
            f"（注：当前使用本地占位 LLM，回答仅为检索片段拼接，不代表真实模型效果。）"
        )


class OpenAICompatibleLLMProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        timeout: int = 30,
        max_retries: int | None = None,
        backoff_seconds: float | None = None,
    ):
        if not api_key:
            raise ProviderConfigurationError(
                "LLM_API_KEY is required for openai_compatible provider"
            )
        if not base_url:
            raise ProviderConfigurationError(
                "LLM_BASE_URL is required for openai_compatible provider"
            )
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def generate_answer(self, question: str, contexts: list[str]) -> str:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        context_text = "\n\n".join(
            f"[Source {i + 1}]: {ctx}" for i, ctx in enumerate(contexts)
        )
        system_prompt = (
            "You are a research paper assistant. Answer the user's question "
            "based ONLY on the provided source contexts. "
            "If the sources are insufficient to answer, clearly state that. "
            "Do not fabricate citations. Reference page/chunk info when available."
        )
        user_content = f"Sources:\n{context_text}\n\nQuestion: {question}"

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await _request_with_retry(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
                provider_name="LLM",
                model=self._model,
                max_retries=self._max_retries,
                backoff_seconds=self._backoff_seconds,
            )

        if resp.status_code != 200:
            raise ProviderRequestError(
                _sanitize_error_message(
                    f"LLM API returned status {resp.status_code}"
                )
            )

        try:
            data = resp.json()
        except Exception:
            raise ProviderResponseError("LLM API returned invalid JSON")

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, TypeError, IndexError):
            raise ProviderResponseError("LLM API response missing content")

        if not content or not content.strip():
            raise ProviderResponseError("LLM API returned empty content")

        return content.strip()


def get_embedding_provider() -> EmbeddingProvider:
    if settings.EMBEDDING_PROVIDER == "local":
        return LocalHashEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)
    if settings.EMBEDDING_PROVIDER == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.EMBEDDING_API_KEY,
            base_url=settings.EMBEDDING_BASE_URL,
            dimension=settings.EMBEDDING_DIMENSION,
            timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
        )
    raise ProviderConfigurationError(
        f"Unknown embedding provider: {settings.EMBEDDING_PROVIDER}"
    )


def get_llm_provider() -> LLMProvider:
    if settings.LLM_PROVIDER == "local":
        return LocalMockLLMProvider()
    if settings.LLM_PROVIDER == "openai_compatible":
        return OpenAICompatibleLLMProvider(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
    raise ProviderConfigurationError(
        f"Unknown LLM provider: {settings.LLM_PROVIDER}"
    )
