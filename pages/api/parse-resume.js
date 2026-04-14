import fs from "fs/promises";
import { IncomingForm } from "formidable";
import pdf from "pdf-parse";
import OpenAI from "openai";
import { applyApiSecurityHeaders, enforceRateLimit, requireSameOrigin } from "../../lib/security";

export const config = {
  api: {
    bodyParser: false,
  },
};

function getOpenAIClient() {
  const apiKey = process.env.OPENAI_API_KEY?.trim();

  if (!apiKey) {
    throw new Error("Missing OPENAI_API_KEY. Copy .env.example to .env.local and add your OpenAI API key.");
  }

  return new OpenAI({ apiKey });
}

function parseForm(req) {
  return new Promise((resolve, reject) => {
    const form = new IncomingForm({
      allowEmptyFiles: false,
      filter: ({ mimetype, originalFilename }) =>
        mimetype === "application/pdf" || originalFilename?.toLowerCase().endsWith(".pdf"),
      maxFileSize: 5 * 1024 * 1024,
      multiples: false,
      maxFields: 0,
      keepExtensions: true,
      maxFiles: 1,
    });

    form.parse(req, (error, fields, files) => {
      if (error) {
        reject(error);
        return;
      }

      resolve({ fields, files });
    });
  });
}

function pickFirstFile(fileValue) {
  if (!fileValue) return null;
  return Array.isArray(fileValue) ? fileValue[0] : fileValue;
}

function extractJsonPayload(content) {
  const text = content
    .replace(/```json\s*/gi, "")
    .replace(/```/g, "")
    .trim();

  const firstBrace = text.indexOf("{");
  const lastBrace = text.lastIndexOf("}");

  if (firstBrace === -1 || lastBrace === -1 || lastBrace <= firstBrace) {
    throw new Error("OpenAI did not return a valid JSON object.");
  }

  return JSON.parse(text.slice(firstBrace, lastBrace + 1));
}

export default async function handler(req, res) {
  applyApiSecurityHeaders(res);
  let uploadedFile = null;

  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  try {
    if (!requireSameOrigin(req, res)) {
      return;
    }

    if (!enforceRateLimit(req, res, { bucket: "resume-parse", limit: 4, windowMs: 15 * 60 * 1000 })) {
      return;
    }

    const { files } = await parseForm(req);
    const resumeFile = pickFirstFile(files.resume);
    uploadedFile = resumeFile;

    if (!resumeFile?.filepath) {
      return res.status(400).json({ error: "Please upload a PDF resume." });
    }

    if (!process.env.OPENAI_API_KEY?.trim()) {
      return res.status(500).json({
        error: "Missing OPENAI_API_KEY. Copy .env.example to .env.local and add your OpenAI API key.",
      });
    }

    const fileBuffer = await fs.readFile(resumeFile.filepath);
    const parsedPdf = await pdf(fileBuffer);
    const rawText = parsedPdf.text?.trim();

    if (!rawText) {
      return res.status(400).json({ error: "Could not extract text from that PDF." });
    }

    const openai = getOpenAIClient();
    const model = process.env.OPENAI_MODEL || "gpt-5-mini";
    const completion = await openai.chat.completions.create({
      model,
      max_completion_tokens: 2500,
      messages: [
        {
          role: "system",
          content:
            "You convert resume text into structured JSON. Return only a single JSON object with no markdown.",
        },
        {
          role: "user",
          content: `Extract the resume below into this exact JSON shape:
{
  "name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "linkedin": "string",
  "website": "string",
  "experience": [
    {
      "company": "string",
      "title": "string",
      "location": "string",
      "start_date": "string",
      "end_date": "string"
    }
  ],
  "education": [
    {
      "degree": "string",
      "school": "string",
      "start_year": "string",
      "end_year": "string"
    }
  ]
}

Rules:
- Use empty strings when a value is missing.
- Preserve wording from the resume when possible.
- Keep experience in reverse chronological order if it is clear.
- Return valid JSON only.

Resume text:
${rawText}`,
        },
      ],
    });

    const content = completion.choices?.[0]?.message?.content ?? "";
    const data = extractJsonPayload(content);

    res.status(200).json({ data });
  } catch (error) {
    console.error("Resume parsing error:", error);
    res.status(500).json({ error: error.message || "Failed to parse resume" });
  } finally {
    if (uploadedFile?.filepath) {
      await fs.unlink(uploadedFile.filepath).catch(() => {});
    }
  }
}
