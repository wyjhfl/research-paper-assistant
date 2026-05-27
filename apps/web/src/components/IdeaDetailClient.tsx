"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { deleteIdea, getErrorMessage } from "@/lib/api";

interface IdeaDetailClientProps {
  ideaId: number;
}

export default function IdeaDetailClient({ ideaId }: IdeaDetailClientProps) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleDelete() {
    if (!confirm("确定要删除这个 Idea 吗？删除后不可恢复。")) return;

    setDeleting(true);
    setError(null);

    try {
      await deleteIdea(ideaId);
      router.push("/ideas");
    } catch (err) {
      setError(getErrorMessage(err, "删除失败"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="shrink-0">
      <button
        onClick={handleDelete}
        disabled={deleting}
        className="rounded-lg px-3 py-1.5 text-xs font-medium bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {deleting ? "删除中..." : "删除 Idea"}
      </button>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
