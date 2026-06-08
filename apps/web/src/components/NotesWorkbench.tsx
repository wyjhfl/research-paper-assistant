"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  createResearchNote,
  deleteResearchNote,
  fetchResearchNotes,
  getErrorMessage,
  type ResearchNoteItem,
} from "@/lib/api";

const NOTE_TYPE_LABELS: Record<string, string> = {
  manual: "手动笔记",
  qa_answer: "问答收藏",
  source_snippet: "来源片段",
  review_matrix: "综述表",
  idea: "Idea",
};

function noteTypeLabel(type: string): string {
  return NOTE_TYPE_LABELS[type] ?? type;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function noteToMarkdown(note: ResearchNoteItem): string {
  const tags = note.tags.length > 0 ? `\n\nTags: ${note.tags.join(", ")}` : "";
  const source = note.paper_title
    ? `\n\nSource: ${note.paper_title}${note.source?.chunk_index != null ? ` / chunk #${note.source.chunk_index}` : ""}`
    : "";
  return [`# ${note.title}`, "", note.content, source, tags].join("\n");
}

export default function NotesWorkbench() {
  const [notes, setNotes] = useState<ResearchNoteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [filter, setFilter] = useState("all");

  async function loadNotes() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchResearchNotes();
      setNotes(res.notes);
    } catch (err) {
      setError(getErrorMessage(err, "加载研究笔记失败"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadNotes();
  }, []);

  const filteredNotes = useMemo(() => {
    if (filter === "all") return notes;
    return notes.filter((note) => note.note_type === filter);
  }, [filter, notes]);

  async function saveManualNote(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const res = await createResearchNote({
        title,
        content,
        note_type: "manual",
        tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
      });
      setNotes((prev) => [res.note, ...prev]);
      setTitle("");
      setContent("");
      setTags("");
    } catch (err) {
      setError(getErrorMessage(err, "保存研究笔记失败"));
    } finally {
      setSaving(false);
    }
  }

  async function removeNote(noteId: number) {
    setError(null);
    try {
      await deleteResearchNote(noteId);
      setNotes((prev) => prev.filter((note) => note.id !== noteId));
    } catch (err) {
      setError(getErrorMessage(err, "删除研究笔记失败"));
    }
  }

  async function copyNote(note: ResearchNoteItem) {
    try {
      await navigator.clipboard.writeText(noteToMarkdown(note));
      setCopiedId(note.id);
      window.setTimeout(() => setCopiedId(null), 1600);
    } catch {
      setError("复制失败，请手动选择笔记内容复制");
    }
  }

  const noteTypes = Array.from(new Set(notes.map((note) => note.note_type)));

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-800">新建手动笔记</h2>
        <p className="mt-1 text-sm text-gray-500">
          用来记录阅读想法、实验计划或 related work 草稿。问答回答和来源片段也可以从对应页面一键收藏。
        </p>
        <form onSubmit={saveManualNote} className="mt-4 space-y-3">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="笔记标题"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="笔记内容"
            rows={8}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            placeholder="标签，用逗号分隔"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={saving || !title.trim() || !content.trim()}
            className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "保存中..." : "保存笔记"}
          </button>
        </form>
      </section>

      <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">研究笔记工作台</h2>
            <p className="mt-1 text-sm text-gray-500">共 {notes.length} 条笔记，支持复制为 Markdown。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setFilter("all")}
              className={`rounded-full border px-3 py-1 text-xs ${filter === "all" ? "border-blue-600 bg-blue-600 text-white" : "border-gray-300 text-gray-600"}`}
            >
              全部
            </button>
            {noteTypes.map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => setFilter(type)}
                className={`rounded-full border px-3 py-1 text-xs ${filter === type ? "border-blue-600 bg-blue-600 text-white" : "border-gray-300 text-gray-600"}`}
              >
                {noteTypeLabel(type)}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading ? (
          <p className="text-sm text-gray-500">正在加载研究笔记...</p>
        ) : filteredNotes.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-200 p-6 text-center">
            <p className="text-sm text-gray-500">暂无笔记。可以先保存一条手动笔记，或在问答页面收藏回答和来源片段。</p>
            <Link href="/papers/ask" className="mt-2 inline-block text-sm text-blue-600 hover:underline">
              前往跨论文问答
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredNotes.map((note) => (
              <article key={note.id} className="rounded-lg border border-gray-200 p-4">
                <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-gray-800">{note.title}</h3>
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
                        {noteTypeLabel(note.note_type)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-gray-500">{formatDate(note.created_at)}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => copyNote(note)}
                      className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                    >
                      {copiedId === note.id ? "已复制" : "复制"}
                    </button>
                    <button
                      type="button"
                      onClick={() => removeNote(note.id)}
                      className="rounded border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                    >
                      删除
                    </button>
                  </div>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">{note.content}</p>
                {(note.paper_title || note.source?.chunk_index != null || note.tags.length > 0) && (
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500">
                    {note.paper_title && <span>论文：{note.paper_title}</span>}
                    {note.source?.chunk_index != null && note.paper_id != null && note.chunk_id != null && (
                      <Link href={`/papers/${note.paper_id}#chunk-${note.chunk_id}`} className="text-blue-600 hover:underline">
                        定位 chunk #{note.source.chunk_index}
                      </Link>
                    )}
                    {note.tags.map((tag) => (
                      <span key={tag} className="rounded bg-gray-100 px-2 py-0.5">#{tag}</span>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
