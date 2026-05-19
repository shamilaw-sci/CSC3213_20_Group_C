'use client';

import { useState } from 'react';
import { format } from 'date-fns';
import {
  ArrowUpCircle, ArrowDownCircle, RotateCcw, PackagePlus,
  ArrowUpRight, ArrowDownLeft, Filter, AlertTriangle, Package,
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
  useCostPerAnimal,
} from '@/hooks/useInventory';
import { StockInDialog, StockOutDialog, StockReturnDialog, AddItemDialog } from './dialogs';

export default function InventoryPage() {
  const { data: items, isLoading: loadingItems } = useInventoryItems();
  const { data: transactions, isLoading: loadingTx } = useInventoryTransactions();
  const { data: lowStockItems } = useLowStockItems(10);
  const { data: costRows, isLoading: loadingCost } = useCostPerAnimal();

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
          </div>
          <div className="flex -space-x-2">
            {lowStockItems.slice(0, 3).map(item => (
              <div key={item.id} title={item.item_name}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full border-2 border-slate-900 bg-slate-800 text-[10px] font-bold text-white">
                {item.item_name.substring(0, 2).toUpperCase()}
              </div>
            ))}
            {lowStockItems.length > 3 && (
              <div className="inline-flex h-8 w-8 items-center justify-center rounded-full border-2 border-slate-900 bg-slate-800 text-[10px] font-bold text-slate-400">
                +{lowStockItems.length - 3}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Summary Cards (top 4 items) ── */}
      <div className="grid gap-6 md:grid-cols-4">
        {loadingItems
          ? Array(4).fill(0).map((_, i) => <Skeleton key={i} className="h-24 bg-slate-900 border border-slate-800 rounded-xl" />)
          : items?.slice(0, 4).map((item) => (
              <Card key={item.id} className="bg-slate-900 border-slate-800">
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-medium text-slate-400 uppercase tracking-wider truncate">{item.item_name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-white">{item.current_stock}</div>
                  <p className="text-xs text-slate-500 mt-1">Unit Cost: LKR {item.unit_cost}</p>
                </CardContent>
              </Card>
            ))}
      </div>

      {/* ── Main Grid: Stock Table + Recent Movements ── */}
      <div className="grid lg:grid-cols-3 gap-8">
        {/* Detailed Stock List */}
        <Card className="lg:col-span-2 bg-slate-900 border-slate-800">
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
        <Card className="bg-slate-900 border-slate-800">
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
              <div className="space-y-3">
                {transactions?.slice(0, 10).map((tx) => {
                  const isOut = tx.transaction_type === 'Issue';
                  const isIn  = tx.transaction_type === 'Return';
                  const color = isOut ? 'rose' : isIn ? 'emerald' : 'sky';
                  return (
                    <div key={tx.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-950 border border-slate-800/50">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-full bg-${color}-500/10 text-${color}-400`}>
                          {isOut ? <ArrowUpRight size={16} /> : <ArrowDownLeft size={16} />}
                        </div>
                        <div>
                          <p className="text-sm font-medium text-white">{tx.inventory_items?.item_name}</p>
                          <p className="text-xs text-slate-500">{format(new Date(tx.transaction_date), 'MMM dd, yyyy')}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className={`text-sm font-bold text-${color}-400`}>
                          {isOut ? '−' : '+'}{tx.quantity}
                        </p>
                        <p className="text-[10px] text-slate-600 uppercase font-bold tracking-tighter">
                          {tx.transaction_type}
                        </p>
                      </div>
                    </div>
                  );
                })}
                {transactions?.length === 0 && (
                  <p className="text-center py-8 text-slate-600 text-sm">No recent movements</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Cost Per Animal Panel ── */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-500/10">
              <Package className="h-5 w-5 text-blue-400" />
            </div>
            <div>
              <CardTitle className="text-white">Cost per Animal Treated</CardTitle>
              <CardDescription>Inventory spend per program divided by animals treated.</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loadingCost ? (
            <div className="space-y-2">
              {Array(3).fill(0).map((_, i) => <Skeleton key={i} className="h-10 w-full bg-slate-800" />)}
            </div>
          ) : !costRows || costRows.length === 0 ? (
            <p className="text-center py-10 text-slate-600 text-sm">No issued transactions linked to programs yet.</p>
          ) : (
            <div className="rounded-md border border-slate-800 overflow-hidden">
              <Table>
                <TableHeader className="bg-slate-950">
                  <TableRow className="hover:bg-transparent border-slate-800">
                    <TableHead className="text-slate-300">Program</TableHead>
                    <TableHead className="text-slate-300 text-right">Animals Treated</TableHead>
                    <TableHead className="text-slate-300 text-right">Total Cost</TableHead>
                    <TableHead className="text-slate-300 text-right">Cost / Animal</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {costRows.map((row) => (
                    <TableRow key={row.program_id} className="border-slate-800 hover:bg-slate-800/40">
                      <TableCell className="font-medium text-white">{row.program_name}</TableCell>
                      <TableCell className="text-right text-slate-300">{row.animals_treated.toLocaleString()}</TableCell>
                      <TableCell className="text-right text-slate-300">
                        LKR {row.total_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge variant="outline" className={
                          row.cost_per_animal > 50 ? 'text-rose-400 border-rose-400/30 bg-rose-400/10'
                          : row.cost_per_animal > 20 ? 'text-amber-400 border-amber-400/30 bg-amber-400/10'
                          : 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10'
                        }>
                          {row.animals_treated > 0
                            ? `LKR ${row.cost_per_animal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                            : '—'}
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
    </div>
  );
}
