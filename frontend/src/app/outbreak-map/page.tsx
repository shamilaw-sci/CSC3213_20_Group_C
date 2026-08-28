// frontend/src/app/outbreak-map/page.tsx
'use client';

import { useQuery } from '@tanstack/react-query';
import { RescueCasesService } from '@/services/rescue-cases.service';
import OutbreakZoneMapWrapper from '@/components/heatmap/OutbreakZoneMapWrapper';

export default function PublicOutbreakMapPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['outbreakZones'],
    queryFn: () => RescueCasesService.getOutbreakZones(),
  });

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-4">
        <h1 className="text-xl font-semibold">VFF Declared Outbreak Zones</h1>
        <p className="text-text-secondary text-sm mt-1">
          Areas with a confirmed outbreak, reviewed and declared by VFF staff.
        </p>
      </div>

      {isLoading && <p>Loading...</p>}
      {error && <p>Failed to load outbreak zones.</p>}
      {data && data.length === 0 && (
        <p className="text-text-secondary py-12 text-center">
          No active outbreaks declared right now.
        </p>
      )}
      {data && data.length > 0 && <OutbreakZoneMapWrapper zones={data} />}
    </div>
  );
}