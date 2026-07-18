'use client';

import { useInventoryItems, useInventoryTransactions, useCreateInventoryTransaction, useCreateInventoryItem } from '@/hooks/useInventory';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Package, Filter, Plus, ArrowDownCircle, ArrowUpCircle, RotateCcw } from 'lucide-react';
import { format } from 'date-fns';
import Swal from 'sweetalert2';
import { toast } from 'sonner';
import { useThemeStore } from '@/store/useThemeStore';
import { useQuery } from '@tanstack/react-query';
import { FinanceService } from '@/services/finance.service';

export default function InventoryPage() {
  const { data: items, isLoading: loadingItems } = useInventoryItems();
  const { data: transactions, isLoading: loadingTransactions } = useInventoryTransactions();
  
  const createItem = useCreateInventoryItem();
  const createTransaction = useCreateInventoryTransaction();

  // Fetch programs for issue/return select list
  const { data: programs } = useQuery({
    queryKey: ['programs'],
    queryFn: FinanceService.getPrograms
  });

  const handleAddItem = () => {
    const isDark = useThemeStore.getState().theme === 'dark';
    const inputStyle = `width: 100%; margin-top: 4px; box-sizing: border-box; font-size: 12px; height: 38px; background: ${isDark ? '#14161C' : '#FFFFFF'}; color: ${isDark ? '#F9FAFB' : '#111318'}; border: 1px solid ${isDark ? '#232730' : '#E5E7EB'}; border-radius: 8px; padding: 0 10px;`;
    
    Swal.fire({
      title: 'Add Inventory Item',
      html: `
        <div style="display: flex; flex-direction: column; gap: 12px; text-align: left; font-family: sans-serif;">
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'}; uppercase; tracking-wider;">ITEM NAME</label>
            <input id="swal-iname" style="${inputStyle}" placeholder="e.g. Rabies Vaccine Vials">
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'}; uppercase; tracking-wider;">INITIAL STOCK</label>
            <input id="swal-istock" type="number" style="${inputStyle}" placeholder="100">
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'}; uppercase; tracking-wider;">UNIT COST (LKR)</label>
            <input id="swal-icost" type="number" style="${inputStyle}" placeholder="1500">
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'}; uppercase; tracking-wider;">SUPPLIER (OPTIONAL)</label>
            <input id="swal-isupplier" style="${inputStyle}" placeholder="e.g. ABC Pharma">
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'}; uppercase; tracking-wider;">EXPIRE DATE (OPTIONAL)</label>
            <input id="swal-iexpire" type="date" style="${inputStyle}">
          </div>
        </div>
      `,
      background: isDark ? '#0F1520' : '#FFFFFF',
      color: isDark ? '#F9FAFB' : '#111318',
      showCancelButton: true,
      confirmButtonText: 'Add Item',
      confirmButtonColor: '#EF9F27',
      cancelButtonText: 'Cancel',
      cancelButtonColor: isDark ? '#232730' : '#E5E7EB',
      preConfirm: () => {
        const name = (document.getElementById('swal-iname') as HTMLInputElement).value.trim();
        const stock = (document.getElementById('swal-istock') as HTMLInputElement).value.trim();
        const cost = (document.getElementById('swal-icost') as HTMLInputElement).value.trim();
        const supplier = (document.getElementById('swal-isupplier') as HTMLInputElement).value.trim();
        const expire = (document.getElementById('swal-iexpire') as HTMLInputElement).value;

        if (!name || !stock || !cost) {
          Swal.showValidationMessage('Item name, stock, and unit cost are required');
          return false;
        }

        const stockVal = parseInt(stock);
        const costVal = parseFloat(cost);

        if (isNaN(stockVal) || stockVal < 0) {
          Swal.showValidationMessage('Stock must be a non-negative integer');
          return false;
        }
        if (isNaN(costVal) || costVal <= 0) {
          Swal.showValidationMessage('Unit cost must be a positive number');
          return false;
        }

        return {
          item_name: name,
          current_stock: stockVal,
          unit_cost: costVal,
          supplier_name: supplier || undefined,
          expire_date: expire || undefined,
        };
      }
    }).then((result) => {
      if (result.isConfirmed && result.value) {
        createItem.mutate(result.value, {
          onSuccess: () => toast.success('Inventory item added successfully!')
        });
      }
    });
  };

  // ------------------------------------------------------------------
  // STOCK IN (green) — new inventory entering the organization.
  //
  // Supplier, Unit Cost, and Expire Date live on the ITEM (set once in
  // Add Item), not repeated on every Stock In — those are one-time
  // facts about the item, not something that changes each restock.
  // Stock In only asks what's actually different each time: how much
  // came in, when, and any notes. Because unit_cost/supplier_name/
  // expire_date are omitted from the request below, the RPC (see
  // migration_004) simply keeps the item's existing values unchanged.
  //
  // transaction_type is always 'Restock', and program_id is always
  // null because incoming stock isn't tied to any single program.
  // ------------------------------------------------------------------
  const handleStockIn = () => {
    if (!items || items.length === 0) {
      toast.error('Add an inventory item first before stocking in');
      return;
    }

    const isDark = useThemeStore.getState().theme === 'dark';
    const inputStyle = `width: 100%; margin-top: 4px; box-sizing: border-box; font-size: 12px; height: 38px; background: ${isDark ? '#14161C' : '#FFFFFF'}; color: ${isDark ? '#F9FAFB' : '#111318'}; border: 1px solid ${isDark ? '#232730' : '#E5E7EB'}; border-radius: 8px; padding: 0 10px;`;
    const textareaStyle = inputStyle.replace('height: 38px', 'height: 70px; padding-top: 8px;');

    const itemsOptions = items.map(item => `<option value="${item.id}">${item.item_name} (Current: ${item.current_stock})</option>`).join('');
    const today = new Date().toISOString().split('T')[0];

    Swal.fire({
      title: 'Stock In',
      html: `
        <div style="display: flex; flex-direction: column; gap: 12px; text-align: left; font-family: sans-serif;">
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">INVENTORY ITEM</label>
            <select id="swal-in-item" style="${inputStyle}">${itemsOptions}</select>
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">QUANTITY</label>
            <input id="swal-in-qty" type="number" style="${inputStyle}" placeholder="50">
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">DATE</label>
            <input id="swal-in-date" type="date" style="${inputStyle}" value="${today}">
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">NOTES (OPTIONAL)</label>
            <textarea id="swal-in-notes" style="${textareaStyle}" placeholder="Any additional detail..."></textarea>
          </div>
        </div>
      `,
      background: isDark ? '#0F1520' : '#FFFFFF',
      color: isDark ? '#F9FAFB' : '#111318',
      showCancelButton: true,
      confirmButtonText: 'Stock In',
      confirmButtonColor: '#16A34A', // green — matches the button's meaning
      cancelButtonText: 'Cancel',
      cancelButtonColor: isDark ? '#232730' : '#E5E7EB',
      preConfirm: () => {
        const itemIdStr = (document.getElementById('swal-in-item') as HTMLSelectElement).value;
        const qtyStr = (document.getElementById('swal-in-qty') as HTMLInputElement).value.trim();
        const dateStr = (document.getElementById('swal-in-date') as HTMLInputElement).value;
        const notes = (document.getElementById('swal-in-notes') as HTMLTextAreaElement).value.trim();

        if (!itemIdStr || !qtyStr || !dateStr) {
          Swal.showValidationMessage('Item, quantity, and date are required');
          return false;
        }

        const qtyVal = parseInt(qtyStr);
        if (isNaN(qtyVal) || qtyVal <= 0) {
          Swal.showValidationMessage('Quantity must be a positive number');
          return false;
        }

        return {
          item_id: parseInt(itemIdStr),
          quantity: qtyVal,
          transaction_type: 'Restock' as const,
          transaction_date: dateStr,
          program_id: null,
          notes: notes || undefined,
        };
      }
    }).then((result) => {
      if (result.isConfirmed && result.value) {
        createTransaction.mutate(result.value, {
          onSuccess: () => toast.success('Stock In recorded successfully!'),
          onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to record Stock In')
        });
      }
    });
  };

  // ------------------------------------------------------------------
  // STOCK OUT (red) — inventory issued for veterinary work.
  // transaction_type is always 'Issue'. program_id matters here: it's
  // how the Cost-per-Animal feature later knows which program consumed
  // this inventory.
  // ------------------------------------------------------------------
  const handleStockOut = () => {
    if (!items || items.length === 0) {
      toast.error('No inventory items available to issue');
      return;
    }

    const isDark = useThemeStore.getState().theme === 'dark';
    const inputStyle = `width: 100%; margin-top: 4px; box-sizing: border-box; font-size: 12px; height: 38px; background: ${isDark ? '#14161C' : '#FFFFFF'}; color: ${isDark ? '#F9FAFB' : '#111318'}; border: 1px solid ${isDark ? '#232730' : '#E5E7EB'}; border-radius: 8px; padding: 0 10px;`;

    const itemsOptions = items.map(item => `<option value="${item.id}">${item.item_name} (Current: ${item.current_stock})</option>`).join('');
    const programsOptions = (programs || []).map(p => `<option value="${p.id}">${p.program_name}</option>`).join('');
    const today = new Date().toISOString().split('T')[0];

    Swal.fire({
      title: 'Stock Out',
      html: `
        <div style="display: flex; flex-direction: column; gap: 12px; text-align: left; font-family: sans-serif;">
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">INVENTORY ITEM</label>
            <select id="swal-out-item" style="${inputStyle}">${itemsOptions}</select>
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">QUANTITY</label>
            <input id="swal-out-qty" type="number" style="${inputStyle}" placeholder="10">
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">PROGRAM (OPTIONAL)</label>
            <select id="swal-out-program" style="${inputStyle}">
              <option value="none">Stock Adjustment (No Program)</option>
              ${programsOptions}
            </select>
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">DATE</label>
            <input id="swal-out-date" type="date" style="${inputStyle}" value="${today}">
          </div>
        </div>
      `,
      background: isDark ? '#0F1520' : '#FFFFFF',
      color: isDark ? '#F9FAFB' : '#111318',
      showCancelButton: true,
      confirmButtonText: 'Stock Out',
      confirmButtonColor: '#DC2626', // red
      cancelButtonText: 'Cancel',
      cancelButtonColor: isDark ? '#232730' : '#E5E7EB',
      preConfirm: () => {
        const itemIdStr = (document.getElementById('swal-out-item') as HTMLSelectElement).value;
        const qtyStr = (document.getElementById('swal-out-qty') as HTMLInputElement).value.trim();
        const progIdStr = (document.getElementById('swal-out-program') as HTMLSelectElement).value;
        const dateStr = (document.getElementById('swal-out-date') as HTMLInputElement).value;

        if (!itemIdStr || !qtyStr || !dateStr) {
          Swal.showValidationMessage('Item, quantity, and date are required');
          return false;
        }

        const qtyVal = parseInt(qtyStr);
        if (isNaN(qtyVal) || qtyVal <= 0) {
          Swal.showValidationMessage('Quantity must be a positive number');
          return false;
        }

        return {
          item_id: parseInt(itemIdStr),
          quantity: qtyVal,
          transaction_type: 'Issue' as const,
          transaction_date: dateStr,
          program_id: progIdStr === 'none' ? null : parseInt(progIdStr),
        };
      }
    }).then((result) => {
      if (result.isConfirmed && result.value) {
        createTransaction.mutate(result.value, {
          onSuccess: () => toast.success('Stock Out recorded successfully!'),
          // The backend surfaces the exact Postgres error (e.g.
          // "Insufficient stock: have 5, requested 10") in
          // err.response.data.detail — showing it directly means the
          // user sees exactly why it failed, not a generic message.
          onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to record Stock Out')
        });
      }
    });
  };

  // ------------------------------------------------------------------
  // STOCK RETURN (light green) — unused inventory coming back.
  // Deliberately the simplest of the three dialogs: just item,
  // quantity, and date. transaction_type is always 'Return'.
  // ------------------------------------------------------------------
  const handleStockReturn = () => {
    if (!items || items.length === 0) {
      toast.error('No inventory items available to return');
      return;
    }

    const isDark = useThemeStore.getState().theme === 'dark';
    const inputStyle = `width: 100%; margin-top: 4px; box-sizing: border-box; font-size: 12px; height: 38px; background: ${isDark ? '#14161C' : '#FFFFFF'}; color: ${isDark ? '#F9FAFB' : '#111318'}; border: 1px solid ${isDark ? '#232730' : '#E5E7EB'}; border-radius: 8px; padding: 0 10px;`;

    const itemsOptions = items.map(item => `<option value="${item.id}">${item.item_name} (Current: ${item.current_stock})</option>`).join('');
    const today = new Date().toISOString().split('T')[0];

    Swal.fire({
      title: 'Stock Return',
      html: `
        <div style="display: flex; flex-direction: column; gap: 12px; text-align: left; font-family: sans-serif;">
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">INVENTORY ITEM</label>
            <select id="swal-ret-item" style="${inputStyle}">${itemsOptions}</select>
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">QUANTITY</label>
            <input id="swal-ret-qty" type="number" style="${inputStyle}" placeholder="10">
          </div>
          <div>
            <label style="font-size: 10px; font-weight: bold; color: ${isDark ? '#9CA3AF' : '#6B7280'};">DATE</label>
            <input id="swal-ret-date" type="date" style="${inputStyle}" value="${today}">
          </div>
        </div>
      `,
      background: isDark ? '#0F1520' : '#FFFFFF',
      color: isDark ? '#F9FAFB' : '#111318',
      showCancelButton: true,
      confirmButtonText: 'Return Stock',
      confirmButtonColor: '#4ADE80', // light green
      cancelButtonText: 'Cancel',
      cancelButtonColor: isDark ? '#232730' : '#E5E7EB',
      preConfirm: () => {
        const itemIdStr = (document.getElementById('swal-ret-item') as HTMLSelectElement).value;
        const qtyStr = (document.getElementById('swal-ret-qty') as HTMLInputElement).value.trim();
        const dateStr = (document.getElementById('swal-ret-date') as HTMLInputElement).value;

        if (!itemIdStr || !qtyStr || !dateStr) {
          Swal.showValidationMessage('Item, quantity, and date are required');
          return false;
        }

        const qtyVal = parseInt(qtyStr);
        if (isNaN(qtyVal) || qtyVal <= 0) {
          Swal.showValidationMessage('Quantity must be a positive number');
          return false;
        }

        return {
          item_id: parseInt(itemIdStr),
          quantity: qtyVal,
          transaction_type: 'Return' as const,
          transaction_date: dateStr,
          program_id: null,
        };
      }
    }).then((result) => {
      if (result.isConfirmed && result.value) {
        createTransaction.mutate(result.value, {
          onSuccess: () => toast.success('Stock Return recorded successfully!'),
          onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to record Stock Return')
        });
      }
    });
  };

  // Maps each of the 3 transaction types to its own icon, color, and sign
  // for the Recent Movements list — replaces the old logic that only
  // distinguished 'Issue' from "everything else", which is no longer
  // accurate now that there are 3 distinct transaction types.
  const getMovementDisplay = (type: string) => {
    switch (type) {
      case 'Issue':
        return { colorClass: 'bg-red-500/10 text-negative', Icon: ArrowUpCircle, sign: '-' };
      case 'Restock':
        return { colorClass: 'bg-green-500/10 text-positive', Icon: ArrowDownCircle, sign: '+' };
      case 'Return':
        return { colorClass: 'bg-green-300/20 text-green-600', Icon: RotateCcw, sign: '+' };
      default:
        return { colorClass: 'bg-gray-500/10 text-text-secondary', Icon: Package, sign: '' };
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
            Inventory System
          </h1>
          <p className="text-text-secondary text-sm">
            Manage medical supplies, equipment, and resource allocations.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button 
            onClick={handleAddItem}
            variant="outline" 
            className="border-border-brand text-text-primary hover:bg-bg-subtle text-xs rounded-lg"
          >
            <Plus className="mr-2 h-4 w-4" /> Add Item
          </Button>
          <Button 
            onClick={handleStockIn}
            className="bg-green-600 hover:bg-green-700 text-white font-semibold text-xs rounded-lg shadow-sm"
          >
            <ArrowDownCircle className="mr-2 h-4 w-4" /> Stock In
          </Button>
          <Button 
            onClick={handleStockOut}
            className="bg-red-600 hover:bg-red-700 text-white font-semibold text-xs rounded-lg shadow-sm"
          >
            <ArrowUpCircle className="mr-2 h-4 w-4" /> Stock Out
          </Button>
          <Button 
            onClick={handleStockReturn}
            className="bg-green-300 hover:bg-green-400 text-green-950 font-semibold text-xs rounded-lg shadow-sm"
          >
            <RotateCcw className="mr-2 h-4 w-4" /> Stock Return
          </Button>
        </div>
      </div>

      {/* Overview KPI Cards */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {loadingItems ? (
          Array(4).fill(0).map((_, i) => <Skeleton key={i} className="h-24 bg-bg-subtle border border-border-brand rounded-card" />)
        ) : (
          items?.slice(0, 4).map(item => (
            <Card key={item.id} className="bg-surface border border-border-brand rounded-card shadow-card p-5">
              <CardHeader className="pb-2 p-0">
                <CardTitle className="text-xs font-semibold text-text-secondary uppercase tracking-wider">{item.item_name}</CardTitle>
              </CardHeader>
              <CardContent className="p-0 pt-2">
                <div className="text-2xl font-bold font-mono text-text-primary">{item.current_stock}</div>
                <p className="text-xs text-text-muted mt-1 font-mono">Unit Cost: ${item.unit_cost}</p>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Stock list & Movements */}
      <div className="grid lg:grid-cols-3 gap-8">
        {/* Stock List Card */}
        <Card className="lg:col-span-2 bg-surface border border-border-brand rounded-card shadow-card p-5">
          <CardHeader className="flex flex-row items-center justify-between p-0 pb-4">
            <div>
              <CardTitle className="text-base font-semibold font-heading text-text-primary">Detailed Stock List</CardTitle>
              <CardDescription className="text-text-secondary text-xs mt-1">Current availability and unit costs.</CardDescription>
            </div>
            <Button variant="ghost" size="icon" className="text-text-secondary hover:text-text-primary hover:bg-bg-subtle">
              <Filter size={18} />
            </Button>
          </CardHeader>
          <CardContent className="p-0 pt-4">
            {loadingItems ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full bg-bg-subtle" />
                <Skeleton className="h-10 w-full bg-bg-subtle" />
              </div>
            ) : (
              <div className="rounded-xl border border-border-brand overflow-hidden">
                <Table>
                  <TableHeader className="bg-bg-subtle">
                    <TableRow className="hover:bg-transparent border-border-brand">
                      <TableHead className="text-text-secondary font-heading text-xs">Item Name</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs">Stock</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs">Unit Cost</TableHead>
                      <TableHead className="text-text-secondary font-heading text-xs">Total Value</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items?.map((item) => (
                      <TableRow key={item.id} className="border-border-brand hover:bg-[#14161C]/40 transition-colors">
                        <TableCell className="font-semibold text-text-primary text-xs">{item.item_name}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={
                            item.current_stock < 10 
                              ? 'text-negative border border-red-500/20 bg-red-500/5 rounded-full px-2 py-0.5 text-[10px]' 
                              : 'text-positive border border-green-500/20 bg-green-500/5 rounded-full px-2 py-0.5 text-[10px]'
                          }>
                            {item.current_stock}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-text-primary font-semibold">LKR {item.unit_cost}</TableCell>
                        <TableCell className="text-text-secondary font-mono text-xs">LKR {(item.current_stock * item.unit_cost).toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Movements Card */}
        <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
          <CardHeader className="p-0 pb-4">
            <CardTitle className="text-base font-semibold font-heading text-text-primary">Recent Movements</CardTitle>
            <CardDescription className="text-text-secondary text-xs mt-1">Last 10 issue/return logs.</CardDescription>
          </CardHeader>
          <CardContent className="p-0 pt-4">
            {loadingTransactions ? (
              <div className="space-y-4">
                <Skeleton className="h-12 w-full bg-bg-subtle" />
                <Skeleton className="h-12 w-full bg-bg-subtle" />
              </div>
            ) : (
              <div className="space-y-4">
                {transactions?.slice(0, 10).map((tx) => {
                  const { colorClass, Icon, sign } = getMovementDisplay(tx.transaction_type);
                  return (
                  <div key={tx.id} className="flex items-center justify-between p-3 rounded-lg bg-bg-subtle border border-border-brand hover:border-accent/20 transition-all">
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-full ${colorClass}`}>
                        <Icon size={16} />
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-text-primary">{tx.inventory_items?.item_name}</p>
                        <p className="text-[10px] text-text-muted mt-0.5">{format(new Date(tx.transaction_date), 'MMM dd, yyyy')} · {tx.transaction_type}</p>
                      </div>
                    </div>
                    <div className="text-right">
                       <p className={`text-xs font-bold font-mono ${sign === '-' ? 'text-negative' : 'text-positive'}`}>
                         {sign}{tx.quantity}
                       </p>
                       <p className="text-[9px] text-text-secondary uppercase font-bold tracking-wider mt-0.5">{tx.programs?.program_name || 'Stock'}</p>
                    </div>
                  </div>
                  );
                })}
                {transactions?.length === 0 && <p className="text-center py-8 text-text-muted text-xs italic">No recent movements</p>}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      
    </div>
  );
}
