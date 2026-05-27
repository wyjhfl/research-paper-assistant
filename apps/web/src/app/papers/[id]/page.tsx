import { fetchPaper } from "@/lib/api";
import { getServerUserId } from "@/lib/server-user";
import Link from "next/link";
import PageHeader from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import PaperQA from "@/components/PaperQA";
import IdeaExtractor from "@/components/IdeaExtractor";
import RebuildEmbeddingsButton from "./RebuildEmbeddingsButton";

export const dynamic = "force-dynamic";

interface PaperDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function PaperDetailPage({ params }: PaperDetailPageProps) {
  const { id } = await params;
  let paper = null;
  let chunks: Array<{
    id: number;
    chunk_index: number;
    text: string;
    page_start: number;
    page_end: number;
    section_title: string | null;
  }> = [];
  let error = false;

  try {
    const res = await fetchPaper(parseInt(id, 10), await getServerUserId());
    paper = res.paper;
    chunks = res.chunks;
  } catch {
    error = true;
  }

  if (error || !paper) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <PageHeader title="论文详情" />
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-700 text-sm">无法加载论文信息，请确认论文 ID 是否正确。</p>
          <Link href="/papers" className="inline-block mt-3 text-sm text-blue-600 hover:underline">返回论文库</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title={paper.title}
        actions={[
          { label: "返回论文库", href: "/papers", primary: false },
          { label: "跨论文问答", href: "/papers/ask", primary: true },
        ]}
      />

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 mb-6">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500 text-xs">文件名</span>
            <p className="font-medium text-gray-800 truncate">{paper.filename}</p>
          </div>
          <div>
            <span className="text-gray-500 text-xs">状态</span>
            <div className="mt-0.5"><StatusBadge status={paper.status} /></div>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Chunks</span>
            <p className="font-medium text-gray-800">{paper.chunk_count}</p>
          </div>
          <div>
            <span className="text-gray-500 text-xs">上传时间</span>
            <p className="font-medium text-gray-800">{new Date(paper.created_at).toLocaleString("zh-CN")}</p>
          </div>
        </div>
        {paper.error_message && (
          <div className="mt-3 p-3 bg-red-50 rounded-md">
            <p className="text-xs text-red-700">{paper.error_message}</p>
          </div>
        )}
        <div className="mt-3">
          <RebuildEmbeddingsButton paperId={paper.id} />
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 mb-6">
        <details>
          <summary className="px-5 py-4 cursor-pointer hover:bg-gray-50 rounded-xl text-sm font-semibold text-gray-700">
            论文片段 ({chunks.length})
          </summary>
          <div className="divide-y divide-gray-100">
            {chunks.map((chunk) => (
              <div key={chunk.id} className="px-5 py-3">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-gray-500">Chunk #{chunk.chunk_index}</span>
                  <span className="text-xs text-gray-400">第 {chunk.page_start}–{chunk.page_end} 页</span>
                  {chunk.section_title && (
                    <span className="text-xs text-blue-600">{chunk.section_title}</span>
                  )}
                </div>
                <p className="text-xs text-gray-600 leading-relaxed line-clamp-3">{chunk.text}</p>
              </div>
            ))}
          </div>
        </details>
      </div>

      <PaperQA paperId={paper.id} />
      <IdeaExtractor paperId={paper.id} />
    </div>
  );
}
