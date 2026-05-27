# Release Evidence — v1.0.0

本文件记录 v1.0.0 正式发布前的完整验证命令与结果，用于发布审计。

v1.0.0 基于 v1.0.0-rc.1 + Phase 44 E2E 证据更新。RC gate 全部 7 步通过，E2E 例外已消除。

## 1. Documentation Secret Scan

命令：`python scripts/check_docs_secrets.py`

结果：✅ DOC SECRET CHECK PASSED

## 2. Frontend Mojibake Scan

命令：`python scripts/check_frontend_mojibake.py`

结果：✅ FRONTEND MOJIBAKE CHECK PASSED

## 3. Production Check

命令：`docker compose exec -T backend python scripts/production_check.py`

结果：✅ 19/19 ALL CHECKS PASSED

检查项：Database / pgvector / Core tables / Storage / Eval / CORS / Real model / Alembic / Backup dir / Backup manifest / Auth config / Job worker / Job poll interval / Job max attempts / Job stale running / Maintenance scripts / Validate manifest script / ENV / Embedding dimension

## 4. Alembic Current

命令：`docker compose exec -T backend python -m alembic current`

结果：✅ 003_job_runs (head)

## 5. Backend Pytest

命令：`docker compose exec -T backend python -m pytest tests/ -q`

结果：✅ 460 passed, 22 skipped, 0 failed

## 6. Frontend Build

命令：`cd apps/web && npm run build`

结果：✅ Next.js 15.5.18 编译成功，13 个路由，0 错误

## 7. Playwright E2E

命令：`cd apps/web && npx playwright test`

结果：✅ 103 passed, 0 failed

7 个 spec 文件全部通过：
- api-error-display.spec.ts
- auth.spec.ts
- jobs.spec.ts
- no-mojibake.spec.ts
- page-smoke.spec.ts
- usage.spec.ts
- user-switcher.spec.ts

## 8. Backup Manifest Validate

命令：`docker compose exec -T backend python scripts/validate_backup_manifest.py artifacts/backups/backup_manifest_20260527_035009.json`

结果：✅ ok: true, errors: [], warnings: []

## 9. Restore Dry-Run

命令：`powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_20260527_035009.json -DryRun`

结果：✅ DB backup found + Storage backup found + Eval backup found，Validation passed. No data was modified.

## 发布前状态

| 检查项 | 结果 |
|--------|------|
| .env 未跟踪 | 确认（.gitignore 包含 .env） |
| v1.0.0-rc.1 tag | 已创建并推送到 GitHub |
| Phase 44 E2E 证据更新 commit | 9b39612 |
| RC gate 全部 7 步 | ✅ 全部通过 |
| E2E 例外 | 已消除（Phase 44 补跑 103/103 通过） |

## 代码变更（Phase 43–44）

- `apps/api/tests/test_backup_lifecycle.py`：新增 `_get_project_root()` 辅助函数，替换 27 处硬编码路径计算，修复 Docker 容器内路径解析问题；新增/更新 RC gate 相关测试
- `docs/RELEASE_NOTES_v1.0.0-rc.1.md`：更新 E2E 例外状态为已消除
- `docs/RC_EVIDENCE_v1.0.0-rc.1.md`：标题改为 E2E Exception Resolved，新增 Phase 44 补跑记录
