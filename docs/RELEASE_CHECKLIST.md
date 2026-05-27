# Release Checklist — v1.0.0

## 基础验收命令

顺序运行，不要并行：

```powershell
# 1. 文档密钥扫描
python scripts/check_docs_secrets.py

# 2. Scanner 自身测试
python -m pytest tests/test_check_docs_secrets.py -q

# 3. 后端测试
docker compose exec -T backend python -m pytest tests/ -q

# 4. 完整验收（含 E2E）
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild
```

### RC Gate 一键执行

```powershell
# 完整 RC 门禁（含 pytest + build + E2E）
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1

# 跳过 E2E
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -SkipE2E

# 含备份验证
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -ManifestPath artifacts/backups/backup_manifest_xxx.json
```

详见 [RELEASE_CANDIDATE_CHECKLIST.md](RELEASE_CANDIDATE_CHECKLIST.md)。

## 真实模型验收

需要 `.env` 中配置 `REAL_MODEL_REQUIRED=true` 且 LLM/Embedding 都为 `openai_compatible` provider：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunRealModelEval
```

如果真实模型评测因外部服务/额度失败，报告为外部依赖失败，不改业务代码绕过。

| 发布前必须运行 | `verify_all -RunRealModelEval`，blocker case 不通过不能发布 |

## E2E 覆盖范围

Playwright E2E 测试覆盖 8 个页面 + 404 + mobile responsive + loading/error 状态 mock：

- `/` 首页
- `/papers` 论文库
- `/papers/[id]` 论文详情
- `/papers/ask` 跨论文问答
- `/ideas` Idea 列表
- `/ideas/[id]` Idea 详情
- `/agent` Agent 工作流
- `/mcp` MCP 说明
- `/usage` 模型调用与质量看板
- `/_not-found` 404 页面

## 已知非阻塞限制

| 限制 | 说明 |
|------|------|
| 单用户 | 当前为 default 用户，无登录/权限 |
| local provider | 默认 local mock/heuristic AI，只适合开发，需配置 openai_compatible 才能使用真实 LLM |
| 真实模型质量 | 依赖外部 provider 可用性和额度 |
| embedding 维度变更 | 需修改 `EMBEDDING_DIMENSION` 并重建数据库 volume 或做迁移 |
| Windows 端口冲突 | Hyper-V 可能保留 7991-8090 等端口范围，后端映射为 `8091:8000`，详见 AGENTS.md #21 |
| MCP transport | 使用 stdio，不暴露 HTTP 端口 |
| MCP save_research_idea | 只支持单个 source_paper_id（长度必须为 1） |
| evidence gate | 保守拒答策略，可能拒绝部分有效问题 |

## 回滚/重建提示

| 操作 | 命令 |
|------|------|
| 清空数据库 volume | `docker compose down -v` |
| 重建服务 | `docker compose up --build` |
| 写入 demo 数据 | `docker compose exec backend python scripts/seed_demo.py` |
| 清除 demo 数据 | `docker compose exec backend python scripts/reset_demo.py` |
| 重建 demo embeddings | `docker compose exec backend python scripts/rebuild_demo_embeddings.py` |

评测报告目录 `artifacts/evals/` 已在 `.gitignore` 中忽略，不提交。

## 安全检查

- [ ] `.env` 不提交（已在 `.gitignore`）
- [ ] `python scripts/check_docs_secrets.py` 通过
- [ ] README / AGENTS / docs 中无真实 token（tp- 前缀、sk- 前缀、API_KEY 赋值、Authorization 头）
- [ ] 不在文档中写真实 DATABASE_URL 连接串
- [ ] `<YOUR_...>` 占位符是安全白名单，不触发误报
- [ ] `model_call_events` 审计表存在（`init_db` 自动创建）
- [ ] 审计记录不含敏感信息（无 prompt/chunk/answer 全文、无 API Key/Authorization/DATABASE_URL）
- [ ] 真实模型调用后 usage API 能查到审计记录（审计使用独立 session 持久化）
- [ ] /usage 页面可访问（模型调用摘要、评测状态正常展示）

## 认证验证

- [ ] `AUTH_ENABLED=true` 时注册/登录/session 流程正常
- [ ] `AUTH_ENABLED=false` 时 X-User-Id header 正常工作（开发模式）
- [ ] 生产环境 `ALLOW_DEV_USER_HEADER=false`（X-User-Id 请求头被忽略）
- [ ] Session cookie 设置了 `HttpOnly`、`SameSite=Lax`、`Path=/`
- [ ] HTTPS 环境下 cookie 设置了 `Secure` 属性
- [ ] `/auth/register` 注册成功返回 201，重复邮箱返回 409
- [ ] `/auth/login` 登录成功返回 200 + Set-Cookie，错误凭据返回 401
- [ ] `/auth/logout` 登出成功返回 200，cookie 被清除
- [ ] `/auth/me` 已登录返回用户信息 + `auth_mode: "session"`，未登录返回 401
- [ ] 前端 `credentials: "include"` 配置正确，跨域请求携带 cookie
- [ ] 响应中不泄露 `password_hash` 或 session token 明文

### Job System Verification

- [ ] `job_runs` table exists in database
- [ ] `JOB_WORKER_ENABLED` is configured
- [ ] `JOB_POLL_INTERVAL_SECONDS > 0`
- [ ] `JOB_MAX_ATTEMPTS >= 1`
- [ ] Worker starts on application startup
- [ ] Pending jobs can be cancelled
- [ ] Failed jobs have sanitized error messages
- [ ] `/jobs` page shows task list

## 生产门禁检查

运行 `production_check.py`（通过 verify_all 或独立运行）：

```bash
docker compose exec backend python scripts/production_check.py
# 或
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunProductionCheck
```

检查项：

- [ ] 数据库连接正常
- [ ] pgvector 扩展已启用
- [ ] 核心表存在（papers, paper_chunks, ideas, idea_sources, agent_runs, model_call_events）
- [ ] STORAGE_PATH 存在且可写
- [ ] STORAGE_PATH 下文件名安全（无路径穿越）
- [ ] REAL_MODEL_REQUIRED=true 时 LLM/Embedding provider 不是 local
- [ ] REAL_MODEL_REQUIRED=true 时 EMBEDDING_DIMENSION 与数据库 vector 列维度一致
- [ ] CORS 非 wildcard（wildcard 为 WARN，不阻塞）
- [ ] 不输出任何敏感配置值（DATABASE_URL、API Key、Authorization）

退出码：有 FAIL → exit 1，只有 WARN → exit 0，全 PASS → exit 0。

## 数据库迁移检查

```bash
# 检查 Alembic 当前版本
docker compose exec backend python -m alembic current

