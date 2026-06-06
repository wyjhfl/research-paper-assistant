from __future__ import annotations

import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CI_YML = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
CI_COMPOSE = PROJECT_ROOT / "docker-compose.ci.yml"


def _load_ci():
    data = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    trigger_key = True if True in data else "on"
    data["on"] = data[trigger_key]
    return data


def _load_ci_compose():
    return yaml.safe_load(CI_COMPOSE.read_text(encoding="utf-8"))


class TestCIWorkflowStructure:
    def test_ci_yml_exists(self):
        assert CI_YML.exists(), ".github/workflows/ci.yml not found"

    def test_workflow_dispatch_present(self):
        ci = _load_ci()
        assert "workflow_dispatch" in ci["on"], "workflow_dispatch trigger missing"

    def test_workflow_dispatch_has_inputs(self):
        ci = _load_ci()
        wd = ci["on"]["workflow_dispatch"]
        assert "inputs" in wd, "workflow_dispatch missing inputs"
        assert "run_e2e" in wd["inputs"], "run_e2e input missing"
        assert "run_backend_integration" in wd["inputs"], "run_backend_integration input missing"

    def test_concurrency_present(self):
        ci = _load_ci()
        assert "concurrency" in ci, "concurrency group missing"
        assert "group" in ci["concurrency"], "concurrency group name missing"
        assert "cancel-in-progress" in ci["concurrency"], "cancel-in-progress missing"

    def test_docs_and_security_job_present(self):
        ci = _load_ci()
        assert "docs-and-security" in ci["jobs"], "docs-and-security job missing"

    def test_backend_unit_job_present(self):
        ci = _load_ci()
        assert "backend-unit" in ci["jobs"], "backend-unit job missing"

    def test_frontend_build_job_present(self):
        ci = _load_ci()
        assert "frontend-build" in ci["jobs"], "frontend-build job missing"

    def test_frontend_e2e_job_present(self):
        ci = _load_ci()
        assert "frontend-e2e" in ci["jobs"], "frontend-e2e job missing"

    def test_backend_integration_job_present(self):
        ci = _load_ci()
        assert "backend-integration" in ci["jobs"], "backend-integration job missing"

    def test_actions_use_node24_compatible_versions(self):
        content = CI_YML.read_text(encoding="utf-8")
        deprecated = [
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/setup-node@v4",
        ]
        for action in deprecated:
            assert action not in content, f"CI must not use deprecated Node 20 action: {action}"
        assert "actions/checkout@v6" in content
        assert "actions/setup-python@v6" in content
        assert "actions/setup-node@v6" in content


class TestFrontendE2E:
    def test_playwright_install_step(self):
        ci = _load_ci()
        steps = ci["jobs"]["frontend-e2e"]["steps"]
        commands = [s.get("run", "") for s in steps]
        assert any("playwright install" in c for c in commands), "playwright install step missing"

    def test_e2e_test_command(self):
        ci = _load_ci()
        steps = ci["jobs"]["frontend-e2e"]["steps"]
        commands = [s.get("run", "") for s in steps]
        assert any("test:e2e" in c or "playwright test" in c for c in commands), "E2E test command missing"

    def test_working_directory(self):
        ci = _load_ci()
        steps = ci["jobs"]["frontend-e2e"]["steps"]
        wd_steps = [s for s in steps if s.get("working-directory") == "apps/web"]
        assert len(wd_steps) >= 2, "E2E steps should use working-directory: apps/web"

    def test_node_version(self):
        ci = _load_ci()
        steps = ci["jobs"]["frontend-e2e"]["steps"]
        setup_steps = [s for s in steps if "setup-node" in s.get("uses", "")]
        assert len(setup_steps) >= 1, "setup-node step missing"
        node_version = setup_steps[0].get("with", {}).get("node-version", "")
        assert node_version == "22", f"Expected Node 22, got {node_version}"

    def test_if_not_on_pull_request(self):
        ci = _load_ci()
        if_condition = ci["jobs"]["frontend-e2e"].get("if", "")
        assert "pull_request" not in if_condition, "frontend-e2e should not run on pull_request by default"


