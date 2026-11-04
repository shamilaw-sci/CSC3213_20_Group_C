// frontend/src/app/donate/thank-you/page.tsx
//
// PayHere sends the donor back here after paying. Arriving here proves
// nothing on its own: the page asks the backend to confirm the order with
// PayHere, and only a confirmed payment is recorded in the ledger. PayHere can
// take a few seconds to settle a payment, so a pending result is retried.
'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, Clock, Heart, Loader2, XCircle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DonationsService, lastOrderId } from '@/services/donations.service';
import { formatLKR } from '@/lib/formatters';

// About 30 seconds of retries before telling the donor we will email them.
const MAX_CHECKS = 10;
const CHECK_EVERY_MS = 3000;

export default function DonationThankYouPage() {
  return (
    <Suspense fallback={null}>
      <ThankYou />
    </Suspense>
  );
}

function ThankYou() {
  // PayHere may append its own ?order_id= to our return URL, so anything after
  // a second "?" is dropped. The donate page also keeps the id for this tab,
  // in case the parameter is lost on the way back.
  const fromUrl = (useSearchParams().get('order_id') ?? '').split('?')[0];
  const orderId = fromUrl || lastOrderId();
  const [checks, setChecks] = useState(0);

  const { data, isError } = useQuery({
    queryKey: ['donation-confirm', orderId],
    queryFn: async () => {
      setChecks((n) => n + 1);
      return DonationsService.confirm(orderId);
    },
    enabled: Boolean(orderId),
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: (query) =>
      query.state.data?.status === 'pending' && checks < MAX_CHECKS ? CHECK_EVERY_MS : false,
  });

  const stillChecking = !data || (data.status === 'pending' && checks < MAX_CHECKS);

  let icon = <Loader2 className="w-10 h-10 text-[#EF9F27] animate-spin" />;
  let heading = 'Confirming your donation…';
  let body: React.ReactNode = 'This usually takes a few seconds. Please keep this page open.';

  if (!orderId || isError) {
    icon = <XCircle className="w-10 h-10 text-negative" />;
    heading = "We couldn't find this donation";
    body = (
      <>
        If you were charged, please contact us at{' '}
        <a href="mailto:vetsforfuturesl@gmail.com" className="text-[#EF9F27] hover:underline">
          vetsforfuturesl@gmail.com
        </a>{' '}
        and we will sort it out.
      </>
    );
  } else if (data?.status === 'paid') {
    icon = <CheckCircle2 className="w-10 h-10 text-[#EF9F27]" />;
    heading = 'Thank you for your donation!';
    body = (
      <>
        We received <strong>{formatLKR(Number(data.amount))}</strong>{' '}
        {data.program_name ? (
          <>for <strong>{data.program_name}</strong>. It will be spent on that program only.</>
        ) : (
          <>to use wherever it is needed most.</>
        )}
        {!data.is_anonymous && ' A thank-you email with your receipt is on its way.'}
      </>
    );
  } else if (data?.status === 'cancelled' || data?.status === 'failed') {
    icon = <XCircle className="w-10 h-10 text-negative" />;
    heading = data.status === 'cancelled' ? 'Payment cancelled' : 'Payment did not go through';
    body = 'Nothing was charged. You are welcome to try again.';
  } else if (!stillChecking) {
    icon = <Clock className="w-10 h-10 text-[#EF9F27]" />;
    heading = 'Your payment is still being processed';
    body =
      'PayHere has not confirmed it yet. Please refresh this page in a minute. Your donation will be recorded as soon as it is confirmed.';
  }

  return (
    <div className="min-h-screen bg-bg-subtle text-text-primary flex items-center justify-center px-4 py-16">
      <Card className="w-full max-w-lg bg-surface border-border-brand/50 rounded-2xl shadow-card">
        <CardContent className="pt-8 pb-8 flex flex-col items-center gap-4 text-center">
          {icon}
          <h1 className="text-2xl font-bold font-heading">{heading}</h1>
          <p className="text-sm text-text-secondary leading-relaxed max-w-sm">{body}</p>
          {orderId && (
            <p className="text-xs text-text-muted font-mono">Reference: {orderId}</p>
          )}
          <div className="flex flex-wrap justify-center gap-3 pt-2">
            {(data?.status === 'cancelled' || data?.status === 'failed') && (
              <Link href="/donate">
                <Button className="bg-[#EF9F27] text-white hover:bg-[#EF9F27]/90 gap-2">
                  <Heart className="w-4 h-4" /> Try again
                </Button>
              </Link>
            )}
            <Link href="/">
              <Button variant="outline">Back to home</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
