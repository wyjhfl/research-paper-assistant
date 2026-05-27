import { fetchIdeas, type IdeaListItem } from "@/lib/api";
import { getServerUserId } from "@/lib/server-user";
import Link from "next/link";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import StatusBadge from "@/components/StatusBadge";

export const dynamic = "force-dynamic";

export default async function IdeasPage() {
  let ideas: IdeaListItem[] = [];
  let fetchError = false;
  try {
    const res = await fetchIdeas(await getServerUserId());
    ideas = res.ideas;
  } catch {
    fetchError = true;
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="Idea 列表"
        description={`共 ${ideas.length} 个研究想法`}
        actions={[
          { label: "论文库", href: "/papers", primary: false },
          { label: "Agent 工作流", href: "/agent", primary: false },
        ]}
      />

      {fetchError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-sm text-red-700">无法连接后端服务。</p>
        </div>
      )}

      {!fetchError && ideas.length === 0 && (
        <EmptyState
          icon="💡"
          title="暂无 Idea"
          description="在论文详情页点击「抽取 Idea」从论文中提取研究想法，或运行 Agent extract_ideas 任务"
          actions={[
            { label: "前往论文库", href: "/papers", primary: true },
            { label: "运行 Agent", href: "/agent", primary: false },
          ]}
        />
      )}

      {ideas.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {ideas.map((idea) => (
            <Link
              key={idea.id}
              href={`/ideas/${idea.id}`}
              className="block bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="text-sm font-semibold text-gray-900 line-clamp-2">{idea.title}</h3>
                <StatusBadge status={idea.confidence >= 0.7 ? "answered" : "insufficient_context"} />
              </div>
              <p className="text-xs text-gray-600 line-clamp-2 mb-2">{idea.summary}</p>
              <div className="flex flex-wrap items-center gap-2">
                {idea.tags.slice(0, 3).map((tag) => (
                  <span key={tag} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-50 text-purple-700">
                    {tag}
                  </span>
                ))}
                <span className="text-xs text-gray-400">
                  置信度 {(idea.confidence * 100).toFixed(0)}%
                </span>
                <span className="text-xs text-gray-400">
                  {idea.source_count} 来源
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-2">
                来源: {idea.paper_title}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
