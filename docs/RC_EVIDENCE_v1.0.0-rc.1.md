# RC Evidence (E2E Exception Resolved) — v1.0.0-rc.1

本文件记录 Phase 43–44 RC gate 的验收命令与结果，用于 v1.0.0-rc.1 tag 审计。

**E2E 例外已消除**：Phase 43 因宿主机无 Node/npm 未能执行 Playwright E2E；Phase 44 配置 Node.js 后补跑，103/103 全部通过。

## Phase 43 实际执行项

### 1. Git / Secret Hygiene

| 检查项 | 命令 | 结果 |
|--------|------|------|
| .env 未跟踪 | `git ls-files .env` | 无输出（.gitignore 包含 .env） |
| 文档 secret scan | `python scripts/check_docs_secrets.py` | PASS |
| 前端乱码 scan | `python scripts/check_frontend_mojibake.py` | PASS |

### 2. Quick Gate

命令：`powershell -ExecutionPolicy Bypass -File scripts/quick_gate.ps1`

| 步骤 | 结果 |
|------|------|
| Documentation secret scan | PASS |
| Frontend mojibake scan | PASS |
| Production check | 19/19 ALL CHECKS PASSED |
| Alembic current | 003_job_runs (head) |

### 3. Production Check

命令：`docker compose exec -T backend python scripts/production_check.py`

结果：19/19 ALL CHECKS PASSED

> **production_check 数量说明**：Phase 41 文档曾记录 "18/18"，Phase 43.1 曾误记 "17/17"。实际 production_check.py 包含 19 个检查项（Database / pgvector / Core tables / Storage / Eval / CORS / Real model / Alembic / Backup dir / Backup manifest / Auth config / Job worker / Job poll interval / Job max attempts / Job stale running / Maintenance scripts / Validate manifest script / ENV / Embedding dimension）。早期文档中的 18/18 是手动计数偏差，并非检查项增减。

### 4. Alembic Current

命令：`docker compose exec -T backend python -m alembic current`

结果：003_job_runs (head)

### 5. Backend Pytest

命令：`docker compose exec -T backend python -m pytest tests/ -q`

结果：453 passed, 22 skipped, 0 failed

### 6. Frontend Build (Phase 43)

前端使用 Docker 多阶段构建（Dockerfile builder 阶段 `npm run build`）。
运行中容器为 runner 阶段，前端服务正常响应。

结果：PASS（构建已在镜像构建时验证）

### 7. Backup / Restore Dry-Run

#### 7.1 Backup

命令：`powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1`

- DB backup：db_backup_20260527_035010.sql
- Storage backup：storage_backup_20260527_035010.zip
- Eval backup：eval_backup_20260527_035009.zip

#### 7.2 Manifest Validate

命令：`docker compose exec -T backend python scripts/validate_backup_manifest.py artifacts/backups/backup_manifest_20260527_035009.json`

结果：ok: true, errors: [], warnings: []

#### 7.3 Restore Dry-Run

命令：`powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_20260527_035009.json -DryRun`

结果：
- DB backup found: db_backup_20260527_035010.sql
- Storage backup found: storage_backup_20260527_035010.zip
- Eval backup found: eval_backup_20260527_035009.zip
- Validation passed. No data was modified.

Drill record：restore_drill_20260527_041436.json

## Phase 44 补跑项（E2E 例外消除）

### Node/npm 环境

- Node.js：v22.17.0（路径 F:\node.js\，已添加到 PATH）
- npm：10.9.2

### 前端依赖安装

命令：`cd apps/web && npm ci`

结果：成功（按 lockfile 安装）

### 前端构建

命令：`cd apps/web && npm run build`

结果：Next.js 15.5.18 编译成功，13 个路由，0 错误

### Playwright E2E

命令：`cd apps/web && npx playwright test`

结果：**103 passed, 0 failed**

7 个 spec 文件全部通过：
- api-error-display.spec.ts
- auth.spec.ts
- jobs.spec.ts
- no-mojibake.spec.ts
- page-smoke.spec.ts
- usage.spec.ts
- user-switcher.spec.ts

## Phase 41 历史参考项

以下为 Phase 41 执行时的结果，仅作历史参考，非 Phase 43/44 新验收：

- Phase 41 RC gate：production check PASS / 420 pytest / 103 E2E
- Phase 41.1 Docker 全量 pytest 因 test DB 残留连接卡死，已恢复并记录到 OPERATIONS_RUNBOOK

## Tag 前状态

| 检查项 | 结果 |
|--------|------|
| .env 未跟踪 | 确认（.gitignore 包含 .env） |
| v1.0.0-rc.1 tag | 已创建并推送到 GitHub |
| RC gate 全部 7 步 | ✅ 全部通过 |

## 代码变更（Phase 43–44）

- `apps/api/tests/test_backup_lifecycle.py`：新增 `_get_project_root()` 辅助函数，替换 27 处硬编码 `.parent.parent.parent.parent` 路径计算，修复 Docker 容器内路径解析为 `/` 的问题
