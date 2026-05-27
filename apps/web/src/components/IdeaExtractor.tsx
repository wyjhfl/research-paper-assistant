"use client";

import { useState } from "react";
import {
  extractIdeas,
  saveIdea,
  getErrorMessage,
  type IdeaCandidateItem,
} from "@/lib/api";

interface IdeaExtractorProps {
  paperId: number;
}

export default function IdeaExtractor({ paperId }: IdeaExtractorProps) {
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<IdeaCandidateItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [savingIdx, setSavingIdx] = useState<number | null>(null);
  const [savedIdxs, setSavedIdxs] = useState<Set<number>>(new Set());
  const [saveErrors, setSaveErrors] = useState<Record<number, string>>({});

  async function handleExtract() {
    setLoading(true);
    setError(null);
    setCandidates([]);
    setSavedIdxs(new Set());
    setSaveErrors({});

    try {
      const res = await extractIdeas(paperId);
      setCandidates(res.candidates);
    } catch (err) {
      setError(getErrorMessage(err, "抽取 Idea 失败"));
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(candidate: IdeaCandidateItem, idx: number) {
    setSavingIdx(idx);
    setSaveErrors((prev) => {
      const next = { ...prev };
      delete next[idx];
      return next;
    });

    try {
      await saveIdea({
        paper_id: paperId,
        title: candidate.title,
        summary: candidate.summary,
        research_question: candidate.research_question,
        method_hint: candidate.method_hint,
        tags: candidate.tags,
        source_chunk_ids: candidate.source_chunk_ids,
        confidence: candidate.confidence,
      });
      setSavedIdxs((prev) => new Set(prev).add(idx));
    } catch (err) {
      setSaveErrors((prev) => ({
        ...prev,
        [idx]: getErrorMessage(err, "保存失败"),
      }));
    } finally {
      setSavingIdx(null);
    }
  }

  return (
    <div className="bg-white rounded-lg shadow mt-6">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-700">Idea 抽取</h2>
        <button
          onClick={handleExtract}
          disabled={loading}
          className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "抽取中..." : "抽取 Idea"}
        </button>
      </div>

      {error && (
        <div className="mx-6 mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {candidates.length === 0 && !loading && !error && (
        <div className="px-6 py-8 text-center">
          <p className="text-gray-400">点击&ldquo;抽取 Idea&rdquo;从论文中提取研究想法</p>
        </div>
      )}

      <div className="divide-y divide-gray-100">
        {candidates.map((c, idx) => (
          <div key={idx} className="px-6 py-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-gray-900 mb-1">
                  {c.title}
                </h3>
                <p className="text-xs text-gray-600 mb-2">{c.summary}</p>

                <div className="space-y-1 mb-2">
                  <p className="text-xs text-gray-500">
                    <span className="font-medium text-gray-700">研究问题：</span>
                    {c.research_question}
                  </p>
                  <p className="text-xs text-gray-500">
                    <span className="font-medium text-gray-700">方法提示：</span>
                    {c.method_hint}
                  </p>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  {c.tags.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-50 text-purple-700"
                    >
                      {tag}
                    </span>
                  ))}
                  <span className="text-xs text-gray-400">
                    置信度: {(c.confidence * 100).toFixed(0)}%
                  </span>
                  <span className="text-xs text-gray-400">
                    来源 Chunk: {c.source_chunk_ids.join(", ")}
                  </span>
                </div>
              </div>

              <button
                onClick={() => handleSave(c, idx)}
                disabled={savingIdx === idx || savedIdxs.has(idx)}
                className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 text-white hover:bg-blue-700"
              >
                {savedIdxs.has(idx)
                  ? "已保存"
                  : savingIdx === idx
                  ? "保存中..."
                  : "保存 Idea"}
              </button>
            </div>

            {saveErrors[idx] && (
              <p className="mt-2 text-xs text-red-600">{saveErrors[idx]}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
