import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  async redirects() {
    return [
      { source: '/hr', destination: '/hr/employees', permanent: false },
      { source: '/finance', destination: '/finance/overview', permanent: false },
      { source: '/inventory', destination: '/inventory/stock', permanent: false },
    ];
  },
  async headers() {
    return [
      {
        // A volunteer link token is their only credential and it sits in the
        // URL. Without this, the browser sends the full URL in the Referer
        // header of every outbound request the page makes — every external
        // font, image, analytics beacon or clicked link — handing the token to
        // third parties.
        //
        // This is the real HTTP header, not the <meta name="referrer"> tag that
        // the route's metadata export also emits. Both are here deliberately:
        // the header applies from the very first byte, while the meta tag is
        // only honoured once the parser reaches it, leaving subresource
        // requests made before that point uncovered.
        source: '/my-assignments/:token*',
        headers: [
          { key: 'Referrer-Policy', value: 'no-referrer' },
          // Keep the page (and therefore the token) out of search indexes if a
          // link is ever pasted somewhere public.
          { key: 'X-Robots-Tag', value: 'noindex, nofollow' },
          // Shared devices are the norm for this audience; do not leave the
          // page sitting in a back-button cache.
          { key: 'Cache-Control', value: 'no-store, private' },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

export default nextConfig;