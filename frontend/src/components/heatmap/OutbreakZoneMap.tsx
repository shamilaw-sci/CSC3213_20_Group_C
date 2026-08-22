// frontend/src/components/heatmap/OutbreakZoneMap.tsx
'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { OutbreakZone } from '@/services/rescue-cases.service';

export default function OutbreakZoneMap({ zones }: { zones: OutbreakZone[] }) {
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

    zones.forEach((z) => {
      const circle = L.circle([z.center_lat, z.center_lng], {
        radius: z.radius_km * 1000,
        color: '#DC2626',
        fillColor: '#DC2626',
        fillOpacity: 0.15,
        weight: 2,
      }).addTo(group);

      circle.bindPopup(`
        <div style="font-size: 12px; line-height: 1.5;">
          <strong style="color:#DC2626;">⚠ ${z.title}</strong><br/>
          Animal: ${z.animal_type}<br/>
          ${z.description ? `${z.description}<br/>` : ''}
          Declared: ${new Date(z.declared_at).toLocaleDateString()}
        </div>
      `);
    });

    if (zones.length > 0) {
      const bounds = L.latLngBounds(zones.map((z) => [z.center_lat, z.center_lng] as [number, number]));
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 });
    }
  }, [zones]);

  return <div ref={mapRef} style={{ height: '500px', width: '100%', borderRadius: '8px' }} />;
}