class TestBackendIntegration:
    def test_docker_compose_up(self):
        ci = _load_ci()
        steps = ci["jobs"]["backend-integration"]["steps"]
        commands = [s.get("run", "") for s in steps]
        assert any("docker compose" in c and "up" in c for c in commands), "docker compose up step missing"

    def test_docker_compose_down(self):
        ci = _load_ci()
        steps = ci["jobs"]["backend-integration"]["steps"]
        commands = [s.get("run", "") for s in steps]
        assert any("docker compose" in c and "down" in c for c in commands), "docker compose down step missing"

    def test_teardown_always_runs(self):
        ci = _load_ci()
        steps = ci["jobs"]["backend-integration"]["steps"]
        teardown_steps = [s for s in steps if "docker compose" in s.get("run", "") and "down" in s.get("run", "")]
        assert len(teardown_steps) >= 1, "teardown step missing"
        assert teardown_steps[0].get("if") == "always()", "teardown should run with if: always()"

    def test_no_eval_real_model(self):
        content = CI_YML.read_text(encoding="utf-8")
        assert "eval_real_model" not in content, "CI must not run eval_real_model.py"
        assert "RunRealModelEval" not in content, "CI must not pass RunRealModelEval"

    def test_smoke_check_step(self):
        ci = _load_ci()
        steps = ci["jobs"]["backend-integration"]["steps"]
        commands = [s.get("run", "") for s in steps]
        assert any("smoke_check" in c for c in commands), "smoke_check step missing"

    def test_pytest_step(self):
        ci = _load_ci()
        steps = ci["jobs"]["backend-integration"]["steps"]
        commands = [s.get("run", "") for s in steps]
        assert any("pytest" in c for c in commands), "pytest step missing"

    def test_uses_ci_compose_override(self):
        content = CI_YML.read_text(encoding="utf-8")
        assert "docker-compose.ci.yml" in content, "backend-integration must use docker-compose.ci.yml"

    def test_all_compose_commands_use_override(self):
        ci = _load_ci()
        steps = ci["jobs"]["backend-integration"]["steps"]
        for step in steps:
            run = step.get("run", "")
            if "docker compose" in run and run.strip():
                assert "docker-compose.ci.yml" in run, f"docker compose command must include docker-compose.ci.yml: {run[:80]}"

    def test_explicit_test_list_not_bare_tests(self):
        content = CI_YML.read_text(encoding="utf-8")
        assert "pytest tests/ -q" not in content, "must not use bare 'pytest tests/ -q'; use explicit test file list"

    def test_no_backup_lifecycle_in_integration(self):
        ci = _load_ci()
        steps = ci["jobs"]["backend-integration"]["steps"]
        commands = [s.get("run", "") for s in steps]
        for cmd in commands:
            assert "test_backup_lifecycle" not in cmd, "test_backup_lifecycle.py should not be in backend-integration"

    def test_no_production_health_in_integration(self):
        ci = _load_ci()
        steps = ci["jobs"]["backend-integration"]["steps"]
        commands = [s.get("run", "") for s in steps]
        for cmd in commands:
            assert "test_production_health" not in cmd, "test_production_health.py should not be in backend-integration"


class TestCIComposeOverride:
    def test_ci_compose_exists(self):
        assert CI_COMPOSE.exists(), "docker-compose.ci.yml not found"

    def test_ci_compose_no_secrets(self):
        content = CI_COMPOSE.read_text(encoding="utf-8")
        for pattern in ["sk-", "tp-", "API_KEY=", "SECRET=", "PASSWORD=", "Authorization"]:
            assert pattern not in content, f"Potential secret in docker-compose.ci.yml: {pattern}"

    def test_ci_compose_env_file_empty(self):
        ci_compose = _load_ci_compose()
        backend = ci_compose["services"]["backend"]
        env_file = backend.get("env_file")
        assert env_file == [] or env_file is None, f"env_file must be empty or absent in CI override, got: {env_file}"

    def test_ci_compose_no_dot_env_reference(self):
        content = CI_COMPOSE.read_text(encoding="utf-8")
        assert ".env" not in content, "docker-compose.ci.yml must not reference .env"

    def test_ci_compose_local_provider(self):
        ci_compose = _load_ci_compose()
        backend_env = ci_compose["services"]["backend"]["environment"]
        assert backend_env.get("LLM_PROVIDER") == "local", "CI compose must use local LLM provider"
        assert backend_env.get("EMBEDDING_PROVIDER") == "local", "CI compose must use local embedding provider"
        assert backend_env.get("REAL_MODEL_REQUIRED") == "false", "CI compose must set REAL_MODEL_REQUIRED=false"


class TestCISecurity:
    def test_no_secrets_in_workflow(self):
        content = CI_YML.read_text(encoding="utf-8")
        for pattern in ["sk-", "tp-", "API_KEY=", "SECRET=", "PASSWORD="]:
            assert pattern not in content, f"Potential secret found: {pattern}"

    def test_no_restore_confirm(self):
        content = CI_YML.read_text(encoding="utf-8")
        assert "ConfirmRestore" not in content, "CI must not run restore with -ConfirmRestore"

    def test_no_artifact_upload_of_secrets(self):
        ci = _load_ci()
        for job_name, job in ci["jobs"].items():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if "upload-artifact" in uses:
                    with_val = step.get("with", {}).get("path", "")
                    assert "artifacts/backups" not in with_val, f"{job_name}: must not upload backups"
                    assert "artifacts/evals" not in with_val, f"{job_name}: must not upload evals"
                    assert ".env" not in with_val, f"{job_name}: must not upload .env"
