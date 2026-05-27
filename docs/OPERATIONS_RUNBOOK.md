# Operations Runbook

运维手册：覆盖服务启停、迁移、备份恢复、存储治理、Job 排障、评测验收。

> 每一步标注操作类型：**只读** / **写入** / **破坏性** / **需要确认**

---

## 1. 启动/停止服务

| 操作 | 命令 | 类型 |
|------|------|------|
| 启动全部服务 | `docker compose up --build` | 写入 |
| 后台启动 | `docker compose up --build -d` | 写入 |
| 停止服务 | `docker compose down` | 写入 |
| 停止并删除 volume | `docker compose down -v` | 破坏性 |

---

## 2. Alembic Migration 检查与升级

| 操作 | 命令 | 类型 |
|------|------|------|
| 查看当前版本 | `docker compose exec backend python -m alembic current` | 只读 |
| 查看 head 版本 | `docker compose exec backend python -m alembic heads` | 只读 |
| 升级到最新 | `docker compose exec backend python -m alembic upgrade head` | 写入 |
| Stamp baseline（旧环境） | `docker compose exec backend python -m alembic stamp 001_baseline` | 写入 |
| 生成新 migration | `cd apps/api && python -m alembic revision --autogenerate -m "描述"` | 写入 |

---

## 3. Production Check

| 操作 | 命令 | 类型 |
|------|------|------|
| 运行生产门禁 | `docker compose exec backend python scripts/production_check.py` | 只读 |
| 通过 verify_all | `powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunProductionCheck` | 只读 |

检查项：DB 连接、pgvector、核心表、Storage 可写、CORS、真实模型配置、Alembic 版本、备份目录、维护脚本。

退出码：有 FAIL → 1，只有 WARN → 0，全 PASS → 0。

---

## 4. Backup

| 操作 | 命令 | 类型 |
|------|------|------|
| 全量备份 | `powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1` | 写入 |
| 单独备份数据库 | `powershell -ExecutionPolicy Bypass -File scripts/backup_postgres.ps1` | 写入 |
| 单独备份 Storage | `powershell -ExecutionPolicy Bypass -File scripts/backup_storage.ps1` | 写入 |

产物：`artifacts/backups/backup_manifest_*.json` + `db/` + `storage/` + `evals/`

---

## 5. Validate Backup Manifest

| 操作 | 命令 | 类型 |
|------|------|------|
| 校验 manifest | `docker compose exec backend python scripts/validate_backup_manifest.py artifacts/backups/backup_manifest_xxx.json` | 只读 |

校验：JSON 可读、BOM 兼容、必填字段、引用文件存在、无 secrets。

输出：`{"ok": true/false, "errors": [...], "warnings": [...]}`

---

## 6. Restore Dry-Run

| 操作 | 命令 | 类型 |
|------|------|------|
| Dry-run 验证 | `powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath <path> -DryRun` | 只读 |
| 实际恢复 | `powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath <path> -ConfirmRestore` | 破坏性 / 需要确认 |

> **禁止在门禁脚本中执行 `-ConfirmRestore`。** DryRun 不需要 `-ConfirmRestore`，不写入 DB/Storage。

DryRun 缺 db/storage 备份时 `exit 1`。

---

## 7. Storage Audit & Cleanup

| 操作 | 命令 | 类型 |
|------|------|------|
| 存储审计 | `docker compose exec backend python scripts/storage_audit.py` | 只读 |
| 清理 dry-run | `docker compose exec backend python scripts/cleanup_storage.py` | 只读 |
| 清理执行 | `docker compose exec backend python scripts/cleanup_storage.py --confirm` | 破坏性 / 需要确认 |

审计输出：total_files、total_bytes、orphan_files、missing_files。

清理安全：路径穿越防护（`relative_to`）、symlink 跳过、默认 dry-run。

---

## 8. Job Cleanup

| 操作 | 命令 | 类型 |
|------|------|------|
| 清理 dry-run | `docker compose exec backend python scripts/cleanup_jobs.py` | 只读 |
| 清理执行 | `docker compose exec backend python scripts/cleanup_jobs.py --confirm` | 破坏性 / 需要确认 |
| 指定保留天数 | `docker compose exec backend python scripts/cleanup_jobs.py --retention-days=60` | 只读 |

默认 retention_days=30，只删 completed/cancelled/failed 且 finished_at 早于 N 天的 job。retention_days < 1 时拒绝执行。

