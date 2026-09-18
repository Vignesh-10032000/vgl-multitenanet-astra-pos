"""TOTP helpers kept independent from HTTP and persistence concerns."""

from __future__ import annotations

import pyotp


def generate_totp_secret() -> str:
    """Create a standards-compatible secret suitable for authenticator applications."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, *, account_name: str, issuer_name: str) -> str:
    """Build the URI consumed by authenticator applications without rendering a QR code."""
    if not secret or not account_name.strip() or not issuer_name.strip():
        raise ValueError("Secret, account name, and issuer are required.")
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_name.strip(), issuer_name=issuer_name.strip()
    )


def verify_totp(secret: str, code: str, *, valid_window: int = 1) -> bool:
    """Allow one adjacent time step for modest clock drift without widening replay risk."""
    if not secret or not isinstance(code, str) or len(code) != 6 or not code.isdigit():
        return False
    try:
        return bool(pyotp.TOTP(secret).verify(code, valid_window=valid_window))
    except (TypeError, ValueError):
        return False
