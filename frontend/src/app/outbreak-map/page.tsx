// frontend/src/app/outbreak-map/page.tsx
'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RescueCasesService } from '@/services/rescue-cases.service';
import CaseHotspotMapWrapper from '@/components/heatmap/CaseHotspotMapWrapper';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export default function PublicOutbreakMapPage() {
  const [days, setDays] = useState('30');

  const { data, isLoading, error } = useQuery({
    queryKey: ['rescueCases', 'hotspots', days],
    queryFn: () => RescueCasesService.getHotspots(Number(days)),
  });

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold">VFF Rescue Case Hotspots</h1>
          <p className="text-text-secondary text-sm mt-1">
            Areas with reported cases. Red markers indicate an active outbreak pattern.
          </p>
        </div>
        <Select
          value={days}
          onValueChange={(value) => {
            if (value !== null) setDays(value);
            }}
            >
          <SelectTrigger className="w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Last 7 days</SelectItem>
            <SelectItem value="30">Last 30 days</SelectItem>
            <SelectItem value="90">Last 90 days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading && <p>Loading map...</p>}
      {error && <p>Failed to load hotspot data.</p>}
      {data && data.length === 0 && (
        <p className="text-text-secondary py-12 text-center">No hotspots to show for this period.</p>
      )}
      {data && data.length > 0 && <CaseHotspotMapWrapper hotspots={data} />}
    </div>
  );
}