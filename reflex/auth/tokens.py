"""Authentication module for DataHub Reflex.

Provides JWT-like token generation and validation using HMAC-SHA256.
No external dependencies — uses Python stdlib only.

Configuration:
    REFLEX_API_SECRET: Shared secret for token signing (required).
    REFLEX_TOKEN_EXPIRY_HOURS: Token lifetime in hours (default: 24).

Roles:
    admin    — Full access (create, approve, publish, read)
    approver — Approve + read (cannot create incidents)
    viewer   — Read-only
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from base64 import urlsafe_b64encode, urlsafe_b64decode
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Optional

from flask import request, jsonify


def _secret() -> bytes:
    secret = os.environ.get("REFLEX_API_SECRET", "").strip()
    if not secret:
        raise RuntimeError("REFLEX_API_SECRET environment variable is required for authentication")
    return secret.encode("utf-8")


def _sign(payload: bytes) -> bytes:
    return hmac.digest(_secret(), payload, hashlib.sha256)


# -- Token generation ---------------------------------------------------------


def create_token(subject: str, role: str = "viewer", expiry_hours: int | None = None) -> str:
    """Create a signed authentication token.

    Args:
        subject: Username or identifier.
        role: One of 'admin', 'approver', 'viewer'.
        expiry_hours: Token lifetime in hours (default from env or 24).

    Returns:
        Base64-encoded token string.
    """
    if expiry_hours is None:
        expiry_hours = int(os.environ.get("REFLEX_TOKEN_EXPIRY_HOURS", "24"))

    payload = {
        "sub": subject,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + expiry_hours * 3600,
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = _sign(payload_bytes)
    token = urlsafe_b64encode(payload_bytes) + b"." + urlsafe_b64encode(signature)
    return token.decode("ascii")


def validate_token(token: str) -> dict:
    """Validate a token and return its payload.

    Args:
        token: The Bearer token string.

    Returns:
        Decoded payload dict with 'sub', 'role', 'iat', 'exp'.

    Raises:
        ValueError: Token is invalid, expired, or tampered.
    """
    try:
        parts = token.split(".")
        if len(parts) != 2:
            raise ValueError("Invalid token format")

        payload_bytes = urlsafe_b64decode(parts[0].encode("ascii"))
        signature = urlsafe_b64decode(parts[1].encode("ascii"))

        expected_sig = _sign(payload_bytes)
        if not hmac.compare_digest(signature, expected_sig):
            raise ValueError("Invalid token signature")

        payload = json.loads(payload_bytes)

        if payload.get("exp", 0) < time.time():
            raise ValueError("Token expired")

        if payload.get("role") not in ("admin", "approver", "viewer"):
            raise ValueError("Invalid role")

        return payload
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise ValueError(f"Token validation failed: {e}") from e


# -- Flask decorators ---------------------------------------------------------


@dataclass
class AuthContext:
    """Authenticated user context extracted from the token."""
    subject: str
    role: str
    token: str


def _extract_token() -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _get_auth() -> AuthContext:
    token = _extract_token()
    if not token:
        raise PermissionError("Missing Authorization header")
    try:
        payload = validate_token(token)
        return AuthContext(subject=payload["sub"], role=payload["role"], token=token)
    except ValueError as e:
        raise PermissionError(str(e))


def require_auth(f: Callable) -> Callable:
    """Decorator: require a valid Bearer token. Any role is accepted."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            request.auth = _get_auth()
        except PermissionError as e:
            return jsonify({"error": "UNAUTHORIZED", "detail": str(e)}), 401
        return f(*args, **kwargs)

    return wrapper


def require_role(*roles: str) -> Callable:
    """Decorator: require a valid token AND one of the specified roles."""

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                auth = _get_auth()
                if auth.role not in roles:
                    return jsonify({
                        "error": "FORBIDDEN",
                        "detail": f"Role '{auth.role}' not in permitted roles: {roles}",
                    }), 403
                request.auth = auth
            except PermissionError as e:
                return jsonify({"error": "UNAUTHORIZED", "detail": str(e)}), 401
            return f(*args, **kwargs)

        return wrapper

    return decorator
