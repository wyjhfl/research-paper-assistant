"use client";

import { useState } from "react";
import Link from "next/link";
import { rebuildEmbeddings, getErrorMessage } from "@/lib/api";

interface RebuildEmbeddingsButtonProps {
  paperId: number;
}

export default function RebuildEmbeddingsButton({ paperId }: RebuildEmbeddingsButtonProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  async function handleRebuild() {
    setLoading(true);
    setError(null);
    setResult(null);
    setJobId(null);

    try {
      const res = await rebuildEmbeddings(paperId);
      if (res.job_id) {
        setJobId(res.job_id);
        setResult("\u4EFB\u52A1\u5DF2\u542F\u52A8");
      } else {
        setResult(`\u5DF2\u91CD\u5EFA ${res.chunks_embedded} \u4E2A\u7247\u6BB5\u7684\u5411\u91CF`);
      }
    } catch (err) {
      setError(getErrorMessage(err, "\u91CD\u5EFA\u5931\u8D25"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={handleRebuild}
          disabled={loading}
          className="rounded-lg px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "\u91CD\u5EFA\u4E2D..." : "\u91CD\u5EFA Embeddings"}
        </button>
        {result && !jobId && <span className="text-xs text-green-600">{result}</span>}
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>
      {jobId && (
        <div className="p-2 bg-green-50 border border-green-200 rounded-md">
          <p className="text-xs text-green-700">
            {"Embeddings \u91CD\u5EFA\u4EFB\u52A1\u5DF2\u542F\u52A8"}
            {" \u00B7 "}
            <Link href="/jobs" className="underline hover:text-green-800">{"\u67E5\u770B\u4EFB\u52A1"}</Link>
          </p>
        </div>
      )}
    </div>
  );
}
