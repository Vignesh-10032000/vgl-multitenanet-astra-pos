"""Store profile API for legal receipt rendering and privileged settings."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, g
from sqlalchemy.orm import Session

from vglpos.api.v1.http import model_response, parse_body
from vglpos.api.v1.idempotency import idempotent
from vglpos.api.v1.openapi import documented
from vglpos.api.v1.schemas.settings import (
    StoreLogoRequest,
    StoreProfileResponse,
    StoreProfileUpdateRequest,
    TeamDirectoryResponse,
    TeamMemberRequest,
    TeamMemberResponse,
)
from vglpos.extensions import db, limiter
from vglpos.security.decorators import require_permission
from vglpos.services.store_profile_service import StoreProfileService, UpdateStoreProfileCommand
from vglpos.services.team_service import SaveTeamMember, TeamService

settings_bp = Blueprint("settings", __name__, url_prefix="/api/v1/settings")


@settings_bp.get("/team")
@require_permission("user.manage")
@documented(
    summary="List this company's team and grantable roles", response_model=TeamDirectoryResponse
)
def team_directory() -> tuple[Response, int]:
    """Keep user discovery behind the live company administrator boundary."""
    with Session(db.engine) as session:
        directory = TeamService(session, g.company_id, g.user_id).directory()
        return model_response(TeamDirectoryResponse.model_validate(directory))


@settings_bp.post("/team")
@require_permission("user.manage")
@limiter.limit("10 per minute")
@idempotent
@documented(
    summary="Create a company team account with a fresh credential proof",
    request_model=TeamMemberRequest,
    response_model=TeamMemberResponse,
)
def create_team_member() -> tuple[Response, int]:
    """Delegate grant checks and credential storage to the tenant service."""
    body = parse_body(TeamMemberRequest)
    with Session(db.engine) as session:
        member = TeamService(session, g.company_id, g.user_id).save(
            SaveTeamMember(**body.model_dump())
        )
        return model_response(TeamMemberResponse.model_validate(member), status=201)


@settings_bp.put("/team/<int:user_id>")
@require_permission("user.manage")
@limiter.limit("10 per minute")
@idempotent
@documented(
    summary="Change staff access and revoke previous sessions",
    request_model=TeamMemberRequest,
    response_model=TeamMemberResponse,
)
def update_team_member(user_id: int) -> tuple[Response, int]:
    """Ensure every access change uses the same privilege and audit checks."""
    body = parse_body(TeamMemberRequest)
    with Session(db.engine) as session:
        member = TeamService(session, g.company_id, g.user_id).save(
            SaveTeamMember(**body.model_dump()), user_id=user_id
        )
        return model_response(TeamMemberResponse.model_validate(member))


@settings_bp.put("/store-logo")
@require_permission("settings.manage")
@idempotent
@documented(
    summary="Upload or remove a normalized store logo",
    request_model=StoreLogoRequest,
    response_model=StoreProfileResponse,
)
def update_store_logo() -> tuple[Response, int]:
    """Delegate raster validation and tenant-bound storage to the profile service."""
    body = parse_body(StoreLogoRequest)
    with Session(db.engine) as session:
        profile = StoreProfileService(session, g.company_id, branch_id=g.branch_id).update_logo(
            user_id=g.user_id, image_base64=body.image_base64
        )
        return model_response(_response(profile))


def _response(profile: object) -> StoreProfileResponse:
    return StoreProfileResponse.model_validate(profile).model_copy(
        update={"time_zone": current_app.config["STORE_TIMEZONE"]}
    )


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
