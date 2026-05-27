# Deployment Evidence — v1.0.0

本文件记录 v1.0.0 部署演练执行结果，用于运维审计。

## 1. Git Status

命令：`git status --short`

结果：✅ 部署演练执行时记录结果；本次提交包含 Runbook、Evidence、README、AGENTS、测试更新

## 2. Docker Compose Config

命令：`docker compose config --quiet`

结果：✅ 配置有效，无错误

## 3. Docker 服务状态

命令：`docker compose ps`

结果：✅ 3 个服务运行中

| 服务 | 状态 | 端口 |
|------|------|------|
| backend | Up (healthy) | 8091→8000 |
| frontend | Up | 3000→3000 |
| postgres | Up (healthy) | 5500→5432 |

## 4. Alembic Upgrade Head

命令：`docker compose exec -T backend python -m alembic upgrade head`

结果：✅ 已在最新版本，无需迁移

## 5. Alembic Current

命令：`docker compose exec -T backend python -m alembic current`

结果：✅ 003_job_runs (head)

## 6. Production Check

命令：`docker compose exec -T backend python scripts/production_check.py`

结果：✅ 19/19 ALL CHECKS PASSED

## 7. Health Endpoint

命令：`GET /health`

结果：✅ `{"status": "ok", "version": "1.0.0", "database": "connected"}`

## 8. Ready Endpoint

命令：`GET /health/ready`

结果：✅ `{"ready": true, "database": "connected", "alembic_current": "003_job_runs", "alembic_head": "003_job_runs"}`

## 9. Worker Health

命令：`GET /jobs/worker/health`（需认证）

结果：✅ `{"worker_enabled": true, "poll_interval_seconds": 1.0, "max_attempts_default": 1, "stale_running_seconds": 900, "running_count": 0, "pending_count": 0, "failed_count": 0, "stale_running_count": 0}`

> AUTH_ENABLED=true 时需 session cookie 认证。X-User-Id header 被拒绝（ALLOW_DEV_USER_HEADER=false）。

## 10. Backup

命令：`powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1`

结果：✅ 全量备份完成

- DB backup: db_backup_20260527_080654.sql
- Storage backup: storage_backup_20260527_080654.zip
- Eval backup: eval_backup_20260527_080654.zip
- Manifest: backup_manifest_20260527_080654.json

## 11. Backup Manifest Validate

命令：`docker compose exec -T backend python scripts/validate_backup_manifest.py artifacts/backups/backup_manifest_20260527_080654.json`

结果：✅ `{"ok": true, "errors": [], "warnings": []}`

## 12. Restore Dry-Run

命令：`powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_20260527_080654.json -DryRun`

结果：✅ DB + Storage + Eval 均找到，Validation passed. No data was modified.

Drill record: restore_drill_20260527_081640.json

## 13. Storage Audit

命令：`docker compose exec -T backend python scripts/storage_audit.py`

结果：✅ 无 missing files

- total_files: 大量（含测试遗留）
- orphan_count: 10408（测试遗留；清理前必须先运行 `cleanup_storage.py` dry-run，人工确认后才可 `--confirm`）
- missing_count: 0

## 前端 Smoke

| 页面 | 预期 | 实际 |
|------|------|------|
| http://localhost:3000 | 首页 | ✅ 可访问 |
| http://localhost:3000/login | 登录页 | ✅ 可访问 |
| http://localhost:3000/register | 注册页 | ✅ 可访问 |
| http://localhost:3000/jobs | 任务列表 | ✅ 可访问 |
| http://localhost:3000/usage | 质量看板 | ✅ 可访问 |

注册/登录 smoke：✅ 注册成功 → 登录成功 → 获取 session cookie

## 部署演练总结

| 步骤 | 结果 |
|------|------|
| git status | ✅ 已记录 |
| docker compose config | ✅ 有效 |
| docker compose ps | ✅ 3 服务运行 |
| alembic upgrade head | ✅ 最新 |
| alembic current | ✅ 003_job_runs (head) |
| production_check | ✅ 19/19 PASSED |
| /health | ✅ ok |
| /health/ready | ✅ ready |
| /jobs/worker/health | ✅ worker_enabled |
| backup_all | ✅ 完成 |
| validate manifest | ✅ ok: true |
| restore dry-run | ✅ 通过 |
| storage_audit | ✅ 0 missing |
| 前端 smoke | ✅ 5 页面可访问 |
