"use client";

import { useState, useEffect } from "react";
import { runAgent, fetchPapers, getErrorMessage, type AgentRunResponse, type PaperListItem } from "@/lib/api";

const TASK_TYPES = [
  {
    value: "summarize_paper",
    label: "论文总结",
    description: "生成论文的结构化摘要，包含概述、关键点和局限性",
    requires: "paper_id",
  },
  {
    value: "extract_ideas",
    label: "Idea 抽取",
    description: "从论文中提取潜在研究想法",
    requires: "paper_id",
  },
  {
    value: "recommend_citations",
    label: "引用推荐",
    description: "基于单篇论文推荐相关引用",
    requires: "paper_id+question_or_draft",
  },
  {
    value: "recommend_citations_multi",
    label: "多论文引用推荐",
    description: "跨论文检索并推荐引用，不填论文则全库检索",
    requires: "question_or_draft",
  },
] as const;

type TaskTypeValue = (typeof TASK_TYPES)[number]["value"];

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "completed"
      ? "bg-green-100 text-green-700"
      : status === "failed"
        ? "bg-red-100 text-red-700"
        : "bg-yellow-100 text-yellow-700";
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

function RagStatusBadge({ status }: { status: string }) {
  const cls =
    status === "answered"
      ? "bg-green-100 text-green-700"
      : "bg-yellow-100 text-yellow-700";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

function SummarizeOutput({ output }: { output: Record<string, unknown> }) {
  const summary = output.summary as Record<string, unknown> | undefined;
  if (!summary) {
    return <pre className="text-xs bg-gray-50 p-3 rounded overflow-auto">{JSON.stringify(output, null, 2)}</pre>;
  }
  return (
    <div className="space-y-3">
      <div>
        <span className="text-xs text-gray-500">标题</span>
        <p className="text-sm text-gray-800">{String(summary.title || "")}</p>
      </div>
      <div>
        <span className="text-xs text-gray-500">概述</span>
        <p className="text-sm text-gray-800">{String(summary.overview || "")}</p>
      </div>
      <div>
        <span className="text-xs text-gray-500">关键点</span>
        <ul className="list-disc list-inside text-sm text-gray-700">
          {((summary.key_points as string[]) || []).map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      </div>
      <div>
        <span className="text-xs text-gray-500">局限性</span>
        <ul className="list-disc list-inside text-sm text-gray-700">
          {((summary.limitations as string[]) || []).map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ExtractIdeasOutput({ output }: { output: Record<string, unknown> }) {
  const ideas = output.ideas as Array<Record<string, unknown>> | undefined;
  if (!ideas || ideas.length === 0) {
    return <p className="text-sm text-gray-400">未抽取到 Idea</p>;
  }
  return (
    <div className="space-y-3">
      {ideas.map((idea, i) => (
        <div key={i} className="border border-gray-200 rounded-lg p-4 space-y-1">
          <p className="text-sm font-semibold text-gray-800">{String(idea.title || "")}</p>
          <p className="text-xs text-gray-600">{String(idea.summary || "")}</p>
          <p className="text-xs text-gray-500">研究问题: {String(idea.research_question || "")}</p>
          <p className="text-xs text-gray-500">方法提示: {String(idea.method_hint || "")}</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {((idea.tags as string[]) || []).map((tag, ti) => (
              <span key={ti} className="inline-block bg-blue-50 text-blue-600 text-xs px-2 py-0.5 rounded">
                {tag}
              </span>
            ))}
          </div>
          <p className="text-xs text-gray-400">置信度: {String(idea.confidence ?? 0)}</p>
        </div>
      ))}
    </div>
  );
}

function CitationOutput({ output }: { output: Record<string, unknown> }) {
  const answer = output.answer as string | undefined;
  const ragStatus = output.rag_status as string | undefined;
  const sources = output.sources as Array<Record<string, unknown>> | undefined;

  return (
    <div className="space-y-3">
      {ragStatus && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">RAG 状态</span>
          <RagStatusBadge status={ragStatus} />
        </div>
      )}
      {answer && (
        <div>
          <span className="text-xs text-gray-500">回答</span>
          <p className="text-sm text-gray-800 mt-1 whitespace-pre-wrap">{answer}</p>
        </div>
      )}
      {sources && sources.length > 0 && (
        <div>
          <span className="text-xs text-gray-500">引用来源</span>
          <div className="space-y-2 mt-1">
            {sources.map((s, i) => (
              <div key={i} className="bg-gray-50 rounded-md p-3 text-xs text-gray-700 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{String(s.paper_title || `Paper ${s.paper_id}`)}</span>
                  <span className="text-gray-400">
                    Chunk {String(s.chunk_id)} (第 {String(s.page_start)}-{String(s.page_end)} 页)
                  </span>
                  <span className="text-gray-400">Score: {String(s.score)}</span>
                </div>
                <p className="text-gray-600 line-clamp-3">{String(s.text_excerpt || "")}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      {(!sources || sources.length === 0) && <p className="text-sm text-gray-400">未找到引用来源</p>}
    </div>
  );
}

function ResultOutput({ taskType, output }: { taskType: string; output: Record<string, unknown> }) {
  if (taskType === "summarize_paper") return <SummarizeOutput output={output} />;
  if (taskType === "extract_ideas") return <ExtractIdeasOutput output={output} />;
  if (taskType === "recommend_citations" || taskType === "recommend_citations_multi")
    return <CitationOutput output={output} />;
  return <pre className="text-xs bg-gray-50 p-3 rounded overflow-auto">{JSON.stringify(output, null, 2)}</pre>;
}

export default function AgentRunner() {
  const [taskType, setTaskType] = useState<TaskTypeValue>("summarize_paper");
  const [paperId, setPaperId] = useState<string>("");
  const [paperIds, setPaperIds] = useState<number[]>([]);
  const [question, setQuestion] = useState<string>("");
  const [draftText, setDraftText] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AgentRunResponse | null>(null);
  const [papers, setPapers] = useState<PaperListItem[]>([]);
  const [papersLoading, setPapersLoading] = useState(false);

  const currentTask = TASK_TYPES.find((t) => t.value === taskType)!;
  const needsPaperId = currentTask.requires === "paper_id" || currentTask.requires === "paper_id+question_or_draft";
  const needsQuestionOrDraft =
    currentTask.requires === "question_or_draft" || currentTask.requires === "paper_id+question_or_draft";
  const isMulti = taskType === "recommend_citations_multi";

  useEffect(() => {
    let cancelled = false;
    setPapersLoading(true);
    fetchPapers()
      .then((res) => {
        if (!cancelled) {
          const completed = res.papers.filter((p) => p.status === "completed");
          setPapers(completed);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setPapersLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function togglePaperId(id: number) {
    setPaperIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function canRun(): boolean {
    if (loading) return false;
    if (needsPaperId && !isMulti && !paperId) return false;
    if (needsQuestionOrDraft && !question && !draftText) return false;
    return true;
  }

  async function handleRun() {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const req: Parameters<typeof runAgent>[0] = {
        task_type: taskType,
        paper_id: needsPaperId && !isMulti && paperId ? parseInt(paperId, 10) : undefined,
        paper_ids: isMulti && paperIds.length > 0 ? paperIds : undefined,
        question: needsQuestionOrDraft && question ? question : undefined,
        draft_text: needsQuestionOrDraft && draftText ? draftText : undefined,
      };
      const res = await runAgent(req);
      setResult(res);
    } catch (err) {
      setError(getErrorMessage(err, "Agent 运行失败"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">Agent 工作流</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-600 mb-1">任务类型</label>
            <select
              value={taskType}
              onChange={(e) => {
                setTaskType(e.target.value as TaskTypeValue);
                setPaperId("");
                setPaperIds([]);
                setQuestion("");
                setDraftText("");
              }}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {TASK_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-500">{currentTask.description}</p>
          </div>

          {needsPaperId && !isMulti && (
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">选择论文</label>
              {papersLoading ? (
                <p className="text-sm text-gray-400">加载论文列表...</p>
              ) : (
                <select
                  value={paperId}
                  onChange={(e) => setPaperId(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">-- 请选择论文 --</option>
                  {papers.map((p) => (
                    <option key={p.id} value={String(p.id)}>
                      {p.title}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}

          {isMulti && (
            <div>
              <label className="block text-sm font-medium text-gray-600 mb-1">选择论文（可多选）</label>
              <p className="text-xs text-gray-400 mb-2">不选择论文则默认全库检索</p>
              {papersLoading ? (
                <p className="text-sm text-gray-400">加载论文列表...</p>
              ) : papers.length === 0 ? (
                <p className="text-sm text-gray-400">暂无已完成论文</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {papers.map((p) => {
                    const selected = paperIds.includes(p.id);
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => togglePaperId(p.id)}
                        className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${
                          selected
                            ? "bg-blue-600 text-white border-blue-600"
                            : "bg-white text-gray-700 border-gray-300 hover:border-blue-400"
                        }`}
                      >
                        {p.title}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {needsQuestionOrDraft && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">问题</label>
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="输入问题"
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-600 mb-1">草稿文本</label>
                <textarea
                  value={draftText}
                  onChange={(e) => setDraftText(e.target.value)}
                  placeholder="输入草稿文本"
                  rows={3}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </>
          )}

          <button
            onClick={handleRun}
            disabled={!canRun()}
            className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
          >
            {loading ? "运行中..." : "运行 Agent"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-700 text-sm">{error}</p>
        </div>
      )}

      {loading && (
        <div className="bg-white rounded-lg shadow p-6 flex items-center justify-center">
          <div className="flex items-center gap-3 text-gray-500">
            <svg className="animate-spin h-5 w-5 text-blue-600" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <span className="text-sm">Agent 正在运行，请稍候...</span>
          </div>
        </div>
      )}

      {result && (
        <div className="bg-white rounded-lg shadow p-4 sm:p-6 space-y-4">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div>
              <span className="text-xs text-gray-500">Run ID</span>
              <p className="font-mono text-sm text-gray-800">{result.run_id}</p>
            </div>
            <div>
              <span className="text-xs text-gray-500">状态</span>
              <div className="mt-0.5">
                <StatusBadge status={result.status} />
              </div>
            </div>
            <div>
              <span className="text-xs text-gray-500">置信度</span>
              <p className="text-sm font-medium text-gray-800">{(result.confidence * 100).toFixed(0)}%</p>
            </div>
            {result.output && typeof result.output === "object" && "rag_status" in result.output && (
              <div>
                <span className="text-xs text-gray-500">RAG 状态</span>
                <div className="mt-0.5">
                  <RagStatusBadge status={String(result.output.rag_status)} />
                </div>
              </div>
            )}
          </div>

          {result.warnings.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3">
              <p className="text-sm font-medium text-yellow-700 mb-1">警告</p>
              <ul className="list-disc list-inside text-sm text-yellow-600">
                {result.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">输出结果</h3>
            <ResultOutput taskType={result.task_type} output={result.output} />
          </div>

          <details className="border-t pt-3">
            <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700">原始数据</summary>
            <pre className="mt-2 text-xs bg-gray-50 p-3 rounded overflow-auto max-h-96">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}
