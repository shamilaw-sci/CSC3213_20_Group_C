'use client';

import { useState, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { format } from 'date-fns';
import { Loader2, ArrowUpCircle, ArrowDownCircle, RotateCcw, PackagePlus } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { useInventoryItems, useStockIn, useStockOut, useStockReturn, useAddInventoryItem, usePrograms } from '@/hooks/useInventory';

const today = () => format(new Date(), 'yyyy-MM-dd');
const todayMax = new Date().toISOString().split('T')[0];

// ─── Field error helper ───────────────────────────────────────────────────────
function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null;
  return <p className="text-xs text-rose-400 mt-1">{msg}</p>;
}

// ─── Zod schemas ──────────────────────────────────────────────────────────────
const stockInSchema = z.object({
  item_id: z.string().min(1, 'Item is required'),
  quantity: z.coerce.number().int().positive('Must be > 0'),
  unit_price: z.coerce.number().min(0).optional(),
  supplier: z.string().optional(),
  supplier_custom: z.string().optional(),
  transaction_date: z.string().min(1, 'Date is required'),
  reason_notes: z.string().optional(),
});

const stockOutSchema = z.object({
  item_id: z.string().min(1, 'Item is required'),
  quantity: z.coerce.number().int().positive('Must be > 0'),
  transaction_date: z.string().min(1, 'Date is required'),
  reason_notes: z.string().optional(),
  program_id: z.string().optional(),
});

const stockReturnSchema = z.object({
  item_id: z.string().min(1, 'Item is required'),
  quantity: z.coerce.number().int().positive('Must be > 0'),
  supplier: z.string().optional(),
  supplier_custom: z.string().optional(),
  reason_notes: z.string().optional(),
});

const addItemSchema = z.object({
  item_name: z.string().min(1, 'Name is required').max(200),
  initial_quantity: z.coerce.number().int().min(0).default(0),
  unit_cost: z.coerce.number().min(0).default(0),
});

type StockInForm = z.infer<typeof stockInSchema>;
type StockOutForm = z.infer<typeof stockOutSchema>;
type StockReturnForm = z.infer<typeof stockReturnSchema>;
type AddItemForm = z.infer<typeof addItemSchema>;

