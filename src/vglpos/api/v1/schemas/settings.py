"""Store-profile contracts used by settings and legal receipt rendering."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from vglpos.api.v1.schemas.common import RequestModel, ResponseModel


class StoreProfileUpdateRequest(RequestModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str = Field(min_length=1, max_length=255)
    gstin: str | None = Field(default=None, pattern=r"^[0-9A-Z]{15}$")
    phone: str = Field(min_length=5, max_length=20)
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=3, max_length=10)


class StoreProfileResponse(ResponseModel):
    logo_data_uri: str | None = None
    time_zone: str = ""
    name: str
    legal_name: str
    gstin: str | None
    phone: str
    address_line1: str
    address_line2: str | None
    city: str
    state: str
    postal_code: str
    address: str


class StoreLogoRequest(RequestModel):
    image_base64: str | None = Field(default=None, min_length=1, max_length=700_000)


class TeamMemberRequest(RequestModel):
    username: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    full_name: str = Field(min_length=1, max_length=255)
    role: Literal[
        "SUPER_ADMIN", "ADMIN", "MANAGER", "CASHIER", "STOCK_CLERK", "ACCOUNTANT", "AUDITOR"
    ]
    is_active: bool = True
    password: str | None = Field(default=None, min_length=12, max_length=1024)
    pin: str | None = Field(default=None, pattern=r"^[0-9]{4,6}$")
    actor_password: str = Field(min_length=1, max_length=1024)
    actor_mfa_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


class TeamMemberResponse(ResponseModel):
    id: int
    username: str
    email: str
    full_name: str
    roles: list[str]
    is_active: bool
    mfa_enabled: bool


class TeamDirectoryResponse(ResponseModel):
    members: list[TeamMemberResponse]
    assignable_roles: list[str]
