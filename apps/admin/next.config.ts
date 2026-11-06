import type { NextConfig } from "next";

const dev = process.env.NODE_ENV !== "production";
const issuerOrigin = new URL(process.env.AUTH_KEYCLOAK_ISSUER ?? "http://keycloak.localhost:8080/realms/dcs-staff").origin;

// Next.js needs inline scripts for hydration; tighten to nonces with the Phase 9 hardening work.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self'${dev ? " ws://localhost:3001" : ""}`,
  `form-action 'self' ${issuerOrigin}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@dcs/ui", "@dcs/api-client", "@dcs/auth"],
  outputFileTracingRoot: new URL("../../", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default config;
