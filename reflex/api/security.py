"""Security middleware for the Reflex API (P1.5).

Provides:
- CORS protection (configurable origins)
- Rate limiting (token bucket per IP)
- Security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- Input validation helpers

Configuration:
    REFLEX_CORS_ORIGINS: Comma-separated allowed origins (default: http://localhost:5000)
    REFLEX_RATE_LIMIT: Max requests per minute per IP (default: 60)
    REFLEX_RATE_LIMIT_BURST: Burst size (default: 10)
"""

from __future__ import annotations

import os
import time
import threading
from collections import defaultdict
from functools import wraps
from typing import Callable

from flask import Flask, request, jsonify


def configure_security(app: Flask) -> None:
    """Apply security headers and CORS to the Flask app."""

    cors_origins = os.environ.get("REFLEX_CORS_ORIGINS", "http://localhost:5000")
    allowed_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

    @app.after_request
    def add_security_headers(response):
        # CORS
        origin = request.headers.get("Origin", "")
        if origin in allowed_origins or "*" in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin if origin in allowed_origins else allowed_origins[0]
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Max-Age"] = "3600"

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Server"] = ""  # Hide server identity

        return response

    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            response = jsonify({"status": "ok"})
            origin = request.headers.get("Origin", "")
            if origin in allowed_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
                response.headers["Access-Control-Max-Age"] = "3600"
            return response, 200


# -- Rate limiting ------------------------------------------------------------


class RateLimiter:
    """Simple token-bucket rate limiter per IP."""

    def __init__(self, rate: int = 60, burst: int = 10):
        self._rate = rate
        self._burst = burst
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def _refill(self, ip: str) -> None:
        now = time.monotonic()
        last_refill, tokens = self._buckets.get(ip, (now, self._burst))
        elapsed = now - last_refill
        new_tokens = min(self._burst, tokens + int(elapsed * self._rate / 60))
        self._buckets[ip] = (now, new_tokens)

    def is_allowed(self, ip: str) -> bool:
        with self._lock:
            self._refill(ip)
            _, tokens = self._buckets.get(ip, (0, self._burst))
            if tokens > 0:
                self._buckets[ip] = (self._buckets[ip][0], tokens - 1)
                return True
            return False

    def remaining(self, ip: str) -> int:
        with self._lock:
            self._refill(ip)
            return self._buckets.get(ip, (0, 0))[1]


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        rate = int(os.environ.get("REFLEX_RATE_LIMIT", "60"))
        burst = int(os.environ.get("REFLEX_RATE_LIMIT_BURST", "10"))
        _rate_limiter = RateLimiter(rate=rate, burst=burst)
    return _rate_limiter


def rate_limit(f: Callable) -> Callable:
    """Decorator: apply rate limiting to a Flask route."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        ip = request.remote_addr or "unknown"
        limiter = get_rate_limiter()
        if not limiter.is_allowed(ip):
            remaining = limiter.remaining(ip)
            return jsonify({
                "error": "RATE_LIMITED",
                "detail": f"Too many requests. Try again later.",
                "retry_after_seconds": max(1, 60 // limiter._rate),
                "remaining": remaining,
            }), 429
        response = f(*args, **kwargs)
        return response

    return wrapper


# -- Input validation ---------------------------------------------------------


def validate_urn(value: str) -> bool:
    """Validate a DataHub URN format."""
    if not value or not isinstance(value, str):
        return False
    return value.startswith("urn:li:") and len(value) > 10


def sanitize_input(value: str, max_length: int = 1000) -> str:
    """Sanitize user input for safe processing."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]
