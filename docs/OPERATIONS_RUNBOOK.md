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

> **Python 探测**：所有 gate 脚本（`verify_all.ps1`、`quick_gate.ps1`、`rc_gate.ps1`）会自动探测宿主机 Python：优先 `python`，其次 `py -3`（Windows Python Launcher）。两者都不存在时明确报错退出（`ERROR: Python was not found. Install Python or add it to PATH.`），不会静默跳过。

---

## 4. Backup

| 操作 | 命令 | 类型 |
|------|------|------|
| 全量备份 | `powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1` | 写入 |
| 单独备份数据库 | `powershell -ExecutionPolicy Bypass -File scripts/backup_postgres.ps1` | 写入 |
| 单独备份 Storage | `powershell -ExecutionPolicy Bypass -File scripts/backup_storage.ps1` | 写入 |

产物：`artifacts/backups/backup_manifest_*.json` + `db/` + `storage/` + `evals/`

### Backup Freshness 检查

| 操作 | 命令 | 类型 |
|------|------|------|
| 检查备份新鲜度 | `python scripts/check_backup_freshness.py --max-age-hours 24` | 只读 |
| 指定备份目录 | `python scripts/check_backup_freshness.py --backups-dir artifacts/backups --max-age-hours 24` | 只读 |
| 允许缺失 manifest | `python scripts/check_backup_freshness.py --allow-missing-manifest` | 只读 |

输出 JSON：`ok`、`latest_manifest`（仅文件名，不含绝对路径）、`age_hours`、`max_age_hours`、`checked_manifest_count`、`skipped_manifest_count`、`timestamp_source`、`warnings`。

退出码：0 = ok，1 = stale/missing/all-corrupted。

> **定时检查**：GitHub Actions workflow `backup-freshness.yml` 每日 00:30 UTC 自动运行。默认 schedule 不执行（避免 hosted runner 默认红灯），需在 GitHub 仓库设置 `BACKUP_FRESHNESS_ENABLED=true` repository variable 后才启用。生产落地需要 self-hosted runner 或外部监控环境能访问备份 manifest 目录。GitHub hosted runner 不具备生产备份可见性。stale/missing manifest 只告警/失败，不自动 backup、不 restore、不删除文件。

> **timestamp 解析与选择**：`check_backup_freshness.py` 按 manifest `timestamp` 字段选择最新 manifest（不按文件 mtime），支持 `yyyyMMdd_HHmmssZ`（backup_all.ps1 格式）、ISO Z、ISO aware、naive ISO。空或非法 timestamp fallback 到文件 mtime，`timestamp_source` 标记为 `mtime_fallback` 并在 warnings 中说明。损坏 JSON manifest 会跳过并在 warnings 中记录文件名（不含绝对路径）；全部损坏则 `ok=false`、exit 1。`--allow-missing-manifest` 只适用于目录无 manifest 文件的情况，不掩盖"存在 manifest 但全损坏"的问题。

---

## 4a. RC Evidence Pack 收集

| 操作 | 命令 | 类型 |
|------|------|------|
| 收集 RC 证据 | `python scripts/collect_rc_evidence.py --output-dir artifacts/rc` | 只读 |

- 只读收集当前仓库状态和门禁结果摘要
- 输出到 `artifacts/rc/`（已 gitignored），不提交到 Git
- 输出 JSON + Markdown 摘要
- 证据内容：timestamp、version、git branch/commit/dirty、workflow 文件存在性、scanner 结果、backup freshness 启用说明
- **证据不得包含**：.env 内容、API key、Authorization、DATABASE_URL 真实值、session token、artifacts/backups 内容、artifacts/evals 内容、宿主机绝对路径
- 不执行 backup、restore、cleanup --confirm、docker compose up、真实模型 eval

---

## 4b. Pre-Tag Check

| 操作 | 命令 | 类型 |
|------|------|------|
| 打 tag 前检查 | `python scripts/pre_tag_check.py` | 只读 |

