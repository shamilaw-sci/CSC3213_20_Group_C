// frontend/src/components/heatmap/CaseHotspotMapWrapper.tsx
'use client';

import dynamic from 'next/dynamic';

const CaseHotspotMap = dynamic(() => import('./CaseHotspotMap'), { ssr: false });

export default function CaseHotspotMapWrapper(props: React.ComponentProps<typeof CaseHotspotMap>) {
  return <CaseHotspotMap {...props} />;
}