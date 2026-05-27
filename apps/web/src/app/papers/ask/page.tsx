import PageHeader from "@/components/PageHeader";
import MultiPaperQA from "@/components/MultiPaperQA";

export default function AskPage() {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="跨论文问答"
        description="在所有已完成论文中检索相关片段，基于 RAG 生成带引用来源的回答。不选择论文则全库检索。"
        actions={[
          { label: "论文库", href: "/papers", primary: false },
          { label: "Agent 工作流", href: "/agent", primary: false },
        ]}
      />
      <MultiPaperQA />
    </div>
  );
}
