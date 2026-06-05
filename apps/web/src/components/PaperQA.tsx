"use client";

import { useState } from "react";
import { askPaper, getErrorMessage, type AskResponse, type SourceItem } from "@/lib/api";

const EVIDENCE_GATE_REASON_MAP: Record<string, string> = {
  score_below_threshold: "检索得分低于阈值",
  evidence_below_threshold: "词汇证据不足",
  no_query_tokens: "问题关键词不足",
  no_chunks: "论文无文本片段",
  no_embeddings: "文本片段未生成向量索引",
  no_retrieved: "未检索到相关片段",
  no_lexical_match: "关键词无匹配",
  llm_failed: "AI 服务暂时不可用",
};

const RETRIEVAL_MODE_MAP: Record<string, string> = {
  vector: "向量",
  lexical: "关键词",
  hybrid: "混合",
};

function translateGateReason(reason?: string): string | null {
  if (!reason) return null;
  return EVIDENCE_GATE_REASON_MAP[reason] ?? reason;
}

interface PaperQAProps {
  paperId: number;
}

export default function PaperQA({ paperId }: PaperQAProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [allowLowConfidence, setAllowLowConfidence] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await askPaper(paperId, question, allowLowConfidence);
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
        <label className="flex items-center gap-2 mt-3 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={allowLowConfidence}
            onChange={(e) => setAllowLowConfidence(e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <span className="text-sm text-gray-600">允许低置信度回答</span>
        </label>
      </form>

      {error && (
        <div className="mx-6 mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {result && (
        <div className="px-6 pb-6">
          <div className="mb-4 p-4 bg-gray-50 rounded-lg">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                  result.status === "answered"
                    ? "bg-green-100 text-green-700"
                    : result.status === "low_confidence_answer"
                      ? "bg-amber-100 text-amber-700"
                      : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {result.status === "answered"
                  ? "已回答"
                  : result.status === "low_confidence_answer"
                    ? "低置信度回答"
                    : "上下文不足"}
              </span>
              <span className="text-xs text-gray-500">
                置信度: {(result.confidence * 100).toFixed(1)}%
              </span>
              <span className="text-xs text-gray-500">
                来源: {result.sources.length}
              </span>
              {result.top_source_score != null && (
                <span className="text-xs text-gray-500">
                  最高相关度: {(result.top_source_score * 100).toFixed(1)}%
                </span>
              )}
            </div>

            {result.status === "low_confidence_answer" && (
              <div className="mb-2 p-3 bg-amber-50 border border-amber-300 rounded-md">
                <p className="text-sm font-medium text-amber-800">
                  警告：低置信度回答，仅供参考
                </p>
              </div>
            )}

            <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {result.answer}
            </p>

            {result.status === "insufficient_context" && (
              <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                <p className="text-sm text-yellow-700 font-medium">
                  检索到了 {result.retrieved_source_count ?? result.sources.length} 个片段，但置信度低于阈值
                </p>
                {translateGateReason(result.evidence_gate_reason) && (
                  <p className="text-sm text-yellow-600 mt-1">
                    原因：{translateGateReason(result.evidence_gate_reason)}
                  </p>
                )}
                <div className="mt-2 text-sm text-yellow-600">
                  <p className="font-medium">建议：</p>
                  <ul className="list-disc list-inside mt-1 space-y-0.5">
                    <li>换更具体的问题</li>
                    <li>上传完整论文</li>
                    <li>尝试低置信度回答</li>
                    <li>后续接入真实 embedding</li>
                  </ul>
                </div>
              </div>
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
                      {source.retrieval_mode && (
                        <span className="text-xs text-gray-400">
                          检索: {RETRIEVAL_MODE_MAP[source.retrieval_mode] ?? source.retrieval_mode}
                        </span>
                      )}
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
