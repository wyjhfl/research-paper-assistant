import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_docs_secrets import (
    RULES,
    Finding,
    _is_local_dev_db,
    _is_placeholder,
    _redact,
    _safe_relative,
    scan_file,
)


def _make_temp_file(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.md"
    p.write_text(content, encoding="utf-8")
    return p


class TestIsPlaceholder:
    def test_your_placeholder(self):
        assert _is_placeholder("<YOUR_MIMO_TOKEN_PLAN_API_KEY>") is True

    def test_your_siliconflow(self):
        assert _is_placeholder("<YOUR_SILICONFLOW_API_KEY>") is True

    def test_replace_me(self):
        assert _is_placeholder("<REPLACE_ME>") is True

    def test_configured_exact(self):
        assert _is_placeholder("configured") is True

    def test_example_exact(self):
        assert _is_placeholder("example") is True

    def test_configured_in_url_not_placeholder(self):
        assert _is_placeholder("http://configured.example.com") is False

    def test_example_in_url_not_placeholder(self):
        assert _is_placeholder("db.example.com") is False

    def test_localhost_not_placeholder(self):
        assert _is_placeholder("localhost") is False

    def test_localhost_real_secret_not_placeholder(self):
        assert _is_placeholder("localhost-real-secret") is False

    def test_real_token_not_placeholder(self):
        assert _is_placeholder("tp-abcdef1234567890abcdef1234567890") is False

    def test_real_sk_not_placeholder(self):
        assert _is_placeholder("sk-abcdef1234567890abcdef1234567890") is False


class TestIsLocalDevDb:
    def test_exact_dev_db(self):
        assert _is_local_dev_db("postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant") is True

    def test_exact_dev_db_test(self):
        assert _is_local_dev_db("postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant_test") is True

    def test_real_password_rejected(self):
        assert _is_local_dev_db("postgresql+asyncpg://admin:RealSecret123@localhost:5432/prod") is False

    def test_other_localhost_db_rejected(self):
        assert _is_local_dev_db("postgresql+asyncpg://user:pass@localhost:5432/mydb") is False

    def test_remote_db_rejected(self):
        assert _is_local_dev_db("postgresql+asyncpg://postgres:postgres@remotehost:5432/research_assistant") is False


class TestRedact:
    def test_short_value(self):
        assert "***" in _redact("ab")

    def test_long_value(self):
        r = _redact("tp-abcdef1234567890abcdef1234567890")
        assert r.startswith("tp-a")
        assert "abcdef1234567890abcdef1234567890" not in r
        assert "chars" in r

    def test_does_not_expose_full_secret(self):
        secret = "sk-SuperSecretTokenThatShouldNotAppear123456"
        r = _redact(secret)
        assert "SuperSecretTokenThatShouldNotAppear123456" not in r


class TestSafeRelative:
    def test_inside_project_fallback(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("x")
        result = _safe_relative(f)
        assert "test.md" in result

    def test_outside_project_returns_str(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("x")
        result = _safe_relative(f)
        assert isinstance(result, str)


class TestScanFile:
    def test_allow_llm_api_key_placeholder(self, tmp_path):
        p = _make_temp_file(tmp_path, "LLM_API_KEY=<YOUR_MIMO_TOKEN_PLAN_API_KEY>\n")
        findings = scan_file(p)
        assert len(findings) == 0

    def test_allow_embedding_api_key_placeholder(self, tmp_path):
        p = _make_temp_file(tmp_path, "EMBEDDING_API_KEY=<YOUR_SILICONFLOW_API_KEY>\n")
        findings = scan_file(p)
        assert len(findings) == 0

    def test_allow_default_local_dev_db(self, tmp_path):
        p = _make_temp_file(tmp_path, "DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant\n")
        findings = scan_file(p)
        assert len(findings) == 0

    def test_reject_local_real_password_db(self, tmp_path):
        p = _make_temp_file(tmp_path, "DATABASE_URL=postgresql+asyncpg://admin:RealSecret123@localhost:5432/prod\n")
        findings = scan_file(p)
        assert len(findings) >= 1

    def test_reject_localhost_disguised_secret(self, tmp_path):
        p = _make_temp_file(tmp_path, "API_KEY=localhost-real-secret\n")
        findings = scan_file(p)
        assert len(findings) >= 1
        names = [f.rule_name for f in findings]
        assert "api-key-assign" in names

    def test_reject_tp_token(self, tmp_path):
        p = _make_temp_file(tmp_path, "LLM_API_KEY=tp-abcdef1234567890abcdef1234567890\n")
        findings = scan_file(p)
        assert len(findings) >= 1
        names = [f.rule_name for f in findings]
        assert "tp-token" in names

    def test_reject_authorization_bearer(self, tmp_path):
        p = _make_temp_file(tmp_path, "Authorization: Bearer sk-abcdef1234567890abcdef12\n")
        findings = scan_file(p)
        assert len(findings) >= 1
        names = [f.rule_name for f in findings]
        assert "authorization-bearer" in names

    def test_reject_localhost_non_default_db(self, tmp_path):
        p = _make_temp_file(tmp_path, "postgresql+asyncpg://user:pass@localhost:5432/mydb\n")
        findings = scan_file(p)
        assert len(findings) >= 1
        names = [f.rule_name for f in findings]
        assert "postgresql-connection" in names

    def test_reject_real_postgresql_connection(self, tmp_path):
        p = _make_temp_file(tmp_path, "postgresql+asyncpg://user:pass@remotehost:5432/mydb\n")
        findings = scan_file(p)
        assert len(findings) >= 1
        names = [f.rule_name for f in findings]
        assert "postgresql-connection" in names

    def test_reject_database_url_real(self, tmp_path):
        p = _make_temp_file(tmp_path, "DATABASE_URL=postgresql+asyncpg://admin:s3cret@db.example.com:5432/prod\n")
        findings = scan_file(p)
        assert len(findings) >= 1

    def test_output_redacted(self, tmp_path):
        secret = "tp-a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        p = _make_temp_file(tmp_path, f"key={secret}\n")
        findings = scan_file(p)
        for f in findings:
            assert secret not in f.redacted

    def test_reject_password_assign(self, tmp_path):
        p = _make_temp_file(tmp_path, "PASSWORD=MyS3cr3tP@ss!\n")
        findings = scan_file(p)
        assert len(findings) >= 1
        names = [f.rule_name for f in findings]
        assert "password-assign" in names

    def test_allow_password_placeholder(self, tmp_path):
        p = _make_temp_file(tmp_path, "PASSWORD=<REPLACE_ME>\n")
        findings = scan_file(p)
        assert len(findings) == 0
