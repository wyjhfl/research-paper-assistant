# Release Notes — v1.0.0

## 概述

v1.0.0 是多 Agent 科研论文助手的正式发布版本。本版本包含完整的论文处理、RAG 问答、多 Agent 工作流、真实认证、后台任务、运维工具链和生产化门禁。

基于 v1.0.0-rc.1，Phase 44 补跑 Playwright E2E 通过（103/103），E2E 例外已消除，RC gate 全部 7 步通过。

## 核心功能

### PDF 解析与 RAG 问答

- pypdf 按页提取 + 固定字符切分 + 重叠
- 单论文 RAG 问答：pgvector 向量检索 + evidence gate + LLM 生成
- 跨论文 RAG 问答：多论文联合检索 + per_paper_limit + paper_title 来源

### Idea 抽取

- 启发式 Idea 抽取 + 来源追溯 + 标签 + 置信度
- Idea 列表 / 详情 / 删除（级联删除来源）

### 多 Agent 工作流

- Supervisor → Reader/Idea/Citation/MultiCitation → Reflection
- 支持 4 种 task_type：summarize_paper / extract_ideas / recommend_citations / recommend_citations_multi
- LangGraph StateGraph 编排，条件路由 + 失败短路

### MCP Server

- 6 个 tools + stdio transport + 安全收口
- 不暴露 DATABASE_URL / file_path / traceback / SQL
- save_research_idea 为唯一写入 tool

### 真实认证

- AUTH_ENABLED=true：注册/登录/HttpOnly session cookie
- Session token 仅存储 hash，不存明文
- ALLOW_DEV_USER_HEADER=false：生产环境禁止 X-User-Id 伪造
- 前端 credentials: "include" 携带 cookie

### 后台任务系统

- Postgres-backed job system（不依赖 Redis/Celery）
- 同步 API 兼容 + async_mode=true 异步模式
- JOB_WORKER_ENABLED / JOB_POLL_INTERVAL_SECONDS / JOB_MAX_ATTEMPTS 可配置
- max_attempts 范围 [1, 10]，失败重试 attempts 可靠持久化
- Jobs API 使用 input_summary / output_summary 安全摘要，不暴露原文

### 模型调用审计

- model_call_events 审计表 + 独立 session 持久化
- 不保存 prompt/chunk/answer 全文和 API Key
- /usage 页面展示调用摘要、最近记录、真实模型评测状态

### 备份与恢复

- 全量备份：PostgreSQL + Storage + Eval artifacts
- backup_manifest_*.json：不含 secrets，引用真实文件路径
- validate_backup_manifest.py：校验 JSON/字段/文件存在/无 secrets
- restore_all.ps1 -DryRun：dry-run 验证，不执行真实恢复
- restore 需要 -ConfirmRestore 显式确认

## 生产化能力

### Production Check

- 检查数据库连接、pgvector、核心表、Storage 可写、CORS、真实模型配置、Alembic 版本、备份目录、认证配置、Job 配置等 19 项
- FAIL 立即退出（exit 1），不允许降级为 WARN
- PASS WITH WARNINGS 通过（exit 0）

### Alembic 迁移

- 3 个 migration：baseline / user_sessions / job_runs
- 生产环境必须 `alembic upgrade head`
- 开发环境兼容 `create_all`

### RC Gate

- 7 步门禁：secret scan → mojibake scan → production check → Alembic current → pytest → npm build → Playwright
- 可选 ManifestPath 增加 validate + restore dry-run
- production_check FAIL 立即退出，不降级
- ManifestPath 只接受项目相对路径

### Quick Gate

- 4 步轻量验证：secret scan → mojibake scan → production check → Alembic current
- 不跑 pytest / Playwright / restore
- 适用于文档/配置小改的快速验证

### 验收分层策略

| Level | 适用场景 | 必须通过 |
|-------|----------|----------|
| Level 1 | 文档/配置小改 | secret scan + 窄测试 |
| Level 2 | 脚本/后端小改 | secret scan + 对应 test file |
| Level 3 | API/DB/认证/Job 语义改动 | secret scan + 相关模块 + production check |
| Level 4 | RC/tag 前 | 完整 rc_gate.ps1 |

### Storage Audit & Cleanup

- storage_audit.py：审计 total_files / orphan_files / missing_files
- cleanup_storage.py：默认 dry-run，--confirm 执行

## 已知限制

- **真实 restore 需人工确认**：`restore_all.ps1 -ConfirmRestore` 不在自动化门禁中执行
- **生产 HTTPS 要求**：SESSION_COOKIE_SECURE=true 需要 HTTPS 环境；本地 HTTP 开发用 false
- **.env 不提交**：.env 由 .gitignore 和人工检查保护，secret scan 不扫描 .env
- **Docker pytest 可能卡死**：并行 pytest 导致 TRUNCATE/DDL 锁；恢复流程见 OPERATIONS_RUNBOOK §12
- **MCP save_research_idea 只支持单个 source_paper_id**（长度必须为 1）
- **local provider 语义有限**：hash embedding + 拼接 LLM，不代表真实模型效果
- **X-User-Id 不是生产认证**：生产环境必须 AUTH_ENABLED=true + session cookie

## 升级 / 部署注意事项

1. 复制 `.env.example` 为 `.env`，按需配置（不要使用真实 key 占位符）
2. 生产环境必须设置：AUTH_ENABLED=true、ALLOW_DEV_USER_HEADER=false、SESSION_COOKIE_SECURE=true、CORS_ALLOWED_ORIGINS 为 HTTPS 域名
3. `docker compose up --build` 启动三个服务
4. 执行 `docker compose exec backend python -m alembic upgrade head` 迁移数据库
5. 运行 `docker compose exec backend python scripts/production_check.py` 确认生产配置
6. 如需 demo 数据：`docker compose exec backend python scripts/seed_demo.py`

## 验收摘要

### v1.0.0 正式发布验证

| 步骤 | 结果 |
|------|------|
| Documentation secret scan | ✅ PASS |
| Frontend mojibake scan | ✅ PASS |
| Production check | ✅ 19/19 ALL CHECKS PASSED |
| Alembic current | ✅ 003_job_runs (head) |
| Backend pytest | ✅ 453 passed / 22 skipped / 0 failed |
| Frontend build | ✅ npm run build 通过 |
| Playwright E2E | ✅ 103 passed / 0 failed |
| Backup manifest validate | ✅ ok: true, errors: [], warnings: [] |
| Restore dry-run | ✅ DB + Storage + Eval 均找到，无数据修改 |

> v1.0.0 正式发布基于 v1.0.0-rc.1 + Phase 44 E2E 证据更新。RC gate 全部 7 步通过。详细证据见 RELEASE_EVIDENCE_v1.0.0.md。
