"use client";

import { useState } from "react";
import {
  askPaper,
  createResearchNote,
  getErrorMessage,
  SINGLE_PAPER_QUESTION_PRESETS,
  type AskResponse,
} from "@/lib/api";
import EvidenceSourcesPanel from "@/components/EvidenceSourcesPanel";

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

const FOLLOW_UPS = [
  "What evidence supports this answer?",
  "What are the limitations of this method?",
  "How can this idea be extended in future work?",
];

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
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);

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

  async function copyAnswer() {
    if (!result?.answer) return;
    try {
      const sourceLines = result.sources.map(
        (source, idx) =>
          `[${idx + 1}] Chunk #${source.chunk_index}, page ${source.page_start}-${source.page_end}, score ${(source.score * 100).toFixed(1)}%`,
      );
      const text = [
        result.answer,
        "",
        "Sources:",
        ...(sourceLines.length > 0 ? sourceLines : ["No sources returned."]),
      ].join("\n");
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("复制失败，请手动选择回答内容复制");
    }
  }

  async function saveAnswerNote() {
    if (!result?.answer) return;
    try {
      await createResearchNote({
        title: `单论文问答：${question.slice(0, 80) || `Paper ${paperId}`}`,
        content: result.answer,
        note_type: "qa_answer",
        paper_id: paperId,
        chunk_id: result.sources[0]?.chunk_id ?? null,
        source: result.sources[0]
          ? {
              paper_id: paperId,
              chunk_id: result.sources[0].chunk_id,
              chunk_index: result.sources[0].chunk_index,
              page_start: result.sources[0].page_start,
              page_end: result.sources[0].page_end,
              score: result.sources[0].score,
              retrieval_mode: result.sources[0].retrieval_mode,
              source_kind: "qa_answer",
            }
          : { paper_id: paperId, source_kind: "qa_answer" },
        tags: ["qa"],
      });
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1600);
    } catch (err) {
      setError(getErrorMessage(err, "保存回答到笔记失败"));
    }
  }

  return (
    <div className="bg-white rounded-lg shadow mt-6">
      <div className="px-6 py-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-700">论文问答</h2>
        <p className="mt-1 text-xs text-gray-500">
          建议优先用英文提问；当前本地 embedding 会结合关键词检索，英文关键词匹配更稳定。
        </p>
      </div>

      <form onSubmit={handleSubmit} className="px-6 py-4">
        <div className="mb-3">
          <p className="mb-2 text-xs font-medium text-gray-500">常用问题模板</p>
          <div className="flex flex-wrap gap-2">
            {SINGLE_PAPER_QUESTION_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => setQuestion(preset.question)}
                title={preset.hint}
                className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
                disabled={loading}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
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
        <p className="mt-1 text-xs text-gray-400">
          如果 strict 模式提示上下文不足，可开启该选项查看带来源的尝试性回答。
        </p>
      </form>

      {error && (
        <div className="mx-6 mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {result && (
        <>
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
              {result.answer && (
                <>
                  <button
                    type="button"
                    onClick={copyAnswer}
                    className="ml-auto rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
                  >
                    {copied ? "已复制" : "复制回答"}
                  </button>
                  <button
                    type="button"
                    onClick={saveAnswerNote}
                    className="rounded border border-blue-200 bg-white px-2 py-1 text-xs text-blue-600 hover:bg-blue-50"
                  >
                    {saved ? "已保存" : "存为笔记"}
                  </button>
                </>
              )}
            </div>

            {result.status === "low_confidence_answer" && (
              <div className="mb-2 p-3 bg-amber-50 border border-amber-300 rounded-md">
                <p className="text-sm font-medium text-amber-800">
                  警告：低置信度回答，仅供参考
                </p>
              </div>
            )}

            {result.query_expansion_applied && (
              <div className="mb-2 p-2 bg-blue-50 border border-blue-200 rounded-md">
                <p className="text-xs text-blue-700">
                  已启用关键词扩展
                  {result.expanded_query_terms && result.expanded_query_terms.length > 0 && (
                    <> - 扩展词：{result.expanded_query_terms.slice(0, 8).join(", ")}</>
                  )}
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

            <EvidenceSourcesPanel sources={result.sources} fallbackPaperId={paperId} />
          </div>
          {result.status !== "insufficient_context" && (
          <div className="mx-6 mb-4 rounded-lg border border-blue-100 bg-blue-50 p-3">
            <p className="mb-2 text-xs font-medium text-blue-800">继续追问</p>
            <div className="flex flex-wrap gap-2">
              {FOLLOW_UPS.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setQuestion(item)}
                  className="rounded-full border border-blue-200 bg-white px-3 py-1 text-xs text-blue-700 hover:bg-blue-100"
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          )}
        </>
      )}
    </div>
  );
}
