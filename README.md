# 多 Agent 科研论文助手

上传科研 PDF、解析论文、构建论文记忆、进行 RAG 问答、抽取研究 Idea、多 Agent 工作流、推荐引用。

> 开发协作规则见 [AGENTS.md](./AGENTS.md)。
> Release Notes 见 [RELEASE_NOTES_v1.0.0.md](docs/RELEASE_NOTES_v1.0.0.md)（v1.0.0 正式版）。
> RC 历史见 [RELEASE_NOTES_v1.0.0-rc.1.md](docs/RELEASE_NOTES_v1.0.0-rc.1.md)。
> 部署手册见 [DEPLOYMENT_RUNBOOK_v1.0.0.md](docs/DEPLOYMENT_RUNBOOK_v1.0.0.md)。
> 运维监控见 [OPERATIONS_MONITORING.md](docs/OPERATIONS_MONITORING.md)。

## 当前能力

| 能力 | 状态 | 说明 |
|------|------|------|
| PDF 解析与 Chunk | ✅ | pypdf 按页提取 + 固定字符切分 + 重叠 |
| 单论文 RAG 问答 | ✅ | pgvector 向量检索 + evidence gate + LLM 生成 |
| 跨论文 RAG 问答 | ✅ | 多论文联合检索 + per_paper_limit + paper_title 来源 |
| Idea 抽取与保存 | ✅ | 启发式抽取 + 来源追溯 + 标签 + 置信度 |
| 多 Agent 工作流 | ✅ | Supervisor → Reader/Idea/Citation/MultiCitation → Reflection |
| MCP Server | ✅ | 6 个 tools + stdio transport + 安全收口 |
| 真实模型连通性 | ✅ | openai_compatible provider + 连通性测试脚本 |
| 一键 Demo | ✅ | seed_demo.py / reset_demo.py |
| 轻量多用户隔离 | ✅ | X-User-Id header 数据隔离，无需登录 |
| 模型调用审计 | ✅ | model_call_events 审计表 + 独立 session 持久化 + 内部脱敏 + 用户隔离查询，不保存 prompt/chunk/API key |
| 审计与质量看板 | ✅ | /usage 页面展示调用摘要、最近记录、真实模型评测状态 |
| 工程健康基线 | ✅ | PDF 解析统一 pypdf、Storage 路径统一、fake text 消除、production_check 门禁 |
| 数据库迁移与备份 | ✅ | Alembic 迁移体系 + PostgreSQL/Storage/Eval 备份恢复 + production_check 增强 |

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Next.js 15 + TypeScript + Tailwind CSS (App Router) |
| 后端 | FastAPI + Pydantic + SQLAlchemy async + asyncpg |
| 数据库 | PostgreSQL 16 + pgvector |
| AI Provider | 本地 hash embedding + 本地 mock LLM / OpenAI Compatible |
| Agent | LangGraph StateGraph + Supervisor 多 Agent 编排 |
| MCP | FastMCP + stdio transport |
| 部署 | Docker Compose (3 services) |

## 快速启动

### 前置条件

- Docker & Docker Compose
- Node.js 20+（仅本地前端开发）
- Python 3.11+（仅本地后端开发）

### Docker Compose（推荐）

```bash
docker compose up --build
```

- 前端：http://localhost:3000
- 后端：http://localhost:8091
- 健康检查：http://localhost:8091/health

> **Windows 用户注意**：Hyper-V 可能保留端口 7991-8090 及更大范围，导致 Docker 无法绑定 8000 端口。当前后端映射为 `8091:8000`。如遇端口冲突，运行 `netsh interface ipv4 show excludedportrange protocol=tcp` 查看排除范围，并修改 `docker-compose.yml` 中的端口映射。

> 如果本地旧 volume schema 异常，可执行 `docker compose down -v` 重建。

### 本地开发

后端：

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd apps/web
npm install
npm run dev
```

## 一键 Demo

### 写入演示数据

```bash
docker compose exec backend python scripts/seed_demo.py
```

创建 3 篇 demo 论文（Transformer / RAG / Multi-Agent）及其 chunks、embeddings 和 ideas。**幂等**：重复运行不会重复创建。

### 清除演示数据

```bash
docker compose exec backend python scripts/reset_demo.py
```

只删除 `demo_*` 数据，不影响用户上传的论文。

### 推荐演示路径

1. 首页查看能力入口和系统状态
2. 进入论文库，看到 3 篇 demo 论文
3. 打开 Transformer 论文详情
4. 单论文问答："What problem does attention solve?"
5. 查看 Idea 列表
6. 进入跨论文问答："How can RAG and multi-agent workflows support research assistants?"
7. 进入 Agent 工作流 → recommend_citations_multi → 不选择论文 → 运行（全库检索）
8. 进入 MCP 页面查看工具说明

> 注意：local provider 是启发式能力（hash embedding + 拼接 LLM），回答质量不代表真实模型效果。

## 常用命令

```bash
# 启动服务
docker compose up --build

# 写入 / 清除 demo 数据
docker compose exec backend python scripts/seed_demo.py
docker compose exec backend python scripts/reset_demo.py

