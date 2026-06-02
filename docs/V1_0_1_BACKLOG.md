# v1.0.1 Backlog

v1.0.0 发布后已知限制、运维观察项和修复计划。按优先级分级。

## P0 — 生产阻塞

当前无 P0 级阻塞项。v1.0.0 核心功能已通过 RC gate 验收。

## P1 — 高优先级修复

### 1. 真实生产域名 CORS / HTTPS / cookie 参数复核 ✅ 已完成 Phase 50

- **问题**：当前 `CORS_ALLOWED_ORIGINS` 默认为 `localhost`，`SESSION_COOKIE_SECURE` 默认为 `false`。生产部署到真实域名后必须更新。
- **修复**：已在 `production_check.py` 中增加生产模式严格检查：
  - 生产模式 CORS `*` 通配符 → **FAIL**
  - 生产模式 CORS 无 origins → **FAIL**
  - 生产模式 CORS 含 localhost / 127.0.0.1 / 0.0.0.0 → **FAIL**
  - 生产模式 CORS 含 `http://` 非 HTTPS → **WARN**
  - 生产模式 AUTH_ENABLED=false → **FAIL**
  - 生产模式 ALLOW_DEV_USER_HEADER=true → **FAIL**
  - 生产模式 SESSION_COOKIE_SECURE=false → **FAIL**
  - 开发模式保留 localhost / HTTP 友好行为（PASS 或 WARN）
- **验证**：`test_production_health.py` 相关测试通过（56 passed, 10 skipped）。

### 2. ops token / 只读 worker health 认证方案 ✅ 已完成 Phase 1

- **问题**：`ops_check.ps1` 在 `AUTH_ENABLED=true` 时无法获取 worker health 数据，只能 WARN 跳过。
- **修复**：实现只读 OPS_TOKEN 认证方案：
  - 新增 `OPS_TOKEN` 配置项，固定使用 `X-Ops-Token` header
  - 新增 `get_worker_health_user_id` 依赖，OPS_TOKEN 通过 `X-Ops-Token` header 认证
  - token 比较使用 `hmac.compare_digest`，防止 timing leak
  - OPS_TOKEN 为空时拒绝任何 ops token 请求
  - OPS_TOKEN 只对 `/jobs/worker/health` 生效，不能访问 `/jobs` 等业务接口
  - OPS_TOKEN 访问返回全局统计（所有用户），普通用户/session 访问返回当前用户维度统计
  - `ops_check.ps1` 读取环境变量 `OPS_TOKEN`，自动附加 header
  - `production_check.py` 在生产模式且 OPS_TOKEN 为空时 WARN；开发模式不因 OPS_TOKEN 为空降级
- **验证**：
  - `test_ops_token_auth_enabled_no_session_no_token_returns_401`
  - `test_ops_token_wrong_token_returns_401`
  - `test_ops_token_correct_returns_200`
  - `test_ops_token_cannot_access_jobs_list`
  - `test_ops_token_empty_rejects_any_token`
  - `test_ops_token_uses_global_stats`
  - `test_user_session_uses_user_id_stats`
  - `test_ops_token_compare_uses_hmac`
  - `test_production_check_ops_token_warn`
  - `test_production_check_ops_token_pass`
  - `test_production_check_ops_token_not_leaked`
  - `test_ops_check_ps1_no_register_login_post`
  - `test_ops_check_ps1_reads_ops_token_env`

### 3. storage orphan 清理 SOP ✅ 已完成 Phase 2

- **问题**：`storage_audit.py` 报告 orphan 文件（当前 10000+），但缺少标准清理流程。
- **修复**：
  1. `cleanup_storage.py` 默认 dry-run，输出结构化 JSON（candidate_count/candidate_bytes/candidate_files）
  2. `--confirm` 才允许实际删除，只删文件不删目录
  3. symlink 跳过、路径穿越防护（`_is_within_storage`）、删除失败记录到 errors
  4. `--limit N` 限制本次处理数量，`--preview-limit N` 限制 dry-run 预览数量
  5. 输出仅含相对 STORAGE_PATH 的路径，不泄露宿主机绝对路径
  6. `storage_audit.py` 增强：`followlinks=False`、symlink 跳过、输出不含绝对路径
  7. OPERATIONS_RUNBOOK.md 增加 Storage Orphan 清理 SOP（5 步流程）
  8. OPERATIONS_MONITORING.md 明确 orphan_count 异常只告警不自动修复
  9. `_referenced_rel_path` 路径归一化：兼容绝对路径、`storage/` 前缀相对路径、纯相对路径，不再 fallback 到 basename
