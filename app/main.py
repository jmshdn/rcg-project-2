from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from .resume_service import list_profile_ids, list_profiles, list_templates, parse_resume_to_json, tailor_resume
from .security import (
    AUTH_COOKIE_NAME,
    access_protection_configured,
    create_session_token,
    enforce_rate_limit,
    get_client_ip,
    is_same_origin,
    session_cookie_settings,
    verify_session_token,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _json_error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


def _add_security_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    if os.getenv("PYTHON_ENV") == "production" or os.getenv("VERCEL") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response


def _public_path(path: str) -> bool:
    return path in {"/login"} or path.startswith("/api/auth/login") or path.startswith("/api/auth/logout")


def _bypassed_path(path: str) -> bool:
    return path.startswith("/static/") or path in {"/favicon.ico", "/robots.txt", "/sitemap.xml"}


@app.middleware("http")
async def auth_and_security_middleware(request: Request, call_next):
    path = request.url.path

    if _bypassed_path(path):
        return _add_security_headers(await call_next(request))

    if access_protection_configured():
        session_secret = os.getenv("SESSION_SECRET", "").strip()
        session_token = request.cookies.get(AUTH_COOKIE_NAME)
        is_authenticated = verify_session_token(session_token, session_secret)

        if path == "/login" and is_authenticated:
            return _add_security_headers(RedirectResponse(url="/", status_code=307))

        if not _public_path(path) and not is_authenticated:
            if path.startswith("/api/"):
                return _add_security_headers(_json_error("Unauthorized", 401))
            next_path = quote(f"{path}?{request.url.query}", safe="/?=&") if request.url.query else quote(path, safe="/")
            return _add_security_headers(RedirectResponse(url=f"/login?next={next_path}", status_code=307))
    elif os.getenv("PYTHON_ENV") == "production" or os.getenv("VERCEL") == "1":
        return _add_security_headers(PlainTextResponse("Access protection is not configured for this deployment.", status_code=503))

    return _add_security_headers(await call_next(request))


def _require_same_origin(request: Request) -> JSONResponse | None:
    return None if is_same_origin(request) else _json_error("Forbidden origin", 403)


def _apply_rate_limit(request: Request, bucket: str, limit: int, window_seconds: int) -> JSONResponse | None:
    retry_after = enforce_rate_limit(bucket, get_client_ip(request), limit, window_seconds)
    if retry_after is None:
        return None
    response = _json_error("Too many requests. Please try again later.", 429)
    response.headers["Retry-After"] = str(retry_after)
    return response


async def _read_json_payload(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as error:
        raise ValueError("Invalid JSON body.") from error

    if not isinstance(payload, dict):
        raise ValueError("Invalid JSON body.")

    return payload


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/parse", response_class=HTMLResponse)
async def parse_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "parse.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"request": request})


@app.get("/api/profiles")
async def api_profiles():
    return list_profiles()


@app.get("/api/resume-list")
async def api_resume_list():
    return list_profile_ids()


@app.get("/api/templates")
async def api_templates():
    return list_templates()


@app.post("/api/auth/login")
async def api_login(request: Request) -> Response:
    same_origin_error = _require_same_origin(request)
    if same_origin_error:
        return same_origin_error

    rate_limit_error = _apply_rate_limit(request, "auth-login", 10, 15 * 60)
    if rate_limit_error:
        return rate_limit_error

    if not access_protection_configured():
        return _json_error("Access protection is not configured.", 500)

    try:
        payload = await _read_json_payload(request)
    except ValueError as error:
        return _json_error(str(error), 400)

    password = str(payload.get("password", ""))
    expected_password = os.getenv("APP_PASSWORD", "").strip()

    if not password:
        return _json_error("Password is required.", 400)
    if password != expected_password:
        return _json_error("Invalid password.", 401)

    response = JSONResponse({"ok": True})
    response.set_cookie(AUTH_COOKIE_NAME, create_session_token(os.getenv("SESSION_SECRET", "").strip()), **session_cookie_settings())
    return response


@app.post("/api/auth/logout")
async def api_logout(request: Request) -> Response:
    same_origin_error = _require_same_origin(request)
    if same_origin_error:
        return same_origin_error

    response = JSONResponse({"ok": True})
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response


async def _generate_resume_response(request: Request, prompt_kind: str) -> Response:
    same_origin_error = _require_same_origin(request)
    if same_origin_error:
        return same_origin_error

    rate_limit_error = _apply_rate_limit(request, f"resume-generate-{prompt_kind}", 6, 15 * 60)
    if rate_limit_error:
        return rate_limit_error

    try:
        payload = await _read_json_payload(request)
    except ValueError as error:
        return PlainTextResponse(str(error), status_code=400)

    profile = str(payload.get("profile", "")).strip()
    job_description = str(payload.get("jd", "")).strip()
    template_name = str(payload.get("template", "Resume")).strip() or "Resume"
    job_title = str(payload.get("jobTitle", "")).strip()
    company_name = str(payload.get("companyName", "")).strip()

    if not profile:
        return PlainTextResponse("Profile required", status_code=400)
    if not job_description:
        return PlainTextResponse("Job description required", status_code=400)
    if len(job_description) > 12000:
        return PlainTextResponse("Job description is too long", status_code=400)
    if len(job_title) > 120:
        return PlainTextResponse("Job title is too long", status_code=400)
    if len(company_name) > 120:
        return PlainTextResponse("Company name is too long", status_code=400)
    if len(template_name) > 120:
        return PlainTextResponse("Template name is invalid", status_code=400)

    try:
        pdf_bytes, filename = await tailor_resume(profile, job_description, template_name, job_title, company_name, prompt_kind=prompt_kind)
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except FileNotFoundError as error:
        return PlainTextResponse(str(error), status_code=404)
    except ValueError as error:
        return PlainTextResponse(str(error), status_code=400)
    except Exception as error:
        return PlainTextResponse(f"PDF generation failed: {error}", status_code=500)


@app.post("/api/generate")
async def api_generate(request: Request) -> Response:
    return await _generate_resume_response(request, "general")


@app.post("/api/generate copy")
async def api_generate_copy(request: Request) -> Response:
    return await _generate_resume_response(request, "game")


@app.post("/api/parse-resume")
async def api_parse_resume(request: Request, resume: UploadFile | None = File(default=None)) -> Response:
    same_origin_error = _require_same_origin(request)
    if same_origin_error:
        return same_origin_error

    rate_limit_error = _apply_rate_limit(request, "resume-parse", 4, 15 * 60)
    if rate_limit_error:
        return rate_limit_error

    if resume is None:
        return _json_error("Please upload a PDF resume.", 400)

    filename = (resume.filename or "").lower()
    if not filename.endswith(".pdf"):
        return _json_error("Please upload a PDF resume.", 400)

    file_bytes = await resume.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        return _json_error("The PDF is too large. Please upload a file smaller than 5 MB.", 400)

    try:
        return JSONResponse({"data": await parse_resume_to_json(file_bytes)})
    except ValueError as error:
        return _json_error(str(error), 400)
    except Exception as error:
        return _json_error(str(error), 500)
