import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient, Response

from app.main import app
from app.config import settings
from app.services.ai_provider import (
    LocalHashEmbeddingProvider,
    LocalMockLLMProvider,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleLLMProvider,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    EmbeddingDimensionError,
    _sanitize_error_message,
    _request_with_retry,
    get_embedding_provider,
    get_llm_provider,
)
from app.services.model_call_audit_service import set_audit_session_factory, get_audit_session_factory
from app.models import ModelCallEvent


def _make_mock_client(responses):
    call_count = 0

    async def _post(*args, **kwargs):
        nonlocal call_count
        resp = responses[call_count] if call_count < len(responses) else responses[-1]
        call_count += 1
        return resp

    mock_client = AsyncMock()
    mock_client.post = _post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _make_200_response(json_data):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = json_data
    return mock_response


def _make_status_response(status_code):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    return mock_response


@pytest.mark.asyncio
async def test_local_embedding_provider_still_works():
    provider = LocalHashEmbeddingProvider(dimension=384)
    result = await provider.embed_texts(["hello world"])
    assert len(result) == 1
    assert len(result[0]) == 384
    assert provider.get_dimension() == 384


@pytest.mark.asyncio
async def test_local_llm_provider_still_works():
    provider = LocalMockLLMProvider()
    result = await provider.generate_answer("What is X?", ["X is a variable"])
    assert "1" in result
    assert "X is a variable" in result