// ─── Supplier Select helper ───────────────────────────────────────────────────
function SupplierSelect({
  suppliers, value, onChange,
}: { suppliers: string[]; value: string; onChange: (v: string) => void }) {
  const [showCustom, setShowCustom] = useState(false);
  return (
    <div className="space-y-2">
      <Select value={showCustom ? '__other__' : value} onValueChange={(v) => {
        if (v === '__other__') { setShowCustom(true); onChange(''); }
        else { setShowCustom(false); onChange(v); }
      }}>
        <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
          <SelectValue placeholder="Select supplier (optional)" />
        </SelectTrigger>
        <SelectContent className="bg-slate-800 border-slate-700 text-white">
          <SelectItem value="">None</SelectItem>
          {suppliers.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          <SelectItem value="__other__">Other…</SelectItem>
        </SelectContent>
      </Select>
      {showCustom && (
        <Input
          placeholder="Enter supplier name"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
        />
      )}
    </div>
  );
}

// ─── STOCK IN DIALOG ──────────────────────────────────────────────────────────
export function StockInDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { data: items } = useInventoryItems();
  const mutation = useStockIn();
  const suppliers = useMemo(() => [...new Set((items ?? []).map(i => i.supplier).filter(Boolean) as string[])], [items]);

  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<StockInForm>({
    resolver: zodResolver(stockInSchema),
    defaultValues: { transaction_date: today(), quantity: '' as any },
  });

  const [supplier, setSupplier] = useState('');

  const onSubmit = (data: StockInForm) => {
    mutation.mutate(
      { item_id: Number(data.item_id), quantity: data.quantity, unit_price: data.unit_price, supplier: supplier || undefined, transaction_date: data.transaction_date, reason_notes: data.reason_notes || undefined },
      { onSuccess: () => { reset(); setSupplier(''); onOpenChange(false); }, }
    );
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) { reset(); setSupplier(''); } onOpenChange(v); }}>
      <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-white">
            <ArrowUpCircle className="text-emerald-400" size={20} /> Stock In
          </DialogTitle>
          <DialogDescription className="text-slate-400">Record incoming stock / resupply.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 space-y-1.5">
              <Label className="text-slate-300">Item <span className="text-rose-400">*</span></Label>
              <Select onValueChange={(v) => setValue('item_id', v)}>
                <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                  <SelectValue placeholder="Select item…" />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700 text-white">
                  {items?.map((it) => (
                    <SelectItem key={it.id} value={String(it.id)}>
                      {it.item_name} <span className="text-slate-400 text-xs">(stock: {it.current_stock})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldError msg={errors.item_id?.message} />
            </div>

            <div className="space-y-1.5">
              <Label className="text-slate-300">Quantity <span className="text-rose-400">*</span></Label>
              <Input type="number" min={1} {...register('quantity')} className="bg-slate-800 border-slate-700 text-white" placeholder="e.g. 50" />
              <FieldError msg={errors.quantity?.message} />
            </div>

            <div className="space-y-1.5">
              <Label className="text-slate-300">Unit Price (LKR)</Label>
              <Input type="number" min={0} step={0.01} {...register('unit_price')} className="bg-slate-800 border-slate-700 text-white" placeholder="e.g. 250.00" />
            </div>

            <div className="col-span-2 space-y-1.5">
              <Label className="text-slate-300">Supplier</Label>
              <SupplierSelect suppliers={suppliers} value={supplier} onChange={setSupplier} />
            </div>

            <div className="space-y-1.5">
              <Label className="text-slate-300">Date <span className="text-rose-400">*</span></Label>
              <Input type="date" max={todayMax} {...register('transaction_date')} className="bg-slate-800 border-slate-700 text-white" />
              <FieldError msg={errors.transaction_date?.message} />
            </div>

            <div className="col-span-2 space-y-1.5">
              <Label className="text-slate-300">Notes</Label>
              <Textarea {...register('reason_notes')} placeholder="e.g. Monthly resupply from supplier" />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" className="text-slate-400" onClick={() => { reset(); setSupplier(''); onOpenChange(false); }}>Cancel</Button>
            <Button type="submit" disabled={mutation.isPending} className="bg-emerald-600 hover:bg-emerald-700">
              {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Confirm In
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── STOCK OUT DIALOG ─────────────────────────────────────────────────────────
export function StockOutDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { data: items } = useInventoryItems();
  const { data: programs } = usePrograms();
  const mutation = useStockOut();

  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<StockOutForm>({
    resolver: zodResolver(stockOutSchema),
    defaultValues: { transaction_date: today(), quantity: '' as any, program_id: '' },
  });

  const selectedItemId = watch('item_id');
  const quantity = watch('quantity');
  const selectedItem = items?.find(i => String(i.id) === selectedItemId);
  const remaining = selectedItem ? selectedItem.current_stock - (Number(quantity) || 0) : null;

  const onSubmit = (data: StockOutForm) => {
    if (selectedItem && data.quantity > selectedItem.current_stock) {
      toast.error(`Insufficient stock. Available: ${selectedItem.current_stock}`);
      return;
    }
    mutation.mutate(
      {
        item_id: Number(data.item_id),
        quantity: data.quantity,
        transaction_date: data.transaction_date,
        reason_notes: data.reason_notes || undefined,
        program_id: data.program_id ? Number(data.program_id) : null,
      },
      { onSuccess: () => { reset(); onOpenChange(false); } }
    );
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v); }}>
      <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-white">
            <ArrowDownCircle className="text-orange-400" size={20} /> Stock Out
          </DialogTitle>
          <DialogDescription className="text-slate-400">Issue stock from inventory.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 space-y-1.5">
              <Label className="text-slate-300">Item <span className="text-rose-400">*</span></Label>
              <Select onValueChange={(v) => setValue('item_id', v)}>
                <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                  <SelectValue placeholder="Select item…" />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700 text-white">
                  {items?.map((it) => (
                    <SelectItem key={it.id} value={String(it.id)} disabled={it.current_stock === 0}>
                      {it.item_name} <span className="text-slate-400 text-xs">(stock: {it.current_stock})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedItem && (
                <p className="text-xs text-slate-400">Available: <span className="font-semibold text-white">{selectedItem.current_stock}</span> units</p>
              )}
              <FieldError msg={errors.item_id?.message} />
            </div>

            <div className="space-y-1.5">
              <Label className="text-slate-300">Quantity <span className="text-rose-400">*</span></Label>
              <Input type="number" min={1} max={selectedItem?.current_stock} {...register('quantity')} className="bg-slate-800 border-slate-700 text-white" placeholder="e.g. 10" />
              {remaining !== null && (
                <p className={`text-xs font-medium ${remaining < 10 ? 'text-rose-400' : 'text-slate-400'}`}>
                  Remaining after: {remaining} units
                </p>
              )}
              <FieldError msg={errors.quantity?.message} />
            </div>

            <div className="space-y-1.5">
              <Label className="text-slate-300">Date <span className="text-rose-400">*</span></Label>
              <Input type="date" max={todayMax} {...register('transaction_date')} className="bg-slate-800 border-slate-700 text-white" />
              <FieldError msg={errors.transaction_date?.message} />
            </div>

            <div className="col-span-2 space-y-1.5">
              <Label className="text-slate-300">
                Program
                <span className="ml-1 text-xs text-slate-500">(required for Cost-per-Animal tracking)</span>
              </Label>
              <Select onValueChange={(v) => setValue('program_id', v)}>
                <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                  <SelectValue placeholder="Select program (optional)…" />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700 text-white">
                  <SelectItem value="">— None —</SelectItem>
                  {programs?.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>
                      {p.program_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="col-span-2 space-y-1.5">
              <Label className="text-slate-300">Notes</Label>
              <Textarea {...register('reason_notes')} placeholder="e.g. Used for patient treatment" />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" className="text-slate-400" onClick={() => { reset(); onOpenChange(false); }}>Cancel</Button>
            <Button type="submit" disabled={mutation.isPending} className="bg-orange-600 hover:bg-orange-700">
              {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Confirm Out
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── STOCK RETURN DIALOG ──────────────────────────────────────────────────────
export function StockReturnDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { data: items } = useInventoryItems();
  const mutation = useStockReturn();
  const suppliers = useMemo(() => [...new Set((items ?? []).map(i => i.supplier).filter(Boolean) as string[])], [items]);

  const { register, handleSubmit, reset, setValue, formState: { errors } } = useForm<StockReturnForm>({
    resolver: zodResolver(stockReturnSchema),
    defaultValues: { quantity: '' as any },
  });
  const [supplier, setSupplier] = useState('');

  const onSubmit = (data: StockReturnForm) => {
    mutation.mutate(
      { item_id: Number(data.item_id), quantity: data.quantity, supplier: supplier || undefined, reason_notes: data.reason_notes || undefined },
      { onSuccess: () => { reset(); setSupplier(''); onOpenChange(false); } }
    );
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) { reset(); setSupplier(''); } onOpenChange(v); }}>
      <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-white">
            <RotateCcw className="text-purple-400" size={20} /> Stock Return
          </DialogTitle>
          <DialogDescription className="text-slate-400">Return items back to inventory.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 space-y-1.5">
              <Label className="text-slate-300">Item <span className="text-rose-400">*</span></Label>
              <Select onValueChange={(v) => setValue('item_id', v)}>
                <SelectTrigger className="bg-slate-800 border-slate-700 text-white">
                  <SelectValue placeholder="Select item…" />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700 text-white">
                  {items?.map((it) => (
                    <SelectItem key={it.id} value={String(it.id)}>
                      {it.item_name} <span className="text-slate-400 text-xs">(stock: {it.current_stock})</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldError msg={errors.item_id?.message} />
            </div>

            <div className="space-y-1.5">
              <Label className="text-slate-300">Quantity <span className="text-rose-400">*</span></Label>
              <Input type="number" min={1} {...register('quantity')} className="bg-slate-800 border-slate-700 text-white" placeholder="e.g. 5" />
              <FieldError msg={errors.quantity?.message} />
            </div>

            <div className="col-span-2 space-y-1.5">
              <Label className="text-slate-300">Supplier</Label>
              <SupplierSelect suppliers={suppliers} value={supplier} onChange={setSupplier} />
            </div>

            <div className="col-span-2 space-y-1.5">
              <Label className="text-slate-300">Reason / Notes</Label>
              <Textarea {...register('reason_notes')} placeholder="e.g. Defective items, expired stock" />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" className="text-slate-400" onClick={() => { reset(); setSupplier(''); onOpenChange(false); }}>Cancel</Button>
            <Button type="submit" disabled={mutation.isPending} className="bg-purple-600 hover:bg-purple-700">
              {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Confirm Return
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── ADD ITEM DIALOG ──────────────────────────────────────────────────────────
export function AddItemDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const mutation = useAddInventoryItem();

  const { register, handleSubmit, reset, formState: { errors } } = useForm<AddItemForm>({
    resolver: zodResolver(addItemSchema),
    defaultValues: { initial_quantity: 0, unit_cost: 0 },
  });

  const onSubmit = (data: AddItemForm) => {
    mutation.mutate(
      { item_name: data.item_name, initial_quantity: data.initial_quantity, unit_cost: data.unit_cost },
      { onSuccess: () => { reset(); onOpenChange(false); } }
    );
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v); }}>
      <DialogContent className="bg-slate-900 border-slate-700 text-white sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-white">
            <PackagePlus className="text-blue-400" size={20} /> Add New Stock Item
          </DialogTitle>
          <DialogDescription className="text-slate-400">Create a new item in the inventory.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label className="text-slate-300">Item Name <span className="text-rose-400">*</span></Label>
            <Input {...register('item_name')} placeholder="e.g. Surgical Gloves" className="bg-slate-800 border-slate-700 text-white placeholder:text-slate-500" />
            <FieldError msg={errors.item_name?.message} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-slate-300">Initial Qty</Label>
              <Input type="number" min={0} {...register('initial_quantity')} className="bg-slate-800 border-slate-700 text-white" placeholder="0" />
              <FieldError msg={errors.initial_quantity?.message} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-slate-300">Unit Cost (LKR)</Label>
              <Input type="number" min={0} step={0.01} {...register('unit_cost')} className="bg-slate-800 border-slate-700 text-white" placeholder="0.00" />
              <FieldError msg={errors.unit_cost?.message} />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" className="text-slate-400" onClick={() => { reset(); onOpenChange(false); }}>Cancel</Button>
            <Button type="submit" disabled={mutation.isPending} className="bg-blue-600 hover:bg-blue-700">
              {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Add Item
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
