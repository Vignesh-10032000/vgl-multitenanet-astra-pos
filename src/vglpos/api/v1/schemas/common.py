"""Shared strict scalar and pagination contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Qty = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
NonNegativeQty = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]
Rate = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class RequestModel(BaseModel):
    """Reject unknown client fields so typos cannot silently change behavior."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseModel(BaseModel):
    """Serialize money and quantity values as exact JSON strings."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class CursorQuery(RequestModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=500)
    limit: int = Field(default=50, ge=1, le=200)


class StatusResponse(ResponseModel):
    status: str
