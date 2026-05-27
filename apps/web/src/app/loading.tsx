export default function Loading() {
  return (
    <main className="max-w-3xl mx-auto px-6 py-16">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-gray-900">多 Agent 科研论文助手</h1>
        <p className="mt-4 text-lg text-gray-500">
          上传科研 PDF · 解析论文 · RAG 问答 · Idea 抽取 · 引用推荐
        </p>
      </div>

      <div className="mt-8 space-y-4">
        <h2 className="text-lg font-semibold text-gray-700">系统状态</h2>
        <div className="bg-white rounded-lg shadow divide-y">
          <div className="flex items-center justify-between px-6 py-4">
            <span className="text-gray-600">后端服务</span>
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-600">
              <span className="w-2 h-2 rounded-full bg-gray-400 animate-pulse" />
              检测中...
            </span>
          </div>
          <div className="flex items-center justify-between px-6 py-4">
            <span className="text-gray-600">数据库连接</span>
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-600">
              <span className="w-2 h-2 rounded-full bg-gray-400 animate-pulse" />
              检测中...
            </span>
          </div>
        </div>
      </div>
    </main>
  );
}
