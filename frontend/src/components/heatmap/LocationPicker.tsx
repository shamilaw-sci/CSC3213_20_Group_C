// frontend/src/components/heatmap/LocationPicker.tsx
'use client';

import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

interface Props {
  initialLat: number;
  initialLng: number;
  // 15 is street level, for a position the browser found. The report page
  // opens zoomed out on the whole island when it has no position to offer.
  initialZoom?: number;
  onChange: (lat: number, lng: number) => void;
}

export default function LocationPicker({ initialLat, initialLng, initialZoom = 15, onChange }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    const map = L.map(mapRef.current).setView([initialLat, initialLng], initialZoom);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(map);

    const marker = L.marker([initialLat, initialLng], { draggable: true }).addTo(map);
    marker.on('dragend', () => {
      const pos = marker.getLatLng();
      onChange(pos.lat, pos.lng);
    });

    map.on('click', (e) => {
      marker.setLatLng(e.latlng);
      onChange(e.latlng.lat, e.latlng.lng);
    });

    markerRef.current = marker;
    mapInstance.current = map;

    return () => { map.remove(); mapInstance.current = null; };
  }, []);

  return (
    <div>
      <p className="text-xs text-text-secondary mb-2">
        Drag the pin (or tap the map) to the exact location if it&apos;s not quite right:
      </p>
      <div ref={mapRef} style={{ height: '250px', width: '100%', borderRadius: '8px' }} />
    </div>
  );
}