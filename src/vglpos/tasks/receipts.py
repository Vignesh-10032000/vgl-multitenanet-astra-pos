"""Asynchronous receipt delivery through a deployment-configured webhook."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from flask import current_app

from vglpos.extensions import celery


@celery.task(
    name="vglpos.send_whatsapp_receipt",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def send_whatsapp_receipt(*, phone: str, invoice_number: str, receipt_url: str) -> dict[str, str]:
    """Send one receipt payload while keeping provider credentials out of job arguments."""
    webhook_url = str(current_app.config["WHATSAPP_WEBHOOK_URL"]).strip()
    api_token = str(current_app.config["WHATSAPP_API_TOKEN"]).strip()
    if not webhook_url or not api_token:
        raise RuntimeError("WhatsApp receipt delivery is not configured.")
    payload = json.dumps(
        {
            "recipient": phone,
            "invoice_number": invoice_number,
            "receipt_url": receipt_url,
        }
    ).encode("utf-8")
    request = Request(
        webhook_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        if not 200 <= response.status < 300:
            raise OSError(f"WhatsApp provider returned HTTP {response.status}.")
    return {"status": "sent", "invoice_number": invoice_number}
