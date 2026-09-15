// frontend/src/components/heatmap/RouteMapWrapper.tsx
'use client';

import dynamic from 'next/dynamic';

// Leaflet touches `window` at module scope, so RouteMap must never be imported
// directly by a page — a direct import fails `npm run build` with
// "window is not defined". ssr: false is only valid inside a Client Component,
// which is what the 'use client' above makes this file.
const RouteMap = dynamic(() => import('./RouteMap'), { ssr: false });

export default function RouteMapWrapper(props: React.ComponentProps<typeof RouteMap>) {
  return <RouteMap {...props} />;
}
