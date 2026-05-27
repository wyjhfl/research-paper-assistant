# AGENTS.md — 项目级开发协作规则

面向后续 AI 工具和开发者的项目上下文，避免重复踩坑。

## 一、Project Overview

- **项目名称**：多 Agent 科研论文助手
- **版本**：1.0.0
- **当前能力**：
  - PDF 上传解析（pypdf 按页提取 + 固定字符切分 + 重叠）
  - chunk 入库（pgvector embedding）
  - 单论文 RAG 问答（向量检索 + evidence gate + LLM 生成）
  - 跨论文 RAG 问答（多论文联合检索 + per_paper_limit + paper_title 来源）
  - Idea 抽取与保存（启发式抽取 + 来源追溯 + 标签 + 置信度）
  - LangGraph Agent 工作流（Supervisor → Reader/Idea/Citation/MultiCitation → Reflection）
  - MCP Server（6 tools + stdio transport + 安全收口）
  - 真实模型评测（6 eval cases + 历史报告 + 趋势对比）
  - Playwright E2E 页面 smoke 测试
  - 轻量多用户隔离（X-User-Id header，不做登录）
  - 前端 apiFetch 统一抛 ApiError（parseApiError 解析 FastAPI 422 detail 数组）
  - 模型调用审计（model_call_events 表 + 脱敏记录 + 用户隔离查询，不保存 prompt/chunk/API key）

## 二、Architecture

```
research-paper-assistant/
├── apps/
│   ├── api/                  # FastAPI 后端
│   │   ├── app/
│   │   │   ├── main.py       # 应用入口 + lifespan
│   │   │   ├── config.py     # 配置管理 (pydantic-settings)
│   │   │   ├── database.py   # 数据库连接 + init_db + migration
│   │   │   ├── models.py     # SQLAlchemy ORM (pgvector)
│   │   │   ├── agents/       # LangGraph StateGraph 多 Agent
│   │   │   ├── mcp/          # MCP Server (FastMCP + 6 tools)
│   │   │   ├── routers/      # API 路由
│   │   │   ├── schemas/      # Pydantic 输入输出
│   │   │   ├── services/     # 业务逻辑层
│   │   │   └── repositories/ # 数据访问层
│   │   ├── tests/            # 后端测试
│   │   └── scripts/          # 运维脚本
│   └── web/                  # Next.js 15 前端
│       └── src/
│           ├── app/          # App Router 页面 (9 routes)
│           ├── components/   # UI 组件
│           └── lib/          # API 封装
├── infra/
│   └── init-db.sql           # 数据库初始化
├── scripts/
│   └── verify_all.ps1        # 统一验收脚本
├── artifacts/evals/          # 真实模型评测报告 (gitignored)
├── storage/                  # PDF 文件存储
├── docker-compose.yml
├── .env.example
├── AGENTS.md                 # 本文件
└── README.md
```

**技术栈**：
- 前端：Next.js 15 + TypeScript + Tailwind CSS (App Router)
- 后端：FastAPI + Pydantic + SQLAlchemy async + asyncpg
- 数据库：PostgreSQL 16 + pgvector
- AI Provider：local hash embedding + local mock LLM / OpenAI Compatible
- Agent：LangGraph StateGraph + Supervisor 多 Agent 编排
- MCP：FastMCP + stdio transport
- 部署：Docker Compose (3 services: backend, frontend, db)

## 三、Important Commands

### 统一验收

```powershell
# 完整验收（Docker build + smoke + pytest + build + E2E）
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1

# 跳过 Docker build（服务已运行）
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild

# 跳过 Docker build + E2E
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E

# 强制真实模型验收（需 REAL_MODEL_REQUIRED=true）
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1 -SkipDockerBuild -SkipE2E -RunRealModelEval
```

### 后端

```bash
# 基础设施验证
docker compose exec -T backend python scripts/smoke_check.py

# 真实模型连通性测试
docker compose exec -T backend python scripts/model_smoke_check.py

# 真实模型评测
docker compose exec -T backend python scripts/eval_real_model.py

# 后端测试
docker compose exec -T backend python -m pytest tests/ -q

# Demo 数据
docker compose exec backend python scripts/seed_demo.py
docker compose exec backend python scripts/reset_demo.py
```

