from __future__ import annotations

import asyncio
import io
import json
import os
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from playwright.async_api import async_playwright
from pybars import Compiler
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parents[1]
RESUMES_DIR = BASE_DIR / "resumes"
RESUME_TEMPLATES_DIR = BASE_DIR / "templates"
PROMPTS_DIR = BASE_DIR / "app" / "prompts"


def get_openai_client() -> AsyncOpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY. Add it to your environment before running the app.")
    return AsyncOpenAI(api_key=api_key)


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"


@lru_cache(maxsize=2)
def load_prompt_template(kind: str) -> str:
    prompt_path = PROMPTS_DIR / ("general.txt" if kind == "general" else "game.txt")
    return prompt_path.read_text(encoding="utf-8")


def list_profiles() -> list[dict[str, str]]:
    return [
        {"id": file_path.stem, "name": file_path.stem.replace("_", " ")}
        for file_path in sorted(RESUMES_DIR.glob("*.json"))
        if file_path.name != "_template.json"
    ]


def list_profile_ids() -> list[str]:
    return [profile["id"] for profile in list_profiles()]


def list_templates() -> list[dict[str, str]]:
    templates: list[dict[str, str]] = []
    for file_path in sorted(RESUME_TEMPLATES_DIR.glob("*.html")):
        template_id = file_path.stem
        name = "Classic (Default)" if template_id == "Resume" else template_id.replace("Resume-", "").replace("-", " ")
        templates.append({"id": template_id, "name": name, "file": file_path.name})
    templates.sort(key=lambda item: (item["id"] != "Resume", item["name"]))
    return templates


def resolve_profile_path(profile_id: str) -> Path | None:
    candidate = RESUMES_DIR / f"{profile_id}.json"
    if candidate.exists() and candidate.name != "_template.json":
        return candidate
    return None


def resolve_template_path(template_id: str) -> Path | None:
    candidate = RESUME_TEMPLATES_DIR / f"{template_id}.html"
    return candidate if candidate.exists() else None


def load_profile(profile_id: str) -> dict[str, Any]:
    profile_path = resolve_profile_path(profile_id)
    if profile_path is None:
        raise FileNotFoundError(f'Profile "{profile_id}" not found')
    return json.loads(profile_path.read_text(encoding="utf-8"))


def parse_resume_date(date_str: Any, *, default_to_now: bool = False) -> datetime | None:
    if not date_str:
        return datetime.utcnow() if default_to_now else None

    normalized = str(date_str).strip()
    if not normalized:
        return datetime.utcnow() if default_to_now else None
    if normalized.lower() == "present":
        return datetime.utcnow()

    for fmt in ("%b %Y", "%B %Y", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue

    return datetime.utcnow() if default_to_now else None


def get_latest_experience_title(profile_data: dict[str, Any]) -> str:
    experience = profile_data.get("experience", []) or []
    if not experience:
        return "Engineer"

    def sort_key(job: dict[str, Any]) -> tuple[datetime, datetime]:
        end_date = parse_resume_date(job.get("end_date"), default_to_now=True) or datetime.min
        start_date = parse_resume_date(job.get("start_date")) or datetime.min
        return (end_date, start_date)

    latest_job = max(experience, key=sort_key)
    return str(latest_job.get("title") or "Engineer").strip() or "Engineer"


def calculate_years_of_experience(experience: list[dict[str, Any]]) -> int:
    if not experience:
        return 0

    parsed_start_dates = [parse_resume_date(job.get("start_date")) for job in experience if job.get("start_date")]
    valid_start_dates = [date for date in parsed_start_dates if date is not None]
    if not valid_start_dates:
        return 0

    earliest = min(valid_start_dates)
    return round((datetime.utcnow() - earliest).days / 365)


def build_base_resume(profile_data: dict[str, Any]) -> str:
    return "\n".join(
        [
            profile_data.get("name", ""),
            " | ".join(
                value
                for value in [profile_data.get("email"), profile_data.get("phone"), profile_data.get("location")]
                if value
            ),
            "",
            "PROFESSIONAL EXPERIENCE",
            *[
                f'{job.get("title", "Role")} at {job.get("company", "")}'
                f'{", " + job.get("location", "") if job.get("location") else ""} | '
                f'{job.get("start_date", "")} - {job.get("end_date", "")}'
                for job in profile_data.get("experience", [])
            ],
            "",
            "EDUCATION",
            *[
                f'{education.get("degree", "")}, {education.get("school", "")} '
                f'({education.get("start_year", "")}-{education.get("end_year", "")})'
                f'{" | " + education.get("grade", "") if education.get("grade") else ""}'
                for education in profile_data.get("education", [])
            ],
        ]
    )


async def call_openai(prompt_or_messages: str | list[dict[str, str]], max_tokens: int = 8000, retries: int = 2, timeout_seconds: int = 180) -> Any:
    client = get_openai_client()
    model = get_openai_model()

    while retries > 0:
        try:
            messages = (
                [{"role": "user", "content": prompt_or_messages}]
                if isinstance(prompt_or_messages, str)
                else [
                    {
                        "role": message["role"] if message["role"] in {"system", "assistant", "user"} else "user",
                        "content": message["content"],
                    }
                    for message in prompt_or_messages
                ]
            )

            return await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    max_completion_tokens=max_tokens,
                    messages=messages,
                ),
                timeout=timeout_seconds,
            )
        except Exception:
            retries -= 1
            if retries == 0:
                raise