- **约束**：不得自动清理，必须人工审核。清理前必须 dry-run。ops_check/production_check 不执行 --confirm。
- **验证**：
  - `test_cleanup_storage_dry_run_no_delete`：dry-run 不删除文件
  - `test_cleanup_storage_confirm_deletes_orphan`：--confirm 删除 orphan
  - `test_cleanup_storage_referenced_not_deleted`：引用文件不被删除
  - `test_cleanup_storage_symlink_skipped`：symlink 跳过
  - `test_cleanup_storage_path_traversal`/`test_cleanup_storage_path_violation_candidate_skipped`：路径穿越防护
  - `test_cleanup_storage_missing_path_returns_safe_json`：STORAGE_PATH 不存在时安全返回
  - `test_cleanup_storage_no_absolute_paths_in_output`：输出不含绝对路径
  - `test_cleanup_storage_dry_run_candidate_preview`：预览截断
  - `test_cleanup_storage_delete_error_recorded`：删除失败有记录
  - `test_storage_audit_is_read_only`：审计只读
  - `test_ops_check_no_cleanup_confirm`：ops_check 不调用 --confirm
  - `test_production_check_no_cleanup_confirm`：production_check 不执行 --confirm
  - `test_cleanup_storage_absolute_file_path_referenced`：绝对路径引用不被删除
  - `test_cleanup_storage_relative_file_path_with_storage_prefix`：storage/ 前缀相对路径引用不被删除
  - `test_cleanup_storage_relative_file_path_without_storage_prefix`：纯相对路径引用不被删除
  - `test_storage_audit_relative_file_path_not_orphan`：相对路径引用不计为 orphan
  - `test_referenced_rel_path_*`：路径归一化单元测试

## P2 — 体验/运维增强

### 4. Playwright dedicated CI job ✅ 已完成 Phase 3

- **问题**：当前 CI 不跑 Playwright E2E，只在本地手动验证。
- **修复**：在 `.github/workflows/ci.yml` 增加 `frontend-e2e` job：
  - Node 22 + npm ci + `npx playwright install --with-deps chromium` + `npm run test:e2e`
  - 触发条件：push main / workflow_dispatch run_e2e=true
  - 不在 PR 默认运行（v1.0.1 patch 阶段控制成本和 flaky 风险）
  - 不依赖真实后端，E2E 使用 `page.route` mock
- **来源**：OPERATIONS_BACKLOG #5

### 5. Docker Compose 全量测试 CI job ✅ 已完成 Phase 3

- **问题**：当前 CI 不启动 PostgreSQL service container，不跑全量 pytest。
- **修复**：在 CI 中增加 `backend-integration` job：
  - 使用 `docker compose -f docker-compose.yml -f docker-compose.ci.yml` 启动服务
  - `docker-compose.ci.yml` 覆盖 backend 的 `env_file` 为空，确保 CI 不读取 `.env`
  - CI 环境变量：`LLM_PROVIDER=local`、`EMBEDDING_PROVIDER=local`、`REAL_MODEL_REQUIRED=false`
  - 运行 smoke check + 显式 DB 集成测试列表（非全量 `pytest tests/`）
  - 不包含 test_backup_lifecycle.py / test_production_health.py（依赖根目录脚本或 PowerShell）
  - `docker compose down`（always 阶段执行）
  - 触发条件：push main / workflow_dispatch run_backend_integration=true
  - 不运行 eval_real_model.py，不传 RunRealModelEval
- **来源**：OPERATIONS_BACKLOG #10

### 6. backup freshness 定时化 ✅ 已完成 Phase 4

