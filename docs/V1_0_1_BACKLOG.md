# v1.0.1 Backlog

v1.0.0 发布后已知限制、运维观察项和修复计划。按优先级分级。

## P0 — 生产阻塞

当前无 P0 级阻塞项。v1.0.0 核心功能已通过 RC gate 验收。

## P1 — 高优先级修复

### 1. 真实生产域名 CORS / HTTPS / cookie 参数复核

- **问题**：当前 `CORS_ALLOWED_ORIGINS` 默认为 `localhost`，`SESSION_COOKIE_SECURE` 默认为 `false`。生产部署到真实域名后必须更新。
- **修复**：部署文档已提示，但缺少自动化检查。建议在 `production_check.py` 中增加：当 `AUTH_ENABLED=true` 且 `SESSION_COOKIE_SECURE=false` 时 WARN；当 `CORS_ALLOWED_ORIGINS` 包含 `localhost` 且非开发模式时 WARN。
- **验证**：production_check 新增项通过。

### 2. ops token / 只读 worker health 认证方案

- **问题**：`ops_check.ps1` 在 `AUTH_ENABLED=true` 时无法获取 worker health 数据，只能 WARN 跳过。
- **修复**：设计只读 ops token（如 `OPS_TOKEN` 环境变量），ops_check 通过 `Authorization` header 携带 token 访问受保护端点。token 权限仅限只读健康检查，不赋予业务操作权限。
- **验证**：ops_check 在 AUTH_ENABLED=true 时能获取 worker health 数据。

### 3. storage orphan 清理 SOP

- **问题**：`storage_audit.py` 报告 orphan 文件（当前 10000+），但缺少标准清理流程。
- **修复**：
  1. `cleanup_storage.py` 默认 dry-run，输出待清理文件列表和大小
  2. 人工审核 dry-run 输出
  3. 确认后 `--confirm` 执行清理
  4. 清理后重新运行 `storage_audit.py` 验证
- **约束**：不得自动清理，必须人工审核。清理前必须 dry-run。
- **验证**：SOP 文档化到 OPERATIONS_MONITORING.md。

## P2 — 体验/运维增强

### 4. Playwright dedicated CI job

- **问题**：当前 CI 不跑 Playwright E2E，只在本地手动验证。
- **修复**：在 `.github/workflows/ci.yml` 增加 `e2e` job，启动 Next.js dev server + 安装 Playwright 浏览器 + 运行 E2E。
- **约束**：资源较重，建议仅在 main 分支 push 时运行，PR 可选。
- **来源**：OPERATIONS_BACKLOG #5

### 5. Docker Compose 全量测试 CI job

- **问题**：当前 CI 不启动 PostgreSQL service container，不跑全量 pytest（460+ tests）。
- **修复**：在 CI 中增加 `backend-integration` job，使用 `docker compose` 启动完整服务后运行 pytest。
- **约束**：资源较重，建议仅在 main 分支 push 时运行。
- **来源**：OPERATIONS_BACKLOG #10

### 6. backup freshness 定时化

- **问题**：当前 `check_backup_freshness.py` 需手动运行。
- **修复**：GitHub Actions scheduled workflow（cron），每日运行 `check_backup_freshness.py`，超龄时创建 Issue 或发送通知。
- **来源**：OPERATIONS_BACKLOG #4 增强

### 7. restore dry-run 定期演练

- **问题**：当前 restore dry-run 需手动运行。
- **修复**：GitHub Actions scheduled workflow（cron），每周运行 `restore_all.ps1 -DryRun`，失败时创建 Issue。
- **来源**：OPERATIONS_BACKLOG #2 增强

### 8. GitHub Release 手动发布步骤自动化

- **问题**：当前 tag + release notes + evidence 需手动操作。
- **修复**：tag push 时自动生成 draft release，包含 release notes 和 evidence 摘要。
- **来源**：OPERATIONS_BACKLOG #7

### 9. 依赖更新策略

- **问题**：npm/pip 依赖无自动更新检查。
- **修复**：启用 Dependabot 或 Renovate，自动创建 PR 更新依赖。安全更新自动合并，功能更新需人工 review。
- **来源**：OPERATIONS_BACKLOG #9

## P3 — 后续功能

### 10. Docker 镜像自动构建与推送

- **问题**：当前 Docker 镜像仅在本地构建。
- **修复**：tag push 时自动构建并推送到 ghcr.io。
- **来源**：OPERATIONS_BACKLOG #8

### 11. 性能基准测试

- **问题**：无 API 响应时间基线。
- **修复**：引入 pytest-benchmark 或 k6，记录关键 API 响应时间，检测性能退化。
- **来源**：OPERATIONS_BACKLOG #11

### 12. API 限流

- **问题**：当前无 API 限流。
- **修复**：引入 slowapi 或 nginx rate limiting。

### 13. 审计日志长期归档

- **问题**：`model_call_events` 表无限增长。
- **修复**：设计归档策略（如 90 天后归档到冷存储）。

## 分级原则

| 级别 | 定义 | 合入条件 |
|------|------|----------|
| P0 | 生产阻塞，服务不可用或数据丢失 | 立即修复，紧急发布 |
| P1 | 高优先级，影响安全或运维可观测性 | 本版本修复 |
| P2 | 体验/运维增强，不影响核心功能 | 视资源情况排期 |
| P3 | 后续功能，长期规划 | 下一个大版本 |

## 变更记录

- Phase 49：初始创建，从 OPERATIONS_BACKLOG 和发布后观察整理
