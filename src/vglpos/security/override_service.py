"""Manager-PIN approvals for discounts, price overrides, and sale voids."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from vglpos.repositories.identity import UserRepository
from vglpos.security.audit import record_audit_event
from vglpos.security.auth_service import AuthService
from vglpos.services.exceptions import AuthorizationError, ValidationError
from vglpos.utils.money import money, to_decimal


@dataclass(frozen=True, slots=True)
class Approval:
    action: str
    approver_user_id: int
    reason: str


class OverrideApprovalService:
    """Apply role limits in the service layer even when a caller bypasses HTTP."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def approve_discount(
        self,
        *,
        company_id: int,
        actor_user_id: int,
        discount_percent: object,
        approval_pin: str | None,
        approver_user_id: int | None,
        reason: str | None,
    ) -> Approval | None:
        """Require a manager PIN only when the actor's configured limit is exceeded."""
        try:
            percent = money(to_decimal(discount_percent))
        except ValueError as exc:
            raise ValidationError("Discount percentage must be numeric.") from exc
        if percent < 0 or percent > Decimal("100.00"):
            raise ValidationError("Discount percentage must be between 0 and 100.")
        actor_context = UserRepository(self.session, company_id).authorization_context(
            actor_user_id, branch_id=None
        )
        if "sale.discount" not in actor_context.permissions:
            raise AuthorizationError("The current user cannot apply discounts.")
        if percent <= actor_context.max_discount_percent:
            return None
        return self._approve(
            company_id=company_id,
            actor_user_id=actor_user_id,
            approval_pin=approval_pin,
            approver_user_id=approver_user_id,
            reason=reason,
            required_permission="sale.discount",
            action="DISCOUNT_OVERRIDE",
            new_values={
                "discount_percent": str(percent),
                "actor_limit": str(actor_context.max_discount_percent),
            },
        )

    def approve_price_override(
        self,
        *,
        company_id: int,
        actor_user_id: int,
        approval_pin: str | None,
        approver_user_id: int | None,
        reason: str | None,
        original_price: object,
        override_price: object,
    ) -> Approval:
        """Record both prices only after a manager verifies the override."""
        try:
            original = money(original_price)
            override = money(override_price)
        except ValueError as exc:
            raise ValidationError("Override prices must be numeric.") from exc
        if original < 0 or override < 0:
            raise ValidationError("Override prices cannot be negative.")
        return self._approve(
            company_id=company_id,
            actor_user_id=actor_user_id,
            approval_pin=approval_pin,
            approver_user_id=approver_user_id,
            reason=reason,
            required_permission="sale.price_override",
            action="PRICE_OVERRIDE",
            new_values={"original_price": str(original), "override_price": str(override)},
        )

    def approve_void(
        self,
        *,
        company_id: int,
        actor_user_id: int,
        sale_id: int,
        approval_pin: str | None,
        approver_user_id: int | None,
        reason: str | None,
    ) -> Approval:
        """Require an attributable manager approval before any sale void."""
        return self._approve(
            company_id=company_id,
            actor_user_id=actor_user_id,
            approval_pin=approval_pin,
            approver_user_id=approver_user_id,
            reason=reason,
            required_permission="sale.void",
            action="SALE_VOID",
            new_values={"sale_id": sale_id},
        )

    def approve_shift_variance(
        self,
        *,
        company_id: int,
        actor_user_id: int,
        shift_id: int,
        variance: object,
        approval_pin: str | None,
        approver_user_id: int | None,
        reason: str | None,
    ) -> Approval:
        """Require an attributable manager before accepting a large drawer variance."""
        try:
            normalized_variance = money(variance)
        except ValueError as exc:
            raise ValidationError("Shift variance must be numeric.") from exc
        return self._approve(
            company_id=company_id,
            actor_user_id=actor_user_id,
            approval_pin=approval_pin,
            approver_user_id=approver_user_id,
            reason=reason,
            required_permission="shift.close",
            action="SHIFT_VARIANCE_APPROVAL",
            new_values={"shift_id": shift_id, "variance": str(normalized_variance)},
        )

    def approve_bulk_price_update(
        self,
        *,
        company_id: int,
        actor_user_id: int,
        category_id: int | None,
        percentage: object,
        approval_pin: str | None,
        approver_user_id: int | None,
        reason: str | None,
    ) -> Approval:
        """Require a manager approval before changing multiple catalogue prices."""
        try:
            normalized_percentage = to_decimal(percentage).quantize(Decimal("0.01"))
        except ValueError as exc:
            raise ValidationError("Bulk price percentage must be numeric.") from exc
        return self._approve(
            company_id=company_id,
            actor_user_id=actor_user_id,
            approval_pin=approval_pin,
            approver_user_id=approver_user_id,
            reason=reason,
            required_permission="product.edit",
            action="BULK_PRICE_APPROVAL",
            new_values={
                "category_id": category_id,
                "percentage": str(normalized_percentage),
            },
        )

    def _approve(
        self,
        *,
        company_id: int,
        actor_user_id: int,
        approval_pin: str | None,
        approver_user_id: int | None,
        reason: str | None,
        required_permission: str,
        action: str,
        new_values: dict[str, object],
    ) -> Approval:
        if approval_pin is None or approver_user_id is None or reason is None:
            raise AuthorizationError("Manager PIN, approver, and reason are required.")
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValidationError("An approval reason is required.")
        approver = AuthService(self.session).verify_approval_pin(
            company_id=company_id,
            user_id=approver_user_id,
            pin=approval_pin,
        )
        context = UserRepository(self.session, company_id).authorization_context(
            approver.id, branch_id=None
        )
        if not ({"OWNER", "MANAGER"} & set(context.role_names)):
            raise AuthorizationError("Approver must hold the OWNER or MANAGER role.")
        if required_permission not in context.permissions:
            raise AuthorizationError("Approver lacks the required permission.")
        record_audit_event(
            self.session,
            company_id=company_id,
            user_id=approver.id,
            action=action,
            entity_type="Approval",
            entity_id=f"{actor_user_id}:{approver.id}",
            new_values={
                **new_values,
                "actor_user_id": actor_user_id,
                "approver_user_id": approver.id,
                "reason": normalized_reason,
            },
        )
        return Approval(action=action, approver_user_id=approver.id, reason=normalized_reason)
