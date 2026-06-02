# CI/CD Runbook — v1.0.1

本文件说明项目 CI 做什么、不做什么，以及后续扩展方向。

## CI Workflow

位置：`.github/workflows/ci.yml`

触发条件：
- push 到 `main` 分支
- pull_request 到 `main` 分支
- workflow_dispatch（手动触发，可选 run_e2e / run_backend_integration）

并发控制：`ci-${{ github.ref }}`，同一分支新提交取消旧运行。

### Jobs

| Job | 运行环境 | 触发条件 | 内容 |
|-----|----------|----------|------|
| docs-and-security | ubuntu-latest | 所有触发 | `check_docs_secrets.py` + `check_frontend_mojibake.py` |
| backend-unit | ubuntu-latest | 所有触发 | `test_check_docs_secrets.py` + 轻量 gate 测试 |
| frontend-build | ubuntu-latest | 所有触发 | `npm ci` + `npm run build` |
| frontend-e2e | ubuntu-latest | push main / workflow_dispatch | Playwright E2E 测试 |
| backend-integration | ubuntu-latest | push main / workflow_dispatch | Docker Compose + smoke + DB 集成 pytest |

### frontend-e2e Job

- 安装 Node 22 + npm ci
- `npx playwright install --with-deps chromium`
- `npm run test:e2e`（启动独立 dev server，不复用旧进程）
- 触发条件：
  - push main：自动运行
  - workflow_dispatch + run_e2e=true：手动触发
- 不在 PR 默认运行（v1.0.1 patch 阶段控制成本和 flaky 风险）
- 不依赖真实后端，E2E 使用 `page.route` mock

### backend-integration Job

- 使用 `docker compose -f docker-compose.yml -f docker-compose.ci.yml` 启动服务
- `docker-compose.ci.yml` 覆盖 backend 的 `env_file` 为空，确保 CI 不读取 `.env`
- CI 环境变量：`LLM_PROVIDER=local`、`EMBEDDING_PROVIDER=local`、`REAL_MODEL_REQUIRED=false`
- 等待 backend healthy（最多 150 秒）
- 运行 smoke check + 显式 DB 集成测试列表（非全量 `pytest tests/`）
- `docker compose down`（always 阶段执行）
- 触发条件：
  - push main：自动运行
  - workflow_dispatch + run_backend_integration=true：手动触发
- 不运行 eval_real_model.py，不传 RunRealModelEval
- 不包含 test_backup_lifecycle.py / test_production_health.py（依赖根目录脚本或 PowerShell）

### CI 专用 Compose Override

位置：`docker-compose.ci.yml`

- 覆盖 backend 的 `env_file: []`，阻止 CI 读取根目录 `.env`
- 显式设置 `DATABASE_URL`、`STORAGE_PATH`、`LLM_PROVIDER=local`、`EMBEDDING_PROVIDER=local`、`REAL_MODEL_REQUIRED=false`
- 不包含任何真实 secret
- 不改变本地 `docker-compose.yml` 的开发行为

### CI 做什么

- 文档 secret 扫描：确保 docs/ 不含 sk-/tp-/DATABASE_URL 真实值
- 前端乱码扫描：确保前端代码不含 mojibake
- 轻量后端测试：不依赖真实数据库的文档/配置守卫测试
- 前端构建验证：确保 Next.js 可成功编译
- Playwright E2E：前端交互测试（push main / 手动触发）
- Docker Compose DB 集成测试：显式测试文件列表（push main / 手动触发）

### CI 明确不做

| 不做 | 原因 |
|------|------|
| 真实 restore（`-ConfirmRestore`） | 危险操作，仅手动运维 |
| 使用真实 `.env` | CI 不持有生产密钥；docker-compose.ci.yml 覆盖 env_file 为空 |
| 跑真实 provider eval | 需要真实 API Key，成本高 |
| 并行多个 backend pytest job | 避免 DDL deadlock |
| 上传 artifacts/backups 或 artifacts/evals | 运行产物不应进入 Git |
| cleanup_storage.py --confirm | 破坏性操作，仅手动运维 |
| PR 默认跑 E2E | 控制成本和 flaky 风险 |

