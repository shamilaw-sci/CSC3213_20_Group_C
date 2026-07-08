'use client';

import { useState } from 'react';
import { format } from 'date-fns';
import {
  ArrowUpCircle, ArrowDownCircle, RotateCcw, PackagePlus,
  Filter, AlertTriangle,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  useInventoryItems,
  useInventoryTransactions,
  useLowStockItems,
} from '@/hooks/useInventory';
import { StockInDialog, StockOutDialog, StockReturnDialog, AddItemDialog } from './dialogs';

export default function InventoryPage() {
  const { data: items, isLoading: loadingItems } = useInventoryItems();
  const { data: transactions, isLoading: loadingTx } = useInventoryTransactions();
  const { data: lowStockItems } = useLowStockItems(10);

  const [stockInOpen, setStockInOpen] = useState(false);
  const [stockOutOpen, setStockOutOpen] = useState(false);
  const [stockReturnOpen, setStockReturnOpen] = useState(false);
  const [addItemOpen, setAddItemOpen] = useState(false);

  return (
    <div className="space-y-8">
      {/* ── Header ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-2">Inventory System</h1>
          <p className="text-slate-400">Manage medical supplies, equipment, and resource allocations.</p>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setStockInOpen(true)} className="bg-emerald-600 hover:bg-emerald-700 text-white">
            <ArrowUpCircle className="w-4 h-4 mr-2" /> Stock In
          </Button>
          <Button onClick={() => setStockOutOpen(true)} variant="outline" className="border-orange-500 text-orange-400 hover:bg-orange-500/10">
            <ArrowDownCircle className="w-4 h-4 mr-2" /> Stock Out
          </Button>
          <Button onClick={() => setStockReturnOpen(true)} variant="outline" className="border-purple-500 text-purple-400 hover:bg-purple-500/10">
            <RotateCcw className="w-4 h-4 mr-2" /> Stock Return
          </Button>
          <Button onClick={() => setAddItemOpen(true)} className="bg-blue-600 hover:bg-blue-700 text-white">
            <PackagePlus className="w-4 h-4 mr-2" /> Add Item
          </Button>
        </div>
      </div>

      {/* Dialogs */}
      <StockInDialog     open={stockInOpen}     onOpenChange={setStockInOpen} />
      <StockOutDialog    open={stockOutOpen}    onOpenChange={setStockOutOpen} />
      <StockReturnDialog open={stockReturnOpen} onOpenChange={setStockReturnOpen} />
      <AddItemDialog     open={addItemOpen}     onOpenChange={setAddItemOpen} />

      {/* ── Low-Stock Alert Banner ── */}
      {lowStockItems && lowStockItems.length > 0 && (
        <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl p-4 flex items-center gap-4 animate-in fade-in slide-in-from-top-4 duration-500">
          <div className="p-2 bg-rose-500/20 rounded-full text-rose-400">
            <AlertTriangle size={20} />
          </div>
          <div className="flex-1">
            <p className="text-sm font-bold text-white">Low Stock Alert</p>
            <p className="text-xs text-rose-400/80">
              {lowStockItems.length} {lowStockItems.length === 1 ? 'item is' : 'items are'} below the minimum threshold (10 units).
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {lowStockItems.map((item) => (
                <span
                  key={item.id}
                  className="rounded-full border border-rose-400/20 bg-rose-400/10 px-2.5 py-1 text-[11px] font-medium text-rose-300"
                >
                  {item.item_name} ({item.current_stock})
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Main Grid: Stock Table + Recent Movements ── */}
      <div className="grid gap-8">
        {/* Detailed Stock List */}
        <Card className="w-full bg-slate-900 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-white">Detailed Stock List</CardTitle>
              <CardDescription>Current availability and unit costs.</CardDescription>
            </div>
            <Button variant="ghost" size="icon" className="text-slate-400"><Filter size={18} /></Button>
          </CardHeader>
          <CardContent>
            {loadingItems ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full bg-slate-800" />
                <Skeleton className="h-10 w-full bg-slate-800" />
              </div>
            ) : (
              <div className="rounded-md border border-slate-800 overflow-x-auto">
                <Table className="min-w-full">
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
                          <Badge variant="outline" className={item.current_stock < 10
                            ? 'text-rose-400 border-rose-400/30 bg-rose-400/10'
                            : 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10'}>
                            {item.current_stock}
                          </Badge>
                        </TableCell>
                        <TableCell>LKR {item.unit_cost}</TableCell>
                        <TableCell className="text-slate-400">
                          LKR {(item.current_stock * item.unit_cost).toLocaleString()}
                        </TableCell>
                      </TableRow>
                    ))}
                    {items?.length === 0 && (
                      <TableRow><TableCell colSpan={4} className="text-center py-8 text-slate-500">No items in inventory yet.</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Movements */}
        <Card className="w-full bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle className="text-white">Recent Movements</CardTitle>
            <CardDescription>Last 10 issue / return / restock logs.</CardDescription>
          </CardHeader>
          <CardContent>
            {loadingTx ? (
              <div className="space-y-4">
                <Skeleton className="h-12 w-full bg-slate-800" />
                <Skeleton className="h-12 w-full bg-slate-800" />
              </div>
            ) : (
              <div className="overflow-x-auto rounded-md border border-slate-800">
                <Table className="min-w-[760px]">
                  <TableHeader className="bg-slate-950">
                    <TableRow className="border-slate-800">
                      <TableHead className="text-slate-300 whitespace-nowrap">Date</TableHead>
                      <TableHead className="text-slate-300 whitespace-nowrap">Item</TableHead>
                      <TableHead className="text-right text-slate-300 whitespace-nowrap">Qty</TableHead>
                      <TableHead className="text-right text-slate-300 whitespace-nowrap">Unit Cost</TableHead>
                      <TableHead className="text-right text-slate-300 whitespace-nowrap">Total Cost</TableHead>
                      <TableHead className="text-right text-slate-300 whitespace-nowrap">Type</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {transactions?.slice(0, 10).map((tx) => {
                      const isOut = tx.transaction_type === 'Issue';
                      const isIn = tx.transaction_type === 'Return';
                      const unitCost = tx.inventory_items?.unit_cost ?? 0;
                      const totalCost = tx.quantity * unitCost;
                      return (
                        <TableRow key={tx.id} className="border-slate-800 hover:bg-slate-800/40">
                          <TableCell className="text-slate-300 text-sm">{format(new Date(tx.transaction_date), 'MMM dd')}</TableCell>
                          <TableCell>
                            <div className="text-sm font-medium text-white">{tx.inventory_items?.item_name ?? 'Unknown item'}</div>
                            {tx.programs?.program_name && (
                              <div className="text-[11px] text-slate-500">{tx.programs.program_name}</div>
                            )}
                          </TableCell>
                          <TableCell className="text-right text-slate-300">{tx.quantity}</TableCell>
                          <TableCell className="text-right text-slate-300">{unitCost > 0 ? `LKR ${unitCost.toLocaleString()}` : '—'}</TableCell>
                          <TableCell className="text-right text-slate-300">{unitCost > 0 ? `LKR ${totalCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}</TableCell>
                          <TableCell className="text-right">
                            <Badge variant="outline" className={
                              isOut ? 'text-rose-400 border-rose-400/30 bg-rose-400/10' : isIn ? 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10' : 'text-sky-400 border-sky-400/30 bg-sky-400/10'
                            }>
                              {tx.transaction_type}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                    {transactions?.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={6} className="text-center py-8 text-slate-500">
                          No recent movements
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

    </div>
  );
}
