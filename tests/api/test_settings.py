"""Store profile API behavior for settings and receipt rendering."""

from __future__ import annotations

from collections.abc import Callable

from flask.testing import FlaskClient


def test_store_profile_read_and_update(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
) -> None:
    original = api_client.get("/api/v1/settings/store-profile", headers=auth_headers)
    assert original.status_code == 200
    payload = {
        "name": "Receipt Test Store",
        "legal_name": "Receipt Test Store Private Limited",
        "gstin": None,
        "phone": "9000000000",
        "address_line1": "44 Receipt Road",
        "address_line2": None,
        "city": "Coimbatore",
        "state": "Tamil Nadu",
        "postal_code": "641001",
    }

    updated = api_client.put(
        "/api/v1/settings/store-profile",
        headers=mutation_headers(),
        json=payload,
    )

    assert updated.status_code == 200, updated.get_data(as_text=True)
    assert updated.get_json()["name"] == payload["name"]
    assert updated.get_json()["address"] == "44 Receipt Road, Coimbatore, Tamil Nadu, 641001"
    reread = api_client.get("/api/v1/settings/store-profile", headers=auth_headers)
    assert reread.get_json() == updated.get_json()


def test_store_profile_validation_failure_does_not_mutate(
    api_client: FlaskClient,
    auth_headers: dict[str, str],
    mutation_headers: Callable[..., dict[str, str]],
) -> None:
    before = api_client.get("/api/v1/settings/store-profile", headers=auth_headers).get_json()

    invalid = api_client.put(
        "/api/v1/settings/store-profile",
        headers=mutation_headers(),
        json={**before, "gstin": "invalid", "address": "ignored response-only field"},
    )

    assert invalid.status_code == 422
    after = api_client.get("/api/v1/settings/store-profile", headers=auth_headers).get_json()
    assert after == before