# 检查 Alembic head 版本
docker compose exec backend python -m alembic heads

# 或通过 verify_all
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunMigrationCheck
```

检查项：

- [ ] Alembic 已初始化（alembic/ 目录存在）
- [ ] 当前版本等于 head（REAL_MODEL_REQUIRED=true 时不一致为 FAIL）
- [ ] 新增 schema 变更已生成对应 migration 文件

## 备份验收

```powershell
# 执行全量备份
powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1

# 或通过 verify_all
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunBackupCheck
```

检查项：

- [ ] backup_all.ps1 执行成功，无报错
- [ ] artifacts/backups/ 下生成 db/、storage/、manifest 文件
- [ ] backup manifest 可读且不含 secrets（无 DATABASE_URL、API Key、Authorization）
- [ ] backup manifest 包含 app_version 和 embedding_dimension

### Restore drill（手动验收）

> 不在自动化验收中执行 restore，避免误覆盖。以下为手动验收步骤：

```powershell
# 1. 执行备份
powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1

# 2. 确认 manifest 存在
Get-Content artifacts/backups/backup_manifest_*.json | ConvertFrom-Json

# 3. 校验 manifest 完整性
docker compose exec backend python scripts/validate_backup_manifest.py artifacts/backups/backup_manifest_xxx.json

# 4. 执行 restore dry-run（不需要 -ConfirmRestore）
powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_xxx.json -DryRun

# 5. 执行恢复（需要 -ConfirmRestore）
powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_xxx.json -ConfirmRestore

# 6. 验证数据完整性
docker compose exec backend python scripts/smoke_check.py
```

- [ ] restore 脚本缺少 -ConfirmRestore 时拒绝执行
- [ ] restore dry-run 不需要 -ConfirmRestore，不执行破坏性操作
- [ ] restore dry-run 缺 db/storage 备份时 exit 1
- [ ] validate_backup_manifest.py 校验通过时 ok=true
- [ ] validate_backup_manifest.py 发现 secret-like 值时 ok=false
- [ ] restore drill 记录生成在 artifacts/backups/restore_drill_*.json
- [ ] restore 后数据完整（smoke_check 通过）
- [ ] restore 不删除数据库（只覆盖）
- [ ] manifest 引用的备份文件真实存在（DB/storage 缺失时 restore_all 必须 exit 1）
- [ ] restore_storage 不删除 /app 或 /app/storage 目录本身（只清空内容）
- [ ] restore_storage 清理失败时终止恢复（fail fast，不允许 WARN 后继续）
- [ ] DryRun 校验 DB/storage 必填（manifest 中 db_backup_file 和 storage_backup_file 不能为空）
- [ ] verify_all 完整执行通过，不允许用"子步骤独立通过"代替整体验收
- [ ] verify_all 在无 python 但有 py launcher 时可运行（Resolve-PythonCommand 返回结构化对象）

## 并发警告

不要并行运行多个后端 pytest / verify_all。后端测试会重建测试表，并发运行可能导致 PostgreSQL DDL deadlock。如果遇到死锁，停止并发任务后顺序重跑即可。
