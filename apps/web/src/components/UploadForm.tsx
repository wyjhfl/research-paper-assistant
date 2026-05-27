"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import { uploadPaper, getErrorMessage } from "@/lib/api";

export default function UploadForm() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
    setError(null);
    setJobId(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    setUploading(true);
    setError(null);
    setJobId(null);
    try {
      const res = await uploadPaper(selectedFile);
      setJobId(res.job_id ?? null);
      setSelectedFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setError(getErrorMessage(err, "Upload failed"));
    } finally {
      setUploading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">{"\u4E0A\u4F20\u8BBA\u6587 PDF"}</h2>

      <div className="flex items-center gap-4">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          onChange={handleFileChange}
          disabled={uploading}
          className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!selectedFile || uploading}
          className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
        >
          {uploading ? "\u4E0A\u4F20\u4E2D..." : "\u4E0A\u4F20"}
        </button>
      </div>

      {uploading && (
        <div className="mt-3">
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div className="bg-blue-600 h-2 rounded-full animate-pulse" style={{ width: "60%" }} />
          </div>
          <p className="text-sm text-gray-500 mt-1">{"\u6B63\u5728\u4E0A\u4F20\uFF0C\u8BF7\u7A0D\u5019..."}</p>
        </div>
      )}

      {jobId && (
        <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-md">
          <p className="text-sm text-green-700">
            {"\u8BBA\u6587\u5DF2\u521B\u5EFA\uFF0C\u540E\u53F0\u4EFB\u52A1\u5DF2\u542F\u52A8"}
          </p>
          <p className="text-xs text-green-600 mt-1">
            {"\u4EFB\u52A1 ID: "}{jobId.slice(0, 16)}...
            {" \u00B7 "}
            <Link href="/jobs" className="underline hover:text-green-800">{"\u67E5\u770B\u4EFB\u52A1"}</Link>
          </p>
        </div>
      )}

      {error && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}
    </form>
  );
}
