import { CompareViewer } from '@/components/compare-viewer';

export default async function ComparePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CompareViewer id={id} />;
}
