import crypto from "crypto";

export const AUTH_COOKIE_NAME = "resume_tailor_session";
const SESSION_TTL_SECONDS = 60 * 60 * 12;

function shouldUseSecureCookies() {
  return process.env.VERCEL === "1" || process.env.AUTH_COOKIE_SECURE === "true";
}

function base64UrlSha256(value) {
  return crypto.createHash("sha256").update(value).digest("base64url");
}

function serializeCookie(name, value, options = {}) {
  const parts = [`${name}=${value}`];

  if (options.maxAge != null) parts.push(`Max-Age=${options.maxAge}`);
  if (options.path) parts.push(`Path=${options.path}`);
  if (options.httpOnly) parts.push("HttpOnly");
  if (options.sameSite) parts.push(`SameSite=${options.sameSite}`);
  if (options.secure) parts.push("Secure");
  if (options.priority) parts.push(`Priority=${options.priority}`);

  return parts.join("; ");
}

export function isAccessProtectionConfigured() {
  return Boolean(process.env.APP_PASSWORD?.trim() && process.env.SESSION_SECRET?.trim());
}

export function createSessionToken(secret, ttlSeconds = SESSION_TTL_SECONDS) {
  const expiresAt = String(Date.now() + ttlSeconds * 1000);
  const signature = base64UrlSha256(`${expiresAt}.${secret}`);
  return `${expiresAt}.${signature}`;
}

export function verifySessionToken(token, secret) {
  if (!token || !secret) return false;

  const [expiresAt, signature] = token.split(".");
  const expiresAtNumber = Number(expiresAt);

  if (!expiresAt || !signature || !Number.isFinite(expiresAtNumber) || expiresAtNumber <= Date.now()) {
    return false;
  }

  const expected = base64UrlSha256(`${expiresAt}.${secret}`);
  const signatureBuffer = Buffer.from(signature);
  const expectedBuffer = Buffer.from(expected);

  if (signatureBuffer.length !== expectedBuffer.length) {
    return false;
  }

  return crypto.timingSafeEqual(signatureBuffer, expectedBuffer);
}

export function buildSessionCookie(secret) {
  return serializeCookie(AUTH_COOKIE_NAME, createSessionToken(secret), {
    httpOnly: true,
    maxAge: SESSION_TTL_SECONDS,
    path: "/",
    priority: "High",
    sameSite: "Lax",
    secure: shouldUseSecureCookies(),
  });
}

export function buildClearedSessionCookie() {
  return serializeCookie(AUTH_COOKIE_NAME, "", {
    httpOnly: true,
    maxAge: 0,
    path: "/",
    priority: "High",
    sameSite: "Lax",
    secure: shouldUseSecureCookies(),
  });
}
