import { fetchPapers, type PaperListItem } from "@/lib/api";
import { getServerUserId } from "@/lib/server-user";
import PaperTable from "@/components/PaperTable";
import UploadForm from "@/components/UploadForm";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";

export const dynamic = "force-dynamic";

interface PapersPageProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function PapersPage({ searchParams }: PapersPageProps) {
  await searchParams;
  let papers: PaperListItem[] = [];
  let fetchError = false;
  try {
    const res = await fetchPapers(await getServerUserId());
    papers = res.papers;
  } catch {
    fetchError = true;
  }

  const completedCount = papers.filter((p) => p.status === "completed").length;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="论文库"
        description={`共 ${papers.length} 篇论文，${completedCount} 篇已完成解析`}
        actions={[
          { label: "跨论文问答", href: "/papers/ask", primary: true },
          { label: "Idea 列表", href: "/ideas", primary: false },
        ]}
      />

      {fetchError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-sm text-red-700">无法连接后端服务，请确认 Docker 容器已启动。</p>
        </div>
      )}

      {!fetchError && papers.length === 0 && (
        <EmptyState
          icon="📚"
          title="暂无论文"
          description="上传 PDF 论文或运行 seed_demo.py 导入示例数据"
          actions={[
            { label: "上传论文", href: "#upload", primary: true },
            { label: "跨论文问答", href: "/papers/ask", primary: false },
          ]}
        />
      )}

      {papers.length > 0 && (
        <div className="mb-6">
          <PaperTable papers={papers} />
        </div>
      )}

      <div id="upload" className="mt-6">
        <UploadForm />
      </div>
    </div>
  );
}