- 只读检查 v1.0.1-rc.1 打 tag 前条件
- 检查项：release notes 存在、evidence 脚本存在、artifacts/rc gitignored、.env 未跟踪、scanner 通过、workflow 安全、version 一致
- 不创建 tag、不 push、不执行 restore/backup/cleanup --confirm/docker compose up/eval_real_model
- 输出结构化 JSON：ok、checks[]、warnings[]
- RC evidence 和 pre-tag check 都是只读，不修改任何状态

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
| 清理 dry-run（限制预览） | `docker compose exec backend python scripts/cleanup_storage.py --preview-limit 50` | 只读 |
| 清理 dry-run（限制候选数） | `docker compose exec backend python scripts/cleanup_storage.py --limit 10` | 只读 |
| 清理执行 | `docker compose exec backend python scripts/cleanup_storage.py --confirm` | 破坏性 / 需要确认 |
| 清理执行（限制数量） | `docker compose exec backend python scripts/cleanup_storage.py --confirm --limit 10` | 破坏性 / 需要确认 |

审计输出：total_files、total_bytes、orphan_files、orphan_count、orphan_bytes、missing_files、missing_count。

清理安全：默认 dry-run、路径穿越防护（`relative_to`）、symlink 跳过、只删文件不删目录、输出仅含相对路径。脚本兼容历史相对 file_path（如 `storage/uploads/default/a.pdf`、`uploads/default/a.pdf`），统一转换为 STORAGE_PATH 相对路径。

### Storage Orphan 清理 SOP

> **禁止自动化 `--confirm`。** 所有真实清理必须人工审核后手动执行。

1. **运行审计**：`docker compose exec backend python scripts/storage_audit.py`
   - 记录 orphan_count、orphan_bytes、missing_count
2. **运行 dry-run**：`docker compose exec backend python scripts/cleanup_storage.py`
   - 输出 JSON 包含 candidate_count、candidate_bytes、candidate_files（相对路径）
   - 如候选文件很多，用 `--preview-limit N` 控制预览数量
3. **人工审核**：
   - 检查 candidate_files 列表，确认无误删风险
   - 检查 candidate_bytes，评估存储回收量
   - 检查 skipped_path_violation、skipped_symlink 是否异常
4. **确认清理**：`docker compose exec backend python scripts/cleanup_storage.py --confirm`
   - 可用 `--limit N` 分批清理，降低风险
   - 删除后输出 deleted_count、deleted_bytes、error_count
5. **验证清理结果**：`docker compose exec backend python scripts/storage_audit.py`
   - 确认 orphan_count 已减少
   - 确认 missing_count 未增加（不应误删引用文件）

### 清理脚本参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--confirm` | 实际删除（不传则 dry-run） | 不传 |
| `--limit N` | 本次最多处理 N 个候选文件（0=不限） | 0 |
| `--preview-limit N` | dry-run 输出最多 N 个候选文件路径 | 100 |

### 清理脚本输出字段

| 字段 | dry-run | --confirm |
|------|---------|-----------|
| dry_run | true | false |
| storage_path_exists | true/false | true/false |
| orphan_count | 总孤儿文件数 | 总孤儿文件数 |
| candidate_count | 候选数 | 0 |
| candidate_bytes | 候选字节数 | 0 |
| candidate_files | 候选文件相对路径列表 | 不输出 |
| preview_truncated | 列表是否截断 | 不输出 |
| deleted_count | 0 | 已删除数 |
| deleted_bytes | 0 | 已删除字节数 |
| skipped_path_violation | 路径穿越跳过数 | 路径穿越跳过数 |
| skipped_symlink | symlink 跳过数 | symlink 跳过数 |
| error_count | 0 | 删除失败数 |
| errors | [] | 错误描述列表（不含绝对路径） |

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
| Worker 健康状态（OPS_TOKEN） | `curl -H "X-Ops-Token: <token>" http://localhost:8091/jobs/worker/health` | 只读 |
| 查看卡住任务数 | 响应中 `stale_running_count` 字段 | 只读 |
| 重试失败 Job | `curl -X POST http://localhost:8091/jobs/{job_id}/retry` | 写入 |
| 前端 /jobs 页面 | http://localhost:3000/jobs | 只读 |

卡住判定：`JOB_STALE_RUNNING_SECONDS`（默认 3600）。

> **OPS_TOKEN**：当 AUTH_ENABLED=true 时，ops_check.ps1 通过环境变量 `OPS_TOKEN` 读取 token，自动附加 `X-Ops-Token` header 访问 worker health。OPS_TOKEN 访问返回全局统计（所有用户），普通用户/session 访问返回当前用户维度统计。OPS_TOKEN 只对 `/jobs/worker/health` 生效，不能访问 `/jobs` 等业务接口。

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
