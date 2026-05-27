import PageHeader from "@/components/PageHeader";
import UsageDashboard from "@/components/UsageDashboard";

export const dynamic = "force-dynamic";

export default function UsagePage() {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="模型调用与质量看板"
        description="查看模型调用审计摘要、最近调用记录和真实模型评测状态"
        actions={[
          { label: "论文库", href: "/papers", primary: false },
          { label: "Agent", href: "/agent", primary: false },
        ]}
      />
      <UsageDashboard />
    </div>
  );
}
