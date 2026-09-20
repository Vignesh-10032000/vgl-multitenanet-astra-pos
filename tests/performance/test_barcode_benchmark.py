"""Barcode endpoint latency regression at the required catalogue cardinality."""

from __future__ import annotations

from decimal import Decimal
from math import ceil
from statistics import median
from time import perf_counter_ns

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from tests.api.conftest import IdentityContext
from vglpos.domain.models import Product
from vglpos.extensions import db
from vglpos.repositories.catalog import ProductRepository

_CATALOGUE_SIZE = 100_000
_SAMPLE_SIZE = 250


def _seed_catalogue(api_app: Flask, identity: IdentityContext) -> str:
    target_barcode = f"BENCH-TARGET-{identity.company.id}"
    with api_app.app_context(), Session(db.engine) as session:
        product = session.get(Product, identity.product.id)
        assert product is not None
        product.barcode = target_barcode
        existing = int(
            session.scalar(
                select(func.count(Product.id)).where(Product.company_id == identity.company.id)
            )
            or 0
        )
        for start in range(existing, _CATALOGUE_SIZE, 5_000):
            end = min(start + 5_000, _CATALOGUE_SIZE)
            session.execute(
                insert(Product),
                [
                    {
                        "company_id": identity.company.id,
                        "sku": f"BENCH-SKU-{identity.company.id}-{index:06d}",
                        "name": f"Benchmark Product {index:06d}",
                        "tax_rate_id": identity.product.tax_rate_id,
                        "barcode": f"BENCH-CODE-{identity.company.id}-{index:06d}",
                        "cost_price": Decimal("10.00"),
                        "selling_price": Decimal("20.00"),
                        "mrp": Decimal("25.00"),
                    }
                    for index in range(start, end)
                ],
            )
        session.commit()
    return target_barcode


@pytest.mark.no_cover
def test_barcode_lookup_p99_under_10ms_at_100k_products(
    api_app: Flask,
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    api_identity: IdentityContext,
) -> None:
    barcode = _seed_catalogue(api_app, api_identity)
    query_durations_ms: list[float] = []
    with api_app.app_context(), Session(db.engine) as session:
        repository = ProductRepository(session, api_identity.company.id)
        for _ in range(_SAMPLE_SIZE):
            started = perf_counter_ns()
            assert repository.find_by_barcode(barcode) is not None
            query_durations_ms.append((perf_counter_ns() - started) / 1_000_000)
    query_p99_ms = sorted(query_durations_ms)[ceil(_SAMPLE_SIZE * 0.99) - 1]

    endpoint = f"/api/v1/products/lookup?barcode={barcode}"
    for _ in range(10):
        assert api_client.get(endpoint, headers=auth_headers).status_code == 200

    durations_ms: list[float] = []
    for _ in range(_SAMPLE_SIZE):
        started = perf_counter_ns()
        response = api_client.get(endpoint, headers=auth_headers)
        durations_ms.append((perf_counter_ns() - started) / 1_000_000)
        assert response.status_code == 200

    p99_ms = sorted(durations_ms)[ceil(_SAMPLE_SIZE * 0.99) - 1]
    assert p99_ms < 10, (
        f"barcode endpoint p99 was {p99_ms:.3f}ms "
        f"(median={median(durations_ms):.3f}ms, max={max(durations_ms):.3f}ms, "
        f"query_p99={query_p99_ms:.3f}ms)"
    )
