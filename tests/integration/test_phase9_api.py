"""Phase 9 compliance administration HTTP contract tests."""

from __future__ import annotations

from uuid import uuid4

from flask.testing import FlaskClient

from .conftest import IdentityContext


def _access_headers(client: FlaskClient, context: IdentityContext) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "company_code": context.company.login_code,
            "username": context.user.username,
            "password": context.password,
            "branch_id": context.branch.id,
            "terminal_id": context.terminal.id,
        },
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def test_settings_templates_queue_health_and_reconciliation_contracts(
    auth_client: FlaskClient, identity_context: IdentityContext
) -> None:
    authorization = _access_headers(auth_client, identity_context)

    settings = auth_client.put(
        "/api/v1/compliance/settings",
        headers={**authorization, "Idempotency-Key": str(uuid4())},
        json={
            "e_invoice_enabled": True,
            "e_invoice_provider": "NIC",
            "e_invoice_reporting_window_days": 30,
            "e_invoice_retry_limit": 5,
            "composition_scheme_enabled": False,
            "composition_declaration": (
                "Composition taxable person, not eligible to collect tax on supplies."
            ),
            "invoice_validation_enabled": True,
            "gst_filing_locked_through": None,
        },
    )
    assert settings.status_code == 200, settings.get_data(as_text=True)
    assert settings.get_json()["e_invoice_enabled"] is True
    assert settings.get_json()["e_invoice_provider"] == "NIC"

    template = auth_client.post(
        "/api/v1/compliance/invoice-templates",
        headers={**authorization, "Idempotency-Key": str(uuid4())},
        json={
            "code": "GST-A5",
            "name": "GST A5 Invoice",
            "paper_size": "A5",
            "mandatory_fields": [
                "supplier_gstin",
                "invoice_number",
                "invoice_date",
                "item_description",
                "hsn_code",
                "taxable_amount",
                "tax_amount",
                "invoice_total",
            ],
            "declaration_text": None,
            "is_default": True,
        },
    )
    assert template.status_code == 201, template.get_data(as_text=True)
    assert template.get_json()["code"] == "GST-A5"
    assert template.get_json()["is_default"] is True

    assert (
        auth_client.get("/api/v1/compliance/settings", headers=authorization).get_json()[
            "invoice_validation_enabled"
        ]
        is True
    )
    assert (
        len(
            auth_client.get(
                "/api/v1/compliance/invoice-templates", headers=authorization
            ).get_json()["items"]
        )
        == 1
    )
    assert auth_client.get("/api/v1/compliance/e-invoices", headers=authorization).get_json() == {
        "items": []
    }
    assert auth_client.get(
        "/api/v1/compliance/reconciliation", headers=authorization
    ).get_json() == {"items": []}
    alert = auth_client.get("/api/v1/compliance/alerts", headers=authorization)
    assert alert.status_code == 200
    assert alert.get_json()["active"] is False


def test_composition_and_e_invoice_cannot_be_enabled_together(
    auth_client: FlaskClient, identity_context: IdentityContext
) -> None:
    authorization = _access_headers(auth_client, identity_context)
    response = auth_client.put(
        "/api/v1/compliance/settings",
        headers={**authorization, "Idempotency-Key": str(uuid4())},
        json={
            "e_invoice_enabled": True,
            "e_invoice_provider": "NIC",
            "e_invoice_reporting_window_days": 30,
            "e_invoice_retry_limit": 5,
            "composition_scheme_enabled": True,
            "composition_declaration": "Composition taxable person.",
            "invoice_validation_enabled": True,
            "gst_filing_locked_through": None,
        },
    )

    assert response.status_code == 400
    assert "cannot enable e-invoice" in response.get_json()["detail"]
