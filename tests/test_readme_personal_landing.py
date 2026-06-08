"""README should describe the current personal-local landing workflow."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
README = PROJECT_ROOT / "README.md"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_links_current_v1_0_1_release_notes():
    content = _readme()
    assert "docs/RELEASE_NOTES_v1.0.1.md" in content
    assert "docs/RELEASE_NOTES_v1.0.1-rc.1.md" in content


def test_readme_mentions_personal_guide_and_notes_download():
    content = _readme()
    assert "/guide" in content
    assert "\u4e2a\u4eba\u672c\u5730\u4f7f\u7528\u6307\u5357" in content
    assert "\u4e0b\u8f7d Markdown" in content
    assert "\u7814\u7a76\u7b14\u8bb0" in content


def test_readme_mentions_current_rag_local_enhancements():
    content = _readme()
    assert "hybrid lexical retrieval" in content
    assert "QUERY_EXPANSION_ENABLED" in content
    assert "\u4e2d\u6587\u95ee\u9898\u82f1\u6587\u5173\u952e\u8bcd\u6269\u5c55" in content



def test_readme_personal_check_prefers_non_destructive_alembic_recovery():
    content = _readme()
    start = content.index("### \u4e2a\u4eba\u672c\u5730\u843d\u5730\u68c0\u67e5")
    end = content.index("### \u672c\u5730\u5f00\u53d1", start)
    section = content[start:end]
    assert "papers/ideas/notes/jobs" in section
    assert "\u524d\u7aef\u6838\u5fc3\u8def\u7531" in section
    assert "\u5173\u952e\u6587\u6848" in section
    assert "save_first_research_note" in section
    assert "alembic stamp" in section
    assert "LOCAL_DOCKER_RUNBOOK.md" in section
    assert "docker compose down -v" in section
    assert "\u53ea\u6709\u786e\u8ba4\u4e0d\u9700\u8981\u4fdd\u7559\u672c\u5730\u6570\u636e" in section
    assert "\u65e7 volume schema \u5f02\u5e38\uff0c\u53ef\u6267\u884c `docker compose down -v`" not in section


def test_readme_mentions_personal_workflow_smoke_script():
    content = _readme()
    assert "scripts/personal_workflow_smoke.py" in content
    assert "scripts/personal_local_check.ps1" in content
    assert "scripts/personal_local_start.ps1" in content
    assert "-SkipBuild" in content
    assert "-RunWorkflowSmoke" in content
    assert "-WriteSmokeNote" in content
    assert "--write-note" in content
    assert "--run-workflow-smoke" in content
    assert "--write-smoke-note" in content
    assert "\u4e0d\u8f93\u51fa\u6a21\u578b\u56de\u7b54\u5168\u6587" in content
