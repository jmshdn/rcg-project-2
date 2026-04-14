import { NextResponse } from "next/server";

const AUTH_COOKIE_NAME = "resume_tailor_session";

function isBypassedPath(pathname) {
  return (
    pathname.startsWith("/_next/") ||
    pathname === "/favicon.ico" ||
    pathname === "/robots.txt" ||
    pathname === "/sitemap.xml"
  );
}

function isPublicPath(pathname) {
  return pathname === "/login" || pathname.startsWith("/api/auth/login") || pathname.startsWith("/api/auth/logout");
}

function toBase64Url(buffer) {
  const bytes = Array.from(new Uint8Array(buffer));
  const binary = String.fromCharCode(...bytes);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

async function sha256(value) {
  const buffer = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return toBase64Url(buffer);
}

async function verifySessionToken(token, secret) {
  if (!token || !secret) return false;

  const [expiresAt, signature] = token.split(".");
  const expiresAtNumber = Number(expiresAt);

  if (!expiresAt || !signature || !Number.isFinite(expiresAtNumber) || expiresAtNumber <= Date.now()) {
    return false;
  }

  const expected = await sha256(`${expiresAt}.${secret}`);
  return signature === expected;
}

export async function middleware(req) {
  const { pathname, search } = req.nextUrl;

  if (isBypassedPath(pathname)) {
    return NextResponse.next();
  }

  const password = process.env.APP_PASSWORD?.trim();
  const sessionSecret = process.env.SESSION_SECRET?.trim();
  const protectionConfigured = Boolean(password && sessionSecret);

  if (!protectionConfigured) {
    if (process.env.NODE_ENV === "production") {
      return new NextResponse("Access protection is not configured for this deployment.", { status: 503 });
    }

    return NextResponse.next();
  }

  const sessionToken = req.cookies.get(AUTH_COOKIE_NAME)?.value;
  const isAuthenticated = await verifySessionToken(sessionToken, sessionSecret);

  if (pathname === "/login" && isAuthenticated) {
    const destination = new URL("/", req.url);
    return NextResponse.redirect(destination);
  }

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  if (isAuthenticated) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const loginUrl = new URL("/login", req.url);
  loginUrl.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/:path*"],
};
