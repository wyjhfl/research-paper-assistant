# MCP Contract — MCP Tools

MCP Server 使用 stdio transport，通过 FastMCP 框架暴露 6 个工具。

启动命令：
- Docker：`docker compose exec backend python run_mcp.py`
- 本地：`cd apps/api && python run_mcp.py`

## 用户隔离

MCP Server 使用 stdio transport，无法接收 HTTP header 或 browser cookie。采用兼容策略：

- 所有 MCP tools 增加可选 `user_id` 参数，默认值为 `"default"`
- 不传 `user_id` 时行为与旧版完全一致，不破坏现有调用
- 传入 `user_id` 时，所有数据查询按该 user_id 隔离
- `user_id` 格式要求：1-64 字符，仅允许字母、数字、下划线、短横线、点号

### 认证边界说明

- Web REST API 使用 session cookie 认证（`AUTH_ENABLED=true` 时强制）
- MCP stdio 场景无 browser cookie，仍通过显式 `user_id` 参数隔离
- MCP token 认证不在本阶段实现，未来可考虑 API Key / Bearer token 绑定
- 生产环境中，MCP 调用者应确保 `user_id` 参数正确，避免跨用户数据泄露

---

## search_papers

用途：按关键词搜索论文库，匹配标题或文件名。

| 属性 | 值 |
|------|---|
| 只读 | 是 |
| 允许无 paper_id 全库检索 | 是（默认全库） |

**输入**：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| query | string | 是 | — | 搜索关键词 |
| limit | int | 否 | 10 | 返回数量上限 |
| user_id | string | 否 | "default" | 用户标识，用于数据隔离 |

**输出**：

```json
{
  "papers": [
    {
      "paper_id": 1,
      "title": "Attention Is All You Need",
      "filename": "sample.pdf",
      "status": "completed",
      "chunk_count": 12,
      "created_at": "2024-01-01T00:00:00"
    }
  ]
}
```

**限制条件**：limit 上限 20

**错误格式**：`{"error": "description"}`

---

## get_paper_summary

用途：获取单篇论文的结构化摘要。

| 属性 | 值 |
|------|---|
| 只读 | 是 |
| 允许无 paper_id 全库检索 | 否（paper_id 必填） |

**输入**：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| paper_id | int | 是 | — | 论文 ID |
| user_id | string | 否 | "default" | 用户标识，用于数据隔离 |

**输出**：

```json
{
  "summary": "This paper introduces the Transformer architecture...",
  "confidence": 0.85
}
```

**限制条件**：论文必须存在且 status 为 completed

**错误格式**：`{"error": "Paper not found"}` 或 `{"error": "Paper X is not ready (status=...)"}`

---

## search_ideas

用途：按关键词搜索 Idea 库，匹配标题、摘要或标签。

| 属性 | 值 |
|------|---|
| 只读 | 是 |
| 允许无 paper_id 全库检索 | 是（默认全库） |

**输入**：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| query | string | 是 | — | 搜索关键词 |
| limit | int | 否 | 10 | 返回数量上限 |
| user_id | string | 否 | "default" | 用户标识，用于数据隔离 |

**输出**：

```json
{
  "ideas": [
    {
      "idea_id": 1,
      "title": "Efficient Attention for Long Sequences",
      "summary": "Explore sparse attention patterns...",
      "paper_id": 1,
      "tags": ["attention", "efficiency"],
      "confidence": 0.72,
      "source_count": 2
    }
  ]
}
```

**限制条件**：limit 上限 20

**错误格式**：`{"error": "description"}`

---

## recommend_citations

用途：基于草稿文本推荐引用，支持单论文/多论文/全库检索。

| 属性 | 值 |
|------|---|
| 只读 | 是 |
| 允许无 paper_id 全库检索 | 是（paper_id 和 paper_ids 都为空时全库检索） |

**输入**：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| draft_text | string | 是 | — | 草稿文本 |
| paper_id | int | 否 | null | 单论文 ID |
| paper_ids | int[] | 否 | null | 多论文 ID 列表，最多 50 个 |
| limit | int | 否 | 8 | 推荐数量上限 |
| user_id | string | 否 | "default" | 用户标识，用于数据隔离 |

**输出**：

```json
{
  "answer": "Based on the draft, consider citing...",
  "rag_status": "answered",
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
      "score": 0.82
    }
  ]
}
```

**限制条件**：
- draft_text 不能为空
- paper_id 优先于 paper_ids：paper_id 非空时走单论文模式；paper_id 为空且 paper_ids 非空时走多论文模式；二者都为空时全库检索
- limit 上限 10

**错误格式**：`{"error": "description"}`

---

## search_paper_chunks

用途：向量检索论文片段，返回最相关的 chunks。

| 属性 | 值 |
|------|---|
| 只读 | 是 |
| 允许无 paper_id 全库检索 | 是（paper_ids 为空时全库检索） |

**输入**：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| query | string | 是 | — | 检索查询 |
| paper_ids | int[] | 否 | null | 限定论文列表，最多 50 个 |
| limit | int | 否 | 10 | 返回数量上限 |
| user_id | string | 否 | "default" | 用户标识，用于数据隔离 |

**输出**：

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

**限制条件**：
- query 不能为空
- limit 上限 20

**错误格式**：`{"error": "description"}`

---

## save_research_idea

用途：保存研究想法到 Idea 库，关联来源论文。

| 属性 | 值 |
|------|---|
| 只读 | 否（写入操作） |
| 允许无 paper_id 全库检索 | 不适用 |

**输入**：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| title | string | 是 | — | Idea 标题 |
| summary | string | 是 | — | Idea 摘要 |
| tags | string[] | 是 | — | 标签列表 |
| source_paper_ids | int[] | 是 | — | 来源论文 ID 列表 |
| user_id | string | 否 | "default" | 用户标识，用于数据隔离 |

**输出**：

```json
{
  "idea_id": 1,
  "title": "Efficient Attention for Long Sequences",
  "paper_id": 1,
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

**限制条件**：
- title 和 summary 不能为空
- title 长度上限 120 字符，summary 长度上限 1000 字符
- tags 最多 10 个
- source_paper_ids 必须正好包含 1 个 paper_id（MCP v1 只支持单论文来源），多个返回 validation_error
- 所有 source_paper_ids 必须存在

**错误格式**：`{"error": "Paper not found: 99"}`

---

## 通用错误格式

所有 MCP tools 在出错时返回：

```json
{
  "error": "Human-readable error description"
}
```

常见错误码场景：
- 参数缺失或类型错误
- paper_id / idea_id 不存在
- 数据库连接失败
- LLM 调用失败（provider 不可用）
