// frontend/src/components/heatmap/RouteMap.tsx
'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { RouteStop } from '@/types';

interface Props {
  start: { lat: number; lng: number };
  stops: RouteStop[];
  // Dashed rather than solid when the legs are straight-line estimates, so the
  // map itself signals that it is not showing real roads.
  approximate?: boolean;
  onSelectStop?: (caseId: string) => void;
  selectedCaseId?: string | null;
}

const ACCENT = '#EF9F27';
const START_COLOR = '#2563EB';

// Numbered markers are built as divIcons rather than image pins: the visit
// order is the entire point of this map, and a number rendered into the marker
// keeps it legible without a legend or a click.
function numberedIcon(sequence: number, selected: boolean): L.DivIcon {
  const size = selected ? 34 : 28;
  return L.divIcon({
    className: '',
    html: `<div style="
      width:${size}px;height:${size}px;border-radius:50%;
      background:${ACCENT};color:#fff;
      display:flex;align-items:center;justify-content:center;
      font-weight:700;font-size:${selected ? 15 : 13}px;
      border:${selected ? 3 : 2}px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,.4);
    ">${sequence}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function startIcon(): L.DivIcon {
  return L.divIcon({
    className: '',
    html: `<div style="
      width:18px;height:18px;border-radius:50%;
      background:${START_COLOR};border:3px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,.4);
    "></div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

export default function RouteMap({
  start,
  stops,
  approximate = false,
  onSelectStop,
  selectedCaseId,
}: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const layerGroup = useRef<L.LayerGroup | null>(null);

  // Held in a ref so the draw effect below does not need onSelectStop in its
  // dependency array — a parent that passes an inline arrow would otherwise
  // redraw every marker on each render and fight the user's map interaction.
  const selectHandler = useRef(onSelectStop);
  selectHandler.current = onSelectStop;

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    // Scroll-wheel zoom off for the same reason as OutbreakZoneMap: this map
    // sits on a scrolling page and would otherwise trap the scroll.
    const map = L.map(mapRef.current, { scrollWheelZoom: false }).setView(
      [start.lat, start.lng],
      13,
    );
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(map);
    layerGroup.current = L.layerGroup().addTo(map);
    mapInstance.current = map;

    // Same fix as OutbreakZoneMap: the container is sized by its parent's CSS,
    // so Leaflet can initialise before the box has its final height and project
    // the polyline to nothing. Re-measuring on resize re-projects it.
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

    L.marker([start.lat, start.lng], { icon: startIcon() })
      .addTo(group)
      .bindPopup('<strong>Your starting point</strong>');

    const path: [number, number][] = [
      [start.lat, start.lng],
      ...stops.map((s) => [s.case.lat, s.case.lng] as [number, number]),
    ];

    if (stops.length > 0) {
      L.polyline(path, {
        color: ACCENT,
        weight: 3,
        opacity: 0.8,
        // The dash is load-bearing, not decorative: it distinguishes a
        // straight-line estimate from a real road route at a glance.
        dashArray: approximate ? '8, 8' : undefined,
      }).addTo(group);
    }

    stops.forEach((stop) => {
      const selected = stop.case.id === selectedCaseId;
      const marker = L.marker([stop.case.lat, stop.case.lng], {
        icon: numberedIcon(stop.sequence, selected),
        zIndexOffset: selected ? 1000 : 0,
      }).addTo(group);

      marker.bindPopup(`
        <div style="font-size:12px;line-height:1.5;">
          <strong>#${stop.sequence} &middot; ${stop.case.animal_type}</strong><br/>
          Urgency: ${stop.case.urgency}<br/>
          ${stop.leg_distance_km.toFixed(1)} km &middot; ~${Math.round(stop.leg_duration_min)} min from previous
        </div>
      `);

      marker.on('click', () => selectHandler.current?.(stop.case.id));
    });

    // Fit to the whole route, including the start, so nothing sits off-screen.
    // maxZoom stops a single nearby case from zooming to street level.
    map.fitBounds(L.latLngBounds(path), { padding: [45, 45], maxZoom: 14 });
  }, [start.lat, start.lng, stops, approximate, selectedCaseId]);

  return <div ref={mapRef} className="h-full w-full" />;
}
