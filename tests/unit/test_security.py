"""Focused tests for Phase 2 credential and TOTP primitives."""

from __future__ import annotations

import pyotp
import pytest
from argon2 import PasswordHasher, Type

from vglpos.security.mfa import generate_totp_secret, provisioning_uri, verify_totp
from vglpos.security.password import (
    hash_password,
    hash_pin,
    needs_rehash,
    pin_needs_rehash,
    verify_password,
    verify_pin,
)


def test_password_hash_uses_required_argon2id_parameters() -> None:
    password_hash = hash_password("A sufficiently long password")

    assert password_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert verify_password(password_hash, "A sufficiently long password")
    assert not verify_password(password_hash, "wrong")
    assert not verify_password("malformed", "anything")
    assert not needs_rehash(password_hash)


def test_password_rehash_and_empty_validation() -> None:
    old_hash = PasswordHasher(
        time_cost=1,
        memory_cost=8192,
        parallelism=1,
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    ).hash("password")

    assert needs_rehash(old_hash)
    assert needs_rehash("malformed")
    with pytest.raises(ValueError, match="cannot be empty"):
        hash_password("")


def test_pin_hash_uses_lower_cost_and_validates_format() -> None:
    pin_hash = hash_pin("2468")

    assert pin_hash.startswith("$argon2id$v=19$m=19456,t=2,p=2$")
    assert verify_pin(pin_hash, "2468")
    assert not verify_pin(pin_hash, "1357")
    assert not verify_pin("malformed", "2468")
    assert not pin_needs_rehash(pin_hash)
    assert pin_needs_rehash("malformed")
    for invalid in ("123", "1234567", "12ab"):
        with pytest.raises(ValueError, match="4 to 6 digits"):
            hash_pin(invalid)


def test_totp_helpers_generate_uri_and_verify_current_code() -> None:
    secret = generate_totp_secret()
    uri = provisioning_uri(secret, account_name="owner@example.invalid", issuer_name="VGL POS")

    assert uri.startswith("otpauth://totp/")
    assert verify_totp(secret, pyotp.TOTP(secret).now())
    assert not verify_totp(secret, "not-a-code")
