from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.config import settings
from app.models import JobRun


def _make_job(
    job_id="job_abc123",
    user_id="user1",
    job_type="process_paper",
    status="pending",
    input_json="{}",
    output_json=None,
    error_message=None,
    progress_current=0,
    progress_total=0,
    attempts=0,
    max_attempts=1,
):
    job = JobRun(
        job_id=job_id,
        user_id=user_id,
        job_type=job_type,
        status=status,
        input_json=input_json,
        output_json=output_json,
        error_message=error_message,
        progress_current=progress_current,
        progress_total=progress_total,
        attempts=attempts,
        max_attempts=max_attempts,
    )
    job.created_at = datetime.now(timezone.utc)
    return job


@pytest.mark.asyncio
async def test_create_job_success():
    from app.services.job_service import JobService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    created_job = _make_job(job_id="job_test123", user_id="user1", job_type="process_paper", status="pending")
    mock_repo.create = AsyncMock(return_value=created_job)

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        result = await service.create_job(user_id="user1", job_type="process_paper")

    assert result.job_id.startswith("job_")
    assert result.status == "pending"


@pytest.mark.asyncio
async def test_create_job_uses_settings_default():
    from app.services.job_service import JobService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    created_job = _make_job(job_id="job_settings", user_id="user1", job_type="process_paper", max_attempts=settings.JOB_MAX_ATTEMPTS)
    mock_repo.create = AsyncMock(return_value=created_job)

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        result = await service.create_job(user_id="user1", job_type="process_paper")

    assert result.max_attempts == settings.JOB_MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_list_jobs_only_current_user():
    from app.services.job_service import JobService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    user1_jobs = [_make_job(job_id="job_a", user_id="user1")]
    mock_repo.list_by_user = AsyncMock(return_value=user1_jobs)

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        result = await service.list_jobs(user_id="user1")

    mock_repo.list_by_user.assert_called_once_with("user1", status=None, job_type=None, limit=50)
    assert len(result) == 1
    assert result[0].user_id == "user1"


@pytest.mark.asyncio
async def test_get_job_other_user_returns_none():
    from app.services.job_service import JobService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    other_job = _make_job(job_id="job_other", user_id="user2")
    mock_repo.get_by_job_id = AsyncMock(return_value=other_job)

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        result = await service.get_job(user_id="user1", job_id="job_other")

    assert result is None


@pytest.mark.asyncio
async def test_cancel_pending_job_success():
    from app.services.job_service import JobService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.cancel_job = AsyncMock(return_value=True)

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        result = await service.cancel_job(user_id="user1", job_id="job_cancel")

    assert result is True
    mock_repo.cancel_job.assert_called_once_with("job_cancel", "user1")


@pytest.mark.asyncio
async def test_cancel_other_user_job_returns_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.jobs.JobService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.cancel_job = AsyncMock(return_value=False)
            MockService.return_value = mock_instance
            with patch("app.routers.jobs.get_user_id", return_value="user1"):
                response = await client.post("/jobs/job_other/cancel")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_job_type_returns_400():
    from app.services.job_service import JobService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        with pytest.raises(ValueError, match="Invalid job_type"):
            await service.create_job(user_id="user1", job_type="invalid_type")


@pytest.mark.asyncio
async def test_worker_execute_process_paper():
    from app.services.job_worker import JobWorker

    worker = JobWorker()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()

    job = _make_job(job_id="job_pp", user_id="user1", job_type="process_paper", input_json='{"paper_id": 42}')
    job.status = "running"

    mock_paper = MagicMock()
    mock_paper.id = 42
    mock_paper.status = "completed"

    with patch("app.services.job_worker.JobRepository", return_value=mock_repo):
        with patch("app.services.paper_service.PaperService") as MockPaperService:
            mock_ps_instance = AsyncMock()
            mock_ps_instance.process_paper = AsyncMock(return_value=mock_paper)
            MockPaperService.return_value = mock_ps_instance
            result = await worker._execute(job, mock_session)

    assert result["paper_id"] == 42
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_worker_execute_failed_job():
    from app.services.job_worker import JobWorker

    worker = JobWorker()
    mock_session = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.begin = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_repo = AsyncMock()
    job = _make_job(job_id="job_fail", user_id="user1", job_type="process_paper", input_json='{"paper_id": 1}')
    job.status = "running"

    mock_repo.claim_pending = AsyncMock(return_value=job)
    mock_repo.mark_completed = AsyncMock()
    mock_repo.mark_failed_with_attempts = AsyncMock()

    with patch("app.services.job_worker.JobRepository", return_value=mock_repo):
        with patch("app.services.paper_service.PaperService") as MockPaperService:
            mock_ps_instance = AsyncMock()
            mock_ps_instance.process_paper = AsyncMock(side_effect=RuntimeError("DB connection lost"))
            MockPaperService.return_value = mock_ps_instance
            claimed = await worker._run_one(mock_session)

    assert claimed is True
    mock_repo.mark_failed_with_attempts.assert_called_once()
    call_args = mock_repo.mark_failed_with_attempts.call_args
    assert "RuntimeError" in call_args[0][1]
    assert "job execution failed" in call_args[0][1]


