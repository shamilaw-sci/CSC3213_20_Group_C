// components/CaseHeatmap.tsx
'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet.heat';

interface CaseGeoPoint {
  id: string;
  animal_type: string;
  status: string;
  lat: number;
  lng: number;
  reported_at: string;
}

interface Props {
  cases: CaseGeoPoint[];
}

export default function CaseHeatmap({ cases }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    // Center roughly on Southern Province, Sri Lanka — adjust to VFF's actual area
    const map = L.map(mapRef.current).setView([6.0, 80.3], 10);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(map);

    mapInstance.current = map;

    return () => {
      map.remove();
      mapInstance.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapInstance.current;
    if (!map || cases.length === 0) return;

    const points: [number, number, number][] = cases.map((c) => [
      c.lat,
      c.lng,
      1, // intensity — could weight by status (e.g. Reported = higher urgency)
    ]);

    // @ts-expect-error — leaflet.heat has no official types
    const heatLayer = L.heatLayer(points, { radius: 40, blur: 25, maxZoom: 12 });
    heatLayer.addTo(map);

    return () => {
      map.removeLayer(heatLayer);
    };
  }, [cases]);

  return <div ref={mapRef} style={{ height: '500px', width: '100%', borderRadius: '8px' }} />;
}