def extract_json_payload(content: str) -> dict[str, Any]:
    cleaned = (
        content.replace("```json", "")
        .replace("```javascript", "")
        .replace("```", "")
        .strip()
    )
    cleaned = re.sub(r"^(here is|here's|this is|the json is):?\s*", "", cleaned, flags=re.IGNORECASE)

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
        raise ValueError("AI did not return valid JSON format. Please try again.")

    payload = cleaned[first_brace:last_brace + 1].strip()

    try:
        return json.loads(payload)
    except json.JSONDecodeError as parse_error:
        fixed_payload = re.sub(r",(\s*[}\]])", r"\1", payload)
        try:
            return json.loads(fixed_payload)
        except json.JSONDecodeError as second_error:
            raise ValueError(f"AI returned invalid JSON: {parse_error.msg}") from second_error


def enforce_summary_prefix(summary: str, summary_prefix: str) -> str:
    summary = summary.strip()
    if not summary:
        return summary_prefix

    if summary.lower().startswith(summary_prefix.lower()):
        return f"{summary_prefix}{summary[len(summary_prefix):]}"

    connector_match = re.match(
        r"^[A-Za-z0-9/&,+\- ]+?(\s+(with|who|bringing|specializing|focused|experienced|offering)\b.*)$",
        summary,
        flags=re.IGNORECASE,
    )
    if connector_match:
        return f"{summary_prefix}{connector_match.group(1)}"

    summary_without_generic_prefix = re.sub(
        r"^senior\s+(software|game)\s+engineer\b[\s,:-]*",
        "",
        summary,
        flags=re.IGNORECASE,
    ).strip()

    if summary_without_generic_prefix:
        return f"{summary_prefix} {summary_without_generic_prefix[:1].lower() + summary_without_generic_prefix[1:]}"

    return summary_prefix


def normalize_resume_content(resume_content: dict[str, Any], years_of_experience: int, summary_prefix: str) -> dict[str, Any]:
    if not all(key in resume_content for key in ("title", "summary", "skills", "experience")):
        raise ValueError("AI response missing required fields (title, summary, skills, or experience)")

    title = str(resume_content.get("title", "")).strip()
    if " at " in title.lower():
        title = re.sub(r"\s+at\s+.*$", "", title, flags=re.IGNORECASE).strip()
    resume_content["title"] = title

    summary = str(resume_content.get("summary", "")).strip()
    if years_of_experience > 10:
        summary = re.sub(r"\b(1[2-9]|[2-9]\d|\d{3})\s*\+\s*years?\b", "more than 10 years", summary, flags=re.IGNORECASE)
        summary = re.sub(r"\b(1[2-9]|[2-9]\d|\d{3})\s*years?\b", "more than 10 years", summary, flags=re.IGNORECASE)

    summary = enforce_summary_prefix(summary, summary_prefix)

    def bold_to_strong(value: Any) -> Any:
        return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value) if isinstance(value, str) else value

    resume_content["summary"] = bold_to_strong(summary)
    for experience in resume_content.get("experience", []) or []:
        if isinstance(experience.get("details"), list):
            experience["details"] = [bold_to_strong(detail) for detail in experience["details"]]

    if isinstance(resume_content.get("skills"), dict):
        resume_content["skills"] = {
            str(key).replace("*", "").strip() or str(key): value
            for key, value in resume_content["skills"].items()
        }

    return resume_content


