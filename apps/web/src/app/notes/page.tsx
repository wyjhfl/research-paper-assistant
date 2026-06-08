import PageHeader from "@/components/PageHeader";
import NotesWorkbench from "@/components/NotesWorkbench";

export default function NotesPage() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="研究笔记"
        description="保存问答回答、来源片段、综述表条目和手动阅读想法，把零散检索结果沉淀为可复用的本地笔记。"
        actions={[
          { label: "跨论文问答", href: "/papers/ask", primary: true },
          { label: "文献综述表", href: "/papers/review", primary: false },
        ]}
      />
      <NotesWorkbench />
    </div>
  );
}
