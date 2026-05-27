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

### 4. backup freshness 告警 ✅ Phase 48 📋 v1.0.1 #6

- 频率：每小时检查（建议）；每日（ops_check）
- 条件：最新 backup manifest 超过 24 小时
- 方式：`python scripts/check_backup_freshness.py --max-age-hours 24`
- 告警：邮件 / Slack / 企业微信
- 落地：check_backup_freshness.py 脚本 + OPERATIONS_MONITORING 每日检查
- v1.0.1 增强：GitHub Actions scheduled workflow 定时化

## 中优先级

### 5. Playwright CI 专用 job 📋 v1.0.1 #4

- 在 CI 中增加 `e2e` job
- 需要：启动 Next.js dev server + 安装 Playwright 浏览器
- 资源需求：比其他 job 更重，建议独立运行
- 参考：`apps/web/playwright.config.ts` 中 `webServer` 配置

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

### 10. 全量 pytest CI job 📋 v1.0.1 #5

- 在 CI 中启动 PostgreSQL service container
- 运行全量 pytest（453+ tests）
- 资源需求较重，建议仅在 main 分支 push 时运行

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
