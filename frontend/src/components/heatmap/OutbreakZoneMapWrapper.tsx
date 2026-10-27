// frontend/src/components/heatmap/OutbreakZoneMapWrapper.tsx
'use client';

import dynamic from 'next/dynamic';

const OutbreakZoneMap = dynamic(() => import('./OutbreakZoneMap'), { ssr: false });

export default function OutbreakZoneMapWrapper(props: React.ComponentProps<typeof OutbreakZoneMap>) {
  return <OutbreakZoneMap {...props} />;
}