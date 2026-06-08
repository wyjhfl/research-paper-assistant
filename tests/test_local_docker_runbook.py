"""Local Docker runbook should document non-destructive personal-use recovery."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = PROJECT_ROOT / "docs" / "LOCAL_DOCKER_RUNBOOK.md"
README = PROJECT_ROOT / "README.md"


def test_runbook_documents_alembic_ready_recovery_without_volume_delete():
    content = RUNBOOK.read_text(encoding="utf-8")
    assert "/health/ready" in content
    assert "alembic_current" in content
    assert "alembic_head" in content
    assert "docker compose exec -T backend python -m alembic current" in content
    assert "docker compose exec -T backend python -m alembic stamp 004_research_notes" in content
    assert "research_notes" in content
    assert "non-destructive" in content


def test_readme_points_old_volume_users_to_runbook_before_down_v():
    content = README.read_text(encoding="utf-8")
    assert "LOCAL_DOCKER_RUNBOOK.md" in content
    assert "alembic stamp" in content
    assert "docker compose down -v" in content
