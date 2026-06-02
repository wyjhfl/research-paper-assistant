# v1.0.1-rc.1 Staging Plan

## Current Version

- **版本号**: 1.0.1-rc.1
- **日期**: 2026-06-01

## Current File Status

- **Modified**: 27 files
- **New**: 14 files
- **Total**: 41 files

## Two-Commit Split Risk Analysis

将 41 个文件拆成两个 commit 存在以下交叉依赖风险：

1. **测试文件跨 Phase 耦合**：`apps/api/tests/test_backup_lifecycle.py` 同时包含 backup freshness（Phase 4）和 rc_evidence/release_notes（Phase 5-6）测试。拆分后 Commit 1 中的 test_backup_lifecycle.py 不完整，Commit 2 需要再次修改同一文件。

2. **文档交叉引用**：`docs/CI_CD_RUNBOOK.md`（Commit 1）引用了 RC Evidence Pack 和 Pre-Tag Check（Commit 2）的内容。拆分后 Commit 1 的文档包含指向尚未提交功能的引用。

3. **pre_tag_check 依赖链**：`scripts/pre_tag_check.py`（Commit 2）检查 `backup-freshness.yml`（Commit 1）和 `collect_rc_evidence.py`（Commit 2）。拆分后 Commit 1 无法独立通过 pre_tag_check 全部 9 项检查。

4. **AGENTS.md pitfall 跨 Phase**：pitfall #66（resolve_git）同时涉及 Phase 0 的脚本和 Phase 8 的测试。拆分后 Commit 1 的 AGENTS.md 不包含完整 pitfall 列表。

5. **独立可验证性**：两个 commit 各自 checkout 后均无法通过完整验证套件，违反原子提交原则。

**结论**：如果不使用 `git add -p` 精细拆分每个文件内的 hunk，两个 commit 均不是独立可验证状态。推荐单 commit 收口。

## Recommended: Single Commit

**Message**: `chore: prepare v1.0.1-rc.1 production hardening`

**Rationale**:
- 当前 27 modified + 14 new 是一个 RC hardening 原子包
- 多个测试文件和文档跨 Phase 耦合，拆分后各 commit 无法独立验证
- 单 commit 能保证 checkout 后整体一致
- 后续真实 CI / Docker / E2E 问题可用后续 rc.2 修复

### Should-Commit Files (41)

**Modified (27)**:

```
.env.example
.github/workflows/ci.yml
.gitignore
AGENTS.md
apps/api/app/config.py
apps/api/app/dependencies.py
apps/api/app/repositories/job_repo.py
apps/api/app/routers/jobs.py
apps/api/app/services/job_service.py
apps/api/scripts/cleanup_storage.py
apps/api/scripts/production_check.py
apps/api/scripts/storage_audit.py
apps/api/tests/test_backup_lifecycle.py
apps/api/tests/test_jobs.py
apps/api/tests/test_storage_lifecycle.py
docs/API_CONTRACT.md
docs/CI_CD_RUNBOOK.md
docs/OPERATIONS_BACKLOG.md
docs/OPERATIONS_MONITORING.md
docs/OPERATIONS_RUNBOOK.md
docs/RELEASE_CANDIDATE_CHECKLIST.md
docs/V1_0_1_BACKLOG.md
scripts/check_backup_freshness.py
scripts/ops_check.ps1
scripts/quick_gate.ps1
scripts/rc_gate.ps1
scripts/verify_all.ps1
```

**New (14)**:

```
.github/workflows/backup-freshness.yml
docker-compose.ci.yml
docs/RELEASE_NOTES_v1.0.1-rc.1.md
docs/V1_0_1_RC_HANDOFF.md
docs/V1_0_1_STAGING_PLAN.md
scripts/collect_rc_evidence.py
scripts/pre_tag_check.py
tests/test_backup_freshness_workflow.py
tests/test_ci_workflow.py
tests/test_gate_scripts_python_resolution.py
tests/test_pre_tag_check.py
tests/test_rc_evidence.py
tests/test_v1_0_1_final_handoff.py
tests/test_v1_0_1_rc_readiness.py
```

### Should-NOT-Commit Files

| Path | Reason |
|------|--------|
| `.env` | Contains secrets, gitignored |
| `artifacts/rc/` | Generated RC evidence, gitignored |
| `artifacts/backups/` | Backup manifests, gitignored |
| `artifacts/evals/` | Eval reports, gitignored |
| `__pycache__/` | Python bytecode cache |
| `.pytest_cache/` | pytest cache |
| `node_modules/` | Frontend dependencies |
| `.next/` | Next.js build output |
| `*.pyc` | Compiled Python files |

### Staging Command Draft

> **WARNING**: These commands are drafts only. Do NOT execute without manual review.