- **问题**：当前 `check_backup_freshness.py` 需手动运行。
- **修复**：
  1. 新增 `.github/workflows/backup-freshness.yml`，schedule 每日 00:30 UTC + workflow_dispatch
  2. 支持 `max_age_hours`、`backups_dir`、`allow_missing_manifest` 输入参数
  3. `check_backup_freshness.py` 新增 `--allow-missing-manifest` 参数
  4. workflow 权限最小化 `permissions: contents: read`
  5. 明确 GitHub hosted runner 不具备生产备份可见性，生产需 self-hosted runner
  6. 只读检查，不备份、不 restore、不删除文件
  7. 默认 schedule 不执行，需 `BACKUP_FRESHNESS_ENABLED=true` repository variable 启用
  8. `_parse_manifest_timestamp` 支持 `yyyyMMdd_HHmmssZ`（backup_all.ps1 格式）、ISO Z、ISO aware、naive ISO
  9. 按 manifest `timestamp` 字段选择最新 manifest（不按文件 mtime），timestamp 缺失/非法才 fallback mtime
  10. 损坏 JSON manifest 跳过并在 warnings 中记录文件名；全部损坏则 `ok=false`、exit 1
  11. `--allow-missing-manifest` 不掩盖"存在 manifest 但全损坏"的问题
  12. 输出增加 `checked_manifest_count`、`skipped_manifest_count`、`timestamp_source`
  13. `_try_parse_timestamp` 替代 `_parse_manifest_timestamp`，非法 timestamp 返回 None，调用方精确区分 manifest vs mtime_fallback
  14. 非法 timestamp 的 fallback_reason 标记为 `invalid`，缺失为 `missing`，warnings 包含文件名
- **来源**：OPERATIONS_BACKLOG #4 增强

### 6a. RC Evidence Pack ✅ 已完成 Phase 5

- **问题**：v1.0.1 RC 缺乏可审计的本地证据收集方案。
- **修复**：
  1. 新增 `scripts/collect_rc_evidence.py`，只读收集仓库状态和门禁结果摘要
  2. 输出到 `artifacts/rc/`（已 gitignored），JSON + Markdown 摘要
  3. 证据内容：timestamp、version、git branch/commit/dirty、workflow 文件存在性、scanner 结果、backup freshness 启用说明
  4. 证据不得包含：.env 内容、API key、Authorization、DATABASE_URL 真实值、session token、artifacts 内容、宿主机绝对路径
  5. git 不可用时记录 unavailable，不失败
  6. scanner 失败时 exit 1
  7. 不执行 backup、restore、cleanup --confirm、docker compose up、真实模型 eval
  8. 不是 CI 自动上传，是本地/人工 RC 流程
- **验证**：`tests/test_rc_evidence.py` 覆盖安全约束和 smoke 测试

### 6b. v1.0.1 RC Release Package ✅ 已完成 Phase 6

- **问题**：v1.0.1 缺乏版本元数据一致化、RC release notes、pre-tag 检查脚本。
- **修复**：
  1. APP_VERSION 更新为 1.0.1-rc.1，同步 config.py、.env.example、API_CONTRACT.md
  2. collect_rc_evidence.py 优先从 config.py 读取版本号，git/scanner 命令使用 cwd=project_root
  3. 新增 docs/RELEASE_NOTES_v1.0.1-rc.1.md，只描述实际完成的 Phase 0-5，不声称 ALL CHECKS PASSED
  4. 新增 scripts/pre_tag_check.py，只读检查打 tag 前条件（9 项检查）
  5. pre_tag_check 不创建 tag、不 push、不执行 destructive 操作
- **验证**：`tests/test_pre_tag_check.py` + `tests/test_rc_evidence.py` 覆盖

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
- Phase 50：P1 #1 CORS/HTTPS/cookie 复核已完成，production_check 增加生产模式严格检查
- Phase 1：P1 #2 OPS_TOKEN 只读 worker health 认证方案已完成
- Phase 2：P1 #3 storage orphan 清理 SOP 生产化已完成
- Phase 3：P2 #4 Playwright CI job + P2 #5 backend integration CI job 已完成
- Phase 4：P2 #6 backup freshness 定时化生产化已完成
- Phase 5：P2 #6a RC Evidence Pack 已完成
- Phase 6：P2 #6b v1.0.1 RC Release Package 生产化已完成
