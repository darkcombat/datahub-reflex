"""Error handling middleware for the Reflex API (P1.2).

Provides structured error responses for all failure modes:
- DataHub unavailable
- Authentication failures
- Insufficient backtest data
- No similar assets found
- LLM errors
- Rejected approvals
- Partial publication
"""

from __future__ import annotations

import traceback
from typing import Any

import structlog
from flask import Flask, jsonify

logger = structlog.get_logger(__name__)


def register_error_handlers(app: Flask) -> None:
    """Register all error handlers on the Flask app."""

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify(_error("BAD_REQUEST", str(e), 400)), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify(_error("UNAUTHORIZED", "Authentication required", 401)), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify(_error("FORBIDDEN", "Insufficient permissions", 403)), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(_error("NOT_FOUND", str(e), 404)), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify(_error("METHOD_NOT_ALLOWED", str(e), 405)), 405

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify(_error("RATE_LIMITED", "Too many requests", 429, retry_safe=True)), 429

    @app.errorhandler(500)
    def internal_error(e):
        logger.error("internal_server_error", error=str(e))
        return jsonify(_error("INTERNAL_ERROR", "An unexpected error occurred", 500)), 500

    @app.errorhandler(Exception)
    def unhandled(e):
        logger.error("unhandled_exception", error=str(e), traceback=traceback.format_exc()[:1000])
        return jsonify(_error("INTERNAL_ERROR", "An unexpected error occurred", 500)), 500


def _error(code: str, detail: str, status: int, retry_safe: bool = False) -> dict[str, Any]:
    return {
        "error": code,
        "detail": detail[:500],
        "status": status,
        "retry_safe": retry_safe,
    }
