import PageHeader from "@/components/PageHeader";
import AgentRunner from "@/components/AgentRunner";

const TASK_DESCRIPTIONS = [
  { type: "summarize_paper", label: "论文总结", desc: "生成论文的结构化摘要，包含概述、关键点和局限性" },
  { type: "extract_ideas", label: "Idea 抽取", desc: "从论文中提取潜在研究想法" },
  { type: "recommend_citations", label: "引用推荐", desc: "基于单篇论文推荐相关引用" },
  { type: "recommend_citations_multi", label: "多论文引用推荐", desc: "跨论文检索并推荐引用，不填论文则全库检索" },
];

export default function AgentPage() {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="Agent 工作流"
        description="LangGraph StateGraph 编排的多 Agent 协作系统，支持论文总结、Idea 抽取和引用推荐"
        actions={[
          { label: "论文库", href: "/papers", primary: false },
          { label: "跨论文问答", href: "/papers/ask", primary: false },
        ]}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {TASK_DESCRIPTIONS.map((t) => (
          <div key={t.type} className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
            <h3 className="text-sm font-semibold text-gray-800 mb-1">{t.label}</h3>
            <p className="text-xs text-gray-500">{t.desc}</p>
          </div>
        ))}
      </div>

      <AgentRunner />
    </div>
  );
}
