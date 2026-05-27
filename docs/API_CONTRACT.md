# API Contract — REST API

Base URL: `http://localhost:8091`

## 通用请求头

所有 REST API 支持可选的 `X-User-Id` 请求头，用于轻量多用户数据隔离。

| Header | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| X-User-Id | string | 否 | "default" | 用户标识，1-64 字符，仅允许字母、数字、下划线、短横线、点号 |

- 缺少 `X-User-Id` 时使用 `"default"`，兼容单用户模式
- 非法 `user_id`（含特殊字符、超长、空字符串）返回 **400**
- 所有数据查询（论文、Idea、Agent Run）按 `user_id` 隔离，不同用户无法访问彼此数据
- 上传论文时自动绑定当前 `user_id`

## Pydantic 校验规则

Phase 24 起，所有 REST API 请求体使用 Pydantic schema 校验。校验失败返回 **422 Unprocessable Entity**（FastAPI 默认行为），响应体包含 `detail` 字段描述具体校验错误。

| 字段 | 校验规则 | 失败状态码 |
|------|---------|-----------|
| question / query | trim 后不能为空 | 422 |
| title / summary | trim 后不能为空 | 422 |
| paper_ids | list[int]，最多 50 个 | 422 |
| top_k (papers/ask) | int，范围 [1, 20] | 422 |
| top_k (papers/search) | int，范围 [1, 50] | 422 |
| confidence | float，范围 [0.0, 1.0] | 422 |
| tags | list[str]，空 tag 自动过滤 | — |
| source_chunk_ids | list[int]，至少 1 个 | 422 |

> **注意**：Phase 24 之前部分接口返回 400 表示参数校验失败，现在统一由 Pydantic 返回 422。业务逻辑错误（如 paper_id 不存在、重复 Idea 标题）仍返回 400/404/409。

---

## Auth

### POST /auth/register

用途：注册新用户。

**请求体**：

