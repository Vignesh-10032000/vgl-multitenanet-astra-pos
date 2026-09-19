"""Receipt delivery worker behavior at the provider boundary."""

from __future__ import annotations

from urllib.request import Request

import pytest
from flask import Flask

from vglpos.tasks.receipts import send_whatsapp_receipt


class _ProviderResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _ProviderResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_receipt_task_posts_authenticated_payload(
    monkeypatch: pytest.MonkeyPatch, api_app: Flask
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request: Request, *, timeout: int) -> _ProviderResponse:
        captured.update(request=request, timeout=timeout)
        return _ProviderResponse(202)

    monkeypatch.setattr("vglpos.tasks.receipts.urlopen", fake_urlopen)
    monkeypatch.setitem(api_app.config, "WHATSAPP_WEBHOOK_URL", "https://provider.invalid/send")
    monkeypatch.setitem(api_app.config, "WHATSAPP_API_TOKEN", "provider-token")
    with api_app.app_context():
        result = send_whatsapp_receipt.run(
            phone="9000000400",
            invoice_number="S/26-27/1",
            receipt_url="https://receipts.invalid/sales/1",
        )
    assert result == {"status": "sent", "invoice_number": "S/26-27/1"}
    request = captured["request"]
    assert isinstance(request, Request)
    assert request.get_header("Authorization") == "Bearer provider-token"
    assert captured["timeout"] == 15


def test_receipt_task_rejects_missing_configuration(api_app: Flask) -> None:
    with api_app.app_context(), pytest.raises(RuntimeError, match="not configured"):
        send_whatsapp_receipt.run(
            phone="9000000401",
            invoice_number="S/26-27/2",
            receipt_url="https://receipts.invalid/sales/2",
        )


def test_receipt_task_rejects_provider_failure(
    monkeypatch: pytest.MonkeyPatch, api_app: Flask
) -> None:
    monkeypatch.setattr(
        "vglpos.tasks.receipts.urlopen", lambda *_args, **_kwargs: _ProviderResponse(500)
    )
    monkeypatch.setitem(api_app.config, "WHATSAPP_WEBHOOK_URL", "https://provider.invalid/send")
    monkeypatch.setitem(api_app.config, "WHATSAPP_API_TOKEN", "provider-token")
    with api_app.app_context(), pytest.raises(OSError, match="HTTP 500"):
        send_whatsapp_receipt.run(
            phone="9000000402",
            invoice_number="S/26-27/3",
            receipt_url="https://receipts.invalid/sales/3",
        )
