"""Signed e-invoice QR rendering shared by browser receipts and A5 PDFs."""

from __future__ import annotations

import base64
from io import BytesIO

import qrcode  # type: ignore[import-untyped]
from qrcode.constants import ERROR_CORRECT_M  # type: ignore[import-untyped]


def qr_matrix(payload: str) -> tuple[tuple[bool, ...], ...]:
    """Encode the signed IRP payload into a standards-compliant QR module matrix."""
    if not payload:
        raise ValueError("Signed QR payload is required.")
    code = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=4, border=4)
    code.add_data(payload)
    code.make(fit=True)
    return tuple(tuple(bool(cell) for cell in row) for row in code.get_matrix())


def qr_png_data_uri(payload: str) -> str:
    """Return a self-contained PNG URI allowed by the receipt's strict CSP."""
    code = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=5, border=4)
    code.add_data(payload)
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