### 后续扩展方向

见 [OPERATIONS_BACKLOG.md](./OPERATIONS_BACKLOG.md)。

## Backup Freshness Workflow

位置：`.github/workflows/backup-freshness.yml`

### 触发条件

| 触发 | 说明 |
|------|------|
| schedule | 每日 00:30 UTC（需 `BACKUP_FRESHNESS_ENABLED=true` repository variable） |
| workflow_dispatch | 手动触发，不受 `BACKUP_FRESHNESS_ENABLED` 限制 |

### 行为

- 执行 `python scripts/check_backup_freshness.py --backups-dir ... --max-age-hours ...`
- 只读检查，不备份、不 restore、不删除文件
- 输出 JSON：`ok`、`latest_manifest`（仅文件名）、`age_hours`、`checked_manifest_count`、`skipped_manifest_count`、`timestamp_source`、`warnings`
- 退出码 0 = ok，1 = stale/missing/all-corrupted
- 按 manifest `timestamp` 字段选择最新 manifest（不按文件 mtime），支持 `yyyyMMdd_HHmmssZ`（backup_all.ps1 格式）、ISO Z、ISO aware、naive ISO
- timestamp 缺失/非法时 fallback 到文件 mtime，`timestamp_source` 标记为 `mtime_fallback` 并在 warnings 中说明
- 损坏 JSON manifest 会跳过并在 warnings 中记录文件名；全部损坏则 `ok=false`、exit 1
- `--allow-missing-manifest` 只适用于目录无 manifest 文件的情况，不掩盖"存在 manifest 但全损坏"的问题

### 生产落地前提

> **GitHub hosted runner 不具备生产备份可见性。** 本 workflow 设计用于 self-hosted runner 或外部监控环境能访问备份 manifest 目录的场景。

**生产启用步骤：**
1. 部署 self-hosted runner 到生产环境
2. 确保 runner 可访问备份 manifest 目录
3. 在 GitHub 仓库 Settings → Variables 中设置 `BACKUP_FRESHNESS_ENABLED=true`
4. schedule 触发才会执行生产检查

**默认 schedule 不执行**，避免 hosted runner 默认红灯。`workflow_dispatch` 手动触发不受此限制。

### 手动触发

在 GitHub Actions 页面选择 "Run workflow"，可选：
- max_age_hours：最大备份年龄（小时），默认 24
- backups_dir：备份目录路径，默认 artifacts/backups
- allow_missing_manifest：无 manifest 时是否仅告警（不失败），默认 false

## RC Evidence Pack

位置：`scripts/collect_rc_evidence.py`

### 用途

v1.0.1 RC 证据包收集，在 RC gate 前运行，生成可审计的本地证据文件。

### 命令

```bash
python scripts/collect_rc_evidence.py --output-dir artifacts/rc
```

### 行为

- 只读收集，不执行 backup、restore、cleanup --confirm、docker compose up、真实模型 eval
- 输出到 `artifacts/rc/`（已 gitignored）
- 输出 JSON + Markdown 摘要
- 证据内容：timestamp、version、git branch/commit/dirty、workflow 文件存在性、scanner 结果、backup freshness 启用说明
- 证据不得包含：.env 内容、API key、Authorization、DATABASE_URL 真实值、session token、artifacts/backups 内容、artifacts/evals 内容、宿主机绝对路径
- git 不可用时记录 unavailable，不失败
- scanner 失败时 exit 1

### 注意

- **不是 CI 自动上传**，是本地/人工 RC 流程
- 证据文件不提交到 Git（`artifacts/rc/` 已 gitignored）
- 不替代 `rc_gate.ps1`，是补充证据收集

## Pre-Tag Check

位置：`scripts/pre_tag_check.py`

