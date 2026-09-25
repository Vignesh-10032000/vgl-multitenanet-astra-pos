"""Pluggable outbound receipt providers and compact A5 PDF rendering."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from urllib.request import Request, urlopen

from vglpos.services.qr_service import qr_matrix
from vglpos.services.sales_service import SaleDetail


class ReceiptProvider(Protocol):
    """Deliver a provider-neutral JSON payload to an external receipt channel."""

    def deliver(self, payload: dict[str, object]) -> None:
        """Raise when the provider does not accept the delivery."""


@dataclass(frozen=True, slots=True)
class WebhookReceiptProvider:
    """POST receipt jobs to a deployment-selected SMS or email gateway."""

    webhook_url: str
    api_token: str

    def deliver(self, payload: dict[str, object]) -> None:
        """Send one authenticated request so provider choice stays outside business code."""
        if not self.webhook_url.strip() or not self.api_token.strip():
            raise RuntimeError("Receipt provider is not configured.")
        request = Request(
            self.webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            if not 200 <= response.status < 300:
                raise OSError(f"Receipt provider returned HTTP {response.status}.")


def render_a5_invoice_pdf(detail: SaleDetail) -> bytes:
    """Render a dependency-free A5 invoice attachment from immutable sale snapshots."""
    sale = detail.sale
    text_lines = [
        "TAX INVOICE",
        f"Invoice: {sale.invoice_number}",
        f"Date: {sale.business_date.isoformat()}",
        f"Taxable: INR {sale.taxable_amount:.2f}",
        f"CGST: INR {sale.cgst_amount:.2f}",
        f"SGST: INR {sale.sgst_amount:.2f}",
        f"IGST: INR {sale.igst_amount:.2f}",
        f"Cess: INR {sale.cess_amount:.2f}",
        f"Total: INR {sale.net_amount:.2f}",
        "",
    ]
    for item in detail.items:
        product = detail.products[item.product_id]
        text_lines.append(
            f"{product.sku} {product.name}  {item.quantity:.3f} x {item.unit_price:.2f}"
        )
    if detail.e_invoice is not None and detail.e_invoice.irn:
        text_lines.extend(
            (
                "",
                f"IRN: {detail.e_invoice.irn}",
                f"Ack No: {detail.e_invoice.ack_number or '-'}",
            )
        )
    if detail.composition_declaration:
        text_lines.extend(("", detail.composition_declaration))
    commands = ["BT", "/F1 10 Tf", "36 559 Td"]
    for index, line in enumerate(text_lines):
        if index:
            commands.append("0 -14 Td")
        safe = line.encode("latin-1", errors="replace").decode("latin-1")
        safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({safe}) Tj")
    commands.append("ET")
    if detail.e_invoice is not None and detail.e_invoice.signed_qr_code:
        matrix = qr_matrix(detail.e_invoice.signed_qr_code)
        module_size = Decimal("1.5")
        origin_x = Decimal("300")
        origin_y = Decimal("36")
        commands.append("0 0 0 rg")
        for row_index, row in enumerate(matrix):
            for column_index, dark in enumerate(row):
                if not dark:
                    continue
                x = origin_x + Decimal(column_index) * module_size
                y = origin_y + Decimal(len(matrix) - row_index - 1) * module_size
                commands.append(f"{x:f} {y:f} {module_size:f} {module_size:f} re f")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 595] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode("ascii"))
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(document)


def pdf_attachment_payload(filename: str, content: bytes) -> dict[str, str]:
    """Encode one PDF using the common webhook attachment shape."""
    return {
        "filename": filename,
        "content_type": "application/pdf",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
