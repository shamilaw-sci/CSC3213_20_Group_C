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
    // Scroll-wheel zoom is off because the map now sits on a page that
    // scrolls — otherwise scrolling past it traps the page. Zoom controls,
    // double-click and pinch still work.
    const map = L.map(mapRef.current, { scrollWheelZoom: false }).setView([6.0, 80.3], 10);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(map);
    layerGroup.current = L.layerGroup().addTo(map);
    mapInstance.current = map;

    // The container is sized by its parent's CSS rather than a fixed inline
    // height, so Leaflet can initialise before the box has its final size. If
    // that happens the circle overlays project to a zero radius and render as
    // "M0 0" — invisible — even though the tiles look fine. Re-measuring on
    // every resize, including the first layout pass, re-projects them.
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(mapRef.current);

    return () => {
      observer.disconnect();
      map.remove();
      mapInstance.current = null;
    };
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

  // Fills whatever the parent sizes it to, so the page controls the height
  // rather than a hard-coded 500px.
  return <div ref={mapRef} className="h-full w-full" />;
}