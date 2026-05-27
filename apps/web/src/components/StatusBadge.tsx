interface StatusBadgeProps {
  status: string;
}

const STYLES: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  answered: "bg-green-100 text-green-700",
  pending: "bg-yellow-100 text-yellow-700",
  running: "bg-blue-100 text-blue-700",
  failed: "bg-red-100 text-red-700",
  insufficient_context: "bg-yellow-100 text-yellow-700",
};

const LABELS: Record<string, string> = {
  completed: "已完成",
  answered: "已回答",
  pending: "处理中",
  running: "运行中",
  failed: "失败",
  insufficient_context: "上下文不足",
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${STYLES[status] || "bg-gray-100 text-gray-700"}`}>
      {LABELS[status] || status}
    </span>
  );
}
