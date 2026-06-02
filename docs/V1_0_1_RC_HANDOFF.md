# v1.0.1-rc.1 RC Handoff Document

## Version

- **版本号**: 1.0.1-rc.1
- **类型**: Patch Release Candidate
- **日期**: 2026-06-01

## Change Summary (Phase 0-7)

| Phase | Description | Key Deliverables |
|-------|-------------|------------------|
| Phase 0 | Python Gate 探测硬化 | `Test-PythonCandidate` + `Resolve-PythonCommand`，Windows Store alias 修复 |
| Phase 1 | OPS_TOKEN 只读 Worker Health | token 认证依赖、`hmac.compare_digest`、ops_check.ps1 支持 |
| Phase 2 | Storage Orphan 清理 SOP | `_referenced_rel_path`、dry-run 默认、JSON 输出、symlink 跳过 |
| Phase 3 | CI/CD 生产门禁增强 | `frontend-e2e` + `backend-integration` jobs、`docker-compose.ci.yml` |
| Phase 4 | Backup Freshness 定时化 | `backup-freshness.yml`、`_try_parse_timestamp`、`BACKUP_FRESHNESS_ENABLED` gate |
| Phase 5 | RC Evidence Pack | `collect_rc_evidence.py`、`artifacts/rc/`（gitignored） |
| Phase 6 | Release Package / Pre-tag | `pre_tag_check.py`、`RELEASE_NOTES_v1.0.1-rc.1.md`、APP_VERSION=1.0.1-rc.1 |
| Phase 7 | Readiness Sweep | `test_v1_0_1_rc_readiness.py`、编号修复、UTF-8 read_text 统一 |
| Phase 8 | Final Handoff Audit | `test_v1_0_1_final_handoff.py`、git tracking 验证、`resolve_git()` 修复 PATH 编码损坏 |

## Files to Commit

### Modified (27 files)

```
 M .env.example
 M .github/workflows/ci.yml
 M .gitignore
 M AGENTS.md
 M apps/api/app/config.py
 M apps/api/app/dependencies.py
 M apps/api/app/repositories/job_repo.py
 M apps/api/app/routers/jobs.py
 M apps/api/app/services/job_service.py
 M apps/api/scripts/cleanup_storage.py
 M apps/api/scripts/production_check.py
 M apps/api/scripts/storage_audit.py
 M apps/api/tests/test_backup_lifecycle.py
 M apps/api/tests/test_jobs.py
 M apps/api/tests/test_storage_lifecycle.py
 M docs/API_CONTRACT.md
 M docs/CI_CD_RUNBOOK.md
 M docs/OPERATIONS_BACKLOG.md
 M docs/OPERATIONS_MONITORING.md
 M docs/OPERATIONS_RUNBOOK.md
 M docs/RELEASE_CANDIDATE_CHECKLIST.md
 M docs/V1_0_1_BACKLOG.md
 M scripts/check_backup_freshness.py
 M scripts/ops_check.ps1
 M scripts/quick_gate.ps1
 M scripts/rc_gate.ps1
 M scripts/verify_all.ps1
```

### New (14 files)

```
?? .github/workflows/backup-freshness.yml
?? docker-compose.ci.yml
?? docs/RELEASE_NOTES_v1.0.1-rc.1.md
?? docs/V1_0_1_RC_HANDOFF.md
?? docs/V1_0_1_STAGING_PLAN.md
?? scripts/collect_rc_evidence.py
?? scripts/pre_tag_check.py
?? tests/test_backup_freshness_workflow.py
?? tests/test_ci_workflow.py
?? tests/test_gate_scripts_python_resolution.py
?? tests/test_pre_tag_check.py
?? tests/test_rc_evidence.py
?? tests/test_v1_0_1_rc_readiness.py
?? tests/test_v1_0_1_final_handoff.py
```

## Files NOT to Commit

| Path | Reason |
|------|--------|
| `.env` | Contains secrets, gitignored |
| `artifacts/rc/` | Generated RC evidence, gitignored |
| `artifacts/backups/` | Backup manifests, gitignored |
| `artifacts/evals/` | Eval reports, gitignored |
| Any `rc_evidence_*.json` / `rc_evidence_*.md` | Generated artifacts in artifacts/rc/ |
| Any `pre_tag_check_*.json` | Generated artifacts in artifacts/rc/ |

## Verification Results

> Local static verification only. Docker, Playwright, GitHub Actions, verify_all, rc_gate, and real model eval were NOT executed.

| Check | Result |
|-------|--------|
| pytest (6 test files, 192 tests) | passed |
| pytest (backup_lifecycle, 35 tests) | passed |
| pytest (gate_scripts_python_resolution, 41 tests) | passed |
| pytest (check_docs_secrets, 34 tests) | passed |
| check_docs_secrets.py | passed |
| check_frontend_mojibake.py | passed |
| collect_rc_evidence.py | exit 0, version=1.0.1-rc.1 |
| pre_tag_check.py | 9/9 passed, ok=true, no warnings |
| git diff --check | no whitespace errors (only LF/CRLF warnings) |
| git ls-files .env | empty (not tracked) |
| git ls-files artifacts/rc artifacts/backups artifacts/evals | empty (not tracked) |

## Unexecuted Items

| Item | Reason |
|------|--------|
| Docker Compose backend-integration | Not executed in this environment |
| Playwright E2E | Not executed in this environment |
| GitHub Actions CI | Not executed in this environment |
| verify_all.ps1 | Not executed in this environment |
| rc_gate.ps1 | Not executed in this environment |
| eval_real_model.py | Not executed in this environment |
| pre_tag_check.py exit 0 | Now passes 9/9 with resolve_git() registry fallback |

## Pre-Tag Manual Steps

1. Ensure git is available (scripts use `resolve_git()` with registry fallback on Windows)
2. Run `python -m pytest tests/test_ci_workflow.py tests/test_backup_freshness_workflow.py tests/test_rc_evidence.py tests/test_pre_tag_check.py tests/test_v1_0_1_rc_readiness.py tests/test_v1_0_1_final_handoff.py -q` — all must pass
3. Run `python -m pytest tests/test_gate_scripts_python_resolution.py tests/test_check_docs_secrets.py -q` — all must pass
4. Run `python -m pytest apps/api/tests/test_backup_lifecycle.py -q -k "ci_workflow or backup_freshness or release_notes or rc_evidence"` — all must pass
5. Run `python scripts/check_docs_secrets.py` — must pass
6. Run `python scripts/check_frontend_mojibake.py` — must pass
7. Run `python scripts/pre_tag_check.py` — all 9 checks must pass
8. Run `python scripts/collect_rc_evidence.py --output-dir artifacts/rc` — save evidence locally
9. Run `git ls-files .env` — must return empty
10. Review `docs/RELEASE_NOTES_v1.0.1-rc.1.md` for accuracy
11. Stage all files listed in "Files to Commit" above (see `docs/V1_0_1_STAGING_PLAN.md` for single-commit draft)
12. Commit with message: `chore: prepare v1.0.1-rc.1 production hardening`
13. Tag: `git tag v1.0.1-rc.1`
14. Push: `git push origin main --tags`

## Constraints

- No .env content in any committed file
- No API keys (sk-/tp- prefixes) in any committed file
- No DATABASE_URL real values in any committed file
- No Authorization headers in any committed file
- No session tokens in any committed file
- No absolute host paths in any committed file
- No ALL CHECKS PASSED claims without full gate execution
- No mojibake in any file
