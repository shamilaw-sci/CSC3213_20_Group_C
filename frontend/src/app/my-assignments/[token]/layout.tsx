import type { Metadata } from 'next';

// The volunteer's link token is their only credential and it sits in the URL.
//
// This is the in-document half of the protection; next.config.ts sets the real
// Referrer-Policy HTTP header on /my-assignments/:token* as well. Both exist on
// purpose. The header applies from the first byte of the response, while this
// tag is only honoured once the parser reaches it — so the tag alone would
// leave any subresource request issued before that point able to leak the full
// URL, and the header alone would not survive the document being saved or
// re-served from somewhere that drops headers.
//
// 'no-referrer' rather than 'origin-when-cross-origin': the latter still sends
// the origin, which is fine, but there is no outbound request from this page
// that benefits from any referrer at all, so the strictest value costs nothing.
//
// This layout is a Server Component purely so it can export metadata — the page
// itself is a Client Component because it has Accept/Decline buttons.
export const metadata: Metadata = {
  title: 'My assignments — Vets For Future',
  referrer: 'no-referrer',
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: { index: false, follow: false },
  },
};

export default function MyAssignmentsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
