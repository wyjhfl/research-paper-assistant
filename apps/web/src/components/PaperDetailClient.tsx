"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import PageHeader from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import PaperQA from "@/components/PaperQA";
import IdeaExtractor from "@/components/IdeaExtractor";
import RebuildEmbeddingsButton from "@/app/papers/[id]/RebuildEmbeddingsButton";
import { fetchPaper, getErrorMessage, type PaperDetail, type ChunkExcerpt } from "@/lib/api";

interface PaperDetailClientProps {
  paperId: number;
}

export default function PaperDetailClient({ paperId }: PaperDetailClientProps) {
  const [paper, setPaper] = useState<PaperDetail | null>(null);
  const [chunks, setChunks] = useState<ChunkExcerpt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeChunkId, setActiveChunkId] = useState<number | null>(null);
  const [expandedChunkIds, setExpandedChunkIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPaper(paperId)
      .then((res) => {
        if (cancelled) return;
        setPaper(res.paper);
        setChunks(res.chunks);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(getErrorMessage(err, "无法加载论文信息，请确认论文 ID 是否正确。"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [paperId]);

  useEffect(() => {
    function applyHash() {
      const match = window.location.hash.match(/^#chunk-(\d+)$/);
      const nextChunkId = match ? Number(match[1]) : null;
      setActiveChunkId(nextChunkId);
      if (nextChunkId != null) {
        setExpandedChunkIds((prev) => {
          const next = new Set(prev);
          next.add(nextChunkId);
          return next;
        });
        window.setTimeout(() => {
          document.getElementById(`chunk-${nextChunkId}`)?.scrollIntoView({
            block: "center",
            behavior: "smooth",
          });
        }, 80);
      }
    }

    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  function toggleChunkExpanded(chunkId: number) {
    setExpandedChunkIds((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  }

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <PageHeader title="论文详情" />
        <div className="bg-white rounded-lg shadow p-6 animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-64 mb-4" />
          <div className="h-24 bg-gray-200 rounded" />
        </div>
      </div>
    );
  }

  if (error || !paper) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <PageHeader title="论文详情" />
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-700 text-sm">{error ?? "无法加载论文信息，请确认论文 ID 是否正确。"}</p>
          <Link href="/papers" className="inline-block mt-3 text-sm text-blue-600 hover:underline">返回论文库</Link>
        </div>
      </div>
    );
  }

  const hasLongChunks = chunks.some((chunk) => chunk.text.length > 220);

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
        <details open>
          <summary className="px-5 py-4 cursor-pointer hover:bg-gray-50 rounded-xl text-sm font-semibold text-gray-700">
            论文片段 ({chunks.length})
          </summary>
          {chunks.length > 0 && (
            <div className="px-5 pb-3 text-xs text-gray-500">
              片段用于回答和 Idea 抽取。当前仅展示预览，引用来源会显示 chunk 编号和页码。
              {hasLongChunks ? " 较长片段已折叠为三行预览。" : ""}
              {activeChunkId != null ? " 已定位的片段会自动高亮并展开。" : ""}
            </div>
          )}
          <div className="max-h-[34rem] divide-y divide-gray-100 overflow-y-auto">
            {chunks.map((chunk) => {
              const isActive = activeChunkId === chunk.id;
              const isExpanded = expandedChunkIds.has(chunk.id);
              return (
              <div
                key={chunk.id}
                id={`chunk-${chunk.id}`}
                className={`scroll-mt-20 px-5 py-3 transition-colors ${
                  isActive ? "bg-blue-50 ring-1 ring-inset ring-blue-200" : ""
                }`}
              >
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="text-xs font-medium text-gray-500">Chunk #{chunk.chunk_index}</span>
                  <span className="text-xs text-gray-400">第 {chunk.page_start}-{chunk.page_end} 页</span>
                  {chunk.section_title && (
                    <span className="text-xs text-blue-600">{chunk.section_title}</span>
                  )}
                  {isActive && (
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                      当前定位
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => toggleChunkExpanded(chunk.id)}
                    className="ml-auto rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
                  >
                    {isExpanded ? "收起全文" : "展开全文"}
                  </button>
                </div>
                <p className={`text-xs text-gray-600 leading-relaxed ${isExpanded ? "" : "line-clamp-3"}`}>
                  {chunk.text}
                </p>
              </div>
              );
            })}
          </div>
        </details>
      </div>

      <PaperQA paperId={paper.id} />
      <IdeaExtractor paperId={paper.id} />
    </div>
  );
}
