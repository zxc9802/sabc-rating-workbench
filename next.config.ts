import type { NextConfig } from 'next';

const config: NextConfig = {
  output: 'standalone',
  // Model analysis may include two calls and bounded source retries.
  experimental: { proxyTimeout: 600_000 },
  distDir: process.env.SABC_NEXT_DIST || ".next",
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${process.env.SABC_API_ORIGIN || "http://127.0.0.1:18765"}/api/:path*` }];
  },
};
export default config;