@pytest.mark.asyncio
async def test_openai_compatible_embedding_with_mock_httpx():
    dim = 4
    mock_client = _make_mock_client([
        _make_200_response({
            "data": [
                {"embedding": [0.1, 0.2, 0.3, 0.4]},
                {"embedding": [0.5, 0.6, 0.7, 0.8]},
            ]
        })
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=dim,
                timeout=30,
            )
            result = await provider.embed_texts(["hello", "world"])
            assert len(result) == 2
            assert len(result[0]) == dim
            assert result[0] == [0.1, 0.2, 0.3, 0.4]


@pytest.mark.asyncio
async def test_openai_compatible_embedding_dimension_mismatch():
    mock_client = _make_mock_client([
        _make_200_response({
            "data": [
                {"embedding": [0.1, 0.2, 0.3]},
            ]
        })
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=4,
            )
            with pytest.raises(EmbeddingDimensionError) as exc_info:
                await provider.embed_texts(["hello"])
            assert exc_info.value.expected == 4
            assert exc_info.value.actual == 3


@pytest.mark.asyncio
async def test_openai_compatible_llm_with_mock_httpx():
    mock_client = _make_mock_client([
        _make_200_response({
            "choices": [
                {
                    "message": {
                        "content": "Based on the sources, X is a variable used in mathematics."
                    }
                }
            ]
        })
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
            )
            result = await provider.generate_answer("What is X?", ["X is a variable"])
            assert "X is a variable" in result or "mathematics" in result


@pytest.mark.asyncio
async def test_openai_compatible_embedding_missing_api_key():
    with pytest.raises(ProviderConfigurationError):
        OpenAICompatibleEmbeddingProvider(
            model="text-embedding-3-small",
            api_key="",
            base_url="https://api.example.com/v1",
        )


@pytest.mark.asyncio
async def test_openai_compatible_llm_missing_api_key():
    with pytest.raises(ProviderConfigurationError):
        OpenAICompatibleLLMProvider(
            model="gpt-4",
            api_key="",
            base_url="https://api.example.com/v1",
        )


@pytest.mark.asyncio
async def test_openai_compatible_embedding_missing_base_url():
    with pytest.raises(ProviderConfigurationError):
        OpenAICompatibleEmbeddingProvider(
            model="text-embedding-3-small",
            api_key="test-key",
            base_url="",
        )


@pytest.mark.asyncio
async def test_openai_compatible_llm_missing_base_url():
    with pytest.raises(ProviderConfigurationError):
        OpenAICompatibleLLMProvider(
            model="gpt-4",
            api_key="test-key",
            base_url="",
        )


@pytest.mark.asyncio
async def test_openai_compatible_embedding_timeout():
    import httpx

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=4,
            )
            with pytest.raises(ProviderRequestError, match="timed out"):
                await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_compatible_llm_timeout():
    import httpx

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
            )
            with pytest.raises(ProviderRequestError, match="timed out"):
                await provider.generate_answer("What is X?", ["X is a variable"])


@pytest.mark.asyncio
async def test_openai_compatible_embedding_non_200():
    mock_client = _make_mock_client([
        _make_status_response(500),
        _make_status_response(500),
        _make_status_response(500),
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=4,
            )
            with pytest.raises(ProviderRequestError, match="retryable error exhausted"):
                await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_compatible_llm_empty_content():
    mock_client = _make_mock_client([
        _make_200_response({
            "choices": [
                {
                    "message": {
                        "content": ""
                    }
                }
            ]
        })
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
            )
            with pytest.raises(ProviderResponseError, match="empty content"):
                await provider.generate_answer("What is X?", ["X is a variable"])


@pytest.mark.asyncio
async def test_provider_errors_do_not_leak_api_key():
    try:
        provider = OpenAICompatibleEmbeddingProvider(
            model="text-embedding-3-small",
            api_key="sk-secret-key-12345",
            base_url="https://api.example.com/v1",
            dimension=4,
        )
        import httpx
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("connection failed to https://api.example.com with key sk-secret-key-12345"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
            with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(ProviderRequestError) as exc_info:
                    await provider.embed_texts(["hello"])
                error_str = str(exc_info.value)
                assert "sk-secret-key-12345" not in error_str
                assert "Authorization" not in error_str
    except ProviderConfigurationError:
        pass


@pytest.mark.asyncio
async def test_mcp_recommend_citations_provider_error_no_leak():
    from app.mcp.tools import tool_recommend_citations

    with patch("app.mcp.tools.RAGService") as mock_rag_cls:
        mock_rag = AsyncMock()
        mock_rag.ask.side_effect = ProviderRequestError("API key sk-leaked-key is invalid")
        mock_rag_cls.return_value = mock_rag

        with patch("app.mcp.tools.PaperRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_paper = MagicMock()
            mock_paper.id = 1
            mock_repo.get_paper = AsyncMock(return_value=mock_paper)
            mock_repo_cls.return_value = mock_repo

            result = await tool_recommend_citations(
                draft_text="test query",
                paper_id=1,
            )
    assert "error" in result
    assert "internal_error" in result["error"]
    error_str = str(result)
    assert "sk-leaked-key" not in error_str
    assert "Authorization" not in error_str


@pytest.mark.asyncio
async def test_get_embedding_provider_local_default():
    provider = get_embedding_provider()
    assert isinstance(provider, LocalHashEmbeddingProvider)


@pytest.mark.asyncio
async def test_get_llm_provider_local_default():
    provider = get_llm_provider()
    assert isinstance(provider, LocalMockLLMProvider)


@pytest.mark.asyncio
async def test_get_embedding_provider_unknown_raises():
    with patch.object(settings, "EMBEDDING_PROVIDER", "unknown_provider"):
        with pytest.raises(ProviderConfigurationError):
            get_embedding_provider()


@pytest.mark.asyncio
async def test_get_llm_provider_unknown_raises():
    with patch.object(settings, "LLM_PROVIDER", "unknown_provider"):
        with pytest.raises(ProviderConfigurationError):
            get_llm_provider()


@pytest.mark.asyncio
async def test_openai_compatible_embedding_fewer_results_than_inputs():
    mock_client = _make_mock_client([
        _make_200_response({
            "data": [
                {"embedding": [0.1, 0.2, 0.3, 0.4]},
            ]
        })
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=4,
            )
            with pytest.raises(ProviderResponseError, match="1 embeddings for 2 inputs"):
                await provider.embed_texts(["hello", "world"])


@pytest.mark.asyncio
async def test_openai_compatible_embedding_more_results_than_inputs():
    mock_client = _make_mock_client([
        _make_200_response({
            "data": [
                {"embedding": [0.1, 0.2, 0.3, 0.4]},
                {"embedding": [0.5, 0.6, 0.7, 0.8]},
                {"embedding": [0.9, 1.0, 1.1, 1.2]},
            ]
        })
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=4,
            )
            with pytest.raises(ProviderResponseError, match="3 embeddings for 1 inputs"):
                await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_embedding_service_count_mismatch_does_not_write():
    from app.services.embedding_service import EmbeddingService
    from app.models import PaperChunk

    mock_provider = AsyncMock()
    mock_provider.embed_texts = AsyncMock(return_value=[[0.1] * 384])

    mock_chunk = MagicMock(spec=PaperChunk)
    mock_chunk.text = "some text"
    mock_chunk.embedding = None

    mock_repo = AsyncMock()
    mock_repo.get_chunks_without_embedding = AsyncMock(return_value=[mock_chunk, mock_chunk])

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    mock_audit_session = AsyncMock()
    mock_audit_session.add = MagicMock()
    mock_audit_session.commit = AsyncMock()
    mock_audit_session.__aenter__ = AsyncMock(return_value=mock_audit_session)
    mock_audit_session.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_audit_session)
    original_factory = get_audit_session_factory()

    with patch("app.services.embedding_service.get_embedding_provider", return_value=mock_provider):
        try:
            set_audit_session_factory(mock_factory)
            svc = EmbeddingService(mock_session)
            svc.repo = mock_repo
            with pytest.raises(ProviderResponseError, match="1 embeddings for 2 chunks"):
                await svc.embed_chunks_for_paper(paper_id=1)
        finally:
            set_audit_session_factory(original_factory)

    audit_calls = [c[0][0] for c in mock_audit_session.add.call_args_list if isinstance(c[0][0], ModelCallEvent)]
    for event in audit_calls:
        assert event.status == "success"


@pytest.mark.asyncio
async def test_llm_timeout_retries_then_succeeds():
    import httpx

    success_resp = _make_200_response({
        "choices": [{"message": {"content": "success answer"}}]
    })
    call_count = 0

    async def _post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            raise httpx.TimeoutException("timeout")
        return success_resp

    mock_client = AsyncMock()
    mock_client.post = _post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                max_retries=2,
                backoff_seconds=0.01,
            )
            result = await provider.generate_answer("What is X?", ["X is a variable"])
            assert result == "success answer"
            assert call_count == 2


@pytest.mark.asyncio
async def test_embedding_429_retries_then_succeeds():
    dim = 4
    responses = [
        _make_status_response(429),
        _make_200_response({
            "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}]
        }),
    ]
    mock_client = _make_mock_client(responses)

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=dim,
                max_retries=2,
                backoff_seconds=0.01,
            )
            result = await provider.embed_texts(["hello"])
            assert len(result) == 1
            assert result[0] == [0.1, 0.2, 0.3, 0.4]


@pytest.mark.asyncio
async def test_401_not_retried():
    call_count = 0

    async def _post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _make_status_response(401)

    mock_client = AsyncMock()
    mock_client.post = _post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                max_retries=2,
                backoff_seconds=0.01,
            )
            with pytest.raises(ProviderRequestError, match="auth error"):
                await provider.generate_answer("What is X?", ["X is a variable"])

    assert call_count == 1


@pytest.mark.asyncio
async def test_403_not_retried():
    call_count = 0

    async def _post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _make_status_response(403)

    mock_client = AsyncMock()
    mock_client.post = _post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=4,
                max_retries=2,
                backoff_seconds=0.01,
            )
            with pytest.raises(ProviderRequestError, match="auth error"):
                await provider.embed_texts(["hello"])

    assert call_count == 1


@pytest.mark.asyncio
async def test_5xx_exceeds_max_retries():
    mock_client = _make_mock_client([
        _make_status_response(503),
        _make_status_response(503),
        _make_status_response(503),
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                max_retries=2,
                backoff_seconds=0.01,
            )
            with pytest.raises(ProviderRequestError, match="retryable error exhausted"):
                await provider.generate_answer("What is X?", ["X is a variable"])


@pytest.mark.asyncio
async def test_response_missing_content_returns_provider_response_error():
    mock_client = _make_mock_client([
        _make_200_response({"choices": []}),
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
            )
            with pytest.raises(ProviderResponseError, match="missing content"):
                await provider.generate_answer("What is X?", ["X is a variable"])


@pytest.mark.asyncio
async def test_embedding_count_mismatch_still_provider_response_error():
    mock_client = _make_mock_client([
        _make_200_response({
            "data": [
                {"embedding": [0.1, 0.2, 0.3, 0.4]},
            ]
        })
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=4,
                max_retries=2,
                backoff_seconds=0.01,
            )
            with pytest.raises(ProviderResponseError, match="1 embeddings for 2 inputs"):
                await provider.embed_texts(["hello", "world"])


@pytest.mark.asyncio
async def test_error_message_does_not_leak_api_key_or_authorization():
    provider = OpenAICompatibleLLMProvider(
        model="gpt-4",
        api_key="sk-super-secret-key-999",
        base_url="https://api.example.com/v1",
        max_retries=0,
    )
    import httpx
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.RequestError(
        "connection failed, api_key=sk-super-secret-key-999 Authorization: Bearer sk-super-secret-key-999"
    ))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ProviderRequestError) as exc_info:
            await provider.generate_answer("What is X?", ["X is a variable"])
        error_str = str(exc_info.value)
        assert "sk-super-secret-key-999" not in error_str
        assert "Authorization" not in error_str or "***REDACTED***" in error_str


@pytest.mark.asyncio
async def test_retry_count_matches_provider_max_retries():
    import httpx

    call_count = 0

    async def _post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.TimeoutException("timeout")

    mock_client = AsyncMock()
    mock_client.post = _post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                max_retries=3,
                backoff_seconds=0.01,
            )
            with pytest.raises(ProviderRequestError):
                await provider.generate_answer("What is X?", ["X is a variable"])
            assert call_count == 4


@pytest.mark.asyncio
async def test_local_provider_not_affected_by_retry_config():
    provider = LocalMockLLMProvider()
    result = await provider.generate_answer("What is X?", ["X is a variable"])
    assert "1" in result

    emb_provider = LocalHashEmbeddingProvider(dimension=384)
    result = await emb_provider.embed_texts(["hello"])
    assert len(result) == 1
    assert len(result[0]) == 384


@pytest.mark.asyncio
async def test_sanitize_error_message_redacts_sensitive_keys():
    msg = "error with api_key=sk-12345 and Authorization: Bearer token-xyz"
    sanitized = _sanitize_error_message(msg)
    assert "sk-12345" not in sanitized
    assert "token-xyz" not in sanitized
    assert "***REDACTED***" in sanitized


@pytest.mark.asyncio
async def test_retryable_429_exhausted_raises_provider_request_error():
    mock_client = _make_mock_client([
        _make_status_response(429),
        _make_status_response(429),
        _make_status_response(429),
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                max_retries=2,
                backoff_seconds=0.01,
            )
            with pytest.raises(ProviderRequestError, match="retryable error exhausted") as exc_info:
                await provider.generate_answer("What is X?", ["X is a variable"])
            error_str = str(exc_info.value)
            assert "status_code=429" in error_str
            assert "attempts=3" in error_str


@pytest.mark.asyncio
async def test_429_exhausted_does_not_return_response():
    mock_client = _make_mock_client([
        _make_status_response(429),
        _make_status_response(429),
        _make_status_response(429),
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                dimension=4,
                max_retries=2,
                backoff_seconds=0.01,
            )
            with pytest.raises(ProviderRequestError, match="retryable error exhausted"):
                await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_5xx_exhausted_does_not_return_response():
    mock_client = _make_mock_client([
        _make_status_response(500),
        _make_status_response(500),
        _make_status_response(500),
    ])

    with patch("app.services.ai_provider.httpx.AsyncClient", return_value=mock_client):
        with patch("app.services.ai_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = OpenAICompatibleLLMProvider(
                model="gpt-4",
                api_key="test-key",
                base_url="https://api.example.com/v1",
                max_retries=2,
                backoff_seconds=0.01,
            )
            with pytest.raises(ProviderRequestError, match="retryable error exhausted"):
                await provider.generate_answer("What is X?", ["X is a variable"])


@pytest.mark.asyncio
async def test_sanitize_redacts_bare_sk_token():
    msg = "error caused by sk-abcdefghijklmnop1234567890"
    sanitized = _sanitize_error_message(msg)
    assert "sk-abcdefghijklmnop1234567890" not in sanitized
    assert "sk-***REDACTED***" in sanitized


@pytest.mark.asyncio
async def test_sanitize_redacts_bare_tp_token():
    msg = "failed with tp-xyzABCDEF1234567890abcdef"
    sanitized = _sanitize_error_message(msg)
    assert "tp-xyzABCDEF1234567890abcdef" not in sanitized
    assert "tp-***REDACTED***" in sanitized


@pytest.mark.asyncio
async def test_sanitize_redacts_authorization_bearer():
    msg = "Authorization: Bearer sk-abcdefghijklmnop1234567890"
    sanitized = _sanitize_error_message(msg)
    assert "sk-abcdefghijklmnop1234567890" not in sanitized
    assert "Bearer" in sanitized
    assert "***REDACTED***" in sanitized


@pytest.mark.asyncio
async def test_sanitize_redacts_postgresql_connection():
    msg = "connect to postgresql+asyncpg://admin:s3cret@db.example.com:5432/prod failed"
    sanitized = _sanitize_error_message(msg)
    assert "s3cret" not in sanitized
    assert "admin:s3cret" not in sanitized
    assert "postgresql+asyncpg://***REDACTED***" in sanitized


@pytest.mark.asyncio
async def test_request_with_retry_no_method_param():
    import inspect
    sig = inspect.signature(_request_with_retry)
    assert "method" not in sig.parameters
