import PageHeader from "@/components/PageHeader";

const MCP_TOOLS = [
  {
    name: "search_papers",
    description: "按关键词搜索论文库，匹配标题或文件名",
    input: "query, limit?",
    output: "papers[] (paper_id, title, filename, status, chunk_count, created_at)",
  },
  {
    name: "get_paper_summary",
    description: "获取单篇论文的结构化摘要",
    input: "paper_id",
    output: "summary, confidence",
  },
  {
    name: "search_ideas",
    description: "按关键词搜索 Idea 库，匹配标题、摘要或标签",
    input: "query, limit?",
    output: "ideas[] (idea_id, title, summary, paper_id, tags, confidence, source_count)",
  },
  {
    name: "recommend_citations",
    description: "基于草稿文本推荐引用，支持单论文/多论文/全库检索",
    input: "draft_text, paper_id?, paper_ids?, limit?",
    output: "answer, rag_status, confidence, sources[]",
  },
  {
    name: "search_paper_chunks",
    description: "向量检索论文片段，返回最相关的 chunks",
    input: "query, paper_ids?, limit?",
    output: "results[] (paper_id, paper_title, chunk_id, page, text_excerpt, score)",
  },
  {
    name: "save_research_idea",
    description: "保存研究想法到 Idea 库，关联来源论文",
    input: "title, summary, tags, source_paper_ids",
    output: "idea_id, title, paper_id, sources[]",
  },
];

export default function McpPage() {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="MCP 工具"
        description="Model Context Protocol 工具集 — 外部 AI 客户端通过 MCP 协议访问论文库与 Idea 库的接口，不等同于 Web API 全量映射"
        actions={[
          { label: "论文库", href: "/papers", primary: false },
          { label: "Agent 工作流", href: "/agent", primary: false },
        ]}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {MCP_TOOLS.map((tool) => (
          <div key={tool.name} className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-1 font-mono">{tool.name}</h3>
            <p className="text-xs text-gray-600 mb-3">{tool.description}</p>
            <div className="space-y-1">
              <div className="flex items-start gap-2">
                <span className="text-xs font-medium text-gray-500 shrink-0">输入</span>
                <span className="text-xs text-gray-700 font-mono">{tool.input}</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-xs font-medium text-gray-500 shrink-0">输出</span>
                <span className="text-xs text-gray-700 font-mono">{tool.output}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 space-y-3">
        <h3 className="text-sm font-semibold text-gray-800">启动方式</h3>
        <pre className="text-xs bg-gray-50 p-3 rounded-md overflow-x-auto">
{`# Docker 环境
docker compose exec backend python run_mcp.py

# 本地环境
cd apps/api
python run_mcp.py`}
        </pre>
        <h3 className="text-sm font-semibold text-gray-800 pt-2">安全注意事项</h3>
        <ul className="list-disc list-inside text-xs text-gray-600 space-y-1">
          <li>MCP 服务器需要后端数据库服务运行</li>
          <li>工具调用不暴露 API Key、DATABASE_URL 或文件路径</li>
          <li>search_paper_chunks 返回结果不包含 file_path</li>
        </ul>
      </div>
    </div>
  );
}
