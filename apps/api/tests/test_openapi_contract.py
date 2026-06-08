from __future__ import annotations

from types import SimpleNamespace
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


def _success_response_schema(spec: dict, path: str, method: str) -> dict:
    method_spec = spec["paths"][path][method]
    responses = method_spec.get("responses", {})
    success_code = "200" if "200" in responses else "201"
    content = responses[success_code]["content"]["application/json"]
    return _resolve_schema(content["schema"], spec)


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
async def test_review_matrix_has_request_and_response_schema():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    spec = resp.json()
    path = spec["paths"]["/papers/review-matrix"]["post"]
    assert "requestBody" in path
    request_schema = _resolve_schema(path["requestBody"]["content"]["application/json"]["schema"], spec)
    request_props = request_schema.get("properties", {})
    assert "paper_ids" in request_props
    assert "max_chunks_per_paper" in request_props

    response_schema = _success_response_schema(spec, "/papers/review-matrix", "post")
    response_props = response_schema.get("properties", {})
    assert "rows" in response_props
    assert "total_papers" in response_props
    assert "generated_by" in response_props


@pytest.mark.asyncio
async def test_ask_responses_include_query_expansion_fields():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    spec = resp.json()

    ask_schema = _success_response_schema(spec, "/papers/{paper_id}/ask", "post")
    ask_props = ask_schema.get("properties", {})
    assert "query_expansion_applied" in ask_props
    assert "expanded_query_terms" in ask_props

    multi_schema = _success_response_schema(spec, "/papers/ask", "post")
    multi_props = multi_schema.get("properties", {})
    assert "query_expansion_applied" in multi_props
    assert "expanded_query_terms" in multi_props


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
async def test_notes_have_request_and_response_schema():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    spec = resp.json()

    create_path = spec["paths"]["/notes"]["post"]
    assert "requestBody" in create_path
    request_schema = _resolve_schema(create_path["requestBody"]["content"]["application/json"]["schema"], spec)
    request_props = request_schema.get("properties", {})
    assert "title" in request_props
    assert "content" in request_props
    assert "note_type" in request_props
    assert "source" in request_props

    list_schema = _success_response_schema(spec, "/notes", "get")
    assert "notes" in list_schema.get("properties", {})
    detail_schema = _success_response_schema(spec, "/notes/{note_id}", "get")
    assert "note" in detail_schema.get("properties", {})


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
        ("/papers/review-matrix", "post"),
        ("/ideas", "post"),
        ("/ideas", "get"),
        ("/ideas/{idea_id}", "get"),
        ("/notes", "post"),
        ("/notes", "get"),
        ("/notes/{note_id}", "get"),
        ("/notes/{note_id}", "patch"),
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
    mock_result.evidence_gate_reason = ""
    mock_result.retrieved_source_count = 0
    mock_result.top_source_score = 0.0

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
async def test_review_matrix_endpoint_returns_rows_without_model_call():
    mock_result = SimpleNamespace(
        rows=[
            SimpleNamespace(
                paper_id=1,
                paper_title="Alpha Paper",
                problem="The paper studies a retrieval problem.",
                method="It proposes a workflow.",
                evidence="Experiments evaluate the workflow.",
                metric="Accuracy is reported.",
                limitation="Limitations remain.",
                future_work="Future work improves retrieval.",
                source_chunk_ids=[10],
                sources=[
                    SimpleNamespace(
                        paper_id=1,
                        paper_title="Alpha Paper",
                        chunk_id=10,
                        chunk_index=0,
                        page_start=1,
                        page_end=1,
                        text_excerpt="This paper studies a retrieval problem.",
                        matched_fields=["problem", "method"],
                    )
                ],
            )
        ],
        total_papers=1,
        generated_by="heuristic",
        warnings=[],
    )

    with patch("app.routers.papers.ReviewMatrixService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.generate = AsyncMock(return_value=mock_result)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/papers/review-matrix",
                json={"paper_ids": [1], "max_chunks_per_paper": 8},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["generated_by"] == "heuristic"
        assert data["total_papers"] == 1
        assert data["rows"][0]["paper_title"] == "Alpha Paper"
        assert data["rows"][0]["source_chunk_ids"] == [10]
        assert data["rows"][0]["sources"][0]["matched_fields"] == ["problem", "method"]
        mock_instance.generate.assert_awaited_once_with(paper_ids=[1], max_chunks_per_paper=8)


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
