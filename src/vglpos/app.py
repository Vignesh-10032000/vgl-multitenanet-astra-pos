"""Application factory.

No module-level ``app`` object exists anywhere in this package. Entry points
call the factory: gunicorn via ``vglpos.app:create_app()``, the Flask CLI via
``--app vglpos.app``, Celery via ``vglpos.celery_app``.
"""

from __future__ import annotations

import uuid

import structlog
from celery import Celery, Task
from flask import Flask, Response, g, request

from vglpos.config import BaseConfig, get_config
from vglpos.errors import problem_response, register_error_handlers
from vglpos.extensions import cache, celery, db, jwt, limiter, migrate
from vglpos.routes import BLUEPRINTS, PUBLIC_ENDPOINTS
from vglpos.utils.logging import configure_logging


def create_app(config_class: type[BaseConfig] | None = None) -> Flask:
    """Build a fully configured application instance.

    WHY a factory: tests, gunicorn workers and the celery worker each need
    their own instance built from an explicit config class; a module-level app
    would make config-before-extensions ordering (the P0-6 bug class) and test
    isolation impossible to guarantee.
    """
    settings = (config_class or get_config())()
    app = Flask("vglpos")

    # Config is applied before ANY extension touches the app. An extension
    # initialised first would silently keep default settings (P0-6).
    app.config.update(settings.flask_config())

    configure_logging(level=str(app.config["LOG_LEVEL"]))
    # Request-context middleware registers BEFORE extensions so request_id is
    # bound even when an extension's own before_request hook (e.g. the rate
    # limiter's storage check) fails — otherwise errors log without an id.
    _register_request_context(app)
    _init_extensions(app)
    _init_celery(app)

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

    _register_endpoint_guard(app)
    _register_security_headers(app)
    register_error_handlers(app)
    return app


def _init_extensions(app: Flask) -> None:
    """Bind the shared extension instances to this app instance."""
    db.init_app(app)
    migrate.init_app(app, db, directory="migrations")
    cache.init_app(app)
    limiter.init_app(app)
    jwt.init_app(app)


def _init_celery(app: Flask) -> Celery:
    """Configure the shared Celery instance from app config.

    WHY the task subclass: every task runs inside a Flask app context so
    extensions (db, cache) work in workers exactly as they do in requests.
    """

    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.conf.update(app.config["CELERY"])
    celery.Task = FlaskTask
    app.extensions["celery"] = celery
    return celery


def _register_request_context(app: Flask) -> None:
    """Give every request a request_id and bind it into the log context."""

    @app.before_request
    def _bind_request_context() -> None:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        g.request_id = request_id
        structlog.contextvars.clear_contextvars()
        # user_id / company_id stay None until the auth phase populates flask.g;
        # binding the keys now keeps log queries uniform from day one.
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            user_id=getattr(g, "user_id", None),
            company_id=getattr(g, "company_id", None),
        )

    @app.after_request
    def _stamp_request_id(response: Response) -> Response:
        response.headers["X-Request-Id"] = getattr(g, "request_id", "")
        return response


def _register_endpoint_guard(app: Flask) -> None:
    """Fail closed on undeclared endpoints.

    WHY: rule 5 says no route ships without an explicit permission decision.
    Until the auth phase introduces permission decorators, every endpoint that
    is not explicitly public is refused — so forgetting the decorator on a
    future route yields a loud 403, never a silently open endpoint.
    """

    @app.before_request
    def _refuse_undeclared_endpoints() -> Response | None:
        endpoint = request.endpoint
        if endpoint is None or endpoint in PUBLIC_ENDPOINTS:
            # None means no URL rule matched; fall through so Flask returns 404.
            return None
        return problem_response(
            status=403,
            title="Forbidden",
            detail=f"Endpoint '{endpoint}' has no permission declaration.",
        )


def _register_security_headers(app: Flask) -> None:
    """Attach security headers to every response.

    WHY no 'unsafe-inline' in script-src: the UI phase ships vanilla ES modules
    served from /static, so inline scripts are never needed and XSS via
    injected inline script is structurally blocked.
    """
    csp = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    )

    @app.after_request
    def _apply_security_headers(response: Response) -> Response:
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if not (app.debug or app.testing):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
