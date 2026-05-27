"use client";

import { useState } from "react";
import { askPaper, getErrorMessage, type AskResponse, type SourceItem } from "@/lib/api";

interface PaperQAProps {
  paperId: number;
}

export default function PaperQA({ paperId }: PaperQAProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await askPaper(paperId, question);
      setResult(res);
    } catch (err) {
      setError(getErrorMessage(err, "问答请求失败"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-lg shadow mt-6">
      <div className="px-6 py-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-700">论文问答</h2>
      </div>

      <form onSubmit={handleSubmit} className="px-6 py-4">
        <div className="flex gap-3">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="输入关于这篇论文的问题..."
            className="flex-1 rounded-lg border border-gray-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "思考中..." : "提问"}
          </button>
        </div>
      </form>

      {error && (
        <div className="mx-6 mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {result && (
        <div className="px-6 pb-6">
          <div className="mb-4 p-4 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                  result.status === "answered"
                    ? "bg-green-100 text-green-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {result.status === "answered" ? "已回答" : "上下文不足"}
              </span>
              {result.status === "answered" && (
                <span className="text-xs text-gray-500">
                  置信度: {(result.confidence * 100).toFixed(1)}%
                </span>
              )}
            </div>
            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {result.answer}
            </p>
            {result.status === "insufficient_context" && (
              <p className="mt-2 text-xs text-yellow-600">
                当前论文片段不足以回答，不生成无依据答案。
              </p>
            )}
          </div>

          {result.sources.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-600 mb-2">
                引用来源 ({result.sources.length})
              </h3>
              <div className="space-y-2">
                {result.sources.map((source: SourceItem, idx: number) => (
                  <div
                    key={source.chunk_id}
                    className="p-3 border border-gray-200 rounded-md"
                  >
                    <div className="flex items-center gap-3 mb-1">
                      <span className="text-xs font-medium text-gray-500">
                        #{idx + 1}
                      </span>
                      <span className="text-xs text-gray-400">
                        Chunk #{source.chunk_index}
                      </span>
                      <span className="text-xs text-gray-400">
                        第 {source.page_start} 页
                        {source.page_start !== source.page_end
                          ? ` - 第 ${source.page_end} 页`
                          : ""}
                      </span>
                      <span className="text-xs font-medium text-blue-600">
                        相关度: {(source.score * 100).toFixed(1)}%
                      </span>
                    </div>
                    <p className="text-xs text-gray-600 leading-relaxed">
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