@pytest.mark.asyncio
async def test_worker_does_not_execute_cancelled_job():
    from app.services.job_worker import JobWorker

    worker = JobWorker()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.claim_pending = AsyncMock(return_value=None)

    with patch("app.services.job_worker.JobRepository", return_value=mock_repo):
        claimed = await worker._run_one(mock_session)

    assert claimed is False


@pytest.mark.asyncio
async def test_rebuild_embeddings_job_calls_correct_service():
    from app.services.job_worker import JobWorker

    worker = JobWorker()
    mock_session = AsyncMock()
    job = _make_job(
        job_id="job_rebuild",
        user_id="user1",
        job_type="rebuild_embeddings",
        input_json='{"paper_id": 7}',
    )
    job.status = "running"

    with patch("app.services.paper_service.PaperService") as MockPaperService:
        mock_ps_instance = AsyncMock()
        mock_ps_instance.rebuild_embeddings = AsyncMock(return_value=15)
        MockPaperService.return_value = mock_ps_instance
        result = await worker._execute(job, mock_session)

    mock_ps_instance.rebuild_embeddings.assert_called_once_with(7)
    assert result["paper_id"] == 7
    assert result["chunks_embedded"] == 15


@pytest.mark.asyncio
async def test_agent_run_job_can_write_output():
    from app.services.job_worker import JobWorker

    worker = JobWorker()
    mock_session = AsyncMock()
    job = _make_job(
        job_id="job_agent",
        user_id="user1",
        job_type="agent_run",
        input_json='{"task_type": "summarize_paper", "paper_id": 3, "question": "What?", "draft_text": ""}',
    )
    job.status = "running"

    agent_result = {"run_id": "abc123", "status": "completed", "task_type": "summarize_paper"}

    with patch("app.services.agent_run_service.AgentRunService") as MockAgentService:
        mock_as_instance = AsyncMock()
        mock_as_instance.run_agent = AsyncMock(return_value=agent_result)
        MockAgentService.return_value = mock_as_instance
        result = await worker._execute(job, mock_session)

    assert result["run_id"] == "abc123"
    assert result["status"] == "completed"


def test_production_check_includes_job_runs_table():
    import inspect
    from scripts.production_check import run_checks
    src = inspect.getsource(run_checks)
    assert '"job_runs"' in src or "'job_runs'" in src


@pytest.mark.asyncio
async def test_auth_enabled_no_session_returns_401():
    original = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = True
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.dependencies.async_session") as mock_session_factory:
                mock_db = AsyncMock()
                mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
                with patch("app.services.auth_service.AuthService") as MockAuthService:
                    mock_auth = AsyncMock()
                    mock_auth.get_user_from_session = AsyncMock(return_value=None)
                    MockAuthService.return_value = mock_auth
                    response = await client.get("/jobs")
    finally:
        settings.AUTH_ENABLED = original

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dev_mode_compat_x_user_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.jobs.JobService") as MockService:
            mock_instance = AsyncMock()
            created_job = _make_job(job_id="job_dev", user_id="default", job_type="process_paper", status="pending")
            mock_instance.create_job = AsyncMock(return_value=created_job)
            MockService.return_value = mock_instance
            with patch("app.routers.jobs.get_user_id", return_value="default"):
                response = await client.post(
                    "/jobs",
                    json={"job_type": "process_paper", "input": {}, "max_attempts": 1},
                )

    assert response.status_code == 201
    mock_instance.create_job.assert_called_once()
    call_args = mock_instance.create_job.call_args
    user_id_arg = call_args.kwargs.get("user_id") or call_args[1].get("user_id") or call_args[0][0]
    assert user_id_arg == "default"