### 前端

```bash
# 构建
cd apps/web && npm run build

# E2E 测试（默认启动独立 dev server，不复用旧进程）
cd apps/web && npm run test:e2e

# E2E 测试（headed 模式）
cd apps/web && npm run test:e2e:headed

# E2E 测试（复用已有 dev server，需先手动启动 npm run dev）
# PowerShell:
$env:E2E_REUSE_EXISTING_SERVER = "true"; npm run test:e2e:reuse
# bash:
E2E_REUSE_EXISTING_SERVER=true npm run test:e2e:reuse
```

## 四、Model Provider Rules

- 默认可以使用 local provider 开发，无需 API Key。
- **正式验收必须 `REAL_MODEL_REQUIRED=true`**，且 LLM/Embedding 都为 `openai_compatible`。
- LLM 使用 `openai_compatible` provider，支持任何 OpenAI 兼容 API。
- Embedding 使用 `openai_compatible` provider，维度由 `EMBEDDING_DIMENSION` 决定。
- **不写入真实 API Key 到代码或文档**，只在 `.env` 中配置（已 gitignored）。
- 切换 embedding 维度需要重建数据库或迁移 vector 列：
  - 修改 `EMBEDDING_DIMENSION`
  - `docker compose down -v` 重建 volume，或手动 ALTER COLUMN
  - 重建 demo embeddings：`docker compose exec backend python scripts/rebuild_demo_embeddings.py`
- 当前真实 embedding 维度以 `.env` / `settings.EMBEDDING_DIMENSION` 为准，不能硬编码猜测。
- local provider 的 hash embedding 默认 384 维。

## 五、Testing Rules

- **后端 pytest 不应调用真实模型**。所有 pytest 用例使用 local provider 或 mock。
- **E2E 应优先用 `page.route` mock 控制不稳定网络状态**，不依赖真实后端响应时序。
- **真实模型质量只由 `model_smoke_check.py` 和 `eval_real_model.py` 验证**，不在 pytest 中测试。
- **新增页面必须补 E2E smoke 测试**，至少覆盖 h1 文本和非空白。
- **修改 MCP tools 后必须更新 `/mcp` 页面和 E2E 工具清单测试**。
- Dynamic SSR 页面（/papers, /ideas）测试不能同步读取 `innerText`，需等待 h1 或使用 `expect.poll`。
- `/papers/ask` loading 测试必须用 `page.route` 延迟响应，避免 flaky。
- E2E 定位使用 `getAppMain(page)` (基于 `data-testid="app-main"`)，避免 Next.js SSR streaming 导致多 `<main>` strict mode 冲突。

## 六、MCP Tools

真实后端 MCP tools（6 个），`/mcp` 页面展示必须与此保持一致：

| Tool | 输入 | 输出 | 读写 |
|------|------|------|------|
| `search_papers` | query, limit? | papers[] (paper_id, title, filename, status, chunk_count, created_at) | 只读 |
| `get_paper_summary` | paper_id | summary, confidence | 只读 |
| `search_ideas` | query, limit? | ideas[] (idea_id, title, summary, paper_id, tags, confidence, source_count) | 只读 |
| `recommend_citations` | draft_text, paper_id?, paper_ids?, limit? | answer, rag_status, confidence, sources[] | 只读 |
| `search_paper_chunks` | query, paper_ids?, limit? | results[] (paper_id, paper_title, chunk_id, chunk_index, page, text_excerpt, score) | 只读 |
| `save_research_idea` | title, summary, tags, source_paper_ids | idea_id, title, paper_id, sources[] | 写入 |

**不存在的旧工具名**（不得出现在 /mcp 页面）：`upload_paper`, `ask_paper`, `multi_paper_ask`, `extract_ideas`, `run_agent`

**MCP 启动命令**：
- Docker：`docker compose exec backend python run_mcp.py`
- 本地：`cd apps/api && python run_mcp.py`
- **不是** `python -m app.mcp.server`

