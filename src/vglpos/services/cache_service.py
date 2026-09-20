"""Event-versioned cache keys for catalogue and dashboard reads."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import date
from typing import Any
from uuid import uuid4

from vglpos.extensions import cache

logger = logging.getLogger(__name__)


def _get(key: str) -> object | None:
    try:
        value: object | None = cache.get(key)
        return value
    except Exception:
        logger.warning("Cache read failed", exc_info=True, extra={"cache_key": key})
        return None


def _set(key: str, value: object) -> None:
    try:
        cache.set(key, value, timeout=0)
    except Exception:
        logger.warning("Cache write failed", exc_info=True, extra={"cache_key": key})


def _generation(namespace: str, company_id: int, branch_id: int | str) -> str:
    key = f"cache-generation:{namespace}:company:{company_id}:branch:{branch_id}"
    value = _get(key)
    return str(value) if value is not None else "0"


def catalogue_key(
    *,
    company_id: int,
    branch_id: int,
    cursor: str | None,
    limit: int,
    query: str | None,
    barcode: str | None,
) -> str:
    """Build a bounded key that separates tenant, branch, version, and query."""
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "barcode": barcode,
                "cursor": cursor,
                "limit": limit,
                "query": query,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    generation = _generation("catalogue", company_id, "all")
    return (
        f"catalogue:company:{company_id}:branch:{branch_id}:"
        f"generation:{generation}:query:{fingerprint}"
    )


def dashboard_key(*, company_id: int, branch_id: int, on_date: date) -> str:
    generation = _generation("dashboard", company_id, branch_id)
    return (
        f"dashboard:company:{company_id}:branch:{branch_id}:"
        f"generation:{generation}:date:{on_date.isoformat()}"
    )


def get_mapping(key: str) -> dict[str, Any] | None:
    value = _get(key)
    if not isinstance(value, Mapping):
        return None
    return {str(item_key): item_value for item_key, item_value in value.items()}


def set_mapping(key: str, value: dict[str, Any]) -> None:
    _set(key, value)


def invalidate_catalogue(company_id: int) -> None:
    _set(
        f"cache-generation:catalogue:company:{company_id}:branch:all",
        uuid4().hex,
    )


def invalidate_dashboard(company_id: int, branch_id: int) -> None:
    _set(
        f"cache-generation:dashboard:company:{company_id}:branch:{branch_id}",
        uuid4().hex,
    )