@pytest.mark.asyncio
async def test_job_id_is_unique():
    from app.services.job_service import JobService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    job_a = _make_job(job_id="job_unique_a", user_id="user1", job_type="process_paper")
    job_b = _make_job(job_id="job_unique_b", user_id="user1", job_type="rebuild_embeddings")
    mock_repo.create = AsyncMock(side_effect=[job_a, job_b])

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        result_a = await service.create_job(user_id="user1", job_type="process_paper")
        result_b = await service.create_job(user_id="user1", job_type="rebuild_embeddings")

    assert result_a.job_id != result_b.job_id


@pytest.mark.asyncio
async def test_worker_max_attempts_1_failure_sets_failed():
    from app.services.job_worker import JobWorker

    worker = JobWorker()
    mock_session = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.begin = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    job = _make_job(
        job_id="job_fail1",
        user_id="user1",
        job_type="process_paper",
        input_json='{"paper_id": 1}',
        max_attempts=1,
        attempts=1,
    )
    job.status = "running"

    mock_repo = AsyncMock()
    mock_repo.claim_pending = AsyncMock(return_value=job)
    mock_repo.mark_completed = AsyncMock()
    mock_repo.mark_failed_with_attempts = AsyncMock()

    with patch("app.services.job_worker.JobRepository", return_value=mock_repo):
        with patch("app.services.paper_service.PaperService") as MockPaperService:
            mock_ps_instance = AsyncMock()
            mock_ps_instance.process_paper = AsyncMock(side_effect=RuntimeError("fail"))
            MockPaperService.return_value = mock_ps_instance
            await worker._run_one(mock_session)

    mock_repo.mark_failed_with_attempts.assert_called_once()
    call_args = mock_repo.mark_failed_with_attempts.call_args
    assert call_args[0][2] == 1
    assert call_args[0][3] == 1


@pytest.mark.asyncio
async def test_worker_max_attempts_2_first_failure_sets_pending():
    from app.services.job_worker import JobWorker

    worker = JobWorker()
    mock_session = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.begin = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    job = _make_job(
        job_id="job_retry1",
        user_id="user1",
        job_type="process_paper",
        input_json='{"paper_id": 1}',
        max_attempts=2,
        attempts=1,
    )
    job.status = "running"

    mock_repo = AsyncMock()
    mock_repo.claim_pending = AsyncMock(return_value=job)
    mock_repo.mark_completed = AsyncMock()
    mock_repo.mark_failed_with_attempts = AsyncMock()

    with patch("app.services.job_worker.JobRepository", return_value=mock_repo):
        with patch("app.services.paper_service.PaperService") as MockPaperService:
            mock_ps_instance = AsyncMock()
            mock_ps_instance.process_paper = AsyncMock(side_effect=RuntimeError("fail"))
            MockPaperService.return_value = mock_ps_instance
            await worker._run_one(mock_session)

    mock_repo.mark_failed_with_attempts.assert_called_once()
    call_args = mock_repo.mark_failed_with_attempts.call_args
    assert call_args[0][2] == 1
    assert call_args[0][3] == 2


