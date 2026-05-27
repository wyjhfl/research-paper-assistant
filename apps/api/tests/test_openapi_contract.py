from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_openapi_json_returns_200():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert "openapi" in spec
    assert "paths" in spec


def _resolve_schema(schema: dict, spec: dict) -> dict:
    if "$ref" in schema:
        ref_path = schema["$ref"].split("/")[-1]
        return spec["components"]["schemas"][ref_path]
    return schema


@pytest.mark.asyncio
async def test_ask_paper_has_request_body_schema():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    spec = resp.json()
    path = spec["paths"]["/papers/{paper_id}/ask"]["post"]
    assert "requestBody" in path
    content = path["requestBody"]["content"]
    assert "application/json" in content
    schema = _resolve_schema(content["application/json"]["schema"], spec)
    assert "question" in schema.get("properties", {})


@pytest.mark.asyncio
async def test_multi_paper_ask_has_request_body_schema():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    spec = resp.json()
    path = spec["paths"]["/papers/ask"]["post"]
    assert "requestBody" in path
    schema = _resolve_schema(path["requestBody"]["content"]["application/json"]["schema"], spec)
    props = schema.get("properties", {})
    assert "question" in props
    assert "paper_ids" in props
    assert "top_k" in props


@pytest.mark.asyncio
async def test_paper_search_has_request_body_schema():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    spec = resp.json()
    path = spec["paths"]["/papers/search"]["post"]
    assert "requestBody" in path
    schema = _resolve_schema(path["requestBody"]["content"]["application/json"]["schema"], spec)
    props = schema.get("properties", {})
    assert "query" in props
    assert "paper_ids" in props
    assert "top_k" in props


@pytest.mark.asyncio
async def test_save_idea_has_request_body_schema():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    spec = resp.json()
    path = spec["paths"]["/ideas"]["post"]
    assert "requestBody" in path
    schema = _resolve_schema(path["requestBody"]["content"]["application/json"]["schema"], spec)
    props = schema.get("properties", {})
    assert "paper_id" in props
    assert "title" in props
    assert "summary" in props
    assert "source_chunk_ids" in props
    assert "confidence" in props


@pytest.mark.asyncio
async def test_main_endpoints_have_response_schema():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    spec = resp.json()

    endpoints_with_response = [
        ("/papers", "get"),
        ("/papers/upload", "post"),
        ("/papers/{paper_id}", "get"),
        ("/papers/{paper_id}/ask", "post"),
        ("/papers/{paper_id}/embeddings/rebuild", "post"),
        ("/papers/{paper_id}/ideas/extract", "post"),
        ("/papers/ask", "post"),
        ("/papers/search", "post"),
        ("/ideas", "post"),
        ("/ideas", "get"),
        ("/ideas/{idea_id}", "get"),
        ("/agent/run", "post"),
        ("/agent/runs/{run_id}", "get"),
    ]

    for path, method in endpoints_with_response:
        assert path in spec["paths"], f"Path {path} not in OpenAPI spec"
        method_spec = spec["paths"][path].get(method)
        assert method_spec is not None, f"Method {method} not found for {path}"
        responses = method_spec.get("responses", {})
        assert "200" in responses or "201" in responses, f"No 200/201 response for {path} {method}"
        success_code = "200" if "200" in responses else "201"
        response_content = responses[success_code].get("content", {})
        assert "application/json" in response_content, f"No JSON response schema for {path} {method}"


@pytest.mark.asyncio
async def test_empty_question_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/papers/ask", json={"question": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_whitespace_question_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/papers/ask", json={"question": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_empty_query_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/papers/search", json={"query": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_paper_ids_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/papers/ask", json={"question": "test", "paper_ids": "not_a_list"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_confidence_above_1_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ideas", json={
            "paper_id": 1,
            "title": "Test",
            "summary": "Test summary",
            "source_chunk_ids": [1],
            "confidence": 2.5,
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_save_idea_empty_source_chunk_ids_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ideas", json={
            "paper_id": 1,
            "title": "Test",
            "summary": "Test summary",
            "source_chunk_ids": [],
            "confidence": 0.5,
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_save_idea_empty_title_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ideas", json={
            "paper_id": 1,
            "title": "   ",
            "summary": "Test summary",
            "source_chunk_ids": [1],
            "confidence": 0.5,
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_save_idea_empty_summary_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ideas", json={
            "paper_id": 1,
            "title": "Test",
            "summary": "   ",
            "source_chunk_ids": [1],
            "confidence": 0.5,
        })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_x_user_id_still_works():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/papers", headers={"X-User-Id": "schema_test_user"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_multi_paper_ask_passes_top_k_to_service():
    mock_result = AsyncMock()
    mock_result.answer = "test answer"
    mock_result.status = "answered"
    mock_result.confidence = 0.9
    mock_result.sources = []

    with patch("app.routers.papers.MultiPaperRAGService") as MockRAG:
        mock_instance = MockRAG.return_value
        mock_instance.ask = AsyncMock(return_value=mock_result)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/papers/ask", json={"question": "test", "top_k": 3})

        assert resp.status_code == 200
        mock_instance.ask.assert_called_once()
        call_kwargs = mock_instance.ask.call_args
        assert call_kwargs.kwargs.get("top_k") == 3 or (len(call_kwargs.args) >= 3 and call_kwargs.args[2] == 3) or call_kwargs.kwargs.get("top_k") == 3


@pytest.mark.asyncio
async def test_paper_search_passes_top_k_to_service():
    with patch("app.routers.papers.MultiPaperRAGService") as MockRAG:
        mock_instance = MockRAG.return_value
        mock_instance.search = AsyncMock(return_value=[])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/papers/search", json={"query": "test", "top_k": 7})

        assert resp.status_code == 200
        mock_instance.search.assert_called_once()
        call_kwargs = mock_instance.search.call_args
        assert call_kwargs.kwargs.get("top_k") == 7 or (len(call_kwargs.args) >= 3 and call_kwargs.args[2] == 7) or call_kwargs.kwargs.get("top_k") == 7


@pytest.mark.asyncio
async def test_multi_paper_ask_top_k_zero_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/papers/ask", json={"question": "test", "top_k": 0})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_multi_paper_ask_top_k_exceeds_max_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/papers/ask", json={"question": "test", "top_k": 999})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_paper_search_top_k_exceeds_max_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/papers/search", json={"query": "test", "top_k": 999})
    assert resp.status_code == 422
