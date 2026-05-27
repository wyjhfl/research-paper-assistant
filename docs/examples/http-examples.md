# HTTP 请求示例

Base URL: `http://localhost:8091`

所有示例不含真实 API Key。paper_id 使用占位符 `1`，文件上传使用 `sample.pdf` 占位。

所有 REST API 支持可选的 `X-User-Id` 请求头（默认 `"default"`），用于轻量多用户数据隔离。详见 [API_CONTRACT.md](../API_CONTRACT.md)。

---

## 1. 上传 PDF

```bash
curl -X POST http://localhost:8091/papers/upload \
  -F "file=@sample.pdf"
```

响应：

```json
{
  "id": 1,
  "title": "Attention Is All You Need",
  "filename": "sample.pdf",
  "status": "completed",
  "chunk_count": 12
}
```

---

## 2. 单论文问答

```bash
curl -X POST http://localhost:8091/papers/1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What problem does attention solve?"}'
```

响应：

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

---

## 3. 跨论文问答

```bash
curl -X POST http://localhost:8000/papers/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How can RAG and multi-agent workflows support research?",
    "paper_ids": [1, 2],
    "top_k": 8
  }'
```

响应：

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

---

## 4. 纯 chunk 检索

```bash
curl -X POST http://localhost:8091/papers/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "transformer architecture",
    "paper_ids": [1],
    "top_k": 10
  }'
```

响应：

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

---

## 5. Idea 抽取

```bash
curl -X POST http://localhost:8091/papers/1/ideas/extract
```

响应：

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

---

## 6. 保存 Idea

```bash
curl -X POST http://localhost:8091/ideas \
  -H "Content-Type: application/json" \
  -d '{
    "paper_id": 1,
    "title": "Efficient Attention for Long Sequences",
    "summary": "Explore sparse attention patterns...",
    "research_question": "Can sparse attention maintain quality?",
    "method_hint": "Compare sparse vs dense attention...",
    "tags": ["attention", "efficiency"],
    "source_chunk_ids": [3, 5],
    "confidence": 0.72
  }'
```

响应 (201)：

```json
{
  "id": 1,
  "paper_id": 1,
  "title": "Efficient Attention for Long Sequences",
  "summary": "Explore sparse attention patterns...",
  "confidence": 0.72,
  "status": "saved",
  "created_at": "2024-01-01T00:00:00",
  "sources": [...]
}
```

---

## 7. Agent recommend_citations_multi

```bash
curl -X POST http://localhost:8091/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "recommend_citations_multi",
    "paper_ids": [1, 2],
    "draft_text": "Recent advances in attention mechanisms have shown promise for improving retrieval tasks."
  }'
```

响应：

```json
{
  "run_id": "a1b2c3d4e5f67890",
  "status": "completed",
  "task_type": "recommend_citations_multi",
  "output": {
    "answer": "Consider citing the following...",
    "rag_status": "answered",
    "sources": [
      {
        "paper_id": 1,
        "paper_title": "Attention Is All You Need",
        "chunk_id": 5,
        "text_excerpt": "...",
        "score": 0.82
      }
    ]
  },
  "warnings": [],
  "confidence": 0.85
}
```

---

## 8. MCP 启动命令和调用说明

### Docker 环境

```bash
docker compose exec backend python run_mcp.py
```

### 本地环境

```bash
cd apps/api
python run_mcp.py
```

### 调用说明

MCP Server 使用 stdio transport，不暴露 HTTP 端口。外部 AI 客户端（如 Claude Desktop、Cursor）通过 MCP 协议连接：

1. 配置 MCP 客户端指向 `python run_mcp.py` 命令
2. 客户端通过 stdio 发送 JSON-RPC 请求
3. Server 返回工具调用结果

可用工具：`search_papers`, `get_paper_summary`, `search_ideas`, `recommend_citations`, `search_paper_chunks`, `save_research_idea`

详见 [MCP_CONTRACT.md](../MCP_CONTRACT.md)。

---

## 9. 带 X-User-Id 的请求示例

以下示例展示如何使用 `X-User-Id` header 进行多用户数据隔离：

### 上传论文到指定用户

```bash
curl -X POST http://localhost:8091/papers/upload \
  -H "X-User-Id: alice" \
  -F "file=@sample.pdf"
```

### 查询指定用户的论文列表

```bash
curl http://localhost:8091/papers \
  -H "X-User-Id: alice"
```

### 指定用户的单论文问答

```bash
curl -X POST http://localhost:8091/papers/1/ask \
  -H "Content-Type: application/json" \
  -H "X-User-Id: alice" \
  -d '{"question": "What problem does attention solve?"}'
```

> 不传 `X-User-Id` 时默认使用 `"default"` 用户，兼容单用户模式。