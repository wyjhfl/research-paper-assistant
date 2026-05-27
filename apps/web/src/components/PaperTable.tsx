import Link from "next/link";
import StatusBadge from "@/components/StatusBadge";

interface PaperTableProps {
  papers: {
    id: number;
    title: string;
    filename: string;
    status: string;
    chunk_count: number;
    created_at: string;
  }[];
}

export default function PaperTable({ papers }: PaperTableProps) {
  return (
    <>
      <div className="hidden md:block bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">标题</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">文件名</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Chunks</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">上传时间</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {papers.map((paper) => (
              <tr key={paper.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 text-sm font-medium text-gray-900 max-w-xs truncate">{paper.title}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{paper.filename}</td>
                <td className="px-6 py-4 text-sm"><StatusBadge status={paper.status} /></td>
                <td className="px-6 py-4 text-sm text-gray-500">{paper.chunk_count}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{new Date(paper.created_at).toLocaleString("zh-CN")}</td>
                <td className="px-6 py-4 text-sm">
                  <Link href={`/papers/${paper.id}`} className="text-blue-600 hover:text-blue-800">
                    查看详情
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="md:hidden space-y-3">
        {papers.map((paper) => (
          <Link
            key={paper.id}
            href={`/papers/${paper.id}`}
            className="block bg-white rounded-xl shadow-sm border border-gray-100 p-4 hover:shadow-md transition-shadow"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="text-sm font-semibold text-gray-900 line-clamp-2">{paper.title}</h3>
              <StatusBadge status={paper.status} />
            </div>
            <div className="flex items-center gap-3 text-xs text-gray-500">
              <span>{paper.filename}</span>
              <span>{paper.chunk_count} chunks</span>
              <span>{new Date(paper.created_at).toLocaleDateString("zh-CN")}</span>
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
