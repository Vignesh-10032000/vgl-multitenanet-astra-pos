"""Identity endpoint contracts shared with OpenAPI generation."""

from __future__ import annotations

from pydantic import Field

from vglpos.api.v1.schemas.common import RequestModel, ResponseModel


class LoginRequest(RequestModel):
    company_code: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)
    branch_id: int | None = Field(default=None, gt=0)
    terminal_id: int | None = Field(default=None, gt=0)
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class PinLoginRequest(RequestModel):
    company_code: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    user_id: int = Field(gt=0)
    pin: str = Field(pattern=r"^\d{4,6}$")
    branch_id: int | None = Field(default=None, gt=0)
    terminal_id: int | None = Field(default=None, gt=0)


class MfaCodeRequest(RequestModel):
    code: str = Field(pattern=r"^\d{6}$")


class AuthUserResponse(ResponseModel):
    id: int
    company_id: int
    branch_id: int | None
    terminal_id: int | None
    full_name: str
    roles: list[str]
    permissions: list[str]
    max_discount_percent: str


class AuthenticationResponse(ResponseModel):
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int
    user: AuthUserResponse


class MfaSetupResponse(ResponseModel):
    provisioning_uri: str


class UserProfileResponse(ResponseModel):
    id: int
    company_id: int
    username: str
    email: str
    full_name: str
    branch_id: int | None
    terminal_id: int | None
    roles: list[str]
    permissions: list[str]
    max_discount_percent: str
    mfa_enabled: bool