---

## 9. Job Worker Health / Stale Job / Retry 排障

| 操作 | 命令 | 类型 |
|------|------|------|
| Worker 健康状态 | `curl http://localhost:8091/jobs/worker/health` | 只读 |
| 查看卡住任务数 | 响应中 `stale_running_count` 字段 | 只读 |
| 重试失败 Job | `curl -X POST http://localhost:8091/jobs/{job_id}/retry` | 写入 |
| 前端 /jobs 页面 | http://localhost:3000/jobs | 只读 |

卡住判定：`JOB_STALE_RUNNING_SECONDS`（默认 3600）。

---

## 10. Real Model Eval 验收入口

| 操作 | 命令 | 类型 |
|------|------|------|
| 连通性测试 | `docker compose exec backend python scripts/model_smoke_check.py` | 只读 |
| 评测运行 | `docker compose exec backend python scripts/eval_real_model.py` | 只读 |
| 通过 verify_all | `powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunRealModelEval` | 只读 |

需要 `REAL_MODEL_REQUIRED=true` + `openai_compatible` provider。

报告位置：`artifacts/evals/real_model_eval_latest.json`

---

## 11. RC Gate

| 操作 | 命令 | 类型 |
|------|------|------|
| 完整 RC 门禁 | `powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1` | 只读 |
| 跳过 E2E | `powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -SkipE2E` | 只读 |
| 含备份验证 | `powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -ManifestPath <path>` | 只读 |
| 跳过 production check | `powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -SkipProductionCheck` | 只读 |

> RC gate 不执行真实 restore，不执行 `-ConfirmRestore`。
> **production_check FAIL 会立即导致 RC gate 失败退出**，不允许降级为 WARN。PASS WITH WARNINGS 时通过（exit code 0）。
> `-ManifestPath` 只接受项目相对路径（如 `artifacts/backups/backup_manifest_xxx.json`），不接受绝对路径。
> `-SkipProductionCheck` 用于开发环境跳过生产配置检查；正式 RC 门禁不得跳过。

---

## 12. Test DB / pytest Hang Recovery

后端 pytest 使用 `research_assistant_test` 数据库，每个测试函数前执行 `TRUNCATE TABLE ... CASCADE`。如果并行运行多个 pytest 进程，或前一次 pytest 异常退出，会导致 TRUNCATE/DDL 锁死。

### 症状

- `docker compose exec -T backend python -m pytest` 长时间无输出（> 5 分钟）
- `docker compose exec -T backend python -m pytest` 输出卡在 `collecting ...` 之后
- `production_check.py` 正常但 pytest 超时

### 诊断步骤

1. 查看挂起连接：

```powershell
docker exec research-paper-assistant-postgres-1 psql -U postgres -d research_assistant -c "SELECT pid, state, LEFT(query, 80) as query FROM pg_stat_activity WHERE datname='research_assistant_test' AND state='active'"
```

2. 如果看到大量 `TRUNCATE TABLE` 行处于 `active` 状态，即为锁死。

### 恢复步骤

1. **终止 test DB 残留连接**：

```powershell
docker exec research-paper-assistant-postgres-1 psql -U postgres -d research_assistant -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='research_assistant_test' AND pid <> pg_backend_pid()"
```

2. **重新运行 pytest**，确认不再卡住。

3. **如果终止连接后仍卡住**，重启 backend 容器：

```powershell
docker compose restart backend
```

4. **如果重启 backend 后仍卡住**，重启 postgres：

```powershell
docker compose restart postgres
# 等待 postgres 就绪后重启 backend
docker compose restart backend
```

### 预防规则

- **不要并行运行多个后端 pytest**，避免 DDL deadlock
- **不要在 CI 和本地同时跑 pytest**，它们共享同一个 test DB
- **pytest 异常退出后**，先执行步骤 1 诊断再重跑
- **如果连续 3 次恢复后仍卡住**，停止继续重跑，记录为环境问题，等待最终 RC gate 时统一验证

### 何时停止重跑

- 恢复连接后重跑仍卡住 → 重启 backend 后重跑
- 重启 backend 后仍卡住 → 重启 postgres 后重跑
- 重启 postgres 后仍卡住 → **停止**，记录为环境问题，推迟到最终 RC gate
- 不要在同一 session 内反复尝试超过 3 次