## 七、Known Pitfalls

1. **Next.js SSR/streaming 页面测试不能同步读取 innerText**：`page.goto()` 返回后 DOM 可能仍处于中间态（loading shell 已替换但数据未到达）。需先 `await expect(h1).toContainText(...)` 或使用 `expect.poll`。
2. **`/papers/ask` loading 测试必须用 `page.route` 延迟响应**：真实接口响应太快，无法稳定捕捉 loading → empty/result 状态链路。用 `page.route("**/papers", async (route) => { await delay(300); ... })` 人为延迟。
3. **`.env` 必须保持 gitignored**：已在 `.gitignore` 中，不要提交。
4. **不要把 local provider 的评测结果当真实模型质量**：local mock LLM 是拼接 contexts，local hash embedding 是确定性 hash 向量，语义能力有限。
5. **修改 embedding dimension 后旧 pgvector 列可能不兼容**：需要 `docker compose down -v` 重建或 ALTER COLUMN。
6. **MCP 页面展示必须和真实后端 tools 保持一致**：后端 tools 定义在 `apps/api/app/mcp/tools.py`，前端展示在 `apps/web/src/app/mcp/page.tsx`。
7. **`-RunRealModelEval` 是强制真实模型验收**：不是 local skip。如果当前是 local provider，脚本失败是正确行为。不想跑真实模型就不传此参数。
8. **PowerShell `2>&1 | ForEach-Object` 会吞掉 `$LASTEXITCODE`**：`verify_all.ps1` 使用 `Invoke-SafeCommand` 先执行命令再检查退出码。
9. **`$ErrorActionPreference = "Stop"` + 外部命令 stderr**：PowerShell 可能将 stderr 转为 terminating error。`Invoke-SafeCommand` 内部临时切换为 `"Continue"`。
10. **`loading.tsx` 中的 `<main>` 和 `<h1>` 会干扰 E2E 定位**：使用 `data-testid="app-main"` + `getAppMain(page)` 解决。
11. **不要因为占位符触发密钥扫描误报就删除必要配置示例**：`scripts/check_docs_secrets.py` 已内置白名单（`<YOUR_...>`、`<REPLACE_ME>`、`localhost` 开发默认数据库严格匹配），如需新增占位符格式请更新脚本中的 `PLACEHOLDER_PATTERNS` 或 `SAFE_LITERAL_EXACT`。
12. **文档密钥扫描不得用宽泛 localhost 白名单**：`localhost` 不在 `SAFE_LITERAL_EXACT` 中，只有精确匹配开发默认数据库连接串才放行（`LOCAL_DEV_DB_EXACT`）。含 `localhost` 的 `API_KEY` 赋值会被正确拒绝。
13. **根目录脚本测试不放入 `apps/api/tests`**：`tests/test_check_docs_secrets.py` 在项目根目录，不继承后端数据库 fixture，由 `verify_all.ps1` 独立运行。根目录 `pytest.ini` 禁用 asyncio 插件（`-p no:asyncio`），不影响 `apps/api/pytest.ini`。
14. **不要并行运行多个后端 pytest / verify_all**：后端测试会重建测试表，并发运行可能导致 PostgreSQL DDL deadlock。如果遇到死锁，停止并发任务后顺序重跑即可。
15. **数据查询必须按 user_id 隔离**：所有 repository 的 get/list/delete 方法必须接受 `user_id` 参数并添加 WHERE 过滤；router 层通过 `Depends(get_user_id)` 获取当前 user_id；MCP tools 默认 `user_id="default"` 保持兼容。新增数据表或查询时务必检查是否遗漏 user_id 过滤。
16. **Playwright E2E 默认不复用旧 dev server**：`playwright.config.ts` 中 `reuseExistingServer` 默认为 `false`，确保每次测试运行当前源码。如果端口 3000 被旧 dev server 占用，Playwright 会启动失败——需先停止旧进程或显式设置 `E2E_REUSE_EXISTING_SERVER=true`。cookie/user isolation 相关测试尤其不能复用旧 dev server，因为 `.next` 缓存可能导致 `getUserId()` 使用过时 bundle。
17. **FastAPI 422 detail 是数组，前端不得直接展示对象**：FastAPI Pydantic 校验错误返回 `{ detail: [{ loc, msg, type }] }` 数组格式，不是字符串。前端 `apiFetch` 统一通过 `parseApiError` 解析为 `ApiError`，格式化成可读文本（如 `请求参数不合法：question: Field required`）。组件 catch 中必须使用 `getErrorMessage(err, fallback)` 而非 `err instanceof Error ? err.message : fallback`，否则 `ApiError` 的 `details` 可能被 `JSON.stringify` 成 `[object Object]`。
18. **真实模型 provider 测试不得调用真实外部 API**：所有 provider pytest 用例必须 mock httpx.AsyncClient，不得发起真实 HTTP 请求。真实模型连通性和质量由 `model_smoke_check.py` 和 `eval_real_model.py` 验证。
19. **Provider 错误日志必须脱敏**：`_sanitize_error_message` 会自动替换 `api_key`、`Authorization`、`secret`、`token`、`database_url` 等敏感 key 的值。日志 extra 中只包含 `provider`、`model`、`status_code`、`attempt`、`error_type`，不包含 prompt 全文、chunk 全文、API Key、Authorization header。
20. **429/5xx/timeout 是可重试，401/403 是配置/权限错误不应重试**：`_request_with_retry` 对 429、500、502、503、504 和网络超时/连接错误做有限重试（受 `PROVIDER_MAX_RETRIES` 控制）；对 400、401、403、404 不重试，直接抛 `ProviderRequestError`。
21. **Windows Hyper-V 可能排除端口 7991-8090 及更大范围**：Docker Desktop 在 Windows 上可能因 Hyper-V 端口保留导致 `0.0.0.0:8000` bind 失败。当前项目后端端口映射为 `8091:8000`（外部 8091，内部 8000）。如需更改，必须同步更新 `docker-compose.yml`、`apps/web/src/lib/api.ts` 默认 URL、`NEXT_PUBLIC_API_URL` 环境变量、以及所有文档和 E2E 测试中的端口引用。可用 `netsh interface ipv4 show excludedportrange protocol=tcp` 查看当前排除范围。
22. **pytest 不跑真实模型，真实质量只看 eval_real_model**：普通 pytest 只测评测框架逻辑（load_eval_cases、assert_eval_result 等），不调用真实 LLM/Embedding。真实模型质量必须通过 `eval_real_model.py` 或 `verify_all -RunRealModelEval` 验证。
23. **新增模型调用点时必须记录审计，且不得保存原文/密钥**：所有真实 LLM / Embedding 调用（`embed_texts`、`generate_answer`）必须通过 `record_model_call` 记录审计事件。审计记录不得包含 prompt 全文、chunk 全文、answer 全文、API Key、Authorization、DATABASE_URL。metadata 只允许白名单字段（paper_id, agent_task_type, eval_case_id, chunk_count, query_length, context_count, paper_ids, idea_count）。审计写入失败只 `logger.warning`，不能让用户请求失败。审计使用独立 session 持久化，不依赖业务 session 是否 commit。
24. **审计记录不能依赖只读请求的业务 session flush**：`record_model_call` 使用独立 session 写入并 commit，不依赖调用方的业务 session。只读请求（如 RAG ask、multi-paper search）的业务 session 可能不会 commit，审计记录仍需持久化。
25. **不允许 fake PDF parse 成功**：PDF 解析失败时 paper.status 必须设为 `failed` 并写入 error_message，绝不允许静默写入 fake text 伪造成功。当前唯一解析路径是 `pdf_parser.parse_pdf()`（基于 pypdf），不存在 fitz/PyMuPDF 路径。
26. **所有上传文件必须落在 STORAGE_PATH**：上传文件保存路径必须基于 `settings.STORAGE_PATH`，不允许硬编码 `uploads/`、`apps/api/uploads/`、`./storage` 等相对路径。文件名必须经过 `_safe_filename()` 安全化，防止路径穿越。
27. **新增 service/helper 时必须检查 user_id**：所有 repository 的 get/list/delete 方法、service 层辅助方法、错误分支、title 查询、paper_title 查询都必须传递和校验 user_id。其他用户数据必须返回 404 或空结果，不能泄露存在性。
28. **schema 变更必须同步 Alembic migration**：修改 `models.py` 后必须生成对应的 Alembic migration（`python -m alembic revision --autogenerate -m "描述"`），不能只依赖 `create_all`。生产环境必须通过 `alembic upgrade head` 迁移。
29. **restore 脚本必须显式确认**：所有 restore 脚本（`restore_postgres.ps1`、`restore_storage.ps1`、`restore_all.ps1`）必须传入 `-ConfirmRestore` 参数才执行，不允许静默覆盖数据。
30. **backup manifest 不得包含 secrets**：`backup_manifest_*.json` 只包含 timestamp、文件名、app_version、embedding_dimension，不包含 DATABASE_URL、API Key、Authorization 等敏感信息。
31. **restore 脚本禁止使用 /app/storage/..**：`restore_storage.ps1` 只允许清空 `/app/storage` 目录内部内容（`find /app/storage -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +`），不允许删除 `/app/storage` 本身，不允许出现 `/app/storage/..`，不允许 `rm -rf /app`。
32. **backup manifest 必须引用真实文件路径**：`backup_all.ps1` 的 manifest 中 `db_backup_file` / `storage_backup_file` / `eval_backup_file` 必须来自子脚本实际输出的文件名，不能硬编码 `db_backup_$timestamp.sql` 等假设值。`restore_all.ps1` 必须按 manifest 真实路径恢复，不能假设固定子目录拼接。
33. **verify_all 不能依赖未探测的宿主机 python**：`verify_all.ps1` 必须通过 `Resolve-PythonCommand` 自动探测 `python` → `py -3`，两者都不存在时输出明确错误并退出，不能假设宿主机 PATH 中一定有 `python`。
34. **PowerShell 不能把 "py -3" 作为单个可执行命令**：`Resolve-PythonCommand` 必须返回结构化对象（`Exe` + `Args`），不能返回带空格的字符串。调用时用 `& $Python.Exe @($Python.Args + @(...))` 拼接，不能 `& "py -3"`。
35. **restore 清理失败必须 fail fast**：`restore_storage.ps1` 清理 `/app/storage` 失败时必须 `exit 1`，不允许 WARN 后继续 copy。旧文件残留会导致恢复不完整。
36. **全量 restore manifest 必须包含 DB 和 storage**：`restore_all.ps1` 的 manifest 中 `db_backup_file` 和 `storage_backup_file` 必填，为空时 `exit 1`。`eval_backup_file` 可选。DryRun 模式也必须执行必填校验。
37. **X-User-Id 不是生产认证**：`X-User-Id` 请求头仅在开发模式（`AUTH_ENABLED=false` 或 `ALLOW_DEV_USER_HEADER=true`）下生效。生产环境必须 `AUTH_ENABLED=true` + `ALLOW_DEV_USER_HEADER=false`，依赖 session cookie 认证。任何把 `X-User-Id` 当作生产认证的逻辑都是错误的。
38. **Session token 仅存储 hash**：数据库中 session 表只存储 token 的 hash 值，不存储明文。验证时对请求 cookie 中的 token 做 hash 后比对。即使数据库泄露也无法还原 session token。
39. **AUTH_ENABLED=true 时前端必须 credentials: include**：启用真实认证后，所有 API 请求必须设置 `credentials: "include"` 以携带 HttpOnly session cookie。否则请求会因缺少认证被 401 拒绝。
40. **前端中文文案必须保持 UTF-8，不允许提交 mojibake**：所有用户可见中文必须是正常简体中文，不允许出现 `鐧`、`閭`、`璇`、`馃`、`鈫`、`鉁`、`澶`、`�` 等乱码片段。新增页面或错误提示后，必须跑乱码扫描测试（`npx playwright test tests/e2e/auth.spec.ts`）。
41. **前端组件避免使用 emoji 和特殊 Unicode 符号**：`👤`、`✕`、`↺` 等字符在某些终端/编码环境下可能显示为乱码。用户图标用纯文本 `用户`，取消按钮用 `×`，重置按钮用 `重置`。
42. **长任务不要直接挂在 HTTP 请求链路**：PDF 处理、embedding 重建等耗时操作应通过 job system 异步执行。同步 API 保留兼容，但生产环境推荐 `async_mode=true`。
43. **新 job_type 必须有 user_id 隔离、状态、测试和文档**：每个新 job_type 必须在 `VALID_JOB_TYPES` 中注册，必须有 worker 执行逻辑，必须有测试覆盖。
44. **不要把模型原文写入 output_json**：job 的 output_json 应只包含结构化摘要，不包含大段模型生成文本。`safe_job_output` 在写入前统一过滤。
45. **Jobs API 不得暴露 raw input_json/output_json**：`/jobs` 响应必须使用 `input_summary` / `output_summary` 安全摘要，不直接返回 `input_json` / `output_json` 原始字段。`agent_run` 的 question、draft_text、answer 等长文本不得原样展示。
46. **max_attempts 必须有范围校验**：`JobCreateRequest.max_attempts` 必须 `ge=1, le=10`，默认使用 `settings.JOB_MAX_ATTEMPTS`。非法值返回 FastAPI 422。
47. **Job 失败重试必须可靠持久化 attempts**：`claim_pending` 后的 attempts/status 必须在新事务中持久化，失败后不能被 rollback 回滚。`mark_failed_with_attempts` 接收显式 attempts/max_attempts 参数决定状态。
48. **job_runs.output_json 必须通过 safe_job_output 过滤后持久化**：`JobWorker._run_one` 在写入 output_json 前必须调用 `safe_job_output(job_type, result)` 过滤敏感/长文本。agent_run 只保留 run_id/status/task_type/confidence/warning_count/source_count/idea_count 等计数字段，不得保存 answer/summary/question/draft_text/sources 原文。
49. **restore/backup 改动必须跑 validate manifest + dry-run**：修改 backup_all.ps1 / restore_all.ps1 / manifest 格式后，必须运行 `validate_backup_manifest.py` 校验最新 manifest，并执行 `restore_all.ps1 -DryRun` 验证恢复路径。不自动覆盖生产数据。
50. **RC/restore/backup 测试不得依赖 glob 默认顺序**：读取 `restore_drill_*.json` 等文件时必须按 mtime 或文件名排序（`sorted(..., key=lambda f: f.stat().st_mtime)`），不能依赖 `glob()` 返回顺序。
51. **不得在门禁脚本里执行真实 restore**：`rc_gate.ps1` 和 `verify_all.ps1` 不得调用 `restore_all.ps1 -ConfirmRestore`。真实 restore 是手动运维操作，不属于自动化门禁。
52. **RC gate 不得把 production_check FAIL 降级为 WARN**：`rc_gate.ps1` 中 `production_check.py` 的 exit code 非 0 时必须立即失败退出，不允许用 `RESULT: FAIL` 匹配降级为 WARN 继续执行。PASS WITH WARNINGS 时 exit code 为 0，可以正常通过。
53. **RC gate ManifestPath 不得使用绝对路径**：`rc_gate.ps1` 的 `-ManifestPath` 参数只接受项目相对路径（如 `artifacts/backups/backup_manifest_xxx.json`），传入绝对路径必须拒绝并输出固定错误 `ManifestPath must be project-relative`，不得回显绝对路径。
54. **Release Notes 不得声称未实际运行的验收结果**：Release Notes 中的验收数据必须标注来源阶段，不得写"ALL CHECKS PASSED"等绝对表述除非在本阶段实际重新执行了完整 rc_gate。未重新执行的验收结果必须注明"Phase XX 执行时结果"。
55. **tag 前必须确认 Release Notes、.env 未跟踪、secret scan**：创建 v1.0.0-rc.1 tag 前必须确认：(1) Release Notes 文件存在且不含 secrets，(2) `git ls-files .env` 无输出，(3) `python scripts/check_docs_secrets.py` 通过。
56. **部署记录不得包含 .env / key / 绝对路径**：DEPLOYMENT_EVIDENCE 和任何部署演练文档不得包含 .env 内容、真实 API Key（sk-/tp-前缀）、DATABASE_URL 真实值、宿主机绝对路径。只记录命令摘要和结果状态。
57. **restore 只能 dry-run**：部署门禁和运维演练中只能执行 `restore_all.ps1 -DryRun`，禁止执行 `-ConfirmRestore`。真实 restore 是独立的手动运维操作。
58. **Docker artifacts 不得提交到 Git**：`artifacts/backups/`、`artifacts/evals/` 等运行产物已在 `.gitignore` 中，不得提交。部署演练产生的 backup manifest、restore drill 记录仅存于本地。
59. **ops_check 不得执行写入/恢复操作**：`ops_check.ps1` 是只读巡检脚本，不得包含 backup、restore、数据库写入、文件删除等操作。只检查状态，不修改状态。
60. **backup freshness 不得输出绝对路径**：`check_backup_freshness.py` 输出 JSON 中 `latest_manifest` 只包含文件名（如 `backup_manifest_20260527_080654.json`），不包含宿主机绝对路径。
61. **stale job 告警不得自动删除/重置任务**：当 `stale_running_count > 0` 时只能告警，不得自动执行 job 重置、删除或状态修改。需人工判断后操作。
62. **运维巡检脚本不得通过注册/登录制造状态**：`ops_check.ps1` 等只读巡检脚本不得调用 `/auth/register`、`/auth/login`、`-Method POST` 等写入操作。巡检只能观察，不能创建用户、创建 session 或修改任何数据。如需认证态数据，应输出 WARN 提示人工检查。
63. **stale job 告警不得自动修复**：巡检发现 `stale_running_count > 0` 时只能输出 WARN，不得自动重置 job 状态、删除 job 或执行任何修复操作。修复需人工判断后手动执行。

