"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  multiPaperAsk,
  fetchPapers,
  getErrorMessage,
  type MultiPaperAskResponse,
  type MultiPaperSourceItem,
  type PaperListItem,
} from "@/lib/api";

export default function MultiPaperQA() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MultiPaperAskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [papers, setPapers] = useState<PaperListItem[]>([]);
  const [papersLoading, setPapersLoading] = useState(true);
  const [papersError, setPapersError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    fetchPapers()
      .then((res) => setPapers(res.papers.filter((p) => p.status === "completed")))
      .catch((err) => setPapersError(getErrorMessage(err, "加载论文列表失败")))
      .finally(() => setPapersLoading(false));
  }, []);

  function togglePaper(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const ids = selectedIds.size > 0 ? Array.from(selectedIds) : undefined;
      const res = await multiPaperAsk(question, ids);
      setResult(res);
    } catch (err) {
      setError(getErrorMessage(err, "问答请求失败"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-4 sm:px-6 py-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-700">跨论文问答</h2>
        <p className="text-sm text-gray-500 mt-2 leading-relaxed">
          全库检索：不选择论文时，系统在所有已完成论文中检索相关片段。指定论文：选择特定论文后，检索范围限定在这些论文内。
        </p>
      </div>

      <div className="px-4 sm:px-6 py-3 border-b border-gray-100">
        {papersLoading ? (
          <div className="flex items-center gap-3 py-4">
            <svg
              className="animate-spin h-4 w-4 text-blue-600"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm text-gray-500">正在加载论文列表...</span>
          </div>
        ) : papersError ? (
          <div className="text-center py-4">
            <p className="text-sm text-red-600">{papersError}</p>
            <Link
              href="/papers"
              className="inline-block mt-2 text-sm text-blue-600 hover:text-blue-700 underline"
            >
              前往论文库
            </Link>
          </div>
        ) : papers.length > 0 ? (
          <>
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-gray-600">
                已选择 {selectedIds.size} 篇论文
              </p>
              {selectedIds.size > 0 && (
                <button
                  type="button"
                  onClick={clearSelection}
                  className="text-xs text-gray-500 hover:text-red-500 transition-colors"
                >
                  清空选择
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {papers.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => togglePaper(p.id)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                    selectedIds.has(p.id)
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white text-gray-600 border-gray-300 hover:border-blue-400"
                  }`}
                >
                  {p.title.length > 30 ? p.title.slice(0, 30) + "…" : p.title}
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="text-center py-4">
            <p className="text-sm text-gray-500">暂无已完成的论文</p>
            <Link
              href="/papers"
              className="inline-block mt-2 text-sm text-blue-600 hover:text-blue-700 underline"
            >
              前往上传
            </Link>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="px-4 sm:px-6 py-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="输入跨论文问题..."
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            提问
          </button>
        </div>
      </form>

      {loading && (
        <div className="px-4 sm:px-6 pb-6">
          <div className="flex items-center gap-3 p-4 bg-blue-50 rounded-lg">
            <svg
              className="animate-spin h-5 w-5 text-blue-600"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <span className="text-sm text-blue-700">正在检索并生成回答...</span>
          </div>
        </div>
      )}

      {error && (
        <div className="mx-4 sm:mx-6 mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {result && (
        <div className="px-4 sm:px-6 pb-6">
          <div className="mb-4 p-4 bg-gray-50 rounded-lg">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span
                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  result.status === "answered"
                    ? "bg-green-100 text-green-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {result.status === "answered" ? "已回答" : "上下文不足"}
              </span>
              <span className="text-sm text-gray-500">
                置信度: {(result.confidence * 100).toFixed(1)}%
              </span>
            </div>
            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {result.answer}
            </p>
            {result.status === "insufficient_context" && (
              <p className="mt-3 text-sm text-yellow-600 font-medium">
                当前论文片段不足以回答该问题，系统拒绝生成无依据答案。
              </p>
            )}
          </div>

          {result.sources.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-600 mb-3">
                引用来源 ({result.sources.length})
              </h3>
              <div className="space-y-3">
                {result.sources.map((source: MultiPaperSourceItem, idx: number) => (
                  <div
                    key={source.chunk_id}
                    className="p-3 sm:p-4 border border-gray-200 rounded-lg"
                  >
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      <span className="text-xs font-medium text-gray-400">
                        #{idx + 1}
                      </span>
                      <span className="text-sm font-bold text-blue-600">
                        {source.paper_title}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-2 text-xs text-gray-500">
                      <span>第 {source.page_start}–{source.page_end} 页</span>
                      <span>片段 #{source.chunk_index}</span>
                      <span className="font-medium text-blue-600">
                        相关度: {(source.score * 100).toFixed(1)}%
                      </span>
                    </div>
                    <p className="text-xs text-gray-600 leading-relaxed line-clamp-4">
                      {source.text_excerpt}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
