import PaperDetailClient from "@/components/PaperDetailClient";

export const dynamic = "force-dynamic";

interface PaperDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function PaperDetailPage({ params }: PaperDetailPageProps) {
  const { id } = await params;
  return <PaperDetailClient paperId={parseInt(id, 10)} />;
}