# 基础设施验证
docker compose exec backend python scripts/smoke_check.py

# 真实模型连通性测试（local 模式自动 SKIP）
docker compose exec backend python scripts/model_smoke_check.py

# 后端测试
docker compose exec -T backend python -m pytest tests/ -q

# 前端构建
cd apps/web && npm run build
```

## 环境变量

复制 `.env.example` 为 `.env` 并按需修改：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DATABASE_URL | postgresql+asyncpg://postgres:postgres@localhost:5432/research_assistant | 数据库连接（开发默认值） |
| STORAGE_PATH | ./storage | PDF 文件存储目录（Docker 默认 /app/storage，映射为 volume） |
| CHUNK_SIZE | 1000 | 每个 chunk 字符数 |
| CHUNK_OVERLAP | 200 | chunk 重叠字符数 |
| EMBEDDING_PROVIDER | local | Embedding 提供者（local / openai_compatible） |
| EMBEDDING_MODEL | local-hash | Embedding 模型名称 |
| EMBEDDING_DIMENSION | 384 | Embedding 向量维度 |
| EMBEDDING_API_KEY | | Embedding API Key（openai_compatible 时必填） |
| EMBEDDING_BASE_URL | | Embedding Base URL（openai_compatible 时必填） |
| EMBEDDING_TIMEOUT_SECONDS | 30 | Embedding 请求超时（秒） |
| LLM_PROVIDER | local | LLM 提供者（local / openai_compatible） |
| LLM_MODEL | local-mock | LLM 模型名称 |
| LLM_API_KEY | | LLM API Key（openai_compatible 时必填） |
| LLM_BASE_URL | | LLM Base URL（openai_compatible 时必填） |
| LLM_TIMEOUT_SECONDS | 30 | LLM 请求超时（秒） |
| RAG_TOP_K | 5 | RAG 检索返回的 top-k chunk 数 |
| RAG_SCORE_THRESHOLD | 0.1 | RAG 最低相关性分数阈值 |
| RAG_EVIDENCE_THRESHOLD | 0.2 | RAG evidence gate 最低词汇重叠率阈值 |
| CORS_ALLOWED_ORIGINS | http://localhost:3000,http://localhost:3001 | 允许的跨域来源（逗号分隔）；生产推荐 HTTPS 域名 |
| AUTH_ENABLED | false | `true` 启用真实认证，`false` 使用开发模式（X-User-Id header） |
| ALLOW_DEV_USER_HEADER | true | 是否允许 X-User-Id 请求头；**生产必须设为 `false`** |
| SESSION_COOKIE_SECURE | false | Session Cookie Secure 属性；**生产 HTTPS 必须设为 `true`**，本地 HTTP 开发用 `false` |
| NEXT_PUBLIC_API_URL | http://localhost:8091 | 浏览器端调用的后端地址 |
| INTERNAL_API_URL | http://localhost:8091 | Next.js Server Component 调用的后端地址（Docker 中为 http://backend:8000） |

## API 概览

### 基础

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查（status + database + version） |

### 论文

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /papers/upload | 上传 PDF 论文 |
| GET | /papers | 获取论文列表 |
| GET | /papers/{id} | 获取论文详情和 chunks |
| POST | /papers/{paper_id}/ask | 单论文 RAG 问答 |
| POST | /papers/{paper_id}/embeddings/rebuild | 重建论文 embedding |
| POST | /papers/ask | 跨论文 RAG 问答（可选 paper_ids 过滤） |
| POST | /papers/search | 跨论文语义检索（纯检索，不调用 LLM） |

### Idea

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /papers/{paper_id}/ideas/extract | 从论文中抽取研究 Idea 候选 |
| POST | /ideas | 保存用户选择的 Idea |
| GET | /ideas | 获取 Idea 列表 |
| GET | /ideas/{idea_id} | 获取 Idea 详情和来源 |
| DELETE | /ideas/{idea_id} | 删除 Idea（级联删除来源） |

### Agent

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /agent/run | 运行 Agent 工作流 |
| GET | /agent/runs/{run_id} | 获取 Agent 运行详情 |

### Usage

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /usage/model-calls | 查询模型调用审计记录（用户隔离） |
| GET | /usage/model-calls/summary | 模型调用聚合统计 |

Agent 支持 4 种 task_type：`summarize_paper` / `extract_ideas` / `recommend_citations` / `recommend_citations_multi`

### 请求示例

POST /agent/run：

```json
{
  "task_type": "recommend_citations_multi",
  "question": "How can attention improve retrieval?",
  "paper_ids": []
}
```

响应：

```json
{
  "run_id": "a1b2c3d4e5f67890",
  "status": "completed",
  "task_type": "recommend_citations_multi",
  "output": { "answer": "...", "sources": [...] },
  "warnings": [],
  "confidence": 0.85
}
```

## MCP Server

### 启动命令

```bash
docker compose exec backend python run_mcp.py
```

MCP Server 使用 stdio transport，供 MCP 客户端启动。

### 客户端配置示例

```json
{
  "mcpServers": {
    "research-paper-assistant": {
      "command": "docker",
      "args": ["compose", "exec", "-T", "backend", "python", "run_mcp.py"]
    }
  }
}
```

> `DATABASE_URL` 请在 `.env` 文件中配置，不要在 MCP 客户端配置中硬编码。

### MCP Tools

| Tool | 说明 | 读写 |
|------|------|------|
| search_papers(query, limit) | 搜索论文（title/filename 模糊匹配） | 只读 |
| get_paper_summary(paper_id) | 获取论文结构化摘要 | 只读 |
| search_ideas(query, limit) | 搜索已保存 Idea | 只读 |
| recommend_citations(draft_text, paper_id?, paper_ids?, limit) | 基于草稿推荐引用（支持单/多/全库模式） | 只读 |
| search_paper_chunks(query, paper_ids?, limit) | 跨论文语义检索 chunk | 只读 |
| save_research_idea(title, summary, tags, source_paper_ids) | 保存研究 Idea（唯一写入 tool） | 写入 |

### 安全限制

- 不暴露 DATABASE_URL / file_path / postgresql / asyncpg
- 内部错误统一返回 `internal_error`，不泄露 traceback / SQL
- 不允许任意 SQL 或读取本地文件
- limit 参数有上限，文本输入有 trim + 长度限制
- save_research_idea 必须有来源（source_paper_ids 长度 = 1）

## 数据库迁移（Alembic）

项目使用 Alembic 管理数据库 schema 迁移。

### 新环境

首次启动时，开发模式仍可使用 `init_db` 的 `create_all` 自动建表。生产环境推荐显式执行迁移：

```bash
docker compose exec backend python -m alembic upgrade head
```

### 旧开发环境

如果已有 Docker volume 中的数据，需要先 stamp baseline 再升级：

```bash
docker compose exec backend python -m alembic stamp 001_baseline
docker compose exec backend python -m alembic upgrade head
```

### 新增 migration

修改 `models.py` 后，生成新的迁移脚本：

```bash
cd apps/api
python -m alembic revision --autogenerate -m "描述变更"
```

然后检查生成的 migration 文件，确认后执行 `alembic upgrade head`。

### EMBEDDING_DIMENSION 变更

`EMBEDDING_DIMENSION` 变更时，需要：
1. 修改 `.env` 中的 `EMBEDDING_DIMENSION`
2. 创建新的 Alembic migration 修改 vector 列维度
3. 重建所有 embeddings（`rebuild_demo_embeddings.py` 或逐篇 rebuild）
4. 如果维度变化较大，可能需要 `docker compose down -v` 重建 volume

### 开发启动 vs 生产迁移

| 场景 | 方式 |
|------|------|
| 开发启动 | `create_all`（自动建表，兼容旧流程） |
| 生产部署 | `alembic upgrade head`（显式迁移，可回滚） |
| CI/CD | `alembic upgrade head` + `production_check.py` |

> Phase 33 或后续再考虑移除 `create_all`，当前两种方式兼容共存。

## 备份与恢复

### 备份

```powershell
# 全量备份（数据库 + Storage + Eval artifacts）
powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1

