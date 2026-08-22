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

  const { data, isLoading, error } = useQuery({
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
    onError: () => toast.error("Couldn't declare the outbreak. Please try again."),
  });

  function resetDeclareForm() {
    setDeclareMode(false);
    setCenter(null);
    setAnimalType('');
    setTitle('');
    setDescription('');
    setRadiusKm(2);
  }

  function handleSubmitDeclare() {
    if (!center || !animalType || !title) {
      toast.error('Click a location on the map and fill in the animal type and title.');
      return;
    }
    declareMutation.mutate();
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Rescue Case Hotspots</h1>

        <div className="flex items-center gap-3">
          <Select
            value={statusFilter}
            onValueChange={(value) => { if (value !== null) setStatusFilter(value); }}
          >
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="Reported">Reported</SelectItem>
              <SelectItem value="Assigned">Assigned</SelectItem>
              <SelectItem value="In Treatment">In Treatment</SelectItem>
              <SelectItem value="Resolved">Resolved</SelectItem>
            </SelectContent>
          </Select>

          {canDeclare && (
            <Button
              variant={declareMode ? 'outline' : undefined}
              className={!declareMode ? 'bg-[#DC2626] text-white hover:bg-[#DC2626]/90' : ''}
              onClick={() => (declareMode ? resetDeclareForm() : setDeclareMode(true))}
            >
              {declareMode ? 'Cancel' : 'Declare Outbreak'}
            </Button>
          )}
        </div>
      </div>

      {declareMode && (
        <div className="bg-surface border border-[#EF9F27]/40 rounded-lg p-4 space-y-3">
          <p className="text-xs text-text-secondary">
            Click a location on the map to set the outbreak center.
            {center ? ` Selected: ${center.lat.toFixed(4)}, ${center.lng.toFixed(4)}` : ' No location selected yet.'}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <input
              placeholder="Animal type (e.g. Dog)"
              value={animalType}
              onChange={(e) => setAnimalType(e.target.value)}
              className="border border-border-brand rounded-lg p-2 bg-bg-subtle text-sm"
            />
            <input
              placeholder="Title (e.g. Suspected mange outbreak)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="border border-border-brand rounded-lg p-2 bg-bg-subtle text-sm"
            />
          </div>
          <textarea
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full border border-border-brand rounded-lg p-2 bg-bg-subtle text-sm"
            rows={2}
          />
          <div className="flex items-center gap-3">
            <label className="text-xs text-text-secondary">Radius: {radiusKm} km</label>
            <input
              type="range" min={0.5} max={10} step={0.5}
              value={radiusKm}
              onChange={(e) => setRadiusKm(Number(e.target.value))}
              className="flex-1"
            />
          </div>
          <Button onClick={handleSubmitDeclare} disabled={declareMutation.isPending} className="bg-[#EF9F27] text-white">
            {declareMutation.isPending ? 'Declaring...' : 'Confirm & Declare Outbreak'}
          </Button>
        </div>
      )}

      {isLoading && <p>Loading map...</p>}
      {error && <p>Failed to load case data.</p>}
      {data && data.length === 0 && (
        <p className="text-text-secondary py-12 text-center">No cases match this filter.</p>
      )}
      {data && (
        <CaseHeatmapWrapper
          cases={data}
          outbreakZones={zones || []}
          declareMode={declareMode}
          previewCenter={center}
          previewRadiusKm={radiusKm}
          onMapClick={declareMode ? (lat, lng) => setCenter({ lat, lng }) : undefined}
        />
      )}
    </div>
  );
}