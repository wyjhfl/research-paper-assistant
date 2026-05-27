import Link from "next/link";

export default function NotFound() {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 text-center">
      <div className="text-6xl mb-4">🔍</div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">页面未找到</h1>
      <p className="text-sm text-gray-500 mb-6">请求的页面不存在或已被移除</p>
      <div className="flex flex-wrap justify-center gap-3">
        <Link
          href="/"
          className="inline-flex items-center px-5 py-2.5 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 transition-colors"
        >
          返回首页
        </Link>
        <Link
          href="/papers"
          className="inline-flex items-center px-5 py-2.5 rounded-lg text-sm font-medium bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 transition-colors"
        >
          论文库
        </Link>
        <Link
          href="/papers/ask"
          className="inline-flex items-center px-5 py-2.5 rounded-lg text-sm font-medium bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 transition-colors"
        >
          跨论文问答
        </Link>
      </div>
    </div>
  );
}