```bash
git add \
  .env.example \
  .github/workflows/ci.yml \
  .github/workflows/backup-freshness.yml \
  .gitignore \
  AGENTS.md \
  apps/api/app/config.py \
  apps/api/app/dependencies.py \
  apps/api/app/repositories/job_repo.py \
  apps/api/app/routers/jobs.py \
  apps/api/app/services/job_service.py \
  apps/api/scripts/cleanup_storage.py \
  apps/api/scripts/production_check.py \
  apps/api/scripts/storage_audit.py \
  apps/api/tests/test_backup_lifecycle.py \
  apps/api/tests/test_jobs.py \
  apps/api/tests/test_storage_lifecycle.py \
  docker-compose.ci.yml \
  docs/API_CONTRACT.md \
  docs/CI_CD_RUNBOOK.md \
  docs/OPERATIONS_BACKLOG.md \
  docs/OPERATIONS_MONITORING.md \
  docs/OPERATIONS_RUNBOOK.md \
  docs/RELEASE_CANDIDATE_CHECKLIST.md \
  docs/RELEASE_NOTES_v1.0.1-rc.1.md \
  docs/V1_0_1_BACKLOG.md \
  docs/V1_0_1_RC_HANDOFF.md \
  docs/V1_0_1_STAGING_PLAN.md \
  scripts/check_backup_freshness.py \
  scripts/collect_rc_evidence.py \
  scripts/ops_check.ps1 \
  scripts/pre_tag_check.py \
  scripts/quick_gate.ps1 \
  scripts/rc_gate.ps1 \
  scripts/verify_all.ps1 \
  tests/test_backup_freshness_workflow.py \
  tests/test_ci_workflow.py \
  tests/test_gate_scripts_python_resolution.py \
  tests/test_pre_tag_check.py \
  tests/test_rc_evidence.py \
  tests/test_v1_0_1_final_handoff.py \
  tests/test_v1_0_1_rc_readiness.py

git commit -m "chore: prepare v1.0.1-rc.1 production hardening"
```

### Tag and Push (manual steps after commit)

> These are NOT part of the current phase. Execute only after manual review.

```bash
git tag v1.0.1-rc.1
git push origin main --tags
```

## Optional Advanced: Two-Commit Plan

> **WARNING**: This plan is NOT recommended. Only use if you can manually split
> file-internal hunks with `git add -p` and run per-commit verification.
> Without per-commit verification, each commit will be in an inconsistent state.

### Commit 1: Production Hardening / Operations / CI Gates

**Message**: `chore: harden v1.0.1 production gates and operations`

**Scope**: Phase 0-4

**Modified files (19)**:

```
.env.example
.github/workflows/ci.yml
.gitignore
AGENTS.md
apps/api/app/dependencies.py
apps/api/app/repositories/job_repo.py
apps/api/app/routers/jobs.py
apps/api/app/services/job_service.py
apps/api/scripts/cleanup_storage.py
apps/api/scripts/production_check.py
apps/api/scripts/storage_audit.py
apps/api/tests/test_backup_lifecycle.py
apps/api/tests/test_jobs.py
apps/api/tests/test_storage_lifecycle.py
scripts/check_backup_freshness.py
scripts/ops_check.ps1
scripts/quick_gate.ps1
scripts/rc_gate.ps1
scripts/verify_all.ps1
```

**New files (5)**:

```
.github/workflows/backup-freshness.yml
docker-compose.ci.yml
tests/test_backup_freshness_workflow.py
tests/test_ci_workflow.py
tests/test_gate_scripts_python_resolution.py
```

**Known issues after this commit alone**:
- `test_backup_lifecycle.py` contains Phase 5-6 tests that reference not-yet-committed scripts
- `AGENTS.md` missing pitfall #66 (resolve_git) which is in Commit 2
- `pre_tag_check.py` not yet committed, so 9-check gate cannot run
- `docs/CI_CD_RUNBOOK.md` references RC Evidence Pack not yet committed

### Commit 2: RC Release Package / Evidence / Pre-tag / Handoff Docs

**Message**: `docs: add v1.0.1 rc release package`

**Scope**: Phase 5-8

**Modified files (8)**:

```
apps/api/app/config.py
docs/API_CONTRACT.md
docs/CI_CD_RUNBOOK.md
docs/OPERATIONS_BACKLOG.md
docs/OPERATIONS_MONITORING.md
docs/OPERATIONS_RUNBOOK.md
docs/RELEASE_CANDIDATE_CHECKLIST.md
docs/V1_0_1_BACKLOG.md
```

**New files (9)**:

```
docs/RELEASE_NOTES_v1.0.1-rc.1.md
docs/V1_0_1_RC_HANDOFF.md
docs/V1_0_1_STAGING_PLAN.md
scripts/collect_rc_evidence.py
scripts/pre_tag_check.py
tests/test_pre_tag_check.py
tests/test_rc_evidence.py
tests/test_v1_0_1_rc_readiness.py
tests/test_v1_0_1_final_handoff.py
```

## Pre-Staging Verification Checklist

Before executing any staging command:

- [ ] `python scripts/pre_tag_check.py` — 9/9 passed
- [ ] `python scripts/check_docs_secrets.py` — passed
- [ ] `python scripts/check_frontend_mojibake.py` — passed
- [ ] `git ls-files .env` — empty
- [ ] `git ls-files artifacts/rc artifacts/backups artifacts/evals` — empty
- [ ] All pytest suites passed
- [ ] Review RELEASE_NOTES for accuracy
- [ ] Confirm .env not staged (`git diff --cached .env` empty)
