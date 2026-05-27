"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchJobs,
  fetchWorkerHealth,
  cancelJob as cancelJobApi,
  retryJob as retryJobApi,
  JobItem,
  WorkerHealth,
  getErrorMessage,
} from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  cancelled: "bg-gray-100 text-gray-800",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "\u7B49\u5F85\u4E2D",
  running: "\u8FD0\u884C\u4E2D",
  completed: "\u5DF2\u5B8C\u6210",
  failed: "\u5DF2\u5931\u8D25",
  cancelled: "\u5DF2\u53D6\u6D88",
};

const AUTO_REFRESH_MS = 5000;

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [health, setHealth] = useState<WorkerHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [jobsResult, healthResult] = await Promise.allSettled([fetchJobs(), fetchWorkerHealth()]);
      if (jobsResult.status === "fulfilled") {
        setJobs(jobsResult.value.jobs);
      } else {
        setError(getErrorMessage(jobsResult.reason));
      }
      if (healthResult.status === "fulfilled") {
        setHealth(healthResult.value);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    const hasActive = jobs.some((j) => j.status === "pending" || j.status === "running");
    if (hasActive) {
      timerRef.current = setInterval(() => {
        loadJobs();
      }, AUTO_REFRESH_MS);
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [jobs, loadJobs]);

  const handleCancel = async (jobId: string) => {
    try {
      await cancelJobApi(jobId);
      await loadJobs();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const handleRetry = async (jobId: string) => {
    try {
      await retryJobApi(jobId);
      await loadJobs();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const hasActive = jobs.some((j) => j.status === "pending" || j.status === "running");

  return (
    <main data-testid="jobs-page" className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{"\u4EFB\u52A1"}</h1>
        <button
          onClick={loadJobs}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          {"\u5237\u65B0"}
        </button>
      </div>

      {health && (
        <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded-md">
          <div className="flex flex-wrap gap-4 text-xs text-gray-600">
            <span>{"\u7B49\u5F85\u4E2D: "}{health.pending_count}</span>
            <span>{"\u8FD0\u884C\u4E2D: "}{health.running_count}</span>
            <span className="text-red-600">{"\u5DF2\u5931\u8D25: "}{health.failed_count}</span>
            {health.stale_running_count > 0 && (
              <span className="text-orange-600 font-semibold">
                {"\u5361\u4F4F\u4EFB\u52A1: "}{health.stale_running_count}
              </span>
            )}
          </div>
        </div>
      )}

      {health && health.stale_running_count > 0 && (
        <div className="mb-4 p-3 bg-orange-50 border border-orange-300 rounded-md text-xs text-orange-700">
          {"\u68C0\u6D4B\u5230 "}{health.stale_running_count}{" \u4E2A\u5361\u4F4F\u4EFB\u52A1\uFF08\u8FD0\u884C\u8D85\u8FC7 "}{health.stale_running_seconds}{" \u79D2\u672A\u5B8C\u6210\uFF09\uFF0C\u8BF7\u68C0\u67E5\u662F\u5426\u9700\u8981\u624B\u52A8\u5904\u7406"}
        </div>
      )}

      {hasActive && (
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-md text-xs text-blue-700">
          {"\u6709\u8FD0\u884C\u4E2D\u6216\u7B49\u5F85\u4E2D\u7684\u4EFB\u52A1\uFF0C\u9875\u9762\u5C06\u6BCF 5 \u79D2\u81EA\u52A8\u5237\u65B0"}
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-md">{error}</div>
      )}

      {loading ? (
        <div className="text-center py-12 text-gray-500">
          {"\u6B63\u5728\u52A0\u8F7D\u4EFB\u52A1\u5217\u8868..."}
        </div>
      ) : jobs.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          {"\u6682\u65E0\u4EFB\u52A1"}
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <div
              key={job.job_id}
              className="bg-white border border-gray-200 rounded-lg p-4"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className={`px-2 py-0.5 text-xs font-medium rounded ${
                      STATUS_COLORS[job.status] || "bg-gray-100 text-gray-800"
                    }`}
                  >
                    {STATUS_LABELS[job.status] || job.status}
                  </span>
                  <span className="text-sm font-medium text-gray-900">
                    {job.job_type}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {job.progress_total > 0 && (
                    <span className="text-xs text-gray-500">
                      {job.progress_current}/{job.progress_total}
                    </span>
                  )}
                  <span className="text-xs text-gray-400">
                    {job.attempts}/{job.max_attempts}
                  </span>
                  {job.status === "pending" && (
                    <button
                      onClick={() => handleCancel(job.job_id)}
                      className="px-3 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                    >
                      {"\u53D6\u6D88"}
                    </button>
                  )}
                  {job.status === "failed" && (
                    <button
                      onClick={() => handleRetry(job.job_id)}
                      className="px-3 py-1 text-xs bg-orange-100 text-orange-700 rounded hover:bg-orange-200"
                    >
                      {"\u91CD\u8BD5"}
                    </button>
                  )}
                </div>
              </div>
              <div className="mt-2 text-xs text-gray-500">
                <span>{job.job_id.slice(0, 16)}...</span>
                <span className="mx-2">|</span>
                <span>{new Date(job.created_at).toLocaleString()}</span>
                {job.finished_at && (
                  <>
                    <span className="mx-2">→</span>
                    <span>{new Date(job.finished_at).toLocaleString()}</span>
                  </>
                )}
              </div>
              {job.input_summary && (
                <div className="mt-1 text-xs text-gray-600">
                  <span className="text-gray-400">{"\u8F93\u5165: "}</span>
                  {job.input_summary}
                </div>
              )}
              {job.output_summary && (
                <div className="mt-1 text-xs text-gray-600">
                  <span className="text-gray-400">{"\u8F93\u51FA: "}</span>
                  {job.output_summary}
                </div>
              )}
              {job.error_message && (
                <div className="mt-2 text-xs text-red-600">{job.error_message}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