# 单独备份数据库
powershell -ExecutionPolicy Bypass -File scripts/backup_postgres.ps1

# 单独备份 Storage
powershell -ExecutionPolicy Bypass -File scripts/backup_storage.ps1
```

备份产物输出到 `artifacts/backups/`，文件名带 UTC 时间戳。`backup_all.ps1` 会生成 `backup_manifest_*.json`，包含：

| 字段 | 说明 |
|------|------|
| timestamp | 备份时间（UTC） |
| db_backup_file | 数据库备份文件名（来自子脚本实际输出） |
| storage_backup_file | Storage 备份文件名（来自子脚本实际输出） |
| eval_backup_file | Eval artifacts 备份文件名（可能为空） |
| app_version | 应用版本（Docker 不可用时为 "unknown"） |
| embedding_dimension | 当前 embedding 维度（Docker 不可用时为 null） |

manifest 不包含任何 secrets。文件名来自子脚本实际返回的路径，不硬编码。

### 恢复

```powershell
# 全量恢复（需要 -ConfirmRestore 确认）
powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_xxx.json -ConfirmRestore

# Dry-run 验证（只检查文件存在，不执行恢复，不需要 -ConfirmRestore）
powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath artifacts/backups/backup_manifest_xxx.json -DryRun

# 单独恢复数据库
powershell -ExecutionPolicy Bypass -File scripts/restore_postgres.ps1 -BackupFile artifacts/backups/db/db_backup_xxx.sql -ConfirmRestore

