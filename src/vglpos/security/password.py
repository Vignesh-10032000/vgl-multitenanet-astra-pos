"""Argon2id credential hashing with separate password and counter-PIN costs."""

from __future__ import annotations

import re

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
_PIN_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
_PIN_PATTERN = re.compile(r"^\d{4,6}$")


def hash_password(password: str) -> str:
    """Hash a non-empty password with the mandatory interactive work factor."""
    if not password:
        raise ValueError("Password cannot be empty.")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return a single boolean for malformed hashes and credential mismatches."""
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Identify hashes that no longer carry the current Argon2id parameters."""
    try:
        return _PASSWORD_HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def hash_pin(pin: str) -> str:
    """Hash only a four-to-six digit counter PIN at the separately tuned cost."""
    if _PIN_PATTERN.fullmatch(pin) is None:
        raise ValueError("PIN must contain 4 to 6 digits.")
    return _PIN_HASHER.hash(pin)


def verify_pin(pin_hash: str, pin: str) -> bool:
    """Verify a counter PIN without exposing malformed stored hashes."""
    try:
        return _PIN_HASHER.verify(pin_hash, pin)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def pin_needs_rehash(pin_hash: str) -> bool:
    """Identify PIN hashes that need the current lower-latency parameters."""
    try:
        return _PIN_HASHER.check_needs_rehash(pin_hash)
    except InvalidHashError:
        return True