## 八、Review Checklist

每次代码变更后审查：

- [ ] 是否破坏现有 API？（路由、请求/响应格式、状态码）
- [ ] 是否泄露密钥？（API Key、Authorization、DATABASE_URL、sk- 前缀）— 修改文档或示例时必须通过 `scripts/check_docs_secrets.py`
- [ ] 是否影响 `verify_all.ps1`？（新增步骤、修改命令、改变退出码）
- [ ] 是否更新 README / AGENTS.md？（新功能、新命令、架构变更）
- [ ] 是否新增或更新 E2E？（新页面必须补 smoke，MCP 变更必须更新工具清单测试）
- [ ] 是否真实模型路径与 local 测试路径分离？（pytest 不调真实模型，eval_real_model 不走 local mock）
- [ ] 是否修改了 MCP tools？（同步更新 /mcp 页面 + E2E + MCP_CONTRACT.md）
- [ ] 是否修改了 API 接口？（同步更新 docs/API_CONTRACT.md）
- [ ] 是否修改了 embedding 维度？（需说明迁移方案）
- [ ] 是否新增了敏感信息检测模式？（更新 `_SENSITIVE_PATTERNS` / `_SENSITIVE_KEYS`）
- [ ] 发布前是否查看 docs/RELEASE_CHECKLIST.md？
- [ ] 是否并行运行了后端测试门禁？（不要并行，避免 DDL deadlock）
- [ ] 涉及数据查询是否检查 user_id 隔离？（所有 repo/service/router 查询必须按 user_id 过滤，MCP tools 默认 user_id="default"）
- [ ] 修改 REST API 是否同步 Pydantic schema + API_CONTRACT + OpenAPI 测试？（新增/修改接口必须同步 request/response schema、更新 docs/API_CONTRACT.md、确保 OpenAPI 合约测试覆盖）
- [ ] 前端 catch 中是否使用 getErrorMessage(err, fallback)？（不得使用 err instanceof Error ? err.message : fallback，否则 ApiError 的 details 可能显示为 [object Object]）
- [ ] Provider 相关代码是否使用 _sanitize_error_message 脱敏？（错误消息不得包含 API Key / Authorization / 完整 URL query）
- [ ] 修改 RAG / Agent / MCP / Provider 时，是否需要新增或更新 `apps/api/evals/real_model_cases.json` 中的 eval case？
- [ ] 新增模型调用点是否记录审计？（所有 embed_texts / generate_answer 调用必须通过 record_model_call 记录，且不得保存原文/密钥）
- [ ] 新增 /usage 页面相关功能是否补 E2E？（empty/error/header/can_proceed 状态必须覆盖）
- [ ] 是否引入硬编码路径？（上传/存储路径必须基于 settings.STORAGE_PATH，不允许硬编码 uploads/ 或 ./storage）
- [ ] 是否绕过 production_check？（新增基础设施依赖必须同步更新 production_check.py）
- [ ] 是否新增运行产物但未加 .gitignore？（新增目录/文件类型必须检查 .gitignore 覆盖）
- [ ] 是否新增/修改了模型字段但未写 migration？（修改 models.py 后必须生成 Alembic migration）
- [ ] 是否修改 storage/eval/db 结构但未更新 backup/restore？（新增备份目标必须同步更新 backup_all/restore_all）
- [ ] 是否修改备份脚本后验证 restore_all 可解析 manifest？（manifest 路径必须与真实备份文件一致）
- [ ] 修改 restore/backup 脚本后是否运行 validate_backup_manifest.py + restore dry-run？（restore/backup 改动必须跑 validate manifest + dry-run）
- [ ] 是否有永远通过的测试断言？（如 `assert x or True`、`assert True` 等无效断言必须修复）
- [ ] 是否有"失败后继续恢复"的逻辑？（restore 清理/复制失败必须 fail fast，不允许 WARN 后继续）
- [ ] 是否把带参数命令作为一个字符串执行？（PowerShell 中 `& "py -3"` 无效，必须拆分为 Exe + Args）
- [ ] 新增端点是否正确处理 401？（AUTH_ENABLED=true 时未认证请求必须返回 401，不能降级为 dev 模式）
- [ ] 响应是否泄露 password_hash 或 session token？（认证相关接口的响应不得包含 password_hash、session token 明文等敏感字段）
- [ ] 是否把 dev user header 误当作生产认证？（`X-User-Id` 仅开发模式有效，不得在生产逻辑中依赖它做身份验证）
- [ ] 是否引入用户可见乱码？（前端中文文案必须保持 UTF-8，不允许 mojibake；新增页面/错误提示后必须跑乱码扫描测试）
- [ ] 是否新增中文文案但缺少 E2E 覆盖？（新增页面/错误提示必须补充对应 E2E 文案断言）
- [ ] 是否新增 job_type 但未加 worker 测试？
- [ ] 是否跨用户读取 job？
- [ ] 是否把模型原文写入 output_json？
- [ ] Jobs API 是否暴露 raw input_json/output_json？（必须使用 input_summary/output_summary 安全摘要）
- [ ] max_attempts 是否有范围校验？（ge=1, le=10，默认 settings.JOB_MAX_ATTEMPTS）
- [ ] Job 失败重试 attempts 是否可靠持久化？（不能被 rollback 回滚）
- [ ] job_runs.output_json 是否通过 safe_job_output 过滤？（agent_run 不得保存 answer/summary/question/draft_text/sources 原文）
- [ ] Release Notes 是否存在且不含 secrets？（sk- / tp- / DATABASE_URL 真实值 / API_KEY 真实值）
- [ ] Release Notes 是否声称了未实际运行的验收结果？（未重新执行的验收必须标注来源阶段）
- [ ] tag 前 .env 是否未被 Git 跟踪？（`git ls-files .env` 必须无输出）
- [ ] tag 前 secret scan 是否通过？（`python scripts/check_docs_secrets.py`）
