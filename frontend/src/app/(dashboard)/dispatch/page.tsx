// frontend/src/app/(dashboard)/dispatch/page.tsx
'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { useQuery } from '@tanstack/react-query';
import { RescueCasesService } from '@/services/rescue-cases.service';
import RouteMapWrapper from '@/components/heatmap/RouteMapWrapper';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn, getErrorMessage } from '@/lib/utils';
import { CaseOut } from '@/types';
import {
  AlertTriangle, MapPin, Navigation, RefreshCw, Crosshair, Route, CheckCircle2,
} from 'lucide-react';

// LocationPicker touches Leaflet, so it gets the same ssr:false treatment as
// every other map component. Imported inline here rather than via a *Wrapper
// file, matching how /report already consumes it.
const LocationPicker = dynamic(
  () => import('@/components/heatmap/LocationPicker'),
  { ssr: false },
);

// Colombo. Only used as the initial centre for the manual picker when we have
// no position at all — never sent to the backend as a real location.
const FALLBACK_CENTER = { lat: 6.9271, lng: 79.8612 };

// Matches URGENCY_ACCENT in case-triage so the colour language stays consistent
// across the two pages a field staff member actually uses.
const URGENCY_ACCENT: Record<CaseOut['urgency'], { bg: string; text: string }> = {
  Critical: { bg: '#DC2626', text: '#FFFFFF' },
  High: { bg: '#EF9F27', text: '#FFFFFF' },
  Medium: { bg: 'transparent', text: '#6B7280' },
  Low: { bg: 'transparent', text: '#9CA3AF' },
};

function UrgencyBadge({ urgency }: { urgency: CaseOut['urgency'] }) {
  const accent = URGENCY_ACCENT[urgency] || URGENCY_ACCENT.Medium;
  const outlined = accent.bg === 'transparent';
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{
        background: accent.bg,
        color: accent.text,
        border: outlined ? '1px solid currentColor' : 'none',
      }}
    >
      {urgency}
    </span>
  );
}

type GeoState = 'pending' | 'granted' | 'denied' | 'unsupported';

