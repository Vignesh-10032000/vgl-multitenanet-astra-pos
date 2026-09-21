"""Store profile API for legal receipt rendering and privileged settings."""

from __future__ import annotations

from flask import Blueprint, Response, g
from sqlalchemy.orm import Session

from vglpos.api.v1.http import model_response, parse_body
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.settings import StoreProfileResponse, StoreProfileUpdateRequest
from vglpos.extensions import db
from vglpos.security.decorators import require_permission
from vglpos.services.store_profile_service import StoreProfileService, UpdateStoreProfileCommand

settings_bp = Blueprint("settings", __name__, url_prefix="/api/v1/settings")


def _response(profile: object) -> StoreProfileResponse:
    return StoreProfileResponse.model_validate(profile)


@settings_bp.get("/store-profile")
@require_permission()
@documented(
    summary="Get the selected branch's legal receipt identity", response_model=StoreProfileResponse
)
def store_profile() -> tuple[Response, int]:
    """Expose receipt identity to any authenticated counter user."""
    with Session(db.engine) as session:
        profile = StoreProfileService(session, g.company_id, branch_id=g.branch_id).get()
        return model_response(_response(profile))


@settings_bp.put("/store-profile")
@require_permission("settings.manage")
@idempotent
@documented(
    summary="Update the selected branch's legal receipt identity",
    request_model=StoreProfileUpdateRequest,
    response_model=StoreProfileResponse,
)
def update_store_profile() -> tuple[Response, int]:
    """Delegate validated legal-profile changes to the transactional service."""
    body = parse_body(StoreProfileUpdateRequest)
    command = UpdateStoreProfileCommand(
        company_id=g.company_id,
        branch_id=g.branch_id,
        user_id=g.user_id,
        **body.model_dump(),
    )
    with Session(db.engine) as session:
        profile = StoreProfileService(session, g.company_id, branch_id=g.branch_id).update(command)
        return model_response(_response(profile))
