"""Store-profile contracts used by settings and legal receipt rendering."""

from __future__ import annotations

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
