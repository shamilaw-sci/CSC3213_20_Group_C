// frontend/src/components/heatmap/CaseHeatmap.tsx
'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet.heat';
import { OutbreakZone } from '@/services/rescue-cases.service';

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
  outbreakZones?: OutbreakZone[];
  declareMode?: boolean;
  previewCenter?: { lat: number; lng: number } | null;
  previewRadiusKm?: number;
  onMapClick?: (lat: number, lng: number) => void;
}

export default function CaseHeatmap({
  cases, outbreakZones = [], declareMode, previewCenter, previewRadiusKm, onMapClick,
}: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const zoneLayer = useRef<L.LayerGroup | null>(null);
  const previewLayer = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;
    const map = L.map(mapRef.current).setView([6.0, 80.3], 10);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(map);
    zoneLayer.current = L.layerGroup().addTo(map);
    previewLayer.current = L.layerGroup().addTo(map);
    mapInstance.current = map;
    return () => { map.remove(); mapInstance.current = null; };
  }, []);

  // heat layer for cases
  useEffect(() => {
    const map = mapInstance.current;
    if (!map || cases.length === 0) return;
    const points: [number, number, number][] = cases.map((c) => [c.lat, c.lng, 1]);
    // @ts-expect-error — leaflet.heat has no official types
    const heatLayer = L.heatLayer(points, { radius: 40, blur: 25, maxZoom: 12 });
    heatLayer.addTo(map);
    return () => { map.removeLayer(heatLayer); };
  }, [cases]);

  // click handler, only active while declaring
  useEffect(() => {
    const map = mapInstance.current;
    if (!map || !onMapClick) return;
    const handler = (e: L.LeafletMouseEvent) => onMapClick(e.latlng.lat, e.latlng.lng);
    if (declareMode) map.on('click', handler);
    return () => { map.off('click', handler); };
  }, [declareMode, onMapClick]);

  // existing declared zones, always shown
  useEffect(() => {
    const group = zoneLayer.current;
    if (!group) return;
    group.clearLayers();
    outbreakZones.forEach((z) => {
      L.circle([z.center_lat, z.center_lng], {
        radius: z.radius_km * 1000,
        color: '#DC2626', fillColor: '#DC2626', fillOpacity: 0.1, weight: 2,
      }).bindPopup(`<strong>${z.title}</strong><br/>${z.animal_type}${z.is_active ? '' : ' (resolved)'}`).addTo(group);
    });
  }, [outbreakZones]);

  // live preview circle while declaring
  useEffect(() => {
    const group = previewLayer.current;
    if (!group) return;
    group.clearLayers();
    if (previewCenter && previewRadiusKm) {
      L.circle([previewCenter.lat, previewCenter.lng], {
        radius: previewRadiusKm * 1000,
        color: '#EF9F27', fillColor: '#EF9F27', fillOpacity: 0.15, weight: 2, dashArray: '6 4',
      }).addTo(group);
      L.marker([previewCenter.lat, previewCenter.lng]).addTo(group);
    }
  }, [previewCenter, previewRadiusKm]);

  return <div ref={mapRef} style={{ height: '500px', width: '100%', borderRadius: '8px' }} />;
}