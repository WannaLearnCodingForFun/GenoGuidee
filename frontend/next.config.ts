import type { NextConfig } from "next";

const backend = (process.env.GENOGUIDE_BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/drug-recommendation", destination: `${backend}/drug-recommendation` },
    ];
  },
};

export default nextConfig;
