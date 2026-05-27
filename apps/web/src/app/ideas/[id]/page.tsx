import { fetchIdea } from "@/lib/api";
import { getServerUserId } from "@/lib/server-user";
import Link from "next/link";
import PageHeader from "@/components/PageHeader";
import IdeaDetailClient from "@/components/IdeaDetailClient";

export const dynamic = "force-dynamic";

interface IdeaDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function IdeaDetailPage({ params }: IdeaDetailPageProps) {
  const { id } = await params;
  let idea = null;
  let error = false;

  try {
    idea = await fetchIdea(parseInt(id, 10), await getServerUserId());
  } catch {
    error = true;
  }

  if (error || !idea) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <PageHeader title="Idea 详情" />
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-700 text-sm">无法加载 Idea 信息。</p>
          <Link href="/ideas" className="inline-block mt-3 text-sm text-blue-600 hover:underline">返回 Idea 列表</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title={idea.title}
        actions={[
          { label: "返回列表", href: "/ideas", primary: false },
          { label: "来源论文", href: `/papers/${idea.paper_id}`, primary: false },
        ]}
      />

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 mb-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex-1">
            <p className="text-sm text-gray-800 leading-relaxed mb-3">{idea.summary}</p>
            <div className="space-y-2">
              <div>
                <span className="text-xs font-medium text-gray-500">研究问题</span>
                <p className="text-sm text-gray-700">{idea.research_question}</p>
              </div>
              <div>
                <span className="text-xs font-medium text-gray-500">方法提示</span>
                <p className="text-sm text-gray-700">{idea.method_hint}</p>
              </div>
            </div>
          </div>
          <IdeaDetailClient ideaId={idea.id} />
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-gray-100">
          {idea.tags.map((tag) => (
            <span key={tag} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-50 text-purple-700">
              {tag}
            </span>
          ))}
          <span className="text-xs text-gray-400">置信度 {(idea.confidence * 100).toFixed(0)}%</span>
          <span className="text-xs text-gray-400">创建于 {new Date(idea.created_at).toLocaleString("zh-CN")}</span>
        </div>
      </div>

      {idea.sources && idea.sources.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">引用来源 ({idea.sources.length})</h3>
          <div className="space-y-3">
            {idea.sources.map((source, idx) => (
              <div key={source.chunk_id} className="p-3 border border-gray-200 rounded-lg">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-gray-500">#{idx + 1}</span>
                  <span className="text-xs text-gray-400">Chunk #{source.chunk_index}</span>
                  <span className="text-xs text-gray-400">第 {source.page_start}–{source.page_end} 页</span>
                </div>
                <p className="text-xs text-gray-600 leading-relaxed">{source.text_excerpt}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
