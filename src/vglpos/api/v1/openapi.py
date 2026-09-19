"""OpenAPI 3.1 generation from registered Flask routes and Pydantic models."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from flask import Blueprint, Response, current_app, jsonify
from pydantic import BaseModel

from vglpos.security.decorators import require_permission

P = ParamSpec("P")
R = TypeVar("R")

openapi_bp = Blueprint("openapi", __name__, url_prefix="/api/v1")


def documented(
    *,
    summary: str,
    request_model: type[BaseModel] | None = None,
    query_model: type[BaseModel] | None = None,
    response_model: type[BaseModel] | None = None,
    success_status: int = 200,
    public: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Attach Pydantic contract metadata consumed by the OpenAPI generator."""

    def decorator(view: Callable[P, R]) -> Callable[P, R]:
        view.__dict__["_openapi_summary"] = summary
        view.__dict__["_openapi_request_model"] = request_model
        view.__dict__["_openapi_query_model"] = query_model
        view.__dict__["_openapi_response_model"] = response_model
        view.__dict__["_openapi_success_status"] = success_status
        view.__dict__["_openapi_public"] = public
        return view

    return decorator


def _schema_ref(model: type[BaseModel], schemas: dict[str, Any]) -> dict[str, str]:
    schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
    definitions = schema.pop("$defs", {})
    schemas.update(definitions)
    schemas[model.__name__] = schema
    return {"$ref": f"#/components/schemas/{model.__name__}"}


def _parameters(
    rule: Any, query_model: type[BaseModel] | None, schemas: dict[str, Any]
) -> list[dict[str, Any]]:
    parameters = [
        {
            "name": name,
            "in": "path",
            "required": True,
            "schema": {
                "type": "integer"
                if type(rule._converters[name]).__name__ == "IntegerConverter"
                else "string"
            },
        }
        for name in sorted(rule.arguments)
    ]
    if query_model is None:
        return parameters
    query_schema = query_model.model_json_schema(ref_template="#/components/schemas/{model}")
    schemas.update(query_schema.pop("$defs", {}))
    required = set(query_schema.get("required", []))
    parameters.extend(
        {
            "name": name,
            "in": "query",
            "required": name in required,
            "schema": schema,
        }
        for name, schema in query_schema.get("properties", {}).items()
    )
    return parameters


def build_openapi() -> dict[str, Any]:
    """Generate paths from Flask's URL map and schemas from attached Pydantic models."""
    paths: dict[str, Any] = {}
    schemas: dict[str, Any] = {}
    for rule in current_app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1/"):
            continue
        path = rule.rule.replace("<int:", "{").replace("<string:", "{").replace(">", "}")
        view = current_app.view_functions[rule.endpoint]
        request_model = getattr(view, "_openapi_request_model", None)
        query_model = getattr(view, "_openapi_query_model", None)
        response_model = getattr(view, "_openapi_response_model", None)
        success_status = str(getattr(view, "_openapi_success_status", 200))
        for method in sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}):
            operation: dict[str, Any] = {
                "operationId": f"{rule.endpoint.replace('.', '_')}_{method.lower()}",
                "summary": getattr(view, "_openapi_summary", rule.endpoint),
                "responses": {success_status: {"description": "Successful response"}},
                "security": (
                    [] if getattr(view, "_openapi_public", False) else [{"bearerAuth": []}]
                ),
            }
            parameters = _parameters(rule, query_model, schemas)
            if method in {"POST", "PUT", "PATCH"}:
                parameters.append(
                    {
                        "name": "Idempotency-Key",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                )
            if parameters:
                operation["parameters"] = parameters
            if request_model is not None:
                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {"schema": _schema_ref(request_model, schemas)}
                    },
                }
            if response_model is not None:
                operation["responses"][success_status]["content"] = {
                    "application/json": {"schema": _schema_ref(response_model, schemas)}
                }
            paths.setdefault(path, {})[method.lower()] = operation
    return {
        "openapi": "3.1.0",
        "info": {"title": "VGL POS API", "version": "1.0.0"},
        "paths": paths,
        "components": {
            "schemas": schemas,
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            },
        },
    }


def docs_access[**DocsP, DocsR](
    view: Callable[DocsP, DocsR],
) -> Callable[DocsP, DocsR]:
    """Require authentication for API documentation only in production."""
    protected = require_permission()(view)

    def wrapped(*args: DocsP.args, **kwargs: DocsP.kwargs) -> DocsR:
        if current_app.config["APP_ENV"] == "production":
            return protected(*args, **kwargs)
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    wrapped.__dict__["_permission_required"] = True
    return wrapped


@openapi_bp.get("/openapi.json")
@docs_access
def openapi_json() -> tuple[Response, int]:
    """Serve the generated OpenAPI document."""
    return jsonify(build_openapi()), 200


@openapi_bp.get("/docs")
@docs_access
def swagger_docs() -> Response:
    """Serve a pinned Swagger UI client for the generated document."""
    html = """<!doctype html><html><head><title>VGL POS API</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css">
</head><body><div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script src="/static/swagger-init.js"></script>
</body></html>"""
    response = current_app.response_class(html, content_type="text/html; charset=utf-8")
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self' https://unpkg.com; "
        "style-src https://unpkg.com; connect-src 'self'; img-src data:"
    )
    return response