# 单独恢复 Storage
powershell -ExecutionPolicy Bypass -File scripts/restore_storage.ps1 -BackupFile artifacts/backups/storage/storage_backup_xxx.zip -ConfirmRestore
```

### Backup Manifest 校验

```bash
# 校验 manifest 完整性（字段、引用文件存在、无 secrets）
docker compose exec backend python scripts/validate_backup_manifest.py artifacts/backups/backup_manifest_xxx.json
```

校验内容：
- JSON 可读、无 BOM 兼容
- 必填字段完整（timestamp、db_backup_file、storage_backup_file）
- 引用的备份文件真实存在
- 不含 secret-like 值（API Key、Authorization、DATABASE_URL 等）

输出：`{"ok": true/false, "errors": [...], "warnings": [...]}`

### Restore Drill 记录

每次 DryRun 或实际 Restore 都会在 `artifacts/backups/` 生成 `restore_drill_*.json`：

| 字段 | 说明 |
|------|------|
| timestamp | 演练时间（UTC） |
| manifest_file | 使用的 manifest 文件名 |
| dry_run | 是否为 dry-run |
| db_backup_present | DB 备份文件是否存在 |
| storage_backup_present | Storage 备份文件是否存在 |
| ok | 演练是否通过 |

> **安全机制**：
> - 所有 restore 脚本必须传入 `-ConfirmRestore` 参数，否则拒绝执行。DryRun 模式不需要 `-ConfirmRestore`。
> - `restore_storage.ps1` 只清空 `/app/storage` 目录内部内容，不删除 `/app/storage` 本身，不使用 `/app/storage/..`。清理失败时立即终止恢复（fail fast）。
> - `restore_all.ps1` 是全量恢复，DB 和 storage 备份必填（manifest 中 `db_backup_file` 和 `storage_backup_file` 不能为空），eval 可选。会验证 manifest 中引用的文件真实存在，缺失时 FAIL（exit 1）。DryRun 模式也执行必填校验。
> - `verify_all.ps1` 自动探测宿主机 Python：优先 `python`，其次 `py -3`（Windows Python Launcher），两者都不存在时明确报错退出。

## 认证模式

系统支持两种认证模式：**开发模式**（dev）和**生产模式**（production），通过环境变量 `AUTH_ENABLED` 控制。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| AUTH_ENABLED | false | `true` 启用真实认证（注册/登录/session），`false` 使用开发模式 |
| ALLOW_DEV_USER_HEADER | true | 是否允许 `X-User-Id` 请求头模拟用户。**生产环境必须设为 `false`** |

### 开发模式（AUTH_ENABLED=false）

- 无需注册/登录，通过 `X-User-Id` 请求头标识用户
- 缺省 `X-User-Id` 时使用 `"default"` 用户
- 适合本地开发和快速原型

### 生产模式（AUTH_ENABLED=true）

- 用户必须通过 `/auth/register` 注册、`/auth/login` 登录
- 登录成功后服务端设置 **HttpOnly** session cookie
- 前端请求需设置 `credentials: "include"` 以携带 cookie
- `X-User-Id` 请求头被忽略（除非 `ALLOW_DEV_USER_HEADER=true`）

### MCP 认证

MCP Server 使用 stdio transport，**不使用 session cookie**。MCP tools 通过可选 `user_id` 参数标识用户，默认 `"default"`。

### Session Cookie 安全

- Cookie 属性：`HttpOnly`（JavaScript 不可读取）、`SameSite=Lax`、`Path=/`
- Session token 在数据库中仅存储 **hash 值**，不存储明文
- 生产环境应额外设置 `Secure` 属性（需 HTTPS）

### 认证页面测试

认证相关页面（登录、注册、UserSwitcher）已纳入 E2E 文案与乱码检查。运行 `npx playwright test tests/e2e/auth.spec.ts` 可验证：
- 页面文案完整可读（登录、注册、邮箱、密码等）
- 错误提示不含 `[object Object]` 或乱码片段
- 源码静态扫描不含常见 mojibake 字符

### 后台任务系统

项目使用 Postgres-backed job system 处理耗时操作（PDF 处理、embedding 重建、Agent 运行等），不引入 Redis/Celery。

**同步 API 兼容**：现有 `/papers/upload`、`/papers/{id}/embeddings/rebuild` 保持同步行为（默认 `async_mode=false`）。设置 `async_mode=true` 时创建后台 job 并立即返回 `job_id`。

**新增配置**：
- `JOB_WORKER_ENABLED`: 是否启动后台 worker（默认 true）
- `JOB_POLL_INTERVAL_SECONDS`: worker 轮询间隔（默认 1.0）
- `JOB_MAX_ATTEMPTS`: job 默认最大重试次数（默认 1，范围 [1, 10]）

**重试语义**：
- `max_attempts=1`：第一次失败后 status 直接变为 `failed`
- `max_attempts=2`：第一次失败后 status 回到 `pending`（等待重试），第二次失败变 `failed`
- 不允许无限重试，最大 `max_attempts=10`
- 失败后 attempts 在新事务中持久化，不会被 rollback 回滚

**API 输出安全**：
- `/jobs` 响应不暴露 `input_json` / `output_json` 原始字段
- 使用 `input_summary` / `output_summary` 返回安全结构化摘要
- `agent_run` 的 question、draft_text、answer 等长文本不在摘要中原样展示
- `error_message` 继续保持脱敏
- `job_runs.output_json` 持久化时通过 `safe_job_output` 过滤，不保存模型原文：
  - `process_paper`：仅 paper_id、status
  - `rebuild_embeddings`：仅 paper_id、chunks_embedded
  - `agent_run`：仅 run_id、status、task_type、confidence、warning_count、source_count/idea_count 等计数字段
  - `real_model_eval`：仅 status、message（截断）

**新增 API**：
- `POST /jobs` — 创建 job（max_attempts 范围 [1, 10]，默认 JOB_MAX_ATTEMPTS）
- `GET /jobs` — 列出当前用户 job
- `GET /jobs/{job_id}` — 查询 job 状态
- `POST /jobs/{job_id}/cancel` — 取消 pending job

**前端**：`/jobs` 页面展示任务列表、状态、进度，支持刷新和取消。

## 真实大模型配置

默认项目使用 local provider，无需 API Key。如需切换到真实模型：

### 配置步骤

1. 复制 `.env.example` 为 `.env`
2. 在 `.env` 中配置真实模型参数（见下方示例）
3. 运行连通性测试：

```bash
docker compose exec backend python scripts/model_smoke_check.py
```

4. 如果 embedding 维度兼容，重建 demo embeddings：

```bash
docker compose exec backend python scripts/rebuild_demo_embeddings.py
```

### MiMo + Silicon Flow 配置示例

> **重要**：MiMo Token Plan 不提供 embedding endpoint，需要为 embedding 使用独立服务。推荐 Silicon Flow 的 BAAI/bge-m3（免费额度）。

```bash
# .env（占位符，不要使用真实 key）