### 用途

v1.0.1-rc.1 打 tag 前只读检查，确保 RC 条件满足。

### 命令

```bash
python scripts/pre_tag_check.py
```

### 行为

- 只读检查，不创建 tag、不 push、不执行 restore/backup/cleanup --confirm/docker compose up/eval_real_model
- 检查项：release notes 存在、evidence 脚本存在、artifacts/rc gitignored、.env 未跟踪、scanner 通过、workflow 安全、version 一致
- 输出结构化 JSON：ok、checks[]、warnings[]
- FAIL 项 exit 1；只有 warnings exit 0

### 注意

- **不是 CI 自动流程**，是本地/人工 RC 流程，不自动创建 tag
- **pre_tag_check 需要 git 可用**：git 不可用时 .env 跟踪检查返回 ok=false，必须人工修复环境或手动执行等价检查，不能视为通过

## 本地验证

CI 命令均可在本地复现：

```bash
python scripts/check_docs_secrets.py
python scripts/check_frontend_mojibake.py
python -m pytest tests/test_check_docs_secrets.py -q
python -m pytest apps/api/tests/test_backup_lifecycle.py -k "release_notes or rc_evidence or deployment or secret_hygiene" -q
cd apps/web && npm ci && npm run build
```

E2E 本地验证：

```bash
cd apps/web && npm ci && npx playwright install --with-deps chromium && npm run test:e2e
```

后端集成本地验证（需 Docker）：

```bash
docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build postgres backend
docker compose -f docker-compose.yml -f docker-compose.ci.yml exec -T backend python scripts/smoke_check.py
docker compose -f docker-compose.yml -f docker-compose.ci.yml exec -T backend python -m pytest \
  tests/test_papers.py tests/test_ideas.py tests/test_multi_paper.py \
  tests/test_user_isolation.py tests/test_jobs.py tests/test_model_call_audit.py \
  tests/test_eval_report.py tests/test_openapi_contract.py \
  tests/test_auth.py tests/test_mcp.py tests/test_agent.py \
  tests/test_langgraph.py tests/test_provider.py tests/test_storage_lifecycle.py \
  -q
docker compose -f docker-compose.yml -f docker-compose.ci.yml down
```

## 故障排查

### CI 失败：secret scan

检查最近提交的文档是否包含 sk-/tp-/DATABASE_URL 真实值。占位符（`<YOUR_...>`、`<REPLACE_ME>`）在白名单中。

### CI 失败：mojibake scan

检查前端代码是否引入乱码中文字符。

### CI 失败：frontend build

检查 TypeScript 类型错误或依赖缺失。本地 `cd apps/web && npm ci && npm run build` 复现。

### CI 失败：backend unit

检查测试是否依赖数据库或 Docker 环境。轻量测试不应依赖运行时服务。

### CI 失败：frontend-e2e

1. 检查 Playwright 版本与浏览器版本是否匹配
2. 本地复现：`cd apps/web && npm ci && npx playwright install --with-deps chromium && npm run test:e2e`
3. 检查是否有 flaky test（网络/时序依赖），优先用 `page.route` mock
4. 查看 trace：Playwright 配置 `trace: "on-first-retry"`

### CI 失败：backend-integration

1. 检查 Docker Compose 是否正常启动：`docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build postgres backend`
2. 查看 backend 日志：`docker compose -f docker-compose.yml -f docker-compose.ci.yml logs backend`
3. 确认 backend healthy：`docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"`
4. 本地复现 pytest：使用上方"后端集成本地验证"命令
5. 检查是否有 DDL deadlock（不要并行跑多个 backend pytest）
6. 检查 docker-compose.ci.yml 是否正确覆盖 env_file（CI 不应读取 .env）

### workflow_dispatch 手动触发

在 GitHub Actions 页面选择 "Run workflow"，可选：
- run_e2e：是否运行 Playwright E2E
- run_backend_integration：是否运行 Docker Compose 集成测试
