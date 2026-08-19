// frontend/src/components/heatmap/CaseHotspotMap.tsx
'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Hotspot } from '@/services/rescue-cases.service';

export default function CaseHotspotMap({ hotspots }: { hotspots: Hotspot[] }) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const layerGroup = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;
    const map = L.map(mapRef.current).setView([6.0, 80.3], 10);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(map);
    layerGroup.current = L.layerGroup().addTo(map);
    mapInstance.current = map;
    return () => { map.remove(); mapInstance.current = null; };
  }, []);

  useEffect(() => {
    const map = mapInstance.current;
    const group = layerGroup.current;
    if (!map || !group) return;
    group.clearLayers();

    hotspots.forEach((h) => {
      const radius = 8 + Math.min(h.count, 20) * 2;
      const color = h.is_active_outbreak ? '#DC2626' : '#EF9F27';
      const marker = L.circleMarker([h.grid_lat, h.grid_lng], {
        radius, color, fillColor: color, fillOpacity: 0.5, weight: 2,
      }).addTo(group);

      const breakdown = Object.entries(h.animal_breakdown)
        .map(([type, n]) => `${type}: ${n}`).join(', ');
      const lastReport = new Date(h.latest_report_at).toLocaleDateString();

      marker.bindPopup(`
        <div style="font-size: 12px; line-height: 1.5;">
          ${h.is_active_outbreak
            ? `<strong style="color:#DC2626;">⚠ Active Outbreak: ${h.outbreak_animal_types.join(', ')}</strong><br/>`
            : ''}
          <strong>${h.count} case${h.count > 1 ? 's' : ''} reported</strong><br/>
          ${breakdown}<br/>
          Last report: ${lastReport}
        </div>
      `);
    });
  }, [hotspots]);

  return <div ref={mapRef} style={{ height: '500px', width: '100%', borderRadius: '8px' }} />;
}