# LLM - MiMo
LLM_PROVIDER=openai_compatible
LLM_MODEL=mimo-v2.5-pro
LLM_API_KEY=<YOUR_MIMO_TOKEN_PLAN_API_KEY>
LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
LLM_TIMEOUT_SECONDS=60

# Embedding - Silicon Flow bge-m3
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_API_KEY=<YOUR_SILICONFLOW_API_KEY>
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_DIMENSION=1024
EMBEDDING_TIMEOUT_SECONDS=60

REAL_MODEL_REQUIRED=true
```

> **注意**：
> - 真实模型可能产生费用
> - 不要提交 `.env`（已在 `.gitignore` 中）
> - 如果模型不支持 embedding endpoint，需要单独选择一个真实 embedding 模型
> - 切换 EMBEDDING_MODEL / EMBEDDING_DIMENSION 后必须 rebuild embeddings
> - 如果 embedding 维度变化，需要重建 DB volume（`docker compose down -v`）或做迁移

### REAL_MODEL_REQUIRED

| 值 | 行为 |
|----|------|
| `false`（默认） | 允许 local provider 运行，开发模式 |
| `true` | LLM 和 Embedding 都必须是 openai_compatible，且 API Key / Base URL / Model 必须全部存在，任何一项不满足则 exit 1 |

用于强制真实模型验收，防止静默回退 local。

### Embedding 维度注意事项

- 数据库 vector 列维度由 `EMBEDDING_DIMENSION` 决定
- local provider 默认 384 维，Silicon Flow bge-m3 为 1024 维
- 如果真实 embedding 返回不同维度，`model_smoke_check` 会明确提示实际维度和需要的操作
- 维度变化时需要修改 `EMBEDDING_DIMENSION` 并重建数据库 volume（`docker compose down -v`）

### 常用命令

```bash
# 连通性测试
docker compose exec backend python scripts/model_smoke_check.py

# 重建 demo embeddings（仅 demo_* papers）
docker compose exec backend python scripts/rebuild_demo_embeddings.py

# 重建单篇论文 embeddings
curl -X POST http://localhost:8091/papers/{paper_id}/embeddings/rebuild
```

## 推荐验收命令

### 日常开发验收

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1
```

默认执行：Docker build → smoke check → pytest → frontend build → E2E tests。

### RC Gate（发布候选门禁）

```powershell
# 完整 RC 门禁
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1

# 跳过 E2E
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -SkipE2E

# 含备份验证
powershell -ExecutionPolicy Bypass -File scripts/rc_gate.ps1 -ManifestPath artifacts/backups/backup_manifest_xxx.json
```

RC gate 顺序运行：secret scan → mojibake scan → production check → Alembic current → pytest → npm build → Playwright。可选 `-ManifestPath` 时额外运行 validate manifest + restore dry-run。**不执行真实 restore。** production_check FAIL 会立即失败退出。`-ManifestPath` 只接受项目相对路径，不接受绝对路径。开发环境可用 `-SkipProductionCheck` 跳过生产配置检查。

### Quick Gate（轻量验证）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/quick_gate.ps1
```

Quick gate 只跑 4 步：secret scan → mojibake scan → production check → Alembic current。**不跑 pytest、不跑 Playwright、不跑 restore**。适用于文档/配置小改的快速验证。完整 RC gate 只在 tag 前跑一次。

### RC Tag 前安全检查

创建 v1.0.0-rc.1 tag 前必须确认：

- `.env` 不得被 Git 跟踪（`git ls-files .env` 无输出）
- 真实 API Key / Token 不得出现在文档、commit message、release notes 中
- 如果 Key 曾暴露，必须轮换后再 tag
- `.env.example` 仅包含安全占位符和开发默认值
- `SESSION_COOKIE_SECURE=true` 需要 HTTPS；本地 HTTP 开发可用 `false`
- `.env` 由 `.gitignore` 和人工检查保护，secret scan 不扫描 `.env`

### 跳过 Docker build

服务已运行时：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild
```

