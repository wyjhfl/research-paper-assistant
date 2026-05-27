"use client";

import { useEffect, useState } from "react";
import {
  fetchModelCalls,
  fetchModelCallSummary,
  fetchLatestEvalReport,
  fetchStorageSummary,
  getErrorMessage,
  type ModelCallListResponse,
  type ModelCallSummaryResponse,
  type EvalReportSummaryResponse,
  type StorageSummary,
} from "@/lib/api";

export default function UsageDashboard() {
  const [summary, setSummary] = useState<ModelCallSummaryResponse | null>(null);
  const [calls, setCalls] = useState<ModelCallListResponse | null>(null);
  const [evalReport, setEvalReport] = useState<EvalReportSummaryResponse | null>(null);
  const [evalNotFound, setEvalNotFound] = useState(false);
  const [storageSummary, setStorageSummary] = useState<StorageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [summaryRes, callsRes] = await Promise.all([
          fetchModelCallSummary(),
          fetchModelCalls(50),
        ]);
        if (cancelled) return;
        setSummary(summaryRes);
        setCalls(callsRes);

        try {
          const storage = await fetchStorageSummary();
          if (cancelled) return;
          setStorageSummary(storage);
        } catch {
        }

        try {
          const report = await fetchLatestEvalReport();
          if (cancelled) return;
          if (report === null) {
            setEvalNotFound(true);
          } else {
            setEvalReport(report);
          }
        } catch {
          if (!cancelled) setEvalNotFound(true);
        }
      } catch (err) {
        if (!cancelled) setError(getErrorMessage(err, "加载用量数据失败"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return <p className="text-sm text-gray-500">正在加载用量数据...</p>;
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4" data-testid="usage-error">
        <p className="text-sm text-red-700">{error}</p>
      </div>
    );
  }

  return (
    <div>
      {storageSummary && (
        <div className="mb-6" data-testid="storage-summary">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">存储用量</h3>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
              <p className="text-xs text-gray-500 mb-1">论文数量</p>
              <p className="text-2xl font-bold text-gray-900" data-testid="paper-count">{storageSummary.paper_count}</p>
            </div>
            <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
              <p className="text-xs text-gray-500 mb-1">文本块数量</p>
              <p className="text-2xl font-bold text-gray-900" data-testid="chunk-count">{storageSummary.chunk_count}</p>
            </div>
            <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
              <p className="text-xs text-gray-500 mb-1">存储占用</p>
              <p className="text-2xl font-bold text-gray-900" data-testid="storage-bytes">
                {storageSummary.storage_bytes < 1024 * 1024
                  ? `${(storageSummary.storage_bytes / 1024).toFixed(1)} KB`
                  : `${(storageSummary.storage_bytes / (1024 * 1024)).toFixed(1)} MB`}
              </p>
            </div>
            <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
              <p className="text-xs text-gray-500 mb-1">失败论文</p>
              <p className={`text-2xl font-bold ${storageSummary.failed_paper_count > 0 ? "text-red-600" : "text-gray-900"}`} data-testid="failed-paper-count">
                {storageSummary.failed_paper_count}
              </p>
            </div>
          </div>
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
            <p className="text-xs text-gray-500 mb-1">总调用次数</p>
            <p className="text-2xl font-bold text-gray-900" data-testid="total-calls">{summary.total_calls}</p>
          </div>
          <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
            <p className="text-xs text-gray-500 mb-1">失败次数</p>
            <p className="text-2xl font-bold text-red-600" data-testid="failed-calls">{summary.failed_calls}</p>
          </div>
          <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
            <p className="text-xs text-gray-500 mb-1">平均耗时 (ms)</p>
            <p className="text-2xl font-bold text-gray-900" data-testid="avg-duration">{summary.avg_duration_ms}</p>
          </div>
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
          <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">按操作类型</h3>
            {Object.keys(summary.calls_by_operation).length === 0 ? (
              <p className="text-xs text-gray-400">暂无数据</p>
            ) : (
              <ul className="space-y-1">
                {Object.entries(summary.calls_by_operation).map(([op, count]) => (
                  <li key={op} className="flex justify-between text-sm">
                    <span className="text-gray-600">{op}</span>
                    <span className="font-medium text-gray-900">{count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">按 Provider</h3>
            {Object.keys(summary.calls_by_provider).length === 0 ? (
              <p className="text-xs text-gray-400">暂无数据</p>
            ) : (
              <ul className="space-y-1">
                {Object.entries(summary.calls_by_provider).map(([prov, count]) => (
                  <li key={prov} className="flex justify-between text-sm">
                    <span className="text-gray-600">{prov}</span>
                    <span className="font-medium text-gray-900">{count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {calls && calls.events.length > 0 && (
        <div className="mb-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">最近模型调用</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="model-calls-table">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">操作</th>
                  <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">Provider</th>
                  <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">模型</th>
                  <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">状态</th>
                  <th className="text-right py-2 px-2 text-xs font-medium text-gray-500">耗时</th>
                  <th className="text-right py-2 px-2 text-xs font-medium text-gray-500">输入字符</th>
                  <th className="text-right py-2 px-2 text-xs font-medium text-gray-500">输出字符</th>
                  <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">时间</th>
                </tr>
              </thead>
              <tbody>
                {calls.events.map((e) => (
                  <tr key={e.id} className="border-b border-gray-50">
                    <td className="py-1.5 px-2 text-gray-700">{e.operation}</td>
                    <td className="py-1.5 px-2 text-gray-700">{e.provider}</td>
                    <td className="py-1.5 px-2 text-gray-700">{e.model}</td>
                    <td className="py-1.5 px-2">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
                        e.status === "success"
                          ? "bg-green-50 text-green-700"
                          : "bg-red-50 text-red-700"
                      }`}>
                        {e.status}
                      </span>
                    </td>
                    <td className="py-1.5 px-2 text-right text-gray-600">{e.duration_ms}ms</td>
                    <td className="py-1.5 px-2 text-right text-gray-600">{e.input_chars}</td>
                    <td className="py-1.5 px-2 text-right text-gray-600">{e.output_chars}</td>
                    <td className="py-1.5 px-2 text-gray-500 text-xs whitespace-nowrap">
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {calls.events.some((e) => e.error_type || e.error_message) && (
            <div className="mt-3">
              <h4 className="text-xs font-semibold text-gray-500 mb-1">错误详情</h4>
              {calls.events
                .filter((e) => e.error_type || e.error_message)
                .map((e) => (
                  <div key={e.id} className="bg-red-50 border border-red-100 rounded p-2 mb-1 text-xs">
                    <span className="font-medium text-red-700">{e.error_type || "Error"}</span>
                    {e.error_message && <span className="text-red-600 ml-1">{e.error_message}</span>}
                  </div>
                ))}
            </div>
          )}
        </div>
      )}

      {calls && calls.events.length === 0 && (
        <div className="mb-6 text-center py-8" data-testid="usage-empty">
          <div className="text-4xl mb-3">📊</div>
          <h3 className="text-lg font-semibold text-gray-700 mb-1">暂无调用记录</h3>
          <p className="text-sm text-gray-500">模型调用审计记录将在此处展示</p>
        </div>
      )}

      <div className="mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">真实模型评测</h3>
        {evalNotFound && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4" data-testid="eval-not-found">
            <p className="text-sm text-gray-500">尚未运行真实模型评测，运行 eval_real_model.py 后将在此展示结果。</p>
          </div>
        )}
        {evalReport && (
          <div data-testid="eval-report">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
              <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
                <p className="text-xs text-gray-500 mb-1">评测状态</p>
                <p className={`text-lg font-bold ${evalReport.can_proceed ? "text-green-600" : "text-red-600"}`} data-testid="eval-can-proceed">
                  {evalReport.can_proceed ? "通过" : "未通过"}
                </p>
              </div>
              <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
                <p className="text-xs text-gray-500 mb-1">通过 / 总数</p>
                <p className="text-lg font-bold text-gray-900" data-testid="eval-totals">
                  {evalReport.totals.passed} / {evalReport.totals.total}
                </p>
              </div>
              <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4">
                <p className="text-xs text-gray-500 mb-1">最近评测时间</p>
                <p className="text-sm font-medium text-gray-900" data-testid="eval-timestamp">
                  {evalReport.timestamp ? new Date(evalReport.timestamp).toLocaleString() : "-"}
                </p>
              </div>
            </div>

            {evalReport.metadata.llm_model && (
              <div className="bg-white rounded-lg shadow-sm border border-gray-100 p-4 mb-4">
                <h4 className="text-xs font-semibold text-gray-500 mb-2">评测配置</h4>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm">
                  <div><span className="text-gray-500">LLM:</span> <span className="text-gray-700">{evalReport.metadata.llm_model}</span></div>
                  <div><span className="text-gray-500">Embedding:</span> <span className="text-gray-700">{evalReport.metadata.embedding_model}</span></div>
                  <div><span className="text-gray-500">维度:</span> <span className="text-gray-700">{evalReport.metadata.embedding_dimension}</span></div>
                </div>
              </div>
            )}

            {evalReport.cases.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="eval-cases-table">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">Case ID</th>
                      <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">类型</th>
                      <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">严重度</th>
                      <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">状态</th>
                      <th className="text-right py-2 px-2 text-xs font-medium text-gray-500">耗时</th>
                      <th className="text-left py-2 px-2 text-xs font-medium text-gray-500">警告</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalReport.cases.map((c) => (
                      <tr key={c.case_id} className="border-b border-gray-50">
                        <td className="py-1.5 px-2 text-gray-700">{c.case_id}</td>
                        <td className="py-1.5 px-2 text-gray-600">{c.type}</td>
                        <td className="py-1.5 px-2">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
                            c.severity === "blocker" ? "bg-red-50 text-red-700" : "bg-yellow-50 text-yellow-700"
                          }`}>
                            {c.severity}
                          </span>
                        </td>
                        <td className="py-1.5 px-2">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
                            c.status === "passed" ? "bg-green-50 text-green-700"
                            : c.status === "warning" ? "bg-yellow-50 text-yellow-700"
                            : "bg-red-50 text-red-700"
                          }`}>
                            {c.status}
                          </span>
                        </td>
                        <td className="py-1.5 px-2 text-right text-gray-600">{c.duration_ms}ms</td>
                        <td className="py-1.5 px-2 text-gray-500 text-xs max-w-xs truncate">
                          {c.warnings.length > 0 ? c.warnings.join("; ") : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
