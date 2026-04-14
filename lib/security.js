const globalStore = globalThis;

if (!globalStore.__resumeTailorRateLimitStore) {
  globalStore.__resumeTailorRateLimitStore = new Map();
}

const rateLimitStore = globalStore.__resumeTailorRateLimitStore;

export function applyApiSecurityHeaders(res, { cacheControl = "no-store" } = {}) {
  res.setHeader("Cache-Control", cacheControl);
  res.setHeader("Referrer-Policy", "same-origin");
  res.setHeader("X-Content-Type-Options", "nosniff");
}

export function getClientIp(req) {
  const forwardedFor = req.headers["x-forwarded-for"];

  if (typeof forwardedFor === "string" && forwardedFor.trim()) {
    return forwardedFor.split(",")[0].trim();
  }

  return req.socket?.remoteAddress || "unknown";
}

export function requireSameOrigin(req, res) {
  const requestOrigin = req.headers.origin;
  const requestHost = req.headers["x-forwarded-host"] || req.headers.host;

  if (!requestOrigin || !requestHost) {
    res.status(403).json({ error: "Forbidden origin" });
    return false;
  }

  try {
    const originUrl = new URL(requestOrigin);

    if (originUrl.host !== requestHost) {
      res.status(403).json({ error: "Forbidden origin" });
      return false;
    }
  } catch {
    res.status(403).json({ error: "Forbidden origin" });
    return false;
  }

  return true;
}

export function enforceRateLimit(req, res, { bucket, limit, windowMs }) {
  const now = Date.now();
  const key = `${bucket}:${getClientIp(req)}`;
  const entry = rateLimitStore.get(key);

  if (!entry || entry.resetAt <= now) {
    rateLimitStore.set(key, { count: 1, resetAt: now + windowMs });
    return true;
  }

  if (entry.count >= limit) {
    const retryAfterSeconds = Math.max(1, Math.ceil((entry.resetAt - now) / 1000));
    res.setHeader("Retry-After", String(retryAfterSeconds));
    res.status(429).json({ error: "Too many requests. Please try again later." });
    return false;
  }

  entry.count += 1;
  return true;
}