### 跳过 E2E

仅验证后端和前端构建：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E
```

### 生产门禁检查

`production_check.py` 检查数据库连接、pgvector、核心表、Storage 可写、eval 报告、CORS、真实模型配置、Alembic 版本、备份目录等。通过 verify_all 运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunProductionCheck
```

或独立运行：

```bash
docker compose exec backend python scripts/production_check.py
```

退出码：有 FAIL → 1，只有 WARN → 0，全 PASS → 0。不输出任何敏感配置值。

### 迁移检查

检查 Alembic 当前版本是否为 head：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunMigrationCheck
```

### 备份检查

执行一次全量备份（不执行恢复）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunBackupCheck
```

### 真实模型完整验收

强制真实模型验收，需要 `.env` 中配置 `REAL_MODEL_REQUIRED=true` 且 LLM/Embedding 都为 `openai_compatible` provider。如果当前是 local provider，此步骤会失败——这是正确行为，不传 `-RunRealModelEval` 即可跳过。

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -RunRealModelEval
```

### E2E 依赖

- Frontend 必须可访问 `http://localhost:3000`
- Backend 必须可访问 `http://localhost:8091`
- Demo 数据已写入：`docker compose exec backend python scripts/seed_demo.py`

### E2E Dev Server 复用策略

Playwright 默认**不复用**已有的 Next dev server，每次运行会启动独立的 dev server 实例。这确保 E2E 测试始终运行当前源码，避免旧 `.next` 缓存导致 cookie/user isolation 测试假失败或假通过。

- **默认行为**（`npm run test:e2e`）：Playwright 启动新的 `npm run dev`，不复用旧进程。如果端口 3000 已被占用，测试会启动失败——需先停止旧 dev server。
- **显式复用**：如需复用已有 dev server（如 Docker 中的前端），设置环境变量后运行 `test:e2e:reuse`：
  ```powershell
  # PowerShell
  $env:E2E_REUSE_EXISTING_SERVER = "true"; npm run test:e2e:reuse
  ```
  ```bash
  # bash
  E2E_REUSE_EXISTING_SERVER=true npm run test:e2e:reuse
  ```
- **外部服务**：如前端运行在 Docker 或其他地址，设置 `E2E_BASE_URL` 即可跳过 dev server 启动：
  ```powershell
  $env:E2E_BASE_URL = "http://localhost:3000"; npm run test:e2e
  ```

> **注意**：cookie/user isolation 相关 E2E 测试不允许默认复用旧 dev server，因为旧 `.next` 缓存可能导致 `getUserId()` 等函数使用过时 bundle。

### 注意事项

- 如果 Docker Desktop 未运行，verify_all 会失败，这是预期行为——请启动 Docker Desktop 后重试。
- 步骤编号会根据传入参数自动调整（如 `-SkipDockerBuild` 时总步数减 1）。
- `verify_all.ps1` 会自动扫描 README / AGENTS / docs 中的疑似密钥（`scripts/check_docs_secrets.py`），同时运行 scanner 自身测试。`<YOUR_...>` 和 `<REPLACE_ME>` 是允许的安全占位符，不会触发误报。
- 不要并行运行多个后端 pytest / verify_all，后端测试会重建测试表，并发可能导致 PostgreSQL DDL deadlock。

### 评测报告位置

- `artifacts/evals/real_model_eval_latest.json` — 最新评测结果
- `artifacts/evals/history/` — 历史评测快照（带时间戳）
- Docker Compose 已挂载 `./artifacts/evals:/app/artifacts/evals`

## 接口与合约文档

- [API_CONTRACT.md](docs/API_CONTRACT.md) — REST API 合约（15 个接口）
- [MCP_CONTRACT.md](docs/MCP_CONTRACT.md) — MCP Tools 合约（6 个工具）
- [http-examples.md](docs/examples/http-examples.md) — curl 请求示例（8 个场景）
- [RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) — 发布候选验收清单

## 测试与验收

### 后端测试

```bash
docker compose exec -T backend python -m pytest tests/ -q
```

当前测试覆盖 PDF、RAG、Idea、Agent、MCP、Provider、用户隔离等核心流程，具体数量以 pytest 输出为准。

### 前端构建

```bash
cd apps/web && npm run build
```

9 个路由：`/` `/papers` `/papers/[id]` `/papers/ask` `/ideas` `/ideas/[id]` `/agent` `/mcp` `/_not-found`

### 真实模型评测集

评测定义文件：`apps/api/evals/real_model_cases.json`

当前包含 12 个评测 case，覆盖 single_rag / multi_rag / agent / mcp / idea 五种类型。

**如何新增 eval case**：
1. 在 `apps/api/evals/real_model_cases.json` 中添加新 case
2. 每个 case 必须包含：`case_id`、`type`（single_rag|multi_rag|agent|mcp|idea）、`description`、`input`、`expected`、`severity`（blocker|warning）
3. `expected` 支持结构化断言：`expected_status`、`min_sources`、`min_distinct_papers`、`allowed_rag_status`、`forbidden_source_paper_ids`、`require_paper_title`、`require_no_sensitive_output`、`require_source_chunk_ids`、`min_candidates`
4. 运行 `docker compose exec backend python scripts/eval_real_model.py` 验证

