# Operations Backlog

本文件列出 v1.0.0 后续建议的运维自动化任务，按优先级排序。

> Phase 48 已落地项标注 ✅。详细监控方案见 [OPERATIONS_MONITORING.md](./OPERATIONS_MONITORING.md)。
> 已纳入 v1.0.1 修复计划的项标注 📋，详见 [V1_0_1_BACKLOG.md](./V1_0_1_BACKLOG.md)。

## 高优先级

### 1. 定期 backup manifest validate ✅ Phase 48

- 频率：每日
- 方式：cron job 或 GitHub Actions scheduled workflow
- 命令：`python scripts/validate_backup_manifest.py artifacts/backups/<latest>.json`
- 目的：确保备份产物完整可用
- 落地：纳入 ops_check.ps1 + OPERATIONS_MONITORING 每周检查

### 2. 定期 restore dry-run drill ✅ Phase 48 📋 v1.0.1 #7

- 频率：每周
- 方式：cron job 或 GitHub Actions scheduled workflow
- 命令：`scripts/restore_all.ps1 -ManifestPath <latest> -DryRun`
- 目的：验证恢复路径可用，不执行真实恢复
- 注意：只 dry-run，不 `-ConfirmRestore`
- 落地：纳入 OPERATIONS_MONITORING 每周检查
- v1.0.1 增强：GitHub Actions scheduled workflow 自动化

### 3. Job worker health 监控 ✅ Phase 48 📋 v1.0.1 #2

- 频率：每 5 分钟（建议）；每日（ops_check）
- 方式：外部监控服务（UptimeRobot / Grafana / 自建）
- 端点：`GET /jobs/worker/health`
- 告警条件：`worker_enabled=false` 或 `stale_running_count > 0`
- 落地：纳入 ops_check.ps1 + OPERATIONS_MONITORING 告警条件
- v1.0.1 增强：ops token 只读认证方案

### 4. backup freshness 告警 ✅ Phase 48 / Phase 4 📋 v1.0.1 #6

- 频率：每小时检查（建议）；每日（ops_check）
- 条件：最新 backup manifest 超过 24 小时
- 方式：`python scripts/check_backup_freshness.py --max-age-hours 24`
- 告警：邮件 / Slack / 企业微信 / GitHub Actions workflow failure
- 落地：check_backup_freshness.py 脚本 + OPERATIONS_MONITORING 每日检查
- Phase 4 增强：GitHub Actions workflow `backup-freshness.yml` 每日 00:30 UTC + workflow_dispatch
- 默认 schedule 不执行，需 `BACKUP_FRESHNESS_ENABLED=true` repository variable 启用
- 生产前提：self-hosted runner 或外部监控环境能访问备份 manifest 目录
- `_parse_manifest_timestamp` 支持 `yyyyMMdd_HHmmssZ`（backup_all.ps1 格式）
- 按 manifest `timestamp` 字段选择最新 manifest（不按文件 mtime），timestamp 缺失/非法才 fallback mtime
- 损坏 JSON manifest 跳过并在 warnings 中记录文件名；全部损坏则 `ok=false`、exit 1
- `_try_parse_timestamp` 替代 `_parse_manifest_timestamp`，非法 timestamp 精确标记为 mtime_fallback

### 4a. RC Evidence Pack ✅ Phase 5 📋 v1.0.1 #6a

- 新增 `scripts/collect_rc_evidence.py`，只读收集仓库状态和门禁结果摘要
- 输出到 `artifacts/rc/`（已 gitignored），JSON + Markdown 摘要
- 证据不得包含：.env 内容、API key、Authorization、DATABASE_URL 真实值、session token、artifacts 内容、宿主机绝对路径
- 不执行 backup、restore、cleanup --confirm、docker compose up、真实模型 eval
- 不是 CI 自动上传，是本地/人工 RC 流程

### 4b. Pre-Tag Check ✅ Phase 6 📋 v1.0.1 #6b

- 新增 `scripts/pre_tag_check.py`，只读检查打 tag 前条件
- 检查项：release notes 存在、evidence 脚本存在、artifacts/rc gitignored、.env 未跟踪、scanner 通过、workflow 安全、version 一致
- 不创建 tag、不 push、不执行 destructive 操作
- APP_VERSION 更新为 1.0.1-rc.1，同步 config.py、.env.example、API_CONTRACT.md
- 新增 docs/RELEASE_NOTES_v1.0.1-rc.1.md

## 中优先级

### 5. Playwright CI 专用 job ✅ Phase 3 📋 v1.0.1 #4

- 在 CI 中增加 `frontend-e2e` job
- 已实现：Node 22 + npm ci + playwright install --with-deps chromium + npm run test:e2e
- 触发条件：push main / workflow_dispatch run_e2e=true
- 不在 PR 默认运行（v1.0.1 patch 阶段控制成本和 flaky 风险）

### 6. 定期 storage_audit ✅ Phase 48 📋 v1.0.1 #3

- 频率：每周
- 命令：`python scripts/storage_audit.py`
- 关注：`missing_count > 0`（文件丢失）或 `orphan_count` 异常增长
- 清理前必须 dry-run：`python scripts/cleanup_storage.py`（默认 dry-run）
- v1.0.1 增强：storage orphan 清理 SOP

### 7. release evidence 自动归档 📋 v1.0.1 #8

- 在 tag 创建时自动生成 RELEASE_EVIDENCE
- 方式：GitHub Actions `release` 事件触发
- 内容：运行门禁命令 + 归档结果到 docs/

## 低优先级

### 8. Docker 镜像自动构建与推送 📋 v1.0.1 #10

- 在 tag 创建时自动构建 Docker 镜像
- 推送到 GitHub Container Registry (ghcr.io)
- 标签：`v1.0.0`、`latest`

### 9. 依赖自动更新 📋 v1.0.1 #9

- Dependabot 或 Renovate
- 自动创建 PR 更新 npm/pip 依赖
- 需要人工 review 后合并

### 10. 全量 pytest CI job ✅ Phase 3 📋 v1.0.1 #5

- 在 CI 中启动 PostgreSQL service container
- 已实现：`backend-integration` job，使用 docker-compose.ci.yml 覆盖 env_file
- CI 不读取 .env，使用 local provider
- 显式 DB 集成测试列表（非全量 pytest tests/）
- 触发条件：push main / workflow_dispatch run_backend_integration=true

### 11. 性能基准测试 📋 v1.0.1 #11

- 记录关键 API 响应时间
- 检测性能退化
- 方式：pytest-benchmark 或 k6

## 实施原则

1. 每项自动化必须先 dry-run，确认安全后才启用
2. 不在自动化中执行真实 restore
3. 不在自动化中使用真实 .env / API Key
4. 告警必须可操作，避免告警疲劳
5. CI 不做重操作，重操作留给运维手动执行
