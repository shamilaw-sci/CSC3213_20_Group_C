// frontend/src/app/(dashboard)/cases/page.tsx
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { RescueCasesService } from '@/services/rescue-cases.service';
import CaseHeatmapWrapper from '@/components/heatmap/CaseHeatmapWrapper';
import { useAuthStore } from '@/store/useAuthStore';
import { hasPermission } from '@/lib/permissions';
import { toast } from 'sonner';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { cn, getErrorMessage } from '@/lib/utils';
import {
  AlertTriangle, RefreshCw, MapPin, Flame, ShieldAlert, Radar, Check,
} from 'lucide-react';

function StatChip({ label, value, tone }: {
  label: string;
  value: number;
  tone?: 'critical';
}) {
  return (
    <div
      className={cn(
        'rounded-card border border-border-brand bg-surface px-4 py-2.5 shadow-card min-w-[120px]',
        tone === 'critical' && value > 0 && 'border-red-500/40 bg-red-500/5'
      )}
    >
      <p
        className={cn(
          'text-xl font-bold font-heading leading-none text-text-primary',
          tone === 'critical' && value > 0 && 'text-red-500'
        )}
      >
        {value}
      </p>
      <p className="text-[10px] uppercase tracking-wider text-text-secondary mt-1">{label}</p>
    </div>
  );
}

// Mirrors what CaseHeatmap actually draws: a leaflet.heat density layer for
// cases, solid red circles for declared zones, and an amber dashed circle for
// the zone being placed. Without this the map is three unexplained colours.
function LegendItem({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-[10px] text-text-secondary">
      {swatch}
      {label}
    </span>
  );
}