**blocker / warning 语义**：
- `blocker`：该 case 失败会导致 `can_proceed=false`，阻止进入下一阶段
- `warning`：该 case 失败记录为 warning，不阻止 `can_proceed`

**运行评测**：
```bash
docker compose exec backend python scripts/eval_real_model.py
# 或通过 verify_all：
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunRealModelEval
```

报告输出：`artifacts/evals/real_model_eval_latest.json`（不提交 Git）

每次运行还会生成带时间戳的历史快照（`artifacts/evals/history/`），支持趋势对比。Docker Compose 已挂载该目录，报告同步到宿主机。可用 `EVAL_REPORT_DIR` 环境变量覆盖输出目录。

说明：
- `pytest` 不调用真实外部模型。
- `eval_real_model.py` 才是真实模型质量验收。
- 当前评测是基线，不代表最终学术可靠性评测。

### 推荐完整验收顺序

```bash
docker compose exec -T backend python scripts/model_smoke_check.py
docker compose exec -T backend python scripts/eval_real_model.py
docker compose exec -T backend python -m pytest tests/ -q
cd apps/web && npm run build
docker compose exec -T backend python scripts/smoke_check.py
```

### 最终验收清单

#### 基础设施

- [ ] `docker compose up --build` 三个服务全部启动
- [ ] `smoke_check.py` 全部 PASS
- [ ] `model_smoke_check.py` local 模式 SKIP 且 exit 0

#### Demo

- [ ] `seed_demo.py` 可运行
- [ ] 重复 `seed_demo.py` 不重复创建
- [ ] /papers 显示 3 篇 demo 论文
- [ ] /papers/ask 可跨论文问答

#### 核心功能

- [ ] PDF 上传可用
- [ ] 单论文问答返回 sources
- [ ] 跨论文问答返回 paper_title sources
- [ ] Idea 列表可见
- [ ] Agent recommend_citations_multi 可运行
- [ ] /mcp 页面可访问

#### 质量

- [ ] `pytest` 全部通过
- [ ] `npm run build` 通过
- [ ] `eval_real_model.py` 全部 passed 或 warning（无 failed）
- [ ] 不泄露 API Key / DATABASE_URL / Authorization / traceback

#### 当前仍未完成的生产化项

- 认证系统（当前仅 X-User-Id header，无登录/权限）
- 数据库备份自动化（当前为手动脚本）
- 后台任务队列
- API 限流
- CORS 生产化（当前为 wildcard *）
- create_all → Alembic 完全切换（当前兼容共存）

## 架构说明

### 目录结构

```
research-paper-assistant/
├── apps/
│   ├── api/                  # FastAPI 后端
│   │   ├── app/
│   │   │   ├── main.py       # 应用入口 + lifespan
│   │   │   ├── config.py     # 配置管理 (pydantic-settings)
│   │   │   ├── database.py   # 数据库连接 + init_db + migration
│   │   │   ├── models.py     # SQLAlchemy ORM (Paper, PaperChunk, Idea, IdeaSource, AgentRun + pgvector)
│   │   │   ├── agents/       # 多 Agent 工作流 (LangGraph StateGraph)
│   │   │   ├── mcp/          # MCP Server (FastMCP + 6 tools)
│   │   │   ├── routers/      # API 路由 (health, papers, ideas, agent)
│   │   │   ├── schemas/      # Pydantic 输入输出
│   │   │   ├── services/     # 业务逻辑层
│   │   │   └── repositories/ # 数据访问层
│   │   ├── tests/            # 后端测试
│   │   └── scripts/          # 运维脚本
│   └── web/                  # Next.js 前端
│       └── src/
│           ├── app/          # App Router 页面
│           ├── components/   # UI 组件
│           └── lib/          # API 封装
├── infra/
│   └── init-db.sql           # 数据库初始化
├── docker-compose.yml
├── .env.example
└── README.md
```

### 数据库表

| 表 | 说明 |
|----|------|
| papers | 论文元数据（title, filename, status, timestamps） |
| paper_chunks | 论文分块（text, page_start/end, embedding vector(EMBEDDING_DIMENSION)） |
| ideas | 研究 Idea（title, summary, research_question, method_hint, tags, confidence） |
| idea_sources | Idea 来源追溯（idea_id → chunk_id, text_excerpt） |
| agent_runs | Agent 运行记录（task_type, status, input_json, output_json） |
| model_call_events | 模型调用审计（operation, provider, model, status, duration_ms, input_chars, output_chars, error_type, error_message, metadata_json） |

### Agent 架构

```
Supervisor → ReaderAgent / IdeaAgent / CitationAgent / MultiCitationAgent → ReflectionAgent
```

- **Supervisor**：校验 task_type，调度对应 Agent
- **ReaderAgent**：结构化摘要（title, overview, key_points, limitations）
- **IdeaAgent**：Idea 候选抽取（含 source_chunk_ids）
- **CitationAgent**：单论文 RAG 引用推荐
- **MultiCitationAgent**：跨论文 RAG 引用推荐（支持 paper_ids / 全库）
- **ReflectionAgent**：来源支撑检查 + warnings

