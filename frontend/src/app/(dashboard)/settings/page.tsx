'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Moon, Sun, Check, Loader2 } from 'lucide-react';
import { useThemeStore } from '@/store/useThemeStore';
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from '@/hooks/useNotifications';
import { KIND_ICON, timeAgo } from '@/components/layout/notification-kinds';
import { cn } from '@/lib/utils';

// The history behind the bell's Updates (migration 032): decisions about
// you, newest first. They are kept, so there is nothing to delete; reading
// one, here or in the bell, marks it read.
function UpdatesHistory() {
  const router = useRouter();
  const { data, isLoading, isError } = useNotifications(200);
  const { mutate: markRead } = useMarkNotificationRead();
  const { mutate: markAllRead, isPending: markingAll } = useMarkAllNotificationsRead();

  return (
    <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
      <CardHeader className="flex flex-row items-center justify-between p-0 pb-4">
        <div>
          <CardTitle className="text-base font-semibold font-heading text-text-primary">Your updates</CardTitle>
          <CardDescription className="text-text-secondary text-xs mt-1">
            Decisions about your leave, attendance corrections, payslips and rescue cases.
          </CardDescription>
        </div>
        {!!data?.unread && (
          <Button onClick={() => markAllRead()} disabled={markingAll} variant="outline" size="sm"
            className="border-border-brand text-text-primary hover:bg-bg-subtle text-[10px] px-2.5 h-8">
            <Check className="mr-1.5 h-3.5 w-3.5" /> Mark all read ({data.unread})
          </Button>
        )}
      </CardHeader>
      <CardContent className="p-0 pt-2 space-y-2">
        {isLoading ? (
          <p className="flex items-center gap-2 py-8 text-xs text-text-secondary">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </p>
        ) : isError || !data ? (
          <p className="py-8 text-xs text-negative">Couldn&apos;t load your updates.</p>
        ) : data.items.length === 0 ? (
          <p className="text-center py-12 text-text-muted text-xs italic">
            Nothing yet. When your leave, a correction or a payslip is decided, or someone assigns you a case, it shows here.
          </p>
        ) : (
          data.items.map((n) => {
            const Icon = KIND_ICON[n.kind];
            return (
              <div key={n.id}
                className={cn('flex items-start gap-3 p-3 rounded-lg border',
                  n.read_at ? 'border-border-brand' : 'bg-accent/5 border-accent/20')}>
                <div className="p-2 rounded bg-bg-subtle border border-border-brand mt-0.5">
                  <Icon className="h-4 w-4 text-accent" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className={cn('text-xs', n.read_at ? 'text-text-secondary' : 'text-text-primary font-semibold')}>{n.title}</p>
                  {n.body && <p className="mt-0.5 text-xs text-text-secondary">{n.body}</p>}
                  <span className="text-[10px] text-text-muted mt-1 block font-mono">{timeAgo(n.created_at)}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  {n.href && (
                    <Button variant="ghost" size="sm" className="h-7 px-2 text-[10px] text-accent hover:bg-accent/10"
                      onClick={() => { if (!n.read_at) markRead(n.id); router.push(n.href!); }}>
                      Open
                    </Button>
                  )}
                  {!n.read_at && (
                    <Button onClick={() => markRead(n.id)} variant="ghost" size="sm" aria-label="Mark as read"
                      className="text-accent hover:bg-accent/10 h-7 w-7 p-0">
                      <Check className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('notifications');
  const { theme, toggleTheme } = useThemeStore();

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
          Settings & Configurations
        </h1>
        <p className="text-text-secondary text-sm">
          Your updates and display preferences.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="bg-bg-subtle border border-border-brand p-1 rounded-lg">
          <TabsTrigger value="notifications" className="data-[state=active]:bg-surface data-[state=active]:text-accent text-xs font-semibold rounded-md transition-all">
            Your Updates
          </TabsTrigger>
          <TabsTrigger value="app" className="data-[state=active]:bg-surface data-[state=active]:text-accent text-xs font-semibold rounded-md transition-all">
            Preferences & Theme
          </TabsTrigger>
        </TabsList>

        {/* Notifications Tab */}
        <TabsContent value="notifications" className="mt-6">
          <UpdatesHistory />
        </TabsContent>

        {/* Preferences Tab */}
        <TabsContent value="app" className="mt-6">
          <Card className="bg-surface border border-border-brand rounded-card shadow-card p-5">
            <CardHeader className="p-0 pb-4">
              <CardTitle className="text-base font-semibold font-heading text-text-primary">Theme Settings</CardTitle>
              <CardDescription className="text-text-secondary text-xs mt-1">Configure workspace aesthetic parameters and interface styling.</CardDescription>
            </CardHeader>
            <CardContent className="p-0 pt-4 space-y-6">
              <div className="flex items-center justify-between p-4 rounded-lg bg-bg-subtle border border-border-brand">
                <div className="space-y-0.5">
                  <h4 className="text-sm font-semibold text-text-primary">Visual Layout Theme</h4>
                  <p className="text-xs text-text-secondary">Toggle between high-contrast dark theme and light theme options.</p>
                </div>
                <div className="flex items-center gap-3">
                  <Sun className={`h-4 w-4 ${theme === 'light' ? 'text-[#EF9F27]' : 'text-text-secondary'}`} />
                  <Switch 
                    checked={theme === 'dark'} 
                    onCheckedChange={toggleTheme}
                    className="data-[state=checked]:bg-[#EF9F27]"
                  />
                  <Moon className={`h-4 w-4 ${theme === 'dark' ? 'text-[#EF9F27]' : 'text-text-secondary'}`} />
                </div>
              </div>

            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