export default function CaseHotspotsPage() {
  const { user } = useAuthStore();
  const canDeclare = hasPermission(user?.role || '', 'rescue:assign');
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [declareMode, setDeclareMode] = useState(false);
  const [center, setCenter] = useState<{ lat: number; lng: number } | null>(null);
  const [radiusKm, setRadiusKm] = useState(2);
  const [animalType, setAnimalType] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['rescueCases', 'geo', statusFilter],
    queryFn: () =>
      RescueCasesService.getCaseGeo(statusFilter === 'all' ? undefined : { status: statusFilter }),
  });

  const { data: zones } = useQuery({
    queryKey: ['outbreakZones'],
    queryFn: () => RescueCasesService.getOutbreakZones(),
  });

  const declareMutation = useMutation({
    mutationFn: () =>
      RescueCasesService.declareOutbreakZone({
        animal_type: animalType,
        title,
        description: description || undefined,
        center_lat: center!.lat,
        center_lng: center!.lng,
        radius_km: radiusKm,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['outbreakZones'] });
      toast.success('Outbreak zone declared — now visible on the public map');
      resetDeclareForm();
    },
    onError: (err) =>
      toast.error(getErrorMessage(err) || "Couldn't declare the outbreak. Please try again."),
  });

  function resetDeclareForm() {
    setDeclareMode(false);
    setCenter(null);
    setAnimalType('');
    setTitle('');
    setDescription('');
    setRadiusKm(2);
  }

  const declareReady = Boolean(center && animalType.trim() && title.trim());

  function handleSubmitDeclare() {
    if (!declareReady) {
      toast.error('Click a location on the map and fill in the animal type and title.');
      return;
    }
    declareMutation.mutate();
  }

  const activeZones = zones?.filter((z) => z.is_active).length ?? 0;
  const reportedCount = data?.filter((c) => c.status === 'Reported').length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight text-text-primary">
            Rescue Case Hotspots
          </h1>
          <p className="text-text-secondary text-sm mt-2 max-w-xl">
            Where reported cases cluster geographically. Use it to spot emerging
            concentrations and declare an outbreak zone that the public map will show.
          </p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isFetching}
          className="gap-2 shrink-0"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', isFetching && 'animate-spin')} aria-hidden="true" />
          Refresh
        </Button>
      </div>

      {data && (
        <div className="flex flex-wrap gap-3">
          <StatChip label="Cases plotted" value={data.length} />
          <StatChip label="Awaiting response" value={reportedCount} />
          <StatChip label="Active zones" value={activeZones} tone="critical" />
        </div>
      )}

      {/* Toolbar sits on its own tinted strip so the controls read as belonging
          to the map below rather than floating loose on the page. */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border-brand bg-bg-subtle dark:bg-bg-brand p-3">
        <div className="flex items-center gap-2">
          <Label htmlFor="status-filter" className="text-xs text-text-secondary shrink-0">
            Showing
          </Label>
          <Select
            value={statusFilter}
            onValueChange={(value) => { if (value !== null) setStatusFilter(value); }}
          >
            <SelectTrigger id="status-filter" className="w-[170px] bg-surface">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="Reported">Reported</SelectItem>
              <SelectItem value="In Treatment">In Treatment</SelectItem>
              <SelectItem value="Resolved">Resolved</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {canDeclare && (
          <Button
            variant={declareMode ? 'outline' : undefined}
            className={cn('gap-2', !declareMode && 'bg-[#DC2626] text-white hover:bg-[#DC2626]/90')}
            onClick={() => (declareMode ? resetDeclareForm() : setDeclareMode(true))}
          >
            {declareMode ? 'Cancel' : <><ShieldAlert className="h-4 w-4" aria-hidden="true" /> Declare Outbreak</>}
          </Button>
        )}
      </div>

      {declareMode && (
        <div className="rounded-card border-2 border-[#EF9F27]/50 bg-[#EF9F27]/5 overflow-hidden">
          <div className="flex items-center gap-2 bg-[#EF9F27]/15 px-4 py-2.5 border-b border-[#EF9F27]/30">
            <ShieldAlert className="h-4 w-4 text-[#EF9F27] shrink-0" aria-hidden="true" />
            <h2 className="text-sm font-bold text-text-primary">Declare an outbreak zone</h2>
            <span className="text-[10px] text-text-secondary ml-auto">
              Visible on the public map once confirmed
            </span>
          </div>

          <div className="p-4 space-y-4">
            {/* The location comes from clicking the map, which is not obvious
                from a form — so it is called out as an explicit first step
                that visibly completes. */}
            <div
              className={cn(
                'flex items-center gap-2.5 rounded-lg border p-3 transition-colors',
                center
                  ? 'border-green-600/40 bg-green-600/10'
                  : 'border-dashed border-border-brand bg-surface'
              )}
            >
              {center ? (
                <Check className="h-4 w-4 text-green-600 shrink-0" aria-hidden="true" />
              ) : (
                <MapPin className="h-4 w-4 text-text-muted shrink-0 animate-pulse" aria-hidden="true" />
              )}
              <p className="text-xs text-text-secondary">
                {center ? (
                  <>
                    Centre set to{' '}
                    <span className="font-mono text-text-primary">
                      {center.lat.toFixed(4)}, {center.lng.toFixed(4)}
                    </span>{' '}
                    — click the map again to move it.
                  </>
                ) : (
                  <>
                    <span className="font-semibold text-text-primary">Step 1:</span>{' '}
                    click a location on the map below to set the outbreak centre.
                  </>
                )}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="animal-type" className="text-xs">Animal type</Label>
                <Input
                  id="animal-type"
                  placeholder="e.g. Dog"
                  value={animalType}
                  onChange={(e) => setAnimalType(e.target.value)}
                  className="bg-surface"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="zone-title" className="text-xs">Title</Label>
                <Input
                  id="zone-title"
                  placeholder="e.g. Suspected mange outbreak"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="bg-surface"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="zone-desc" className="text-xs">
                Description <span className="text-text-muted font-normal">(optional)</span>
              </Label>
              <textarea
                id="zone-desc"
                placeholder="Anything responders should know before attending"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full border border-border-brand rounded-lg p-2.5 bg-surface text-sm placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
                rows={2}
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="zone-radius" className="text-xs">Radius</Label>
                <span className="text-xs font-mono font-semibold text-text-primary">
                  {radiusKm} km
                </span>
              </div>
              <input
                id="zone-radius"
                type="range" min={0.5} max={10} step={0.5}
                value={radiusKm}
                onChange={(e) => setRadiusKm(Number(e.target.value))}
                className="w-full accent-[#EF9F27]"
              />
              <div className="flex justify-between text-[10px] text-text-muted">
                <span>0.5 km</span>
                <span>10 km</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Button
                onClick={handleSubmitDeclare}
                disabled={declareMutation.isPending || !declareReady}
                className="bg-[#EF9F27] text-white hover:bg-[#EF9F27]/90 gap-2"
              >
                {declareMutation.isPending ? 'Declaring…' : 'Confirm & declare outbreak'}
              </Button>
              {!declareReady && (
                <span className="text-[11px] text-text-muted">
                  {!center
                    ? 'Set a centre on the map to continue'
                    : 'Add an animal type and title to continue'}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {isLoading && <Skeleton className="h-[560px] w-full bg-bg-subtle rounded-card" />}

      {error && (
        <div className="flex flex-wrap items-center gap-3 text-sm text-rose-500 bg-rose-500/10 p-4 rounded-lg border border-rose-500/20">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="flex-1 min-w-[200px]">
            {getErrorMessage(error) || 'Failed to load case data.'}
          </span>
          <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-2">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Retry
          </Button>
        </div>
      )}

      {data && (
        // The map used to sit on the page as a bare rectangle. Framing it with
        // a header and legend gives it an edge and explains what it is showing.
        <div className="rounded-card border border-border-brand bg-surface shadow-card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-border-brand bg-bg-subtle dark:bg-bg-brand">
            <div className="flex items-center gap-2">
              <Radar className="h-4 w-4 text-accent shrink-0" aria-hidden="true" />
              <h2 className="text-sm font-bold text-text-primary">Case density</h2>
              {declareMode && (
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[#EF9F27] bg-[#EF9F27]/15 px-2 py-0.5 rounded-full">
                  Click to place zone
                </span>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              <LegendItem
                swatch={<Flame className="h-3 w-3 text-orange-500" aria-hidden="true" />}
                label="Case density"
              />
              <LegendItem
                swatch={
                  <span className="h-2.5 w-2.5 rounded-full border-2 border-[#DC2626] bg-[#DC2626]/20 shrink-0" />
                }
                label="Declared zone"
              />
              {declareMode && (
                <LegendItem
                  swatch={
                    <span className="h-2.5 w-2.5 rounded-full border-2 border-dashed border-[#EF9F27] bg-[#EF9F27]/20 shrink-0" />
                  }
                  label="Pending zone"
                />
              )}
            </div>
          </div>

          <div className="relative">
            <CaseHeatmapWrapper
              cases={data}
              outbreakZones={zones || []}
              declareMode={declareMode}
              previewCenter={center}
              previewRadiusKm={radiusKm}
              onMapClick={declareMode ? (lat, lng) => setCenter({ lat, lng }) : undefined}
            />

            {/* Kept as an overlay rather than replacing the map, so the zone
                circles and the map itself stay visible and usable when a
                filter happens to match nothing. */}
            {data.length === 0 && (
              <div className="absolute inset-x-0 top-4 flex justify-center pointer-events-none z-[500]">
                <div className="flex items-center gap-2 rounded-full bg-surface/95 border border-border-brand shadow-lg px-4 py-2 backdrop-blur-sm">
                  <MapPin className="h-3.5 w-3.5 text-text-muted shrink-0" aria-hidden="true" />
                  <p className="text-xs text-text-secondary">
                    No cases match this filter.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
