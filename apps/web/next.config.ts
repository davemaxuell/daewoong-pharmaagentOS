import type { NextConfig } from "next";

const production = process.env.NODE_ENV === "production";
const runningOnVercel = process.env.VERCEL === "1";
const scriptPolicy = production
  ? "script-src 'self' 'unsafe-inline'"
  : "script-src 'self' 'unsafe-inline' 'unsafe-eval'";

const nextConfig: NextConfig = {
  // Local development uses 127.0.0.1 in .env.local. Next.js protects dev-only
  // chunks and HMR endpoints by origin, so this host must be explicit or the
  // client shell never hydrates and interactive controls remain inert.
  allowedDevOrigins: ["127.0.0.1"],
  // Docker images consume Next's minimal standalone server. Vercel's Next.js
  // adapter performs its own output tracing and expects the standard build
  // layout, so standalone output must stay disabled on Vercel builders.
  ...(runningOnVercel ? {} : { output: "standalone" as const }),
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-DNS-Prefetch-Control", value: "off" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          ...(production
            ? [
                {
                  key: "Strict-Transport-Security",
                  value: "max-age=31536000; includeSubDomains",
                },
              ]
            : []),
          {
            key: "Content-Security-Policy",
            value:
              `default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; font-src 'self'; style-src 'self' 'unsafe-inline'; ${scriptPolicy}; connect-src 'self'`,
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
