'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FinanceService } from '@/services/finance.service';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Handshake,
  Plus,
  Dog,
  CheckCircle2,
  Clock,
  AlertCircle,
  TrendingUp,
  Search,
  Filter,
  Info,
  Database,
  Package,
  CircleDollarSign,
} from 'lucide-react';
import { useState, useMemo } from 'react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { type Program } from '@/types';

// Mock data for demo purposes when backend is unavailable
const MOCK_PROGRAMS: Program[] = [
  { id: 101, program_name: 'Regional Vaccination Alpha', status: 'Active', total_animals_treated: 1240 },
  { id: 102, program_name: 'Urban Spay & Neuter Program', status: 'In Progress', total_animals_treated: 450 },
  { id: 103, program_name: 'Wildlife Habitat Restoration', status: 'Active', total_animals_treated: 85 },
  { id: 104, program_name: 'Endangered Species Monitoring', status: 'Active', total_animals_treated: 12 },
  { id: 105, program_name: 'Community Animal Health Clinic', status: 'In Progress', total_animals_treated: 890 },
];

export default function ProgramsPage() {
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [lifecycleFilter, setLifecycleFilter] = useState('all');
  const [startDateFilter, setStartDateFilter] = useState('');
  const [endDateFilter, setEndDateFilter] = useState('');
  const [budgetMinFilter, setBudgetMinFilter] = useState('');
  const [budgetMaxFilter, setBudgetMaxFilter] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    program_name: '',
    status: 'Active',
    total_animals_treated: '',
    budget_amount: '',
    start_date: '',
    end_date: '',
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  
  const { data: programs, isLoading, isError } = useQuery({
    queryKey: ['programs'],
    queryFn: FinanceService.getPrograms,
    retry: 1
  });

  const { data: costRows, isLoading: loadingCost } = useQuery({
    queryKey: ['program-cost-per-animal'],
    queryFn: FinanceService.getCostPerAnimal,
    retry: 1
  });

  const createProgramMutation = useMutation({
    mutationFn: FinanceService.createProgram,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['programs'] });
      toast.success('Program created successfully.');
      setCreateOpen(false);
      setForm({
        program_name: '',
        status: 'Active',
        total_animals_treated: '',
        budget_amount: '',
        start_date: '',
        end_date: '',
      });
      setFormErrors({});
    },
    onError: (error: unknown) => {
      const errorMessage =
        typeof error === 'object' &&
        error !== null &&
        'response' in error &&
        typeof (error as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Unable to create program.';

      toast.error(errorMessage);
    },
  });

  // Use mock data if API fails or returns empty for now
  const displayPrograms = useMemo(() => {
    if (isLoading) return [];
    if (!programs || programs.length === 0 || isError) return MOCK_PROGRAMS;
    return programs;
  }, [programs, isLoading, isError]);

  const isActiveStatus = (status: string) => {
    const normalized = (status || '').toLowerCase();
    return ['active', 'in progress', 'ongoing', 'planned'].includes(normalized);
  };

  const filteredPrograms = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    const minBudget = budgetMinFilter ? Number(budgetMinFilter) : null;
    const maxBudget = budgetMaxFilter ? Number(budgetMaxFilter) : null;
    const startDate = startDateFilter ? new Date(startDateFilter) : null;
    const endDate = endDateFilter ? new Date(endDateFilter) : null;

    return displayPrograms.filter((program) => {
      const programName = (program.program_name || '').toLowerCase();
      if (query && !programName.includes(query)) {
        return false;
      }

      if (statusFilter !== 'all') {
        const normalized = (program.status || '').toLowerCase();
        if (!normalized.includes(statusFilter.toLowerCase())) {
          return false;
        }
      }

      if (lifecycleFilter !== 'all') {
        const isCompleted = (program.status || '').toLowerCase().includes('complete');
        if (lifecycleFilter === 'active' && !isActiveStatus(program.status)) {
          return false;
        }
        if (lifecycleFilter === 'completed' && !isCompleted) {
          return false;
        }
      }

      const budgetAmount = typeof program.budget_amount === 'number' ? program.budget_amount : null;
      if (minBudget !== null && (budgetAmount === null || budgetAmount < minBudget)) {
        return false;
      }
      if (maxBudget !== null && (budgetAmount === null || budgetAmount > maxBudget)) {
        return false;
      }

      const programStartDate = program.start_date ? new Date(program.start_date) : null;
      const programEndDate = program.end_date ? new Date(program.end_date) : null;
      if (startDate && (programStartDate === null || programStartDate < startDate)) {
        return false;
      }
      if (endDate && (programEndDate === null || programEndDate > endDate)) {
        return false;
      }

      return true;
    });
  }, [displayPrograms, searchTerm, statusFilter, lifecycleFilter, startDateFilter, endDateFilter, budgetMinFilter, budgetMaxFilter]);

  const handleCreateProgram = () => {
    const nextErrors: Record<string, string> = {};

    if (!form.program_name.trim()) {
      nextErrors.program_name = 'Program name is required.';
    }

    if (form.start_date && form.end_date && new Date(form.end_date) < new Date(form.start_date)) {
      nextErrors.end_date = 'End date must be on or after the start date.';
    }

    if (Object.keys(nextErrors).length > 0) {
      setFormErrors(nextErrors);
      return;
    }

    setFormErrors({});

    createProgramMutation.mutate({
      program_name: form.program_name.trim(),
      status: form.status,
      total_animals_treated: Number(form.total_animals_treated || 0),
      budget_amount: form.budget_amount ? Number(form.budget_amount) : undefined,
      start_date: form.start_date || undefined,
      end_date: form.end_date || undefined,
    });
  };

  const handleInputChange = (field: string, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setFormErrors((current) => ({ ...current, [field]: '' }));
  };

  const getStatusStyles = (status: string) => {
    switch ((status || 'Active').toLowerCase()) {
      case 'active': 
        return {
          icon: <CheckCircle2 size={14} />,
          bg: 'bg-emerald-500/10',
          text: 'text-emerald-400',
          border: 'border-emerald-500/20'
        };
      case 'in progress': 
        return {
          icon: <Clock size={14} />,
          bg: 'bg-amber-500/10',
          text: 'text-amber-400',
          border: 'border-amber-500/20'
        };
      default: 
        return {
          icon: <AlertCircle size={14} />,
          bg: 'bg-slate-500/10',
          text: 'text-slate-400',
          border: 'border-slate-500/20'
        };
    }
  };

  return (
    <div className="space-y-8 pb-12 animate-in fade-in duration-700">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <h1 className="text-3xl font-bold tracking-tight text-white">Program Registry</h1>
            {isError && (
              <Badge variant="outline" className="text-[10px] uppercase font-bold text-amber-500 border-amber-500/20 bg-amber-500/5 h-5">
                <Database size={10} className="mr-1" /> Demo Mode
              </Badge>
            )}
          </div>
          <p className="text-slate-400 max-w-2xl">
            Strategic oversight of environmental initiatives, animal health programs, and ecological impact assessments.
          </p>
        </div>
        
        <Button
          className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20 px-6"
          onClick={() => setCreateOpen(true)}
        >
          <Plus className="mr-2 h-4 w-4" /> Initialize Program
        </Button>
      </div>

      {/* Stats/Dashboard Briefing (Optional Visual Add-on) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Active Programs', value: displayPrograms.filter(p => p.status === 'Active').length, icon: CheckCircle2, color: 'text-emerald-400' },
          { label: 'Total Impact', value: displayPrograms.reduce((acc, p) => acc + (p.total_animals_treated || 0), 0).toLocaleString(), icon: Dog, color: 'text-blue-400' },
          { label: 'Growth/mo', value: '+12%', icon: TrendingUp, color: 'text-indigo-400' },
          { label: 'Resources', value: '94%', icon: Info, color: 'text-slate-400' },
        ].map((stat, idx) => (
          <div key={idx} className="bg-slate-900/40 border border-slate-800 p-4 rounded-xl flex items-center gap-4">
            <div className={cn("p-2 rounded-lg bg-slate-800/50", stat.color)}>
              <stat.icon size={20} />
            </div>
            <div>
              <p className="text-xs text-slate-500 font-medium uppercase tracking-wider">{stat.label}</p>
              <p className="text-xl font-bold text-white">{stat.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
          <Input 
            placeholder="Search tactical programs..." 
            className="pl-10 bg-slate-900/50 border-slate-800 focus:border-blue-500/50 transition-all h-11"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <Button
          variant="outline"
          className="border-slate-800 hover:bg-slate-800 h-11"
          onClick={() => setShowFilters((current) => !current)}
        >
          <Filter className="mr-2 h-4 w-4" /> Advanced Filter
        </Button>
      </div>

      {showFilters && (
        <Card className="bg-slate-900/50 border-slate-800">
          <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4 pt-6">
            <div className="space-y-2">
              <Label className="text-slate-300">Status</Label>
              <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value ?? 'all')}>
                <SelectTrigger className="bg-slate-950/70 border-slate-800">
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="in progress">In Progress</SelectItem>
                  <SelectItem value="complete">Completed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">Lifecycle</Label>
              <Select value={lifecycleFilter} onValueChange={(value) => setLifecycleFilter(value ?? 'all')}>
                <SelectTrigger className="bg-slate-950/70 border-slate-800">
                  <SelectValue placeholder="Any lifecycle" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any lifecycle</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">Start date</Label>
              <Input
                type="date"
                className="bg-slate-950/70 border-slate-800"
                value={startDateFilter}
                onChange={(event) => setStartDateFilter(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">End date</Label>
              <Input
                type="date"
                className="bg-slate-950/70 border-slate-800"
                value={endDateFilter}
                onChange={(event) => setEndDateFilter(event.target.value)}
              />
            </div>
            <div className="space-y-2 md:col-span-2 xl:col-span-1">
              <Label className="text-slate-300">Budget min</Label>
              <Input
                type="number"
                min="0"
                placeholder="0"
                className="bg-slate-950/70 border-slate-800"
                value={budgetMinFilter}
                onChange={(event) => setBudgetMinFilter(event.target.value)}
              />
            </div>
            <div className="space-y-2 md:col-span-2 xl:col-span-1">
              <Label className="text-slate-300">Budget max</Label>
              <Input
                type="number"
                min="0"
                placeholder="100000"
                className="bg-slate-950/70 border-slate-800"
                value={budgetMaxFilter}
                onChange={(event) => setBudgetMaxFilter(event.target.value)}
              />
            </div>
            <div className="md:col-span-2 xl:col-span-2 flex items-end">
              <Button
                variant="ghost"
                className="text-slate-300 hover:bg-slate-800"
                onClick={() => {
                  setStatusFilter('all');
                  setLifecycleFilter('all');
                  setStartDateFilter('');
                  setEndDateFilter('');
                  setBudgetMinFilter('');
                  setBudgetMaxFilter('');
                }}
              >
                Clear filters
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Programs Grid */}
      {isLoading ? (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1,2,3].map(i => (
            <Skeleton key={i} className="h-48 w-full bg-slate-900/50 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {filteredPrograms.map((program) => {
            const styles = getStatusStyles(program.status);
            return (
              <Card key={program.id} className="bg-slate-900/50 border-slate-800 hover:border-blue-600/30 transition-all hover:-translate-y-1 duration-300 group relative overflow-hidden flex flex-col">
                <div className="absolute top-0 left-0 w-1 h-full bg-blue-600/0 group-hover:bg-blue-600 transition-colors" />
                
                <CardHeader className="pb-2">
                  <div className="flex justify-between items-start mb-3">
                    <Badge variant="outline" className="text-[10px] text-blue-400 border-blue-400/20 bg-blue-400/5">
                      #ID-{program.id}
                    </Badge>
                    <div className={cn("flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-tight", styles.bg, styles.text, styles.border)}>
                      {styles.icon}
                      {program.status || 'Active'}
                    </div>
                  </div>
                  <CardTitle className="text-xl text-white group-hover:text-blue-400 transition-colors leading-tight">
                    {program.program_name}
                  </CardTitle>
                </CardHeader>

                <CardContent className="flex-1 py-4">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2 text-slate-400">
                        <Dog size={16} className="text-blue-400" />
                        Cumulative Impact
                      </div>
                      <span className="text-white font-bold tracking-tight">
                        {(program.total_animals_treated ?? 0).toLocaleString()} <span className="text-[10px] font-normal text-slate-500">Units</span>
                      </span>
                    </div>
                    
                    <div className="space-y-1.5">
                      <div className="flex justify-between text-[10px] uppercase font-bold text-slate-500">
                        <span>Milestone Progress</span>
                        <span>{Math.round(Math.min(100, ((program.total_animals_treated || 0) / 1500) * 100))}%</span>
                      </div>
                      <div className="w-full bg-slate-800/50 rounded-full h-1.5 overflow-hidden">
                        <div 
                          className="bg-blue-500 h-full rounded-full transition-all duration-1000" 
                          style={{ width: `${Math.min(100, ((program.total_animals_treated || 0) / 1500) * 100)}%` }} 
                        />
                      </div>
                    </div>
                  </div>
                </CardContent>

                <CardFooter className="pt-4 border-t border-slate-800/50 flex justify-between items-center bg-slate-800/10">
                  <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white hover:bg-slate-800 -ml-2">
                    <TrendingUp className="mr-2 h-4 w-4 text-emerald-400" /> Analytics
                  </Button>
                  <div className="flex items-center gap-2">
                     <span className="text-[10px] text-slate-500 italic">Updated 2h ago</span>
                     <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
                  </div>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}
      
      <Card className="bg-slate-900/50 border-slate-800">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-500/10">
              <Package className="h-5 w-5 text-blue-400" />
            </div>
            <div>
              <CardTitle className="text-white">Cost per Animal Treated</CardTitle>
              <CardDescription>Inventory spend attributed to each program, divided by animals treated.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loadingCost ? (
            <div className="space-y-2">
              {Array(3).fill(0).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full bg-slate-800/60" />
              ))}
            </div>
          ) : !costRows || costRows.length === 0 ? (
            <p className="text-center py-10 text-slate-600 text-sm">No issued transactions linked to programs yet.</p>
          ) : (
            <div className="rounded-md border border-slate-800 overflow-hidden">
              <table className="min-w-full divide-y divide-slate-800">
                <thead className="bg-slate-950/80">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-300">Program</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-300">Animals Treated</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-300">Total Inventory Cost</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-300">Cost / Animal</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 bg-slate-900/40">
                  {costRows.map((row) => (
                    <tr key={row.program_id} className="hover:bg-slate-800/30">
                      <td className="px-4 py-3 text-sm font-medium text-white">{row.program_name}</td>
                      <td className="px-4 py-3 text-right text-sm text-slate-300">{row.animals_treated.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right text-sm text-slate-300">LKR {row.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      <td className="px-4 py-3 text-right">
                        <Badge variant="outline" className={
                          row.cost_per_animal > 50 ? 'text-rose-400 border-rose-400/30 bg-rose-400/10'
                          : row.cost_per_animal > 20 ? 'text-amber-400 border-amber-400/30 bg-amber-400/10'
                          : 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10'
                        }>
                          {row.animals_treated > 0
                            ? `LKR ${row.cost_per_animal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                            : '—'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {filteredPrograms.length === 0 && !isLoading && (
        <div className="text-center py-24 bg-slate-900/30 rounded-3xl border border-dashed border-slate-800 shadow-inner">
          <div className="mx-auto h-20 w-20 bg-slate-800/50 rounded-full flex items-center justify-center mb-6">
            <Handshake className="h-10 w-10 text-slate-600" />
          </div>
          <h3 className="text-2xl font-semibold text-slate-300 mb-2">Operational Gap Detected</h3>
          <p className="text-slate-500 max-w-sm mx-auto">
            No active programs match your current filter parameters. Try clearing your search or establishing a new initiative.
          </p>
          <Button variant="link" className="mt-4 text-blue-400 hover:text-blue-300" onClick={() => setSearchTerm('')}>
            Clear Search Parameters
          </Button>
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="bg-slate-950 border-slate-800 text-white sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="text-white">Create program</DialogTitle>
            <DialogDescription className="text-slate-400">
              Capture the basic metadata for a new initiative and make it available in the registry.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="program_name" className="text-slate-300">Program name</Label>
              <Input
                id="program_name"
                value={form.program_name}
                onChange={(event) => handleInputChange('program_name', event.target.value)}
                className="bg-slate-900/70 border-slate-800"
                placeholder="e.g. Coastal Marine Rescue"
              />
              {formErrors.program_name && <p className="text-sm text-rose-400">{formErrors.program_name}</p>}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-slate-300">Status</Label>
                <Select value={form.status} onValueChange={(value) => handleInputChange('status', value ?? 'Active')}>
                  <SelectTrigger className="bg-slate-900/70 border-slate-800">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Active">Active</SelectItem>
                    <SelectItem value="In Progress">In Progress</SelectItem>
                    <SelectItem value="Completed">Completed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="total_animals_treated" className="text-slate-300">Animals treated</Label>
                <Input
                  id="total_animals_treated"
                  type="number"
                  min="0"
                  value={form.total_animals_treated}
                  onChange={(event) => handleInputChange('total_animals_treated', event.target.value)}
                  className="bg-slate-900/70 border-slate-800"
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="budget_amount" className="text-slate-300">Budget</Label>
                <div className="relative">
                  <CircleDollarSign className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                  <Input
                    id="budget_amount"
                    type="number"
                    min="0"
                    value={form.budget_amount}
                    onChange={(event) => handleInputChange('budget_amount', event.target.value)}
                    className="pl-9 bg-slate-900/70 border-slate-800"
                    placeholder="5000"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Start date</Label>
                <Input
                  type="date"
                  value={form.start_date}
                  onChange={(event) => handleInputChange('start_date', event.target.value)}
                  className="bg-slate-900/70 border-slate-800"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-slate-300">End date</Label>
              <Input
                type="date"
                value={form.end_date}
                onChange={(event) => handleInputChange('end_date', event.target.value)}
                className="bg-slate-900/70 border-slate-800"
              />
              {formErrors.end_date && <p className="text-sm text-rose-400">{formErrors.end_date}</p>}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" className="border-slate-800 hover:bg-slate-800" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button className="bg-blue-600 hover:bg-blue-700" onClick={handleCreateProgram} disabled={createProgramMutation.isPending}>
              {createProgramMutation.isPending ? 'Creating…' : 'Create program'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
