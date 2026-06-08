"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  fetchHealth,
  fetchPapers,
  fetchResearchNotes,
  fetchWorkerHealth,
  getErrorMessage,
  type HealthResponse,
  type PaperListResponse,
  type ResearchNoteListResponse,
  type WorkerHealth,
} from "@/lib/api";

type LoadState = "loading" | "ok" | "warn" | "error";

interface LandingSnapshot {
  health: HealthResponse | null;
  papers: PaperListResponse | null;
  notes: ResearchNoteListResponse | null;
  worker: WorkerHealth | null;
}

function statusClass(state: LoadState): string {
  if (state === "ok") return "bg-green-50 text-green-700 border-green-200";
  if (state === "warn") return "bg-yellow-50 text-yellow-700 border-yellow-200";
  if (state === "error") return "bg-red-50 text-red-700 border-red-200";
  return "bg-gray-50 text-gray-500 border-gray-200";
}

function statusLabel(state: LoadState): string {
  if (state === "ok") return "正常";
  if (state === "warn") return "需关注";
  if (state === "error") return "异常";
  return "检查中";
}

export default function LocalLandingStatus() {
  const [snapshot, setSnapshot] = useState<LandingSnapshot>({
    health: null,
    papers: null,
    notes: null,
    worker: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadStatus() {
    setLoading(true);
    setError(null);
    try {
      const [health, papers, notes, worker] = await Promise.all([
        fetchHealth(),
        fetchPapers(),
        fetchResearchNotes({ limit: 20 }),
        fetchWorkerHealth(),
      ]);
      setSnapshot({ health, papers, notes, worker });
    } catch (err) {
      setError(getErrorMessage(err, "无法连接本地服务"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStatus();
  }, []);

  const summary = useMemo(() => {
    const completedPapers = snapshot.papers?.papers.filter((paper) => paper.status === "completed").length ?? 0;
    const totalChunks = snapshot.papers?.papers.reduce((sum, paper) => sum + paper.chunk_count, 0) ?? 0;
    const noteCount = snapshot.notes?.total ?? 0;
    const pendingJobs = snapshot.worker?.pending_count ?? 0;
    const staleJobs = snapshot.worker?.stale_running_count ?? 0;
    const backendOk = snapshot.health?.status === "ok" && snapshot.health.database === "connected";
    const workerOk = Boolean(snapshot.worker?.worker_enabled) && staleJobs === 0;
    const state: LoadState = loading ? "loading" : error ? "error" : backendOk && workerOk ? "ok" : "warn";
    return { completedPapers, totalChunks, noteCount, pendingJobs, staleJobs, backendOk, workerOk, state };
  }, [error, loading, snapshot]);

  return (
    <section className="mb-8 rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-800">本地落地状态</h2>
          <p className="mt-1 text-sm text-gray-500">
            检查后端、数据库、论文库、研究笔记和任务 worker，确认当前环境是否适合开始使用。
          </p>
        </div>
        <button
          type="button"
          onClick={loadStatus}
          className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
        >
          重新检查
        </button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className={`rounded-full border px-3 py-1 text-xs font-medium ${statusClass(summary.state)}`}>
          总体：{statusLabel(summary.state)}
        </span>
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
          <p className="text-xs text-gray-500">后端 / 数据库</p>
          <p className="mt-1 text-sm font-semibold text-gray-800">
            {loading ? "检查中" : summary.backendOk ? "已连接" : "未就绪"}
          </p>
          <p className="mt-1 text-xs text-gray-500">版本：{snapshot.health?.version ?? "未知"}</p>
        </div>
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
          <p className="text-xs text-gray-500">论文库</p>
          <p className="mt-1 text-sm font-semibold text-gray-800">
            {summary.completedPapers} 篇已完成 / {summary.totalChunks} 个片段
          </p>
          <Link href="/papers" className="mt-1 inline-block text-xs text-blue-600 hover:underline">
            管理论文
          </Link>
        </div>
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
          <p className="text-xs text-gray-500">研究笔记</p>
          <p className="mt-1 text-sm font-semibold text-gray-800">{summary.noteCount} 条笔记</p>
          <Link href="/notes" className="mt-1 inline-block text-xs text-blue-600 hover:underline">
            打开笔记
          </Link>
        </div>
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-3">
          <p className="text-xs text-gray-500">任务 Worker</p>
          <p className="mt-1 text-sm font-semibold text-gray-800">
            {loading ? "检查中" : summary.workerOk ? "运行中" : "需关注"}
          </p>
          <p className="mt-1 text-xs text-gray-500">
            待处理 {summary.pendingJobs} / stale {summary.staleJobs}
          </p>
        </div>
      </div>

      {!loading && !error && summary.completedPapers === 0 && (
        <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-3 text-sm text-blue-700">
          还没有已完成论文。建议先上传 1-3 篇论文，然后使用跨论文问答、综述表和研究笔记工作台。
        </div>
      )}
    </section>
  );
}
