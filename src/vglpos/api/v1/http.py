"""Strict Pydantic parsing and exact JSON response helpers."""

from __future__ import annotations

from typing import Any

from flask import Response, jsonify, request
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from vglpos.services.exceptions import RequestValidationError


def _validation_error(exc: PydanticValidationError) -> RequestValidationError:
    issue = exc.errors(include_url=False)[0]
    location = ".".join(str(item) for item in issue["loc"])
    return RequestValidationError(f"Invalid {location or 'request'}: {issue['msg']}.")


def parse_body[ModelT: BaseModel](model: type[ModelT]) -> ModelT:
    """Validate one JSON object and reject missing, malformed, or extra fields."""
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise RequestValidationError("A JSON object is required.")
    try:
        return model.model_validate(value)
    except PydanticValidationError as exc:
        raise _validation_error(exc) from exc


def parse_query[ModelT: BaseModel](model: type[ModelT]) -> ModelT:
    """Validate query parameters with the same fail-closed extra-field policy."""
    try:
        return model.model_validate(request.args.to_dict(flat=True))
    except PydanticValidationError as exc:
        raise _validation_error(exc) from exc


def model_response(model: BaseModel, *, status: int = 200) -> tuple[Response, int]:
    """Emit a response model in JSON mode so Decimal values remain strings."""
    return jsonify(model.model_dump(mode="json")), status


def json_response(payload: dict[str, Any], *, status: int = 200) -> tuple[Response, int]:
    """Emit pre-normalized JSON for token responses and small command acknowledgements."""
    return jsonify(payload), status
