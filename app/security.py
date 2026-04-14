from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict

from fastapi import Request

AUTH_COOKIE_NAME = "resume_tailor_session"
SESSION_TTL_SECONDS = 60 * 60 * 12


def _sha256_base64url(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def should_use_secure_cookies() -> bool:
    return os.getenv("VERCEL") == "1" or os.getenv("AUTH_COOKIE_SECURE") == "true"


def access_protection_configured() -> bool:
    return bool(os.getenv("APP_PASSWORD", "").strip() and os.getenv("SESSION_SECRET", "").strip())


def create_session_token(secret: str, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    expires_at = str(int(time.time() * 1000) + ttl_seconds * 1000)
    signature = _sha256_base64url(f"{expires_at}.{secret}")
    return f"{expires_at}.{signature}"


def verify_session_token(token: str | None, secret: str | None) -> bool:
    if not token or not secret:
        return False

    parts = token.split(".", 1)
    if len(parts) != 2:
        return False

    expires_at, signature = parts

    try:
        expires_at_number = int(expires_at)
    except ValueError:
        return False

    if expires_at_number <= int(time.time() * 1000):
        return False

    expected = _sha256_base64url(f"{expires_at}.{secret}")
    return hmac.compare_digest(signature, expected)


def session_cookie_settings() -> dict:
    return {
        "httponly": True,
        "max_age": SESSION_TTL_SECONDS,
        "path": "/",
        "samesite": "lax",
        "secure": should_use_secure_cookies(),
    }


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def is_same_origin(request: Request) -> bool:
    request_origin = request.headers.get("origin", "").strip()
    request_host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")

    if not request_origin or not request_host:
        return False

    try:
        from urllib.parse import urlparse

        return urlparse(request_origin).netloc == request_host
    except Exception:
        return False


@dataclass
class RateLimitEntry:
    count: int
    reset_at: float


_rate_limit_store: Dict[str, RateLimitEntry] = {}
_rate_limit_lock = threading.Lock()


def enforce_rate_limit(bucket: str, client_key: str, limit: int, window_seconds: int) -> int | None:
    now = time.time()
    entry_key = f"{bucket}:{client_key}"

    with _rate_limit_lock:
        entry = _rate_limit_store.get(entry_key)

        if entry is None or entry.reset_at <= now:
            _rate_limit_store[entry_key] = RateLimitEntry(count=1, reset_at=now + window_seconds)
            return None

        if entry.count >= limit:
            return max(1, int(entry.reset_at - now))

        entry.count += 1
        return None

