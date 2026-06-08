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