Agent 编排使用 LangGraph StateGraph（`langgraph_runner.py`），支持条件路由和失败短路。旧 GraphRunner 保留为兼容入口。

当前暂不启用 checkpoint、streaming、human-in-the-loop。

### AI Provider 架构

| Provider | 接口 | 本地实现 | OpenAI Compatible |
|----------|------|----------|-------------------|
| Embedding | `embed_texts(texts) -> list[list[float]]` | LocalHashEmbeddingProvider（hash 向量，无状态，可复现） | OpenAICompatibleEmbeddingProvider（维度校验） |
| LLM | `generate_answer(question, contexts) -> str` | LocalMockLLMProvider（拼接 contexts） | OpenAICompatibleLLMProvider（system prompt 限制） |

Provider 异常体系：

| 异常 | 说明 |
|------|------|
| ProviderConfigurationError | 配置缺失（API Key / Base URL 为空） |
| ProviderRequestError | 请求失败（超时、网络错误、非 2xx） |
| ProviderResponseError | 响应格式异常（空内容、条数不一致） |
| EmbeddingDimensionError | 返回向量维度与 EMBEDDING_DIMENSION 不匹配 |

所有 provider 异常不泄露 API Key / Authorization / 完整 URL / traceback。

Provider 稳定性配置：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| PROVIDER_TIMEOUT_SECONDS | 60 | 预留统一超时上限，当前未生效；LLM 和 Embedding 各自使用 LLM_TIMEOUT_SECONDS / EMBEDDING_TIMEOUT_SECONDS |
| PROVIDER_MAX_RETRIES | 2 | 最大重试次数（429/5xx/timeout/连接错误触发） |
| PROVIDER_RETRY_BACKOFF_SECONDS | 1.0 | 退避基数，实际等待 = backoff × (attempt + 1) |

Provider 错误安全收口：
- 可重试：429、500/502/503/504、网络超时、连接错误
- 不重试：400、401/403、404、响应 schema 不合法
- 错误消息经 `_sanitize_error_message` 脱敏，不包含 API Key / Authorization / 完整 URL query
- 日志只记录 `provider`、`model`、`status_code`、`attempt`、`error_type`，不记录 prompt/chunk 全文

### RAG 检索流程

1. 用户提问 → embed_query 生成问题向量
2. pgvector 余弦距离检索 top-k chunk
3. 过滤低于 score threshold 的 chunk
4. Evidence gate：词汇重叠率低于阈值 → `insufficient_context`
5. 有足够上下文 → LLM 生成回答 + 返回 sources

### 前端路由

| 路径 | 说明 |
|------|------|
| / | 产品首页（Landing Dashboard + 系统状态） |
| /papers | 论文库（上传 + 列表） |
| /papers/[id] | 论文详情（问答 + Idea + Chunks） |
| /papers/ask | 跨论文问答 |
| /ideas | Idea 列表 |
| /ideas/[id] | Idea 详情 |
| /agent | Agent 工作流 |
| /mcp | MCP Server 说明 |

## 轻量多用户隔离

系统支持通过 `X-User-Id` 请求头实现轻量多用户数据隔离，**无需登录注册**。

### 工作方式

- 所有 REST API 接受可选的 `X-User-Id` 请求头
- 缺省时使用 `"default"` 用户，兼容单用户模式
- 不同 `user_id` 的论文、Idea、Agent Run 完全隔离
- `user_id` 格式：1-64 字符，仅允许字母、数字、下划线、短横线、点号
- 非法 `user_id` 返回 400 错误

### 前端用户切换

导航栏右侧显示当前用户标识（👤），点击可输入新的 `user_id` 并保存到 `localStorage`。

### MCP 兼容

MCP tools 增加可选 `user_id` 参数（默认 `"default"`），不破坏旧调用。

### 使用示例

```bash
# 上传论文到 alice 用户
curl -X POST http://localhost:8091/papers/upload \
  -H "X-User-Id: alice" \
  -F "file=@paper.pdf"

# 查看 alice 的论文
curl http://localhost:8091/papers -H "X-User-Id: alice"

# 不传 header 时使用 default 用户
curl http://localhost:8091/papers
```

## 当前限制

- 默认使用 local mock / heuristic AI，需配置 openai_compatible provider 才能使用真实 LLM
- 轻量多用户隔离通过 X-User-Id header 实现，不做登录/权限验证
- local embedding 语义有限
- evidence gate 会保守拒答
- MCP save_research_idea 只支持单个 source_paper_id（长度必须为 1）
- 切换 embedding provider/dimension 后需手动 rebuild
- 审计记录不保存 prompt/chunk/answer 全文和 API Key，只存字符数和脱敏错误信息；审计使用独立 session 持久化，不依赖业务接口是否 commit

## 后续路线

- 正式用户登录与权限系统（当前仅 X-User-Id 轻量隔离）
- 真实 LLM / Embedding 深度集成
- arXiv 实时论文接入
- 协作式研究工作流
- 模型调用成本监控与预算告警