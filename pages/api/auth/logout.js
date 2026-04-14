import { buildClearedSessionCookie } from "../../../lib/auth";
import { applyApiSecurityHeaders, requireSameOrigin } from "../../../lib/security";

export default function handler(req, res) {
  applyApiSecurityHeaders(res);

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  if (!requireSameOrigin(req, res)) {
    return;
  }

  res.setHeader("Set-Cookie", buildClearedSessionCookie());
  return res.status(200).json({ ok: true });
}
