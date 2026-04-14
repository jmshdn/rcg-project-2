/** @type {import('next').NextConfig} */
const isProduction = process.env.NODE_ENV === "production";

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "connect-src 'self'",
  "font-src 'self' https://fonts.gstatic.com data:",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "img-src 'self' data: blob:",
  "object-src 'none'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
].join("; ");

const nextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["openai"],
  async headers() {
    const headers = [
      {
        source: "/:path*",
        headers: [
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-DNS-Prefetch-Control", value: "off" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Robots-Tag", value: "noindex, nofollow" },
        ],
      },
    ];

    if (isProduction) {
      headers[0].headers.push(
        { key: "Content-Security-Policy", value: contentSecurityPolicy },
        { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" }
      );
    }

    return headers;
  },
};

module.exports = nextConfig;
