"""Redis-backed HTTP idempotency with body-conflict detection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from functools import wraps
from typing import cast
from uuid import UUID

from flask import g, make_response, request

from vglpos.extensions import cache
from vglpos.services.exceptions import ConflictError, RequestValidationError

_TTL_SECONDS = 86_400
_LOCK_SECONDS = 30


def _validated_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    try:
        parsed = UUID(key)
    except ValueError as exc:
        raise RequestValidationError("Idempotency-Key must be a UUIDv4.") from exc
    if parsed.version != 4 or str(parsed) != key.lower():
        raise RequestValidationError("Idempotency-Key must be a canonical UUIDv4.")
    return key.lower()


def _request_hash() -> str:
    value = request.get_json(silent=True)
    body = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if value is not None
        else request.get_data(cache=True).decode("utf-8", errors="replace")
    )
    material = f"{request.method}\n{request.path}\n{request.query_string.decode()}\n{body}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _cache_key(key: str) -> str:
    actor = f"{getattr(g, 'company_id', 'public')}:{getattr(g, 'user_id', 'public')}"
    digest = hashlib.sha256(f"{actor}:{request.endpoint}:{key}".encode()).hexdigest()
    return f"idempotency:{digest}"


def idempotent[**P, R](view: Callable[P, R]) -> Callable[P, R]:
    """Return the first completed response for an identical mutation request."""

    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        key = _validated_key()
        request_hash = _request_hash()
        storage_key = _cache_key(key)
        stored = cache.get(storage_key)
        if isinstance(stored, dict):
            if stored.get("request_hash") != request_hash:
                raise ConflictError("Idempotency-Key was already used with a different request.")
            response = make_response(stored["body"], int(stored["status"]))
            response.headers["Content-Type"] = str(stored["content_type"])
            response.headers["Idempotent-Replay"] = "true"
            return cast(R, response)

        lock_key = f"{storage_key}:lock"
        if not cache.add(lock_key, request_hash, timeout=_LOCK_SECONDS):
            raise ConflictError("An identical idempotent request is still being processed.")
        try:
            response = make_response(view(*args, **kwargs))
            if response.status_code < 500:
                cache.set(
                    storage_key,
                    {
                        "request_hash": request_hash,
                        "body": response.get_data(),
                        "status": response.status_code,
                        "content_type": response.content_type,
                    },
                    timeout=_TTL_SECONDS,
                )
            return cast(R, response)
        finally:
            cache.delete(lock_key)

    wrapped.__dict__["_idempotent"] = True
    return cast(Callable[P, R], wrapped)