export default function DispatchPage() {
  const { user } = useAuthStore();
  const canView = user && hasPermission(user.role, 'rescue:read');

  const [origin, setOrigin] = useState<{ lat: number; lng: number } | null>(null);
  const [geoState, setGeoState] = useState<GeoState>('pending');
  const [showPicker, setShowPicker] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  useEffect(() => {
    if (!navigator.geolocation) {
      setGeoState('unsupported');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setOrigin({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGeoState('granted');
      },
      // Covers denial, timeout and position-unavailable alike: in all three we
      // have no position, and the response is the same — offer the manual pin.
      () => setGeoState('denied'),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  }, []);

  const { data: route, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ['myRoute', origin?.lat, origin?.lng],
    queryFn: () => RescueCasesService.getMyRoute(origin!.lat, origin!.lng),
    // No origin means nothing to route from. Waiting is correct here; firing
    // with a fallback coordinate would silently plan a route from Colombo for
    // someone standing in Kandy.
    enabled: !!origin && !!canView,
  });

  if (!canView) {
    return (
      <div className="rounded-card border border-border-brand bg-surface p-8 text-center">
        <AlertTriangle className="mx-auto mb-3 text-text-secondary" size={28} />
        <p className="text-text-primary font-semibold">Not available for your role</p>
        <p className="text-sm text-text-secondary mt-1">
          Field dispatch requires rescue case access.
        </p>
      </div>
    );
  }

  const pickerCenter = origin ?? FALLBACK_CENTER;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-heading text-text-primary flex items-center gap-2">
            <Navigation size={22} className="text-accent" />
            Field Dispatch
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Your open cases, ordered into an efficient visiting route.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowPicker((v) => !v)}
          >
            <Crosshair size={15} className="mr-1.5" />
            {showPicker ? 'Hide' : 'Set'} start point
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={!origin || isFetching}
          >
            <RefreshCw size={15} className={cn('mr-1.5', isFetching && 'animate-spin')} />
            Recalculate
          </Button>
        </div>
      </div>

      {/* Geolocation on a desktop is frequently off by kilometres, so the
          correction affordance is offered even on success — not only on
          failure, which would leave a confidently-wrong position unfixable. */}
      {geoState === 'granted' && !showPicker && (
        <p className="text-xs text-text-secondary flex items-center gap-1.5">
          <MapPin size={13} className="text-accent" />
          Starting from your detected location. Not right?{' '}
          <button
            className="underline hover:text-text-primary"
            onClick={() => setShowPicker(true)}
          >
            Set it manually
          </button>
          .
        </p>
      )}

      {(geoState === 'denied' || geoState === 'unsupported') && !origin && (
        <div className="rounded-card border border-border-brand bg-surface p-4">
          <p className="text-sm text-text-primary font-medium flex items-center gap-2">
            <MapPin size={15} className="text-accent" />
            {geoState === 'unsupported'
              ? 'This browser cannot report your location.'
              : 'Location access was not granted.'}
          </p>
          <p className="text-xs text-text-secondary mt-1">
            Drop a pin below to set your starting point and the route will be built from there.
          </p>
          <Button size="sm" className="mt-3" onClick={() => setShowPicker(true)}>
            Drop a pin
          </Button>
        </div>
      )}

      {geoState === 'pending' && !origin && (
        <p className="text-xs text-text-secondary">Detecting your location…</p>
      )}

      {showPicker && (
        <div className="rounded-card border border-border-brand bg-surface p-4">
          <LocationPicker
            initialLat={pickerCenter.lat}
            initialLng={pickerCenter.lng}
            onChange={(lat, lng) => {
              setOrigin({ lat, lng });
              setGeoState('granted');
            }}
          />
          <p className="text-xs text-text-secondary mt-2">
            Start point: {pickerCenter.lat.toFixed(4)}, {pickerCenter.lng.toFixed(4)}
          </p>
        </div>
      )}

      {/* Straight-line fallback is stated plainly rather than hidden — the
          numbers are still useful, but only if you know what they are. */}
      {route && !route.used_road_distances && route.stops.length > 0 && (
        <div className="rounded-card border border-amber-500/40 bg-amber-500/5 p-3">
          <p className="text-xs text-amber-600 dark:text-amber-400 flex items-start gap-2">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            {route.degraded_reason ??
              'Showing straight-line estimates rather than road distances.'}
          </p>
        </div>
      )}

      {error && (
        <div className="rounded-card border border-red-500/40 bg-red-500/5 p-4">
          <p className="text-sm text-red-500 flex items-center gap-2">
            <AlertTriangle size={15} />
            {getErrorMessage(error)}
          </p>
          <Button size="sm" variant="outline" className="mt-3" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      )}

      {isLoading && origin && (
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <Skeleton className="h-[520px] rounded-card" />
          <div className="space-y-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 rounded-card" />)}
          </div>
        </div>
      )}

      {route && route.stops.length === 0 && (
        <div className="rounded-card border border-border-brand bg-surface p-10 text-center">
          <CheckCircle2 className="mx-auto mb-3 text-accent" size={30} />
          <p className="text-text-primary font-semibold">No cases assigned to you</p>
          <p className="text-sm text-text-secondary mt-1">
            When a case is assigned to you it will appear here with a route.
          </p>
        </div>
      )}

      {route && route.stops.length > 0 && origin && (
        <>
          <div className="flex flex-wrap gap-3">
            <SummaryChip
              icon={<Route size={15} />}
              label="Stops"
              value={String(route.stops.length)}
            />
            <SummaryChip
              icon={<Navigation size={15} />}
              label={route.used_road_distances ? 'Total driving' : 'Total (straight line)'}
              value={`${route.total_distance_km.toFixed(1)} km`}
            />
            <SummaryChip
              icon={<RefreshCw size={15} />}
              label="Estimated time"
              value={formatMinutes(route.total_duration_min)}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <div className="h-[520px] overflow-hidden rounded-card border border-border-brand bg-surface">
              <RouteMapWrapper
                start={origin}
                stops={route.stops}
                approximate={!route.used_road_distances}
                selectedCaseId={selectedCaseId}
                onSelectStop={setSelectedCaseId}
              />
            </div>

            <ol className="space-y-3 lg:max-h-[520px] lg:overflow-y-auto lg:pr-1">
              {route.stops.map((stop) => (
                <li key={stop.case.id}>
                  <button
                    onClick={() => setSelectedCaseId(stop.case.id)}
                    className={cn(
                      'w-full rounded-card border bg-surface p-3 text-left transition-colors',
                      stop.case.id === selectedCaseId
                        ? 'border-accent'
                        : 'border-border-brand hover:border-accent/50',
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-white">
                        {stop.sequence}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate font-semibold text-text-primary">
                            {stop.case.animal_type}
                          </p>
                          <UrgencyBadge urgency={stop.case.urgency} />
                        </div>
                        {stop.case.description && (
                          <p className="mt-0.5 line-clamp-2 text-xs text-text-secondary">
                            {stop.case.description}
                          </p>
                        )}
                        <p className="mt-1.5 text-xs text-text-secondary">
                          {stop.leg_distance_km.toFixed(1)} km ·{' '}
                          {formatMinutes(stop.leg_duration_min)} from previous
                        </p>
                        <p className="text-[11px] text-text-secondary/70">
                          {stop.cumulative_distance_km.toFixed(1)} km ·{' '}
                          {formatMinutes(stop.cumulative_duration_min)} cumulative
                        </p>
                      </div>
                    </div>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        </>
      )}
    </div>
  );
}

function SummaryChip({ icon, label, value }: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-[130px] rounded-card border border-border-brand bg-surface px-4 py-2.5 shadow-card">
      <p className="text-xl font-bold font-heading leading-none text-text-primary">
        {value}
      </p>
      <p className="mt-1 flex items-center gap-1.5 text-xs text-text-secondary">
        {icon}
        {label}
      </p>
    </div>
  );
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}