```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "display_name": "Alice"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 是 | 邮箱地址，唯一 |
| password | string | 是 | 密码，最少 8 字符 |
| display_name | string | 是 | 显示名称 |

**响应** (201)：

```json
{
  "id": "a1b2c3d4",
  "email": "user@example.com",
  "display_name": "Alice"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 用户 ID |
| email | string | 邮箱 |
| display_name | string | 显示名称 |

**常见错误**：
- 409 — 邮箱已被注册
- 422 — 参数校验失败（邮箱格式、密码长度、display_name 为空）

**是否依赖真实模型**：否

---

### POST /auth/login

用途：用户登录，成功后设置 HttpOnly session cookie。

**请求体**：

```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 是 | 邮箱地址 |
| password | string | 是 | 密码 |

**响应** (200)：

```json
{
  "id": "a1b2c3d4",
  "email": "user@example.com",
  "display_name": "Alice"
}
```

**Set-Cookie**：`session=<token>; HttpOnly; SameSite=Lax; Path=/`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 用户 ID |
| email | string | 邮箱 |
| display_name | string | 显示名称 |

**常见错误**：
- 401 — 邮箱或密码错误
- 422 — 参数校验失败

**是否依赖真实模型**：否

---

### POST /auth/logout

用途：用户登出，清除 session cookie。

**请求体**：无

**响应** (200)：

```json
{
  "ok": true
}
```

**是否依赖真实模型**：否

---

### GET /auth/me

用途：获取当前登录用户信息。

**请求体**：无

**响应** (200)：

```json
{
  "id": "a1b2c3d4",
  "email": "user@example.com",
  "display_name": "Alice",
  "auth_mode": "session"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 用户 ID |
| email | string | 邮箱 |
| display_name | string | 显示名称 |
| auth_mode | string | `"session"`（真实认证）或 `"dev"`（开发模式 X-User-Id） |

**常见错误**：
- 401 — 未登录且非开发模式

**说明**：
- `X-User-Id` 请求头仅在开发模式（`ALLOW_DEV_USER_HEADER=true`）下生效，生产环境被忽略
- `auth_mode` 为 `"dev"` 时表示当前用户身份来自 `X-User-Id` 请求头，非真实认证

**是否依赖真实模型**：否

---

## Jobs API

### POST /jobs

创建后台任务。

**请求**：
```json
{
  "job_type": "process_paper | rebuild_embeddings | agent_run | real_model_eval",
  "input": {},
  "max_attempts": 1
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| job_type | string | 是 | — | 任务类型 |
| input | object | 否 | {} | 任务输入（不直接暴露给前端） |
| max_attempts | int | 否 | JOB_MAX_ATTEMPTS | 最大重试次数，范围 [1, 10] |

**响应** (201)：
```json
{
  "job_id": "job_...",
  "job_type": "process_paper",
  "status": "pending",
  "input_summary": "paper_id=42",
  "output_summary": null,
  "error_message": null,
  "progress_current": 0,
  "progress_total": 0,
  "attempts": 0,
  "max_attempts": 1,
  "created_at": "...",
  "started_at": null,
  "finished_at": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| job_id | string | 任务唯一 ID |
| job_type | string | 任务类型 |
| status | string | pending / running / completed / failed / cancelled |
| input_summary | string\|null | 安全输入摘要（不暴露 raw JSON） |
| output_summary | string\|null | 安全输出摘要（不暴露 raw JSON，agent_run 不泄露 question/draft_text/answer） |
| error_message | string\|null | 脱敏错误信息 |
| progress_current | int | 当前进度 |
| progress_total | int | 总进度 |
| attempts | int | 已尝试次数 |
| max_attempts | int | 最大重试次数 |
| created_at | datetime | 创建时间 |
| started_at | datetime\|null | 开始时间 |
| finished_at | datetime\|null | 完成时间 |

**安全说明**：
- 响应不包含 `input_json` / `output_json` 原始字段
- `input_summary` / `output_summary` 只返回结构化摘要
- `agent_run` 的 question、draft_text、answer 等长文本不在摘要中原样展示
- `error_message` 继续保持脱敏
- `job_runs.output_json` 本身只保存安全结构化摘要（通过 `safe_job_output` 过滤），不保存模型原文
  - `process_paper`：仅 paper_id、status
  - `rebuild_embeddings`：仅 paper_id、chunks_embedded
  - `agent_run`：仅 run_id、status、task_type、confidence、warning_count、source_count/idea_count 等计数字段、output_keys、rag_status
  - `real_model_eval`：仅 status、message（截断至 300 字符）

**重试语义**：
- `max_attempts=1`：第一次失败后 status 直接变为 `failed`
- `max_attempts=2`：第一次失败后 status 回到 `pending`（等待重试），第二次失败变 `failed`
- 不允许无限重试，最大 `max_attempts=10`

**常见错误**：
- 422 — `max_attempts` 不在 [1, 10] 范围
- 400 — `job_type` 不合法

### GET /jobs

列出当前用户任务。

**Query 参数**：
- `status` (optional): 按状态过滤
- `job_type` (optional): 按类型过滤
- `limit` (default 50, max 100)

**响应** (200)：
```json
{
  "jobs": [
    {
      "job_id": "job_...",
      "job_type": "process_paper",
      "status": "completed",
      "input_summary": "paper_id=42",
      "output_summary": "paper_id=42, status=completed",
      "error_message": null,
      "progress_current": 1,
      "progress_total": 1,
      "attempts": 1,
      "max_attempts": 1,
      "created_at": "...",
      "started_at": "...",
      "finished_at": "..."
    }
  ],
  "total": 1
}
```

### GET /jobs/{job_id}

查询任务详情。其他用户的 job 返回 404。

### POST /jobs/{job_id}/cancel

取消 pending 状态的任务。running 状态不可取消。

---

### async_mode 兼容

`POST /papers/upload?async_mode=true`：创建 paper 记录后返回 `job_id`，PDF 处理在后台执行。

`POST /papers/{id}/embeddings/rebuild?async_mode=true`：创建 rebuild_embeddings job 后返回 `job_id`。

---

## Health

### GET /health

用途：健康检查，返回服务状态和数据库连接信息。

**响应**：

```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "connected"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 固定 "ok" |
| version | string | 应用版本号 |
| database | string | "connected" 或错误信息 |

**常见错误**：数据库不可用时 `database` 字段返回错误描述。

**是否依赖真实模型**：否

---

## Papers

### POST /papers/upload

用途：上传 PDF 论文，自动解析、分块、生成 embedding。

**请求**：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | PDF 文件 |

**响应** (200)：

```json
{
  "id": 1,
  "title": "Attention Is All You Need",
  "filename": "sample.pdf",
  "status": "completed",
  "chunk_count": 12
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 论文 ID |
| title | string | 论文标题（从 PDF 提取） |
| filename | string | 原始文件名 |
| status | string | "pending" / "processing" / "completed" / "failed" |
| chunk_count | int | 分块数量 |

**用户隔离**：论文自动绑定当前 X-User-Id。

**常见错误**：
- 400：文件格式不支持（非 PDF）
- 413：文件过大
- 500：解析失败（status="failed"，error_message 有值）

**是否依赖真实模型**：embedding 生成依赖 provider（local 或 openai_compatible）

---

### GET /papers

用途：获取论文列表（当前不支持分页，返回全部论文）。

**响应** (200)：

```json
{
  "papers": [
    {
      "id": 1,
      "title": "Attention Is All You Need",
      "filename": "sample.pdf",
      "status": "completed",
      "chunk_count": 12,
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "total": 3
}
```

**用户隔离**：只返回当前 user_id 的论文。

**常见错误**：无

**是否依赖真实模型**：否

---

### GET /papers/{paper_id}

用途：获取论文详情和分块内容。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| paper_id | int | 论文 ID |

**响应** (200)：

```json
{
  "paper": {
    "id": 1,
    "title": "Attention Is All You Need",
    "filename": "sample.pdf",
    "status": "completed",
    "error_message": null,
    "chunk_count": 12,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00"
  },
  "chunks": [
    {
      "id": 1,
      "chunk_index": 0,
      "text": "...",
      "page_start": 1,
      "page_end": 1,
      "section_title": "Introduction"
    }
  ]
}
```

**用户隔离**：只能访问当前 user_id 的论文，其他用户论文返回 404。

**常见错误**：404 — 论文不存在

**是否依赖真实模型**：否

---

### POST /papers/{paper_id}/embeddings/rebuild

用途：重建论文的 embedding 向量。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| paper_id | int | 论文 ID |

**响应** (200)：

```json
{
  "paper_id": 1,
  "chunks_embedded": 12
}
```

**用户隔离**：只能重建当前 user_id 的论文。

**常见错误**：404 — 论文不存在

**是否依赖真实模型**：embedding 生成依赖 provider

---

### POST /papers/{paper_id}/ask

用途：单论文 RAG 问答。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| paper_id | int | 论文 ID |

**请求体**：

```json
{
  "question": "What problem does attention solve?"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| question | string | 是 | 用户问题 |

**响应** (200)：

```json
{
  "answer": "Attention solves the problem of...",
  "status": "answered",
  "confidence": 0.85,
  "sources": [
    {
      "paper_id": 1,
      "chunk_id": 3,
      "chunk_index": 2,
      "page_start": 3,
      "page_end": 4,
      "text_excerpt": "...",
      "score": 0.82
    }
  ]
}
```

**RAG 响应契约**：
- `status` 只能是 `"answered"` 或 `"insufficient_context"`
- `sources` 必须包含 `chunk_id`、`paper_id`、`page_start`、`page_end`、`text_excerpt`、`score`
- `insufficient_context` 时 `answer` 为固定提示，不允许编造答案
- `confidence` 范围 [0, 1]

**用户隔离**：只能对当前 user_id 的论文提问。

**常见错误**：404 — 论文不存在

**是否依赖真实模型**：LLM 生成答案依赖 provider

---

### POST /papers/ask

用途：跨论文 RAG 问答，支持指定论文或全库检索。

**请求体**：

```json
{
  "question": "How can RAG and multi-agent workflows support research?",
  "paper_ids": [1, 2],
  "top_k": 8
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| question | string | 是 | — | 用户问题 |
| paper_ids | int[] | 否 | null | 限定论文 ID 列表，null 表示全库检索，最多 50 个 |
| top_k | int | 否 | 8 | 检索 top-k chunk，范围 [1, 20] |

**响应** (200)：

```json
{
  "answer": "RAG and multi-agent workflows...",
  "status": "answered",
  "confidence": 0.78,
  "sources": [
    {
      "paper_id": 1,
      "paper_title": "Attention Is All You Need",
      "chunk_id": 5,
      "chunk_index": 4,
      "page_start": 5,
      "page_end": 6,
      "text_excerpt": "...",
      "score": 0.79
    }
  ]
}
```

**跨论文 RAG 响应契约**：
- `status` 只能是 `"answered"` 或 `"insufficient_context"`
- `sources` 必须包含 `paper_title`（跨论文独有字段）
- `insufficient_context` 不允许编造答案

**用户隔离**：全库检索只检索当前 user_id 的 completed papers；paper_ids 过滤校验归属当前 user_id。

**常见错误**：
- 404 — paper_ids 包含不存在的论文 ID
- 503 — AI provider 不可用或配置错误

**是否依赖真实模型**：LLM 生成答案依赖 provider

---

### POST /papers/search

用途：纯向量检索，不调用 LLM，只返回匹配的 chunk。

**请求体**：

```json
{
  "query": "transformer architecture",
  "paper_ids": [1],
  "top_k": 10
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| query | string | 是 | — | 检索查询 |
| paper_ids | int[] | 否 | null | 限定论文，null 表示全库，最多 50 个 |
| top_k | int | 否 | 10 | 返回数量，范围 [1, 50] |

**响应** (200)：

```json
{
  "results": [
    {
      "paper_id": 1,
      "paper_title": "Attention Is All You Need",
      "chunk_id": 3,
      "chunk_index": 2,
      "page_start": 3,
      "page_end": 4,
      "text_excerpt": "...",
      "score": 0.85
    }
  ]
}
```

**用户隔离**：全库检索只检索当前 user_id 的 papers；paper_ids 过滤校验归属当前 user_id。

**常见错误**：
- 404 — paper_ids 包含不存在的论文 ID
- 503 — AI provider 不可用或配置错误

**是否依赖真实模型**：embedding 生成依赖 provider，但不调用 LLM

---

## Ideas

### POST /papers/{paper_id}/ideas/extract

用途：从论文中抽取研究 Idea 候选。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| paper_id | int | 论文 ID |

**响应** (200)：

```json
{
  "paper_id": 1,
  "candidates": [
    {
      "title": "Efficient Attention for Long Sequences",
      "summary": "Explore sparse attention patterns...",
      "research_question": "Can sparse attention maintain quality?",
      "method_hint": "Compare sparse vs dense attention...",
      "tags": ["attention", "efficiency"],
      "source_chunk_ids": [3, 5],
      "confidence": 0.72
    }
  ]
}
```

**用户隔离**：只能对当前 user_id 的论文抽取 Idea。

**常见错误**：404 — 论文不存在

**是否依赖真实模型**：LLM 生成 Idea 依赖 provider

---

### POST /ideas

用途：保存用户选择的 Idea。

**请求体**：

```json
{
  "paper_id": 1,
  "title": "Efficient Attention for Long Sequences",
  "summary": "Explore sparse attention patterns...",
  "research_question": "Can sparse attention maintain quality?",
  "method_hint": "Compare sparse vs dense attention...",
  "tags": ["attention", "efficiency"],
  "source_chunk_ids": [3, 5],
  "confidence": 0.72
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| paper_id | int | 是 | — | 来源论文 ID |
| title | string | 是 | — | Idea 标题，trim 后不能为空 |
| summary | string | 是 | — | Idea 摘要，trim 后不能为空 |
| research_question | string | 否 | "" | 研究问题 |
| method_hint | string | 否 | "" | 方法提示 |
| tags | string[] | 否 | [] | 标签列表，空 tag 自动过滤 |
| source_chunk_ids | int[] | 是 | — | 来源 chunk ID 列表，至少 1 个 |
| confidence | float | 否 | 0.5 | 置信度 [0.0, 1.0] |

**响应** (201)：

```json
{
  "id": 1,
  "paper_id": 1,
  "title": "Efficient Attention for Long Sequences",
  "summary": "Explore sparse attention patterns...",
  "research_question": "Can sparse attention maintain quality?",
  "method_hint": "Compare sparse vs dense attention...",
  "tags": ["attention", "efficiency"],
  "confidence": 0.72,
  "status": "saved",
  "created_at": "2024-01-01T00:00:00",
  "sources": [
    {
      "paper_id": 1,
      "chunk_id": 3,
      "chunk_index": 2,
      "page_start": 3,
      "page_end": 4,
      "text_excerpt": "..."
    }
  ]
}
```

**用户隔离**：Idea 自动绑定当前 user_id；source chunks 必须属于当前 user_id 的论文。

**常见错误**：
- 422 — 参数校验失败（空 title/summary、空 source_chunk_ids、confidence 超范围）
- 400 — paper_id 或 source_chunk_ids 不存在/无效（业务逻辑错误）
- 409 — 同一论文下 Idea 标题重复

**是否依赖真实模型**：否（纯数据操作）

---

### GET /ideas

用途：获取 Idea 列表（当前不支持分页，返回全部 Idea）。

**响应** (200)：

```json
{
  "ideas": [
    {
      "id": 1,
      "paper_id": 1,
      "paper_title": "Attention Is All You Need",
      "title": "Efficient Attention for Long Sequences",
      "summary": "Explore sparse attention patterns...",
      "tags": ["attention", "efficiency"],
      "confidence": 0.72,
      "created_at": "2024-01-01T00:00:00",
      "source_count": 2
    }
  ],
  "total": 5
}
```

**用户隔离**：只返回当前 user_id 的 Idea。

**常见错误**：无

**是否依赖真实模型**：否

---

### GET /ideas/{idea_id}

用途：获取 Idea 详情和来源。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| idea_id | int | Idea ID |

**响应** (200)：

```json
{
  "id": 1,
  "paper_id": 1,
  "title": "Efficient Attention for Long Sequences",
  "summary": "Explore sparse attention patterns...",
  "research_question": "Can sparse attention maintain quality?",
  "method_hint": "Compare sparse vs dense attention...",
  "tags": ["attention", "efficiency"],
  "confidence": 0.72,
  "status": "saved",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "sources": [
    {
      "paper_id": 1,
      "chunk_id": 3,
      "chunk_index": 2,
      "page_start": 3,
      "page_end": 4,
      "text_excerpt": "..."
    }
  ]
}
```

**用户隔离**：只能访问当前 user_id 的 Idea，其他用户 Idea 返回 404。

**常见错误**：404 — Idea 不存在

**是否依赖真实模型**：否

---

### DELETE /ideas/{idea_id}

用途：删除 Idea 及其来源（级联删除）。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| idea_id | int | Idea ID |

**响应** (204)：无内容

**用户隔离**：只能删除当前 user_id 的 Idea。

**常见错误**：404 — Idea 不存在

**是否依赖真实模型**：否

---

## Agent

### POST /agent/run

用途：运行 Agent 工作流。

**请求体**：

```json
{
  "task_type": "recommend_citations_multi",
  "paper_id": null,
  "paper_ids": [1, 2],
  "question": "How can attention improve retrieval?",
  "draft_text": "Recent advances in attention mechanisms..."
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| task_type | string | 是 | — | 任务类型（见下方） |
| paper_id | int | 否 | null | 单论文 ID |
| paper_ids | int[] | 否 | null | 多论文 ID 列表，最多 50 个 |
| question | string | 否 | "" | 问题文本 |
| draft_text | string | 否 | "" | 草稿文本（引用推荐用） |

**task_type 可选值**：

| 值 | 说明 | 必填参数 |
|----|------|---------|
| summarize_paper | 论文总结 | paper_id |
| extract_ideas | Idea 抽取 | paper_id |
| recommend_citations | 单论文引用推荐 | paper_id, draft_text |
| recommend_citations_multi | 多论文/全库引用推荐 | paper_ids 或 null（全库）, draft_text |

**响应** (200)：

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

**Agent 响应契约**：
- `agent_runs.status` 只能是 `"pending"` / `"running"` / `"completed"` / `"failed"`
- `output.rag_status` 只能是 `"answered"` / `"insufficient_context"`
- `recommend_citations_multi` 必须返回带 `paper_title` 的 sources
- `warnings` 由 ReflectionAgent 生成，包含来源支撑不足等提醒
- `confidence` 范围 [0, 1]

**用户隔离**：Agent Run 自动绑定当前 user_id；paper_id / paper_ids 校验归属当前 user_id。

**常见错误**：
- 400 — task_type 不合法或必填参数缺失
- 404 — paper_id 不存在
- 503 — AI provider 不可用或配置错误
- 500 — Agent 执行失败

**是否依赖真实模型**：LLM 生成依赖 provider

---

### GET /agent/runs/{run_id}

用途：获取 Agent 运行详情。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| run_id | string | 运行 ID |

**响应** (200)：

```json
{
  "run_id": "a1b2c3d4e5f67890",
  "task_type": "recommend_citations_multi",
  "status": "completed",
  "paper_id": null,
  "input": { "task_type": "recommend_citations_multi", "paper_ids": [1, 2] },
  "output": { "answer": "...", "sources": [...] },
  "error_message": null,
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00"
}
```

**用户隔离**：只能查询当前 user_id 的 Agent Run，其他用户 Run 返回 404。

**常见错误**：404 — 运行记录不存在

**是否依赖真实模型**：否（纯数据查询）

---

## Usage

### GET /usage/model-calls

用途：查询当前用户的模型调用审计记录。

**查询参数**：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| limit | int | 否 | 50 | 返回数量，范围 [1, 200] |
| operation | string | 否 | null | 过滤操作类型（embedding_chunks / embedding_query / llm_answer / llm_idea_extract / agent_run / eval_case） |
| status | string | 否 | null | 过滤状态（success / failed） |
| provider | string | 否 | null | 过滤 provider（local / openai_compatible） |

**响应** (200)：

```json
{
  "events": [
    {
      "id": 1,
      "operation": "embedding_chunks",
      "provider": "local",
      "model": "local-hash",
      "status": "success",
      "duration_ms": 100,
      "input_count": 5,
      "input_chars": 500,
      "output_chars": 0,
      "error_type": null,
      "error_message": null,
      "metadata_json": "{\"paper_id\": 1, \"chunk_count\": 5}",
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "total": 1
}
```

**用户隔离**：只返回当前 X-User-Id 的审计记录。

**安全保证**：
- 不包含 prompt 全文、chunk 全文、answer 全文
- 不包含 API Key、Authorization、DATABASE_URL
- metadata_json 只保存白名单字段（paper_id, agent_task_type, eval_case_id, chunk_count, query_length, context_count, paper_ids, idea_count）
- error_message 经过脱敏和截断（最大 300 字符）

**Response Schema** (ModelCallListResponse)：

| 字段 | 类型 | 说明 |
|------|------|------|
| events | ModelCallEventItem[] | 审计事件列表 |
| total | int | 返回事件数量 |

ModelCallEventItem 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 事件 ID |
| operation | string | 操作类型 |
| provider | string | 提供商 |
| model | string | 模型名称 |
| status | string | 状态 |
| duration_ms | int | 耗时毫秒 |
| input_count | int | 输入数量 |
| input_chars | int | 输入字符数 |
| output_chars | int | 输出字符数 |
| error_type | string\|null | 错误类型 |
| error_message | string\|null | 脱敏错误信息 |
| metadata_json | string\|null | 白名单元数据 JSON |
| created_at | datetime | 创建时间 |

**常见错误**：422 — limit 超过 200

**是否依赖真实模型**：否（纯数据查询）

---

### GET /usage/model-calls/summary

用途：查询当前用户的模型调用聚合统计。

**查询参数**：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| operation | string | 否 | null | 过滤操作类型 |
| provider | string | 否 | null | 过滤 provider |

**响应** (200)：

```json
{
  "total_calls": 100,
  "success_calls": 95,
  "failed_calls": 5,
  "avg_duration_ms": 150.5,
  "calls_by_operation": {
    "embedding_chunks": 30,
    "embedding_query": 40,
    "llm_answer": 20,
    "llm_idea_extract": 5,
    "agent_run": 5
  },
  "calls_by_provider": {
    "local": 80,
    "openai_compatible": 20
  }
}
```

**用户隔离**：只统计当前 X-User-Id 的审计记录。

**Response Schema** (ModelCallSummaryResponse)：

| 字段 | 类型 | 说明 |
|------|------|------|
| total_calls | int | 总调用数 |
| success_calls | int | 成功调用数 |
| failed_calls | int | 失败调用数 |
| avg_duration_ms | float | 平均耗时毫秒 |
| calls_by_operation | object | 按操作类型分组计数 |
| calls_by_provider | object | 按提供商分组计数 |

**常见错误**：无

**是否依赖真实模型**：否（纯数据查询）

---

### GET /usage/eval-report/latest

用途：读取最新真实模型评测报告的安全摘要。

**查询参数**：无

**响应** (200)：

```json
{
  "timestamp": "2025-05-24T10:00:00+00:00",
  "can_proceed": true,
  "metadata": {
    "llm_model": "gpt-4",
    "embedding_model": "text-embedding-3-small",
    "embedding_dimension": 1536,
    "case_file": ""
  },
  "totals": {
    "total": 5,
    "passed": 4,
    "warning": 1,
    "failed": 0,
    "blocker_failed": 0
  },
  "trend": {
    "previous_report_count": 1,
    "previous_latest_timestamp": "2025-05-23T10:00:00+00:00",
    "passed_delta": 1,
    "warning_delta": 0,
    "failed_delta": -1
  },
  "cases": [
    {
      "case_id": "single_rag_basic",
      "type": "single_rag",
      "severity": "blocker",
      "status": "passed",
      "duration_ms": 1200,
      "warnings": []
    }
  ]
}
```

**404 响应**：报告不存在时返回 `{ "detail": "No eval report found" }`

**Response Schema** (EvalReportSummaryResponse)：

| 字段 | 类型 | 说明 |
|------|------|------|
| timestamp | string | 评测时间 |
| can_proceed | bool | 是否通过（blocker_failed==0） |
| metadata.llm_model | string | LLM 模型名 |
| metadata.embedding_model | string | Embedding 模型名 |
| metadata.embedding_dimension | int | 向量维度 |
| metadata.case_file | string | 固定为空（不暴露路径） |
| totals.total | int | 总用例数 |
| totals.passed | int | 通过数 |
| totals.warning | int | 警告数 |
| totals.failed | int | 失败数 |
| totals.blocker_failed | int | Blocker 失败数 |
| trend.previous_report_count | int | 历史报告数 |
| trend.previous_latest_timestamp | string\|null | 上次报告时间 |
| trend.passed_delta | int | 通过数变化 |
| trend.warning_delta | int | 警告数变化 |
| trend.failed_delta | int | 失败数变化 |
| cases[].case_id | string | 用例 ID |
| cases[].type | string | 用例类型 |
| cases[].severity | string | 严重度 |
| cases[].status | string | 状态 |
| cases[].duration_ms | int | 耗时 |
| cases[].warnings | string[] | 警告列表 |

**安全说明**：
- 不返回 answer_preview、sanitized_preview、checks、confidence、source_count 等大段输出
- 不返回 failed_details
- case_file 固定为空，不暴露文件路径
- 所有字段经过脱敏，不包含 API Key / Authorization / DATABASE_URL
- 只读取固定路径 `artifacts/evals/real_model_eval_latest.json`，不允许路径穿越

**是否依赖真实模型**：否（只读文件）