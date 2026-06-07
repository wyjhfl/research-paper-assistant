import PageHeader from "@/components/PageHeader";
import ReviewMatrix from "@/components/ReviewMatrix";

export default function ReviewMatrixPage() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="文献综述表"
        description="把已完成论文整理为问题、方法、证据、指标、局限与未来工作的结构化矩阵，便于写 related work。"
        actions={[
          { label: "论文库", href: "/papers", primary: false },
          { label: "跨论文问答", href: "/papers/ask", primary: true },
        ]}
      />
      <ReviewMatrix />
    </div>
  );
}
