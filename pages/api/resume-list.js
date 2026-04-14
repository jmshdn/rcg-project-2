import fs from "fs";
import path from "path";
import { applyApiSecurityHeaders } from "../../lib/security";

export default function handler(req, res) {
  applyApiSecurityHeaders(res);

  if (req.method !== "GET") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const resumesDir = path.join(process.cwd(), "resumes");
  const files = fs.readdirSync(resumesDir).filter(f => f.endsWith(".json"));
  const names = files.map(f => f.replace(".json", ""));
  res.status(200).json(names);
}
