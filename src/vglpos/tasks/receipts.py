"""Asynchronous receipt delivery through a deployment-configured webhook."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

from flask import current_app

from vglpos.extensions import celery
from vglpos.services.receipt_delivery import WebhookReceiptProvider


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


@celery.task(
    name="vglpos.send_sms_receipt",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def send_sms_receipt(*, phone: str, invoice_number: str, receipt_url: str) -> dict[str, str]:
    """Send a concise receipt link through the configured pluggable SMS gateway."""
    provider = WebhookReceiptProvider(
        str(current_app.config["SMS_WEBHOOK_URL"]),
        str(current_app.config["SMS_API_TOKEN"]),
    )
    provider.deliver(
        {
            "recipient": phone,
            "message": f"Invoice {invoice_number}: {receipt_url}",
            "invoice_number": invoice_number,
            "receipt_url": receipt_url,
        }
    )
    return {"status": "sent", "invoice_number": invoice_number}


@celery.task(
    name="vglpos.send_email_receipt",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def send_email_receipt(
    *,
    email: str,
    invoice_number: str,
    receipt_url: str,
    attachment: dict[str, str],
) -> dict[str, str]:
    """Send a B2B invoice with its generated A5 PDF through an email gateway."""
    provider = WebhookReceiptProvider(
        str(current_app.config["EMAIL_WEBHOOK_URL"]),
        str(current_app.config["EMAIL_API_TOKEN"]),
    )
    provider.deliver(
        {
            "from": str(current_app.config["EMAIL_FROM"]),
            "recipient": email,
            "subject": f"Tax invoice {invoice_number}",
            "receipt_url": receipt_url,
            "attachments": [attachment],
        }
    )
    return {"status": "sent", "invoice_number": invoice_number}
