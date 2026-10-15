"""RFC 7807 problem responses and application-wide error handling."""

from __future__ import annotations

import json

import structlog
from flask import Flask, Response, g, request
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError
from werkzeug.exceptions import HTTPException

from vglpos.services.exceptions import ServiceError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class VglPosError(Exception):
    """Base class for every typed application error.

    WHY: rule 8 requires typed exceptions everywhere. Services raise
    subclasses; exactly one handler translates them to problem+json, so no
    internal detail or stack trace can leak to a client from an ad-hoc handler.
    """

    status_code: int = 500
    title: str = "Internal Server Error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def problem_response(
    *, status: int, title: str, detail: str, type_: str = "about:blank"
) -> Response:
    """Build an RFC 7807 ``application/problem+json`` response.

    WHY request_id in the body: support staff correlate a customer-reported
    error with logs by this single value; without it every incident starts
    with log spelunking by timestamp.
    """
    body = {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.path,
        "request_id": getattr(g, "request_id", None),
    }
    return Response(json.dumps(body), status=status, content_type="application/problem+json")


def register_error_handlers(app: Flask) -> None:
    """Attach the three handlers that make every error response RFC 7807."""

    @app.errorhandler(OperationalError)
    @app.errorhandler(RedisError)
    def _handle_dependency_outage(exc: Exception) -> Response:
        logger.error("dependency_unavailable", error_type=type(exc).__name__)
        response = problem_response(
            status=503,
            title="Service temporarily unavailable",
            detail="The service is temporarily unavailable. Please try again shortly.",
            type_="urn:vglpos:error:dependency-unavailable",
        )
        response.headers["Retry-After"] = "30"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(VglPosError)
    def _handle_application_error(exc: VglPosError) -> Response:
        logger.warning(
            "application_error",
            error_type=type(exc).__name__,
            status=exc.status_code,
            detail=exc.detail,
        )
        return problem_response(status=exc.status_code, title=exc.title, detail=exc.detail)

    @app.errorhandler(ServiceError)
    def _handle_service_error(exc: ServiceError) -> Response:
        logger.warning(
            "service_error",
            error_type=exc.error_type,
            status=exc.status_code,
            detail=exc.detail,
        )
        return problem_response(
            status=exc.status_code,
            title="Request Rejected",
            detail=exc.detail,
            type_=f"urn:vglpos:error:{exc.error_type}",
        )

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException) -> Response:
        return problem_response(
            status=exc.code or 500, title=exc.name, detail=exc.description or ""
        )

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception) -> Response:
        # Full traceback goes to the log; the client gets a generic body because
        # internal details in a 500 are an information leak.
        logger.exception("unhandled_exception", error_type=type(exc).__name__)
        return problem_response(
            status=500,
            title="Internal Server Error",
            detail="An unexpected error occurred. Quote the request_id when reporting this.",
        )
