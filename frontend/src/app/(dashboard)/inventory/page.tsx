'use client';

import { useState } from 'react';
import {
  useInventoryItems,
  useInventoryTransactions,
  useCreateInventoryTransaction,
  useCreateInventoryItem,
  usePrograms,
  useCostPerAnimal,
} from '@/hooks/useInventory';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { Package, ArrowUpRight, ArrowDownLeft, Filter, Plus, CalendarIcon, Loader2 } from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

// ─── Issue / Return Dialog ──────────────────────────────────────────────────

function IssueReturnDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { data: items } = useInventoryItems();
  const { data: programs } = usePrograms();
  const mutation = useCreateInventoryTransaction();

  const [itemId, setItemId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [txType, setTxType] = useState<'Issue' | 'Return'>('Issue');
  const [date, setDate] = useState<Date>(new Date());
  const [calOpen, setCalOpen] = useState(false);
  const [programId, setProgramId] = useState('');

  const reset = () => {
    setItemId('');
    setQuantity('');
    setTxType('Issue');
    setDate(new Date());
    setProgramId('');
  };

  const handleSubmit = () => {
    if (!itemId || !quantity || Number(quantity) <= 0) {
      toast.error('Please fill in all required fields.');
      return;
    }
    mutation.mutate(
      {
        item_id: Number(itemId),
        quantity: Number(quantity),
        transaction_type: txType,
        transaction_date: format(date, 'yyyy-MM-dd'),
        program_id: programId ? Number(programId) : null,
      },
      {
        onSuccess: () => {
          toast.success(`${txType} recorded successfully.`);
          reset();
          onOpenChange(false);
        },
        onError: (err: any) => {
          toast.error(err?.response?.data?.detail ?? 'Failed to record transaction.');
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v); }}>
      <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-white">Issue / Return Stock</DialogTitle>
          <DialogDescription className="text-slate-400">
            Record an inventory movement against a program or general stock.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Item */}
          <div className="space-y-1.5">
            <Label className="text-slate-300">Item <span className="text-rose-400">*</span></Label>
            <Select value={itemId} onValueChange={(v) => setItemId(v ?? '')}>
              <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                <SelectValue placeholder="Select an item…" />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700 text-white">
                {items?.map((it) => (
                  <SelectItem key={it.id} value={String(it.id)}>
                    {it.item_name} <span className="text-slate-400 text-xs ml-1">(stock: {it.current_stock})</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Quantity */}
          <div className="space-y-1.5">
            <Label className="text-slate-300">Quantity <span className="text-rose-400">*</span></Label>
            <Input
              type="number"
              min={1}
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder="e.g. 5"
              className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
            />
          </div>

          {/* Transaction type */}
          <div className="space-y-1.5">
            <Label className="text-slate-300">Type <span className="text-rose-400">*</span></Label>
            <Select value={txType} onValueChange={(v) => setTxType(v as 'Issue' | 'Return')}>
              <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700 text-white">
                <SelectItem value="Issue">Issue (out)</SelectItem>
                <SelectItem value="Return">Return (in)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Date */}
          <div className="space-y-1.5">
            <Label className="text-slate-300">Date <span className="text-rose-400">*</span></Label>
            <Popover open={calOpen} onOpenChange={setCalOpen}>
              <PopoverTrigger
                  className={cn(
                    'w-full inline-flex items-center justify-start text-left font-normal rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
                    !date && 'text-slate-500'
                  )}
                >
                  <CalendarIcon className="mr-2 h-4 w-4 text-slate-400" />
                  {date ? format(date, 'PPP') : 'Pick a date'}
                </PopoverTrigger>
              <PopoverContent className="w-auto p-0 bg-slate-800 border-slate-700" align="start">
                <Calendar
                  mode="single"
                  selected={date}
                  onSelect={(d) => { if (d) { setDate(d); setCalOpen(false); } }}
                  initialFocus
                />
              </PopoverContent>
            </Popover>
          </div>

          {/* Program (optional) */}
          <div className="space-y-1.5">
            <Label className="text-slate-300">Program <span className="text-slate-500 text-xs">(optional)</span></Label>
            <Select value={programId} onValueChange={(v) => setProgramId(v ?? '')}>
              <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                <SelectValue placeholder="None (general stock)" />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700 text-white">
                <SelectItem value="">None (general stock)</SelectItem>
                {programs?.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.program_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" className="text-slate-400 hover:text-white" onClick={() => { reset(); onOpenChange(false); }}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={mutation.isPending}
            className={txType === 'Issue' ? 'bg-rose-600 hover:bg-rose-700' : 'bg-emerald-600 hover:bg-emerald-700'}
          >
            {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {txType === 'Issue' ? 'Issue Stock' : 'Return Stock'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Add Item Dialog ─────────────────────────────────────────────────────────

function AddItemDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const mutation = useCreateInventoryItem();

  const [name, setName] = useState('');
  const [unitCost, setUnitCost] = useState('');
  const [stock, setStock] = useState('');

  const reset = () => { setName(''); setUnitCost(''); setStock(''); };

  const handleSubmit = () => {
    if (!name.trim() || !unitCost || !stock) {
      toast.error('Please fill in all fields.');
      return;
    }
    mutation.mutate(
      {
        item_name: name.trim(),
        unit_cost: parseFloat(unitCost),
        current_stock: parseInt(stock, 10),
      },
      {
        onSuccess: () => {
          toast.success(`"${name.trim()}" added to inventory.`);
          reset();
          onOpenChange(false);
        },
        onError: (err: any) => {
          toast.error(err?.response?.data?.detail ?? 'Failed to add item.');
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v); }}>
      <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-white">Add New Item</DialogTitle>
          <DialogDescription className="text-slate-400">
            Create a new inventory item with an initial stock level.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label className="text-slate-300">Item Name <span className="text-rose-400">*</span></Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Surgical Gloves"
              className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-slate-300">Unit Cost (USD) <span className="text-rose-400">*</span></Label>
            <Input
              type="number"
              min={0}
              step={0.01}
              value={unitCost}
              onChange={(e) => setUnitCost(e.target.value)}
              placeholder="e.g. 2.50"
              className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-slate-300">Initial Stock <span className="text-rose-400">*</span></Label>
            <Input
              type="number"
              min={0}
              value={stock}
              onChange={(e) => setStock(e.target.value)}
              placeholder="e.g. 100"
              className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" className="text-slate-400 hover:text-white" onClick={() => { reset(); onOpenChange(false); }}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={mutation.isPending}
            className="bg-blue-600 hover:bg-blue-700"
          >
            {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Add Item
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function InventoryPage() {
  const { data: items, isLoading: loadingItems } = useInventoryItems();
  const { data: transactions, isLoading: loadingTransactions } = useInventoryTransactions();

  const [issueOpen, setIssueOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-2">Inventory System</h1>
          <p className="text-slate-400">Manage medical supplies, equipment, and resource allocations.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="border-slate-800" onClick={() => setAddOpen(true)}>
            <Plus className="mr-2 h-4 w-4" /> Add Item
          </Button>
          <Button className="bg-blue-600 hover:bg-blue-700" onClick={() => setIssueOpen(true)}>
            <Package className="mr-2 h-4 w-4" /> Issue/Return
          </Button>
        </div>
      </div>

      {/* Dialogs */}
      <IssueReturnDialog open={issueOpen} onOpenChange={setIssueOpen} />
      <AddItemDialog open={addOpen} onOpenChange={setAddOpen} />

      {/* Stock summary cards */}
      <div className="grid gap-6 md:grid-cols-4">
        {loadingItems ? (
          Array(4).fill(0).map((_, i) => <Skeleton key={i} className="h-24 bg-slate-900 border border-slate-800 rounded-xl" />)
        ) : (
          items?.slice(0, 4).map((item) => (
            <Card key={item.id} className="bg-slate-900 border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-slate-400 uppercase tracking-wider">{item.item_name}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-white">{item.current_stock}</div>
                <p className="text-xs text-slate-500 mt-1">Unit Cost: ${item.unit_cost}</p>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Main content */}
      <div className="grid lg:grid-cols-3 gap-8">
        {/* Stock list */}
        <Card className="lg:col-span-2 bg-slate-900 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-white">Detailed Stock List</CardTitle>
              <CardDescription>Current availability and unit costs.</CardDescription>
            </div>
            <Button variant="ghost" size="icon" className="text-slate-400">
              <Filter size={18} />
            </Button>
          </CardHeader>
          <CardContent>
            {loadingItems ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full bg-slate-800" />
                <Skeleton className="h-10 w-full bg-slate-800" />
              </div>
            ) : (
              <div className="rounded-md border border-slate-800 overflow-hidden">
                <Table>
                  <TableHeader className="bg-slate-950">
                    <TableRow className="hover:bg-transparent border-slate-800">
                      <TableHead className="text-slate-300">Item Name</TableHead>
                      <TableHead className="text-slate-300">Stock</TableHead>
                      <TableHead className="text-slate-300">Unit Cost</TableHead>
                      <TableHead className="text-slate-300">Total Value</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items?.map((item) => (
                      <TableRow key={item.id} className="border-slate-800 hover:bg-slate-800/40">
                        <TableCell className="font-medium">{item.item_name}</TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={
                              item.current_stock < 10
                                ? 'text-rose-400 border-rose-400/30 bg-rose-400/10'
                                : 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10'
                            }
                          >
                            {item.current_stock}
                          </Badge>
                        </TableCell>
                        <TableCell>${item.unit_cost}</TableCell>
                        <TableCell className="text-slate-400">
                          ${(item.current_stock * item.unit_cost).toLocaleString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent movements */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle className="text-white">Recent Movements</CardTitle>
            <CardDescription>Last 10 issue/return logs.</CardDescription>
          </CardHeader>
          <CardContent>
            {loadingTransactions ? (
              <div className="space-y-4">
                <Skeleton className="h-12 w-full bg-slate-800" />
                <Skeleton className="h-12 w-full bg-slate-800" />
              </div>
            ) : (
              <div className="space-y-4">
                {transactions?.slice(0, 10).map((tx) => (
                  <div key={tx.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-950 border border-slate-800/50">
                    <div className="flex items-center gap-3">
                      <div
                        className={`p-2 rounded-full ${
                          tx.transaction_type === 'Issue'
                            ? 'bg-rose-500/10 text-rose-400'
                            : 'bg-emerald-500/10 text-emerald-400'
                        }`}
                      >
                        {tx.transaction_type === 'Issue' ? <ArrowUpRight size={16} /> : <ArrowDownLeft size={16} />}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white">{tx.inventory_items?.item_name}</p>
                        <p className="text-xs text-slate-500">{format(new Date(tx.transaction_date), 'MMM dd, yyyy')}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-bold ${tx.transaction_type === 'Issue' ? 'text-rose-400' : 'text-emerald-400'}`}>
                        {tx.transaction_type === 'Issue' ? '-' : '+'}
                        {tx.quantity}
                      </p>
                      <p className="text-[10px] text-slate-600 uppercase font-bold tracking-tighter">
                        {tx.programs?.program_name || 'Stock'}
                      </p>
                    </div>
                  </div>
                ))}
                {transactions?.length === 0 && (
                  <p className="text-center py-8 text-slate-600 text-sm">No recent movements</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Cost-per-animal panel */}
      <CostPerAnimalPanel />
    </div>
  );
}

// ─── Cost Per Animal Panel ────────────────────────────────────────────────────

function CostPerAnimalPanel() {
  const { data: rows, isLoading } = useCostPerAnimal();

  return (
    <Card className="bg-slate-900 border-slate-800">
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
        {isLoading ? (
          <div className="space-y-2">
            {Array(3).fill(0).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full bg-slate-800" />
            ))}
          </div>
        ) : !rows || rows.length === 0 ? (
          <p className="text-center py-10 text-slate-600 text-sm">
            No issued transactions linked to programs yet.
          </p>
        ) : (
          <div className="rounded-md border border-slate-800 overflow-hidden">
            <Table>
              <TableHeader className="bg-slate-950">
                <TableRow className="hover:bg-transparent border-slate-800">
                  <TableHead className="text-slate-300">Program</TableHead>
                  <TableHead className="text-slate-300 text-right">Animals Treated</TableHead>
                  <TableHead className="text-slate-300 text-right">Total Inventory Cost</TableHead>
                  <TableHead className="text-slate-300 text-right">Cost per Animal</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.program_id} className="border-slate-800 hover:bg-slate-800/40">
                    <TableCell className="font-medium text-white">{row.program_name}</TableCell>
                    <TableCell className="text-right text-slate-300">
                      {row.animals_treated.toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right text-slate-300">
                      ${row.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </TableCell>
                    <TableCell className="text-right">
                      <Badge
                        variant="outline"
                        className={
                          row.cost_per_animal > 50
                            ? 'text-rose-400 border-rose-400/30 bg-rose-400/10'
                            : row.cost_per_animal > 20
                            ? 'text-amber-400 border-amber-400/30 bg-amber-400/10'
                            : 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10'
                        }
                      >
                        ${row.cost_per_animal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
