"""Phase 2 authorization, tenancy, override, and audit integration tests."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import AuditLog, Permission, Role, RolePermission, User, UserRole
from vglpos.extensions import db
from vglpos.routes import PUBLIC_ENDPOINTS
from vglpos.security.audit import set_audit_context
from vglpos.security.decorators import require_permission
from vglpos.security.override_service import OverrideApprovalService
from vglpos.security.password import hash_password
from vglpos.services.exceptions import AuthorizationError

from .conftest import IdentityContext


def _login(client: FlaskClient, context: IdentityContext) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "company_code": context.company.login_code,
            "username": context.user.username,
            "password": context.password,
            "branch_id": context.branch.id,
            "terminal_id": context.terminal.id,
        },
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert isinstance(body, dict)
    return body


def _bearer(body: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_p0_2_every_api_route_is_permission_guarded(auth_app: Flask) -> None:
    failures: list[str] = []
    for rule in auth_app.url_map.iter_rules():
        if not rule.rule.startswith("/api/") or rule.endpoint in PUBLIC_ENDPOINTS:
            continue
        view = auth_app.view_functions[rule.endpoint]
        if getattr(view, "_permission_required", False) is not True:
            failures.append(f"{','.join(sorted(rule.methods or set()))} {rule.rule}")
    assert not failures, f"API routes without permission declarations: {failures}"


def test_unknown_permission_code_fails_closed_at_registration() -> None:
    with pytest.raises(RuntimeError, match="Unknown permission code"):
        require_permission("unknown.permission")


def test_token_cannot_be_used_to_access_another_company(
    auth_client: FlaskClient,
    identity_factory: Callable[[], IdentityContext],
) -> None:
    company_a = identity_factory()
    company_b = identity_factory()
    token = _login(auth_client, company_a)

    response = auth_client.get(f"/api/v1/products/{company_b.product.id}", headers=_bearer(token))

    assert response.status_code == 404
    assert response.get_json()["detail"] == "Product was not found."


def test_permission_denial_is_audited(
    auth_app: Flask,
    auth_client: FlaskClient,
    identity_context: IdentityContext,
) -> None:
    with auth_app.app_context(), Session(db.engine) as session:
        assignment = session.scalar(
            select(RolePermission)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(
                RolePermission.company_id == identity_context.company.id,
                RolePermission.role_id == identity_context.role.id,
                Permission.code == "product.view",
            )
        )
        assert assignment is not None
        session.delete(assignment)
        session.commit()

    token = _login(auth_client, identity_context)
    denied = auth_client.get(
        f"/api/v1/products/{identity_context.product.id}", headers=_bearer(token)
    )
    assert denied.status_code == 403

    with auth_app.app_context(), Session(db.engine) as session:
        event = session.scalar(
            select(AuditLog)
            .where(
                AuditLog.company_id == identity_context.company.id,
                AuditLog.user_id == identity_context.user.id,
                AuditLog.action == "PERMISSION_DENIED",
            )
            .order_by(AuditLog.id.desc())
        )
        assert event is not None
        assert event.entity_id == "phase2_product_detail"
        assert event.new_values is not None
        assert event.new_values["required"] == ["product.view"]


def test_audit_log_records_who_changed_what_and_redacts_secrets(
    auth_app: Flask,
    identity_context: IdentityContext,
) -> None:
    old_email = identity_context.user.email
    new_email = f"changed-{old_email}"
    with auth_app.app_context(), Session(db.engine) as session:
        user = session.get(User, identity_context.user.id)
        assert user is not None
        set_audit_context(
            session,
            user_id=identity_context.user.id,
            ip_address="127.0.0.2",
            user_agent="phase2-test",
            request_id="12345678-1234-1234-1234-123456789012",
        )
        user.email = new_email
        user.password_hash = hash_password("Replacement password 42!")
        session.commit()

        event = session.scalar(
            select(AuditLog)
            .where(
                AuditLog.company_id == identity_context.company.id,
                AuditLog.entity_type == "User",
                AuditLog.entity_id == str(identity_context.user.id),
                AuditLog.action == "UPDATE",
            )
            .order_by(AuditLog.id.desc())
        )
        assert event is not None
        assert event.user_id == identity_context.user.id
        assert event.ip_address == "127.0.0.2"
        assert event.user_agent == "phase2-test"
        assert event.request_id == "12345678-1234-1234-1234-123456789012"
        assert event.old_values == {
            "email": old_email,
            "password_hash": "[REDACTED]",
        }
        assert event.new_values == {
            "email": new_email,
            "password_hash": "[REDACTED]",
        }


def test_audit_log_is_append_only_at_the_orm_boundary(
    auth_app: Flask,
    identity_context: IdentityContext,
) -> None:
    with auth_app.app_context(), Session(db.engine) as session:
        event = session.scalar(
            select(AuditLog)
            .where(AuditLog.company_id == identity_context.company.id)
            .order_by(AuditLog.id)
        )
        assert event is not None
        event.action = "TAMPERED"
        with pytest.raises(RuntimeError, match="append-only"):
            session.commit()
        session.rollback()


def test_discount_above_role_limit_requires_manager_pin(
    auth_app: Flask,
    identity_context: IdentityContext,
) -> None:
    with auth_app.app_context(), Session(db.engine, expire_on_commit=False) as session:
        discount_permission = session.scalar(
            select(Permission).where(Permission.code == "sale.discount")
        )
        assert discount_permission is not None
        cashier = User(
            company_id=identity_context.company.id,
            username=f"cashier-{identity_context.company.id}",
            email=f"cashier-{identity_context.company.id}@example.invalid",
            password_hash=hash_password("Cashier password 42!"),
            full_name="Test Cashier",
        )
        cashier_role = Role(
            company_id=identity_context.company.id,
            name="CASHIER",
            max_discount_percent=Decimal("5.00"),
        )
        session.add_all([cashier, cashier_role])
        session.flush()
        session.add_all(
            [
                UserRole(
                    company_id=identity_context.company.id,
                    user_id=cashier.id,
                    role_id=cashier_role.id,
                ),
                RolePermission(
                    company_id=identity_context.company.id,
                    role_id=cashier_role.id,
                    permission_id=discount_permission.id,
                ),
            ]
        )
        session.commit()

        service = OverrideApprovalService(session)
        assert (
            service.approve_discount(
                company_id=identity_context.company.id,
                actor_user_id=cashier.id,
                discount_percent="5.00",
                approval_pin=None,
                approver_user_id=None,
                reason=None,
            )
            is None
        )
        with pytest.raises(AuthorizationError, match="Manager PIN"):
            service.approve_discount(
                company_id=identity_context.company.id,
                actor_user_id=cashier.id,
                discount_percent="5.01",
                approval_pin=None,
                approver_user_id=None,
                reason=None,
            )

        approval = service.approve_discount(
            company_id=identity_context.company.id,
            actor_user_id=cashier.id,
            discount_percent="12.50",
            approval_pin=identity_context.pin,
            approver_user_id=identity_context.user.id,
            reason="Festival promotion",
        )
        assert approval is not None
        assert approval.approver_user_id == identity_context.user.id
        session.commit()

        event = session.scalar(
            select(AuditLog)
            .where(
                AuditLog.company_id == identity_context.company.id,
                AuditLog.action == "DISCOUNT_OVERRIDE",
            )
            .order_by(AuditLog.id.desc())
        )
        assert event is not None
        assert event.user_id == identity_context.user.id
        assert event.new_values is not None
        assert event.new_values["actor_user_id"] == cashier.id
        assert event.new_values["reason"] == "Festival promotion"
