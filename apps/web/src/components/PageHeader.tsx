import Link from "next/link";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: { label: string; href: string; primary?: boolean }[];
}

export default function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          {description && <p className="mt-1 text-sm text-gray-500 leading-relaxed">{description}</p>}
        </div>
        {actions && actions.length > 0 && (
          <div className="flex flex-wrap gap-2 shrink-0">
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
    </div>
  );
}