@pytest.mark.asyncio
async def test_mark_failed_with_attempts_logic():
    from app.repositories.job_repo import JobRepository

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.flush = AsyncMock()
    repo = JobRepository(mock_db)

    await repo.mark_failed_with_attempts("job_x", "error", attempts=1, max_attempts=1)
    mock_db.execute.assert_called_once()
    update_stmt = mock_db.execute.call_args[0][0]
    compiled = str(update_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "failed" in compiled

    mock_db.execute.reset_mock()
    await repo.mark_failed_with_attempts("job_y", "error", attempts=1, max_attempts=2)
    mock_db.execute.assert_called_once()
    update_stmt = mock_db.execute.call_args[0][0]
    compiled = str(update_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "pending" in compiled


@pytest.mark.asyncio
async def test_post_jobs_max_attempts_0_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.jobs.get_user_id", return_value="user1"):
            response = await client.post(
                "/jobs",
                json={"job_type": "process_paper", "input": {}, "max_attempts": 0},
            )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_jobs_no_raw_json_in_response():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.jobs.JobService") as MockService:
            mock_instance = AsyncMock()
            job = _make_job(
                job_id="job_safe",
                user_id="user1",
                job_type="process_paper",
                input_json='{"paper_id": 42}',
                output_json='{"paper_id": 42, "status": "completed"}',
            )
            mock_instance.list_jobs = AsyncMock(return_value=[job])
            MockService.return_value = mock_instance
            with patch("app.routers.jobs.get_user_id", return_value="user1"):
                response = await client.get("/jobs")

    assert response.status_code == 200
    data = response.json()
    assert "input_json" not in data["jobs"][0]
    assert "output_json" not in data["jobs"][0]
    assert "input_summary" in data["jobs"][0]
    assert "output_summary" in data["jobs"][0]


@pytest.mark.asyncio
async def test_agent_run_job_output_no_long_text():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.jobs.JobService") as MockService:
            mock_instance = AsyncMock()
            long_question = "A" * 500
            long_answer = "B" * 500
            long_draft = "C" * 500
            job = _make_job(
                job_id="job_agent_safe",
                user_id="user1",
                job_type="agent_run",
                input_json=f'{{"task_type": "summarize_paper", "paper_id": 3, "question": "{long_question}", "draft_text": "{long_draft}"}}',
                output_json=f'{{"run_id": "abc", "status": "completed", "answer": "{long_answer}"}}',
            )
            mock_instance.list_jobs = AsyncMock(return_value=[job])
            MockService.return_value = mock_instance
            with patch("app.routers.jobs.get_user_id", return_value="user1"):
                response = await client.get("/jobs")

    assert response.status_code == 200
    data = response.json()
    job_data = data["jobs"][0]
    assert "input_json" not in job_data
    assert "output_json" not in job_data
    assert long_question not in job_data.get("input_summary", "")
    assert long_answer not in job_data.get("output_summary", "")
    assert long_draft not in job_data.get("input_summary", "")


def test_safe_job_output_agent_run_strips_answer_and_sources():
    from app.services.job_worker import safe_job_output

    result = {
        "run_id": "abc123",
        "status": "completed",
        "task_type": "recommend_citations_multi",
        "output": {
            "answer": "This is a very long answer that should not be persisted in job_runs.output_json",
            "sources": [{"paper_id": 1}, {"paper_id": 2}],
            "rag_status": "answered",
        },
        "warnings": ["warning1"],
        "confidence": 0.85,
    }
    safe = safe_job_output("agent_run", result)
    assert "answer" not in safe
    assert "sources" not in safe
    assert "output" not in safe
    assert safe["run_id"] == "abc123"
    assert safe["status"] == "completed"
    assert safe["task_type"] == "recommend_citations_multi"
    assert safe["confidence"] == 0.85
    assert safe["warning_count"] == 1
    assert safe["source_count"] == 2
    assert safe["rag_status"] == "answered"
    assert "output_keys" in safe
    assert "answer" in safe["output_keys"]


def test_safe_job_output_agent_run_no_question_or_draft_text():
    from app.services.job_worker import safe_job_output

    result = {
        "run_id": "xyz",
        "status": "completed",
        "task_type": "summarize_paper",
        "question": "What is attention?",
        "draft_text": "Some draft text here",
        "output": {"summary": "A summary", "retrieved_chunks": [1, 2, 3]},
        "confidence": 0.7,
    }
    safe = safe_job_output("agent_run", result)
    assert "question" not in safe
    assert "draft_text" not in safe
    assert "summary" not in safe
    assert "retrieved_chunks" not in safe
    assert safe["chunk_count"] == 3
    assert safe["run_id"] == "xyz"
    assert safe["confidence"] == 0.7


def test_safe_job_output_agent_run_preserves_safe_fields():
    from app.services.job_worker import safe_job_output

    result = {
        "run_id": "r1",
        "status": "completed",
        "task_type": "extract_ideas",
        "confidence": 0.9,
        "output": {"ideas": [{"title": "idea1"}, {"title": "idea2"}]},
        "warnings": [],
    }
    safe = safe_job_output("agent_run", result)
    assert safe["run_id"] == "r1"
    assert safe["status"] == "completed"
    assert safe["task_type"] == "extract_ideas"
    assert safe["confidence"] == 0.9
    assert safe["warning_count"] == 0
    assert safe["idea_count"] == 2


def test_safe_job_output_process_paper_and_rebuild():
    from app.services.job_worker import safe_job_output

    pp = safe_job_output("process_paper", {"paper_id": 42, "status": "completed", "extra": "ignored"})
    assert pp == {"paper_id": 42, "status": "completed"}
    assert "extra" not in pp

    rb = safe_job_output("rebuild_embeddings", {"paper_id": 7, "chunks_embedded": 15, "extra": "ignored"})
    assert rb == {"paper_id": 7, "chunks_embedded": 15}
    assert "extra" not in rb


def test_safe_job_output_real_model_eval_truncates_message():
    from app.services.job_worker import safe_job_output

    long_msg = "X" * 500
    ev = safe_job_output("real_model_eval", {"status": "completed", "message": long_msg})
    assert ev["status"] == "completed"
    assert len(ev["message"]) < 500
    assert ev["message"].endswith("...")


@pytest.mark.asyncio
async def test_worker_agent_run_output_json_is_safe():
    from app.services.job_worker import JobWorker

    worker = JobWorker()
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.claim_pending = AsyncMock(return_value=None)

    long_answer = "A" * 1000
    agent_result = {
        "run_id": "safe_run",
        "status": "completed",
        "task_type": "recommend_citations_multi",
        "output": {
            "answer": long_answer,
            "sources": [{"paper_id": 1, "text": "chunk text"}],
            "rag_status": "answered",
        },
        "warnings": [],
        "confidence": 0.88,
    }

    job = _make_job(
        job_id="job_safe_agent",
        user_id="user1",
        job_type="agent_run",
        input_json='{"task_type": "recommend_citations_multi", "paper_ids": [1]}',
    )
    job.status = "running"
    job.attempts = 1
    job.max_attempts = 1

    mock_repo.claim_pending = AsyncMock(return_value=job)
    mock_repo.mark_completed = AsyncMock()
    mock_repo.mark_failed_with_attempts = AsyncMock()

    with patch("app.services.job_worker.JobRepository", return_value=mock_repo):
        with patch("app.services.agent_run_service.AgentRunService") as MockAgentService:
            mock_as_instance = AsyncMock()
            mock_as_instance.run_agent = AsyncMock(return_value=agent_result)
            MockAgentService.return_value = mock_as_instance
            await worker._run_one(mock_session)

    mock_repo.mark_completed.assert_called_once()
    output_arg = mock_repo.mark_completed.call_args[0][1]
    output_data = json.loads(output_arg)
    assert "answer" not in output_data
    assert "sources" not in output_data
    assert long_answer not in output_arg
    assert output_data["run_id"] == "safe_run"
    assert output_data["status"] == "completed"
    assert output_data["source_count"] == 1
    assert output_data["confidence"] == 0.88


def test_safe_job_output_unknown_type_does_not_return_raw():
    from app.services.job_worker import safe_job_output

    result = {
        "status": "completed",
        "answer": "secret answer text",
        "raw_text": "sensitive raw output",
        "secret_key": "should not persist",
    }
    safe = safe_job_output("unknown_job_type", result)
    assert safe == {"status": "completed"}
    assert "answer" not in safe
    assert "raw_text" not in safe
    assert "secret_key" not in safe


def test_safe_job_output_unknown_type_none_status():
    from app.services.job_worker import safe_job_output

    result = {"data": "something"}
    safe = safe_job_output("future_type", result)
    assert safe == {"status": None}
    assert "data" not in safe


@pytest.mark.asyncio
async def test_upload_async_mode_creates_process_paper_job():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.papers.PaperService") as MockPaperService:
            mock_ps = AsyncMock()
            mock_paper = MagicMock()
            mock_paper.id = 1
            mock_paper.title = "Test Paper"
            mock_paper.filename = "test.pdf"
            mock_paper.status = "pending"
            mock_ps.upload_paper = AsyncMock(return_value=mock_paper)
            MockPaperService.return_value = mock_ps
            with patch("app.routers.papers.PaperRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.get_chunk_count = AsyncMock(return_value=0)
                MockRepo.return_value = mock_repo
                with patch("app.routers.papers.get_user_id", return_value="user1"):
                    response = await client.post(
                        "/papers/upload?async_mode=true",
                        files={"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
                    )

    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] is not None
    assert data["job_id"].startswith("job_")


@pytest.mark.asyncio
async def test_rebuild_async_mode_creates_rebuild_job():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.papers.PaperService") as MockPaperService:
            mock_ps = AsyncMock()
            mock_ps.rebuild_embeddings = AsyncMock(return_value=5)
            mock_ps.get_paper = AsyncMock(return_value=MagicMock())
            MockPaperService.return_value = mock_ps
            with patch("app.routers.papers.PaperRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.get_chunk_count = AsyncMock(return_value=5)
                MockRepo.return_value = mock_repo
                with patch("app.routers.papers.get_user_id", return_value="user1"):
                    response = await client.post("/papers/1/embeddings/rebuild?async_mode=true")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] is not None
    assert data["job_id"].startswith("job_")


@pytest.mark.asyncio
async def test_upload_sync_mode_no_job_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.papers.PaperService") as MockPaperService:
            mock_ps = AsyncMock()
            mock_paper = MagicMock()
            mock_paper.id = 2
            mock_paper.title = "Sync Paper"
            mock_paper.filename = "sync.pdf"
            mock_paper.status = "completed"
            mock_ps.upload_paper = AsyncMock(return_value=mock_paper)
            mock_ps.process_paper = AsyncMock(return_value=mock_paper)
            MockPaperService.return_value = mock_ps
            with patch("app.routers.papers.PaperRepository") as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.get_chunk_count = AsyncMock(return_value=3)
                MockRepo.return_value = mock_repo
                with patch("app.routers.papers.get_user_id", return_value="user1"):
                    response = await client.post(
                        "/papers/upload?async_mode=false",
                        files={"file": ("sync.pdf", b"%PDF-1.4 sync", "application/pdf")},
                    )

    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] is None


@pytest.mark.asyncio
async def test_worker_health_returns_user_stats():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.jobs.JobService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.get_worker_health = AsyncMock(return_value={
                "worker_enabled": True,
                "poll_interval_seconds": 1.0,
                "max_attempts_default": 1,
                "stale_running_seconds": 900,
                "running_count": 2,
                "pending_count": 3,
                "failed_count": 1,
                "stale_running_count": 0,
            })
            MockService.return_value = mock_instance
            with patch("app.routers.jobs.get_user_id", return_value="user1"):
                response = await client.get("/jobs/worker/health")

    assert response.status_code == 200
    data = response.json()
    assert data["worker_enabled"] is True
    assert data["running_count"] == 2
    assert data["pending_count"] == 3
    assert data["failed_count"] == 1
    assert data["stale_running_count"] == 0
    assert data["stale_running_seconds"] == 900


@pytest.mark.asyncio
async def test_worker_health_does_not_cross_user():
    from app.services.job_service import JobService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.count_by_user_and_status = AsyncMock(return_value={"running": 1, "pending": 0, "failed": 0})
    mock_repo.count_stale_running = AsyncMock(return_value=0)

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        result = await service.get_worker_health("user1")

    mock_repo.count_by_user_and_status.assert_called_once_with("user1")
    mock_repo.count_stale_running.assert_called_once_with("user1", settings.JOB_STALE_RUNNING_SECONDS)
    assert result["running_count"] == 1


@pytest.mark.asyncio
async def test_stale_running_count_correct():
    from app.services.job_service import JobService

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.count_by_user_and_status = AsyncMock(return_value={"running": 3, "pending": 1})
    mock_repo.count_stale_running = AsyncMock(return_value=2)

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        result = await service.get_worker_health("user1")

    assert result["running_count"] == 3
    assert result["stale_running_count"] == 2


@pytest.mark.asyncio
async def test_retry_failed_job_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.jobs.JobService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.retry_job = AsyncMock(return_value=True)
            MockService.return_value = mock_instance
            with patch("app.routers.jobs.get_user_id", return_value="user1"):
                response = await client.post("/jobs/job_failed1/retry")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_retry_other_user_returns_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.jobs.JobService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.retry_job = AsyncMock(return_value=False)
            MockService.return_value = mock_instance
            with patch("app.routers.jobs.get_user_id", return_value="user1"):
                response = await client.post("/jobs/job_other/retry")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_retry_non_failed_returns_409():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.routers.jobs.JobService") as MockService:
            mock_instance = AsyncMock()
            mock_instance.retry_job = AsyncMock(return_value="not_failed")
            MockService.return_value = mock_instance
            with patch("app.routers.jobs.get_user_id", return_value="user1"):
                response = await client.post("/jobs/job_running/retry")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_retry_job_clears_fields():
    from app.services.job_service import JobService
    from app.models import JobRun

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    job = JobRun(
        job_id="job_retry_clear",
        user_id="user1",
        job_type="process_paper",
        status="failed",
        input_json="{}",
        error_message="some error",
        attempts=2,
        max_attempts=2,
    )
    mock_repo.get_by_job_id = AsyncMock(return_value=job)
    mock_repo.retry_job = AsyncMock(return_value=True)

    with patch("app.services.job_service.JobRepository", return_value=mock_repo):
        service = JobService(mock_db)
        result = await service.retry_job("user1", "job_retry_clear")

    assert result is True
