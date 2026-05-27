import Link from "next/link";

interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  actions?: { label: string; href: string; primary?: boolean }[];
}

export default function EmptyState({ icon = "📄", title, description, actions }: EmptyStateProps) {
  return (
    <div className="text-center py-12 px-4">
      <div className="text-4xl mb-3">{icon}</div>
      <h3 className="text-lg font-semibold text-gray-700 mb-1">{title}</h3>
      {description && <p className="text-sm text-gray-500 max-w-md mx-auto mb-4">{description}</p>}
      {actions && actions.length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {actions.map((a) => (
            <Link
              key={a.href + a.label}
              href={a.href}
              className={`inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                a.primary
                  ? "bg-blue-600 text-white hover:bg-blue-700"
                  : "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50"
              }`}
            >
              {a.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
