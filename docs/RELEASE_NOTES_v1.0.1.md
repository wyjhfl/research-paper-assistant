# Release Notes: v1.0.1

**Release**: v1.0.1
**Based on**: v1.0.1-rc.1 / commit d1d37154c893b5a69c68b427824951dd9f991125
**Date**: 2026-06-04

## RC Acceptance

- v1.0.1-rc.1 was pushed to origin and CI was confirmed successful by manual user review of GitHub Actions.
- Local static checks passed: pre_tag_check (9/9), docs secret scan, frontend mojibake scan.
- Remote tag hash matched local tag hash: d1d37154c893b5a69c68b427824951dd9f991125.

## Changes (from v1.0.0 to v1.0.1)

### Phase 0: Python Gate 探测硬化
- `Test-PythonCandidate` + `Resolve-PythonCommand`，Windows Store alias 修复

### Phase 1: OPS_TOKEN 只读 Worker Health
- token 认证依赖、`hmac.compare_digest`、ops_check.ps1 支持

### Phase 2: Storage Orphan 清理 SOP
- `_referenced_rel_path`、dry-run 默认、JSON 输出、symlink 跳过

### Phase 3: CI/CD 生产门禁增强
- `frontend-e2e` + `backend-integration` jobs、`docker-compose.ci.yml`

### Phase 4: Backup Freshness 定时化
- `backup-freshness.yml`、`_try_parse_timestamp`、`BACKUP_FRESHNESS_ENABLED` gate

### Phase 5: RC Evidence Pack
- `collect_rc_evidence.py`、`artifacts/rc/`（gitignored）

### Phase 6: Release Package / Pre-tag
- `pre_tag_check.py`、`RELEASE_NOTES_v1.0.1-rc.1.md`、APP_VERSION bump

### Phase 7: Readiness Sweep
- `test_v1_0_1_rc_readiness.py`、编号修复、UTF-8 read_text 统一

### Phase 8: Final Handoff Audit
- `test_v1_0_1_final_handoff.py`、git tracking 验证、`resolve_git()` 修复 PATH 编码损坏

## Not Executed Locally

The following items were NOT executed in the local release process:

- Docker Compose backend-integration (CI only)
- Playwright E2E (CI only)
- verify_all.ps1
- rc_gate.ps1
- eval_real_model.py

## Security

- No force push
- No tag rewrite (v1.0.1-rc.1 tag preserved)
- No .env/artifacts committed
- No restore/backup/cleanup --confirm executed
- No eval_real_model.py executed
