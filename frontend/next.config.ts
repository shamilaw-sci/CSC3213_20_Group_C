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
};

export default nextConfig;