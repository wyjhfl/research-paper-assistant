"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="max-w-3xl mx-auto px-6 py-16">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-gray-900">多 Agent 科研论文助手</h1>
      </div>

      <div className="mt-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-700 font-medium">页面加载出错</p>
          <p className="text-red-500 text-sm mt-2">{error.message}</p>
          <button
            onClick={reset}
            className="mt-4 px-4 py-2 bg-red-100 text-red-700 rounded-md hover:bg-red-200 transition-colors text-sm"
          >
            重试
          </button>
        </div>
      </div>
    </main>
  );
}
