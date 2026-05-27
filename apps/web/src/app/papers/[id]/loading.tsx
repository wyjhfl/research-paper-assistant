export default function PaperDetailLoading() {
  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="h-4 w-24 bg-gray-200 rounded animate-pulse mb-4" />
      <div className="bg-white rounded-lg shadow p-6 mb-6 animate-pulse">
        <div className="h-8 bg-gray-200 rounded w-64 mb-4" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i}>
              <div className="h-4 bg-gray-200 rounded w-16 mb-2" />
              <div className="h-4 bg-gray-200 rounded w-24" />
            </div>
          ))}
        </div>
      </div>
      <div className="bg-white rounded-lg shadow p-6 animate-pulse">
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-gray-200 rounded" />
          ))}
        </div>
      </div>
    </div>
  );
}
