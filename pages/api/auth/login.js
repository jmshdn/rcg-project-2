import crypto from "crypto";
import { buildSessionCookie, isAccessProtectionConfigured } from "../../../lib/auth";
import { applyApiSecurityHeaders, enforceRateLimit, requireSameOrigin } from "../../../lib/security";

export const config = {
  api: {
    bodyParser: {
      sizeLimit: "8kb",
    },
  },
};

function matchesPassword(submittedPassword, expectedPassword) {
  const submitted = Buffer.from(submittedPassword || "");
  const expected = Buffer.from(expectedPassword || "");

  if (submitted.length !== expected.length) {
    return false;
  }

  return crypto.timingSafeEqual(submitted, expected);
}

export default function handler(req, res) {
  applyApiSecurityHeaders(res);

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  if (!requireSameOrigin(req, res)) {
    return;
  }

  if (!enforceRateLimit(req, res, { bucket: "auth-login", limit: 10, windowMs: 15 * 60 * 1000 })) {
    return;
  }

  if (!isAccessProtectionConfigured()) {
    return res.status(500).json({ error: "Access protection is not configured." });
  }

  const password = typeof req.body?.password === "string" ? req.body.password : "";
  const expectedPassword = process.env.APP_PASSWORD?.trim() || "";

  if (!password) {
    return res.status(400).json({ error: "Password is required." });
  }

  if (!matchesPassword(password, expectedPassword)) {
    return res.status(401).json({ error: "Invalid password." });
  }

  res.setHeader("Set-Cookie", buildSessionCookie(process.env.SESSION_SECRET.trim()));
  return res.status(200).json({ ok: true });
}
