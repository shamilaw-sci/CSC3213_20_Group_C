'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RescueCasesService } from '@/services/rescue-cases.service';
import CaseHeatmapWrapper from '@/components/heatmap/CaseHeatmapWrapper';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export default function CaseHotspotsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const { data, isLoading, error } = useQuery({
    queryKey: ['rescueCases', 'geo', statusFilter],
    queryFn: () =>
      RescueCasesService.getCaseGeo(
        statusFilter === 'all' ? undefined : { status: statusFilter }
      ),
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Rescue Case Hotspots</h1>

        <Select
          value={statusFilter}
          onValueChange={(value) => {
            if (value !== null) setStatusFilter(value);
          }}
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
      </div>

      {isLoading && <p>Loading map...</p>}
      {error && <p>Failed to load case data.</p>}
      {data && data.length === 0 && (
        <p className="text-text-secondary py-12 text-center">
          No cases match this filter.
        </p>
      )}
      {data && data.length > 0 && <CaseHeatmapWrapper cases={data} />}
    </div>
  );
}