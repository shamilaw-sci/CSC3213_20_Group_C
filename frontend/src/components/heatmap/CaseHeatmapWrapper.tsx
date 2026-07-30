// components/CaseHeatmapWrapper.tsx
'use client';

import dynamic from 'next/dynamic';

const CaseHeatmap = dynamic(() => import('./CaseHeatmap'), { ssr: false });

export default CaseHeatmapWrapper;

function CaseHeatmapWrapper(props: React.ComponentProps<typeof CaseHeatmap>) {
  return <CaseHeatmap {...props} />;
}