def merge_experience(profile_data: dict[str, Any], ai_experience: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_full_experience = bool(ai_experience) and all(
        item.get("company") is not None and item.get("start_date") is not None and item.get("end_date") is not None
        for item in ai_experience
    )

    if has_full_experience:
        return [
            {
                "title": item.get("title") or "Engineer",
                "company": item.get("company"),
                "location": item.get("location") or "",
                "start_date": item.get("start_date"),
                "end_date": item.get("end_date"),
                "details": item.get("details") if isinstance(item.get("details"), list) else [],
            }
            for item in ai_experience
        ]

    merged: list[dict[str, Any]] = []
    for index, job in enumerate(profile_data.get("experience", [])):
        ai_job = ai_experience[index] if index < len(ai_experience) else {}
        merged.append(
            {
                "title": job.get("title") or ai_job.get("title") or "Engineer",
                "company": job.get("company"),
                "location": job.get("location") or "",
                "start_date": job.get("start_date"),
                "end_date": job.get("end_date"),
                "details": ai_job.get("details") if isinstance(ai_job.get("details"), list) else [],
            }
        )
    return merged


def sanitize_filename_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", re.sub(r"\s+", "", value or ""))


def build_download_filename(profile_name: str, company_name: str, job_title: str) -> str:
    base_name = sanitize_filename_part(profile_name or "resume")
    if sanitize_filename_part(company_name):
        base_name += f"_{sanitize_filename_part(company_name)}"
    if sanitize_filename_part(job_title):
        base_name += f"_{sanitize_filename_part(job_title)}"
    return f"{base_name}.pdf"


@lru_cache(maxsize=16)
def _compile_handlebars_template(template_name: str):
    template_path = resolve_template_path(template_name)
    if template_path is None:
        raise FileNotFoundError(f'Template "{template_name}" not found')
    return Compiler().compile(template_path.read_text(encoding="utf-8"))


def render_resume_html(template_name: str, template_data: dict[str, Any]) -> str:
    template = _compile_handlebars_template(template_name)

    def join_helper(this, *args):
        value = args[-2] if len(args) >= 2 else (args[0] if args else [])
        separator = args[-1] if len(args) >= 2 else ", "
        return separator.join(value) if isinstance(value, list) else ""

    def format_key_helper(this, *args):
        return args[-1] if args else ""

    rendered = template(template_data, helpers={"join": join_helper, "formatKey": format_key_helper})
    return rendered if isinstance(rendered, str) else rendered.decode("utf-8")


async def render_pdf_from_html(html: str) -> bytes:
    if sys.platform == "win32":
        loop_name = asyncio.get_running_loop().__class__.__name__.lower()
        if "selector" in loop_name:
            raise RuntimeError(
                "Playwright cannot launch Chromium on Windows when Uvicorn is started with --reload. "
                "Start the app without --reload: .\\.venv\\Scripts\\python -m uvicorn main:app"
            )

    launch_args = ["--no-sandbox"] if os.getenv("VERCEL") == "1" or os.getenv("PYTHON_ENV") == "production" else []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=launch_args)
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            return await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "15mm", "bottom": "15mm", "left": "0mm", "right": "0mm"},
            )
        finally:
            await browser.close()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


async def tailor_resume(profile_id: str, job_description: str, template_name: str, job_title: str, company_name: str, prompt_kind: str = "general") -> tuple[bytes, str]:
    profile_data = load_profile(profile_id)
    years_of_experience = calculate_years_of_experience(profile_data.get("experience", []))
    latest_experience_title = get_latest_experience_title(profile_data)
    prompt = load_prompt_template(prompt_kind).replace("${baseResume}", build_base_resume(profile_data)).replace("${jobDescription}", job_description)

    ai_response = await call_openai(prompt)
    finish_reason = ai_response.choices[0].finish_reason if ai_response.choices else None
    content = (ai_response.choices[0].message.content or "").strip() if ai_response.choices else ""

    if finish_reason == "length":
        concise_prompt = prompt.replace("8–10 bullets per role", "6–8 bullets per role").replace("NEVER fewer than 8 bullets per role", "NEVER fewer than 6 bullets per role")
        retry_response = await call_openai(concise_prompt, max_tokens=10000)
        content = (retry_response.choices[0].message.content or "").strip() if retry_response.choices else ""

    if content.lower().startswith(("i'm sorry", "i cannot", "i apologize")):
        raise ValueError("AI refused to generate resume. The prompt may be too complex. Please try again with a shorter job description or simpler requirements.")

    summary_prefix = latest_experience_title
    resume_content = normalize_resume_content(extract_json_payload(content), years_of_experience, summary_prefix)

    template_data = {
        "name": profile_data.get("name"),
        "title": latest_experience_title,
        "email": profile_data.get("email"),
        "phone": profile_data.get("phone"),
        "location": profile_data.get("location"),
        "linkedin": profile_data.get("linkedin"),
        "website": profile_data.get("website"),
        "summary": resume_content.get("summary"),
        "skills": resume_content.get("skills"),
        "experience": merge_experience(profile_data, resume_content.get("experience") or []),
        "education": profile_data.get("education"),
    }

    pdf_bytes = await render_pdf_from_html(render_resume_html(template_name, template_data))
    filename = build_download_filename(profile_data.get("name", "resume"), company_name, job_title)
    return pdf_bytes, filename


async def parse_resume_to_json(file_bytes: bytes) -> dict[str, Any]:
    raw_text = extract_text_from_pdf(file_bytes)
    if not raw_text:
        raise ValueError("Could not extract text from that PDF.")

    completion = await call_openai(
        [
            {
                "role": "system",
                "content": "You convert resume text into structured JSON. Return only a single JSON object with no markdown.",
            },
            {
                "role": "user",
                "content": f"""Extract the resume below into this exact JSON shape:
{{
  "name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "linkedin": "string",
  "website": "string",
  "experience": [
    {{
      "company": "string",
      "title": "string",
      "location": "string",
      "start_date": "string",
      "end_date": "string"
    }}
  ],
  "education": [
    {{
      "degree": "string",
      "school": "string",
      "start_year": "string",
      "end_year": "string"
    }}
  ]
}}

Rules:
- Use empty strings when a value is missing.
- Preserve wording from the resume when possible.
- Keep experience in reverse chronological order if it is clear.
- Return valid JSON only.

Resume text:
{raw_text}""",
            },
        ],
        max_tokens=2500,
    )

    return extract_json_payload((completion.choices[0].message.content or "") if completion.choices else "")
