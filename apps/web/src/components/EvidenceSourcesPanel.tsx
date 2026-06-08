"use client";

import { useState } from "react";
import Link from "next/link";
import { createResearchNote, getErrorMessage } from "@/lib/api";

interface EvidenceSource {
  paper_id: number;
  paper_title?: string;
  chunk_id: number;
  chunk_index: number;
  page_start: number;
  page_end: number;
  text_excerpt: string;
  score: number;
  vector_score?: number;
  lexical_score?: number;
  retrieval_mode?: string;
}

interface EvidenceSourcesPanelProps {
  sources: EvidenceSource[];
  fallbackPaperId?: number;
  title?: string;
}

const RETRIEVAL_MODE_MAP: Record<string, string> = {
  vector: "向量",
  lexical: "关键词",
  hybrid: "混合",
};

function formatPercent(value: number | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "无";
  return `${(value * 100).toFixed(1)}%`;
}

function buildModeSummary(sources: EvidenceSource[]): string {
  const counts = new Map<string, number>();
  for (const source of sources) {
    const mode = source.retrieval_mode || "unknown";
    counts.set(mode, (counts.get(mode) || 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([mode, count]) => `${RETRIEVAL_MODE_MAP[mode] ?? mode} ${count}`)
    .join(", ");
}

function averageScore(sources: EvidenceSource[]): number | undefined {
  if (sources.length === 0) return undefined;
  return sources.reduce((sum, source) => sum + source.score, 0) / sources.length;
}

function maxScore(
  sources: EvidenceSource[],
  selector: (source: EvidenceSource) => number | undefined,
): number | undefined {
  const values = sources
    .map(selector)
    .filter((value): value is number => typeof value === "number" && !Number.isNaN(value));
  if (values.length === 0) return undefined;
  return Math.max(...values);
}

export default function EvidenceSourcesPanel({
  sources,
  fallbackPaperId,
  title = "引用来源",
}: EvidenceSourcesPanelProps) {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  if (sources.length === 0) return null;

  function sourceKey(source: EvidenceSource, idx: number): string {
    return `${source.paper_id}-${source.chunk_id}-${idx}`;
  }

  function toggleExpanded(key: string) {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function copySource(source: EvidenceSource, idx: number) {
    const key = sourceKey(source, idx);
    const pageText = source.page_start === source.page_end
      ? `page ${source.page_start}`
      : `pages ${source.page_start}-${source.page_end}`;
    const text = [
      source.paper_title ? `Paper: ${source.paper_title}` : `Paper ID: ${source.paper_id}`,
      `Chunk: #${source.chunk_index}`,
      `Location: ${pageText}`,
      `Score: ${formatPercent(source.score)}`,
      "",
      source.text_excerpt,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
    } catch {
      setCopiedKey(`${key}-failed`);
    }
    window.setTimeout(() => setCopiedKey(null), 1600);
  }

  async function saveSourceNote(source: EvidenceSource, idx: number) {
    const key = sourceKey(source, idx);
    setSaveError(null);
    try {
      await createResearchNote({
        title: `来源片段：${source.paper_title || `Paper ${source.paper_id}`} / chunk #${source.chunk_index}`,
        content: source.text_excerpt,
        note_type: "source_snippet",
        paper_id: source.paper_id || fallbackPaperId || null,
        chunk_id: source.chunk_id,
        source: {
          paper_id: source.paper_id || fallbackPaperId || null,
          paper_title: source.paper_title || null,
          chunk_id: source.chunk_id,
          chunk_index: source.chunk_index,
          page_start: source.page_start,
          page_end: source.page_end,
          score: source.score,
          retrieval_mode: source.retrieval_mode,
          source_kind: "evidence_source",
        },
        tags: ["source"],
      });
      setSavedKey(key);
      window.setTimeout(() => setSavedKey(null), 1600);
    } catch (err) {
      setSaveError(getErrorMessage(err, "保存来源片段失败"));
    }
  }

  const topScore = maxScore(sources, (source) => source.score);
  const topLexicalScore = maxScore(sources, (source) => source.lexical_score);
  const topVectorScore = maxScore(sources, (source) => source.vector_score);
  const avgScore = averageScore(sources);

  return (
    <section>
      <h3 className="mb-3 text-sm font-medium text-gray-600">
        {title} ({sources.length})
      </h3>

      <div className="mb-3 rounded-lg border border-blue-100 bg-blue-50 p-3">
        <p className="mb-2 text-xs font-semibold text-blue-800">证据质量摘要</p>
        <div className="grid gap-2 text-xs text-blue-700 sm:grid-cols-2 lg:grid-cols-4">
          <span>最高相关度: {formatPercent(topScore)}</span>
          <span>平均相关度: {formatPercent(avgScore)}</span>
          <span>关键词最高: {formatPercent(topLexicalScore)}</span>
          <span>向量最高: {formatPercent(topVectorScore)}</span>
        </div>
        <p className="mt-2 text-xs text-blue-700">
          检索模式: {buildModeSummary(sources) || "无"}
        </p>
      </div>

      {saveError && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700">
          {saveError}
        </div>
      )}

      <div className="space-y-3">
        {sources.map((source, idx) => {
          const key = sourceKey(source, idx);
          const isExpanded = expandedKeys.has(key);
          const paperId = source.paper_id || fallbackPaperId;
          return (
            <article
              key={key}
              className="rounded-lg border border-gray-200 p-3 transition-colors hover:border-blue-200 hover:bg-blue-50/40 sm:p-4"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-gray-400">#{idx + 1}</span>
                {source.paper_title && (
                  <span className="text-sm font-bold text-blue-600">{source.paper_title}</span>
                )}
                {paperId != null && (
                  <Link
                    href={`/papers/${paperId}#chunk-${source.chunk_id}`}
                    className="text-xs font-medium text-blue-600 hover:underline"
                  >
                    定位片段
                  </Link>
                )}
                <button
                  type="button"
                  onClick={() => toggleExpanded(key)}
                  className="rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
                >
                  {isExpanded ? "收起片段" : "展开片段"}
                </button>
                <button
                  type="button"
                  onClick={() => copySource(source, idx)}
                  className="rounded border border-gray-200 bg-white px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
                >
                  {copiedKey === key ? "已复制" : copiedKey === `${key}-failed` ? "复制失败" : "复制片段"}
                </button>
                <button
                  type="button"
                  onClick={() => saveSourceNote(source, idx)}
                  className="rounded border border-blue-200 bg-white px-2 py-0.5 text-xs text-blue-600 hover:bg-blue-50"
                >
                  {savedKey === key ? "已保存" : "存为笔记"}
                </button>
              </div>

              <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
                <span>
                  第 {source.page_start}
                  {source.page_start !== source.page_end ? ` 至 ${source.page_end}` : ""} 页
                </span>
                <span>片段 #{source.chunk_index}</span>
                <span className="font-medium text-blue-600">
                  相关度: {formatPercent(source.score)}
                </span>
                {source.lexical_score != null && (
                  <span>关键词: {formatPercent(source.lexical_score)}</span>
                )}
                {source.vector_score != null && (
                  <span>向量: {formatPercent(source.vector_score)}</span>
                )}
                {source.retrieval_mode && (
                  <span>
                    检索: {RETRIEVAL_MODE_MAP[source.retrieval_mode] ?? source.retrieval_mode}
                  </span>
                )}
              </div>

              <p className={`text-xs leading-relaxed text-gray-600 ${isExpanded ? "" : "line-clamp-4"}`}>
                {source.text_excerpt}
              </p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
