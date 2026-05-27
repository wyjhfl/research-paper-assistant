import Link from "next/link";
import PageHeader from "@/components/PageHeader";

const CAPABILITIES = [
  {
    icon: "📚",
    title: "PDF 上传与论文库",
    description: "上传科研 PDF，自动解析、分块、构建向量索引",
    href: "/papers",
  },
  {
    icon: "💬",
    title: "单论文问答",
    description: "基于论文内容的 RAG 问答，附引用来源与置信度",
    href: "/papers",
  },
  {
    icon: "🔍",
    title: "跨论文问答",
    description: "全库检索或指定论文范围，跨文献回答问题",
    href: "/papers/ask",
  },
  {
    icon: "💡",
    title: "Idea 抽取",
    description: "从论文中提取研究想法、研究问题与方法提示",
    href: "/ideas",
  },
  {
    icon: "🤖",
    title: "Agent 工作流",
    description: "LangGraph 编排的多 Agent 协作：总结、Idea、引用推荐",
    href: "/agent",
  },
  {
    icon: "🔧",
    title: "MCP 工具",
    description: "Model Context Protocol 工具集，支持外部集成",
    href: "/mcp",
  },
  {
    icon: "📊",
    title: "真实模型评测",
    description: "eval_real_model.py 脚本验证真实 LLM + Embedding 质量",
    href: "",
  },
];

const QUICK_START = [
  { label: "上传论文", href: "/papers", primary: true },
  { label: "跨论文问答", href: "/papers/ask", primary: true },
  { label: "运行 Agent", href: "/agent", primary: false },
];

export default function HomePage() {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="多 Agent 科研论文助手"
        description="上传 PDF、构建论文记忆、RAG 问答、Idea 抽取、Agent 引用推荐 — 一站式科研辅助平台"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {CAPABILITIES.map((cap) => {
          const inner = (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow h-full">
              <div className="text-2xl mb-2">{cap.icon}</div>
              <h3 className="text-sm font-semibold text-gray-900 mb-1">{cap.title}</h3>
              <p className="text-xs text-gray-500 leading-relaxed">{cap.description}</p>
            </div>
          );
          return cap.href ? (
            <Link key={cap.title} href={cap.href} className="block">
              {inner}
            </Link>
          ) : (
            <div key={cap.title}>{inner}</div>
          );
        })}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-base font-semibold text-gray-800 mb-3">快速开始</h2>
        <div className="flex flex-wrap gap-3">
          {QUICK_START.map((qs) => (
            <Link
              key={qs.href + qs.label}
              href={qs.href}
              className={`inline-flex items-center px-5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                qs.primary
                  ? "bg-blue-600 text-white hover:bg-blue-700"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              {qs.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
