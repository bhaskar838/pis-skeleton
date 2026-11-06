"""FastAPI dependencies: authentication, org context, permission checks (SPEC §8.2–8.4).

* Customer routes take the active org from the ``X-DCS-Org`` header and re-check an **active** membership on
  every request. A missing membership answers 404, so org IDs cannot be probed (OPEN_QUESTIONS Q1).
* Permissions are evaluated from the membership role on every request, so role changes apply immediately.
* Owner/Admin (and all staff) need an MFA-authenticated token (OPEN_QUESTIONS Q5).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select

from control_api.audit import Actor
from control_api.models import Membership, Org
from control_api.state import AppState
from control_api.users import UserDirectory, UserRef
from dcs_authz import STAFF_ROLES
from dcs_common import context
from dcs_common.auth import Principal, TokenError, bearer_from_header
from dcs_common.problem import ProblemError, forbidden, mfa_required, not_found, unauthorized


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.dcs
    return state


def get_users(request: Request) -> UserDirectory:
    users: UserDirectory = request.app.state.users
    return users


StateDep = Annotated[AppState, Depends(get_state)]


async def get_principal(request: Request, state: StateDep) -> Principal:
    try:
        token = bearer_from_header(request.headers.get("authorization"))
        return await state.validator.validate(token)
    except TokenError as exc:
        raise unauthorized(str(exc)) from None


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def customer_principal(principal: PrincipalDep) -> Principal:
    if principal.is_staff:
        raise forbidden("Staff tokens cannot be used on customer routes.")
    return principal


CustomerDep = Annotated[Principal, Depends(customer_principal)]


async def current_user(
    principal: CustomerDep, users: Annotated[UserDirectory, Depends(get_users)]
) -> UserRef:
    return await users.ensure(principal)


UserDep = Annotated[UserRef, Depends(current_user)]


@dataclass(frozen=True)
class OrgContext:
    org_id: uuid.UUID
    tenant_id: str
    org_status: str
    user: UserRef
    role: str
    permissions: frozenset[str]
    principal: Principal
    actor: Actor

    def has(self, permission: str) -> bool:
        return permission in self.permissions


def parse_org_header(value: str | None) -> uuid.UUID:
    if not value:
        raise ProblemError(400, slug="org-required", detail="Send the active organisation in X-DCS-Org.")
    try:
        return uuid.UUID(value)
    except ValueError:
        raise not_found() from None


async def org_context(
    request: Request,
    state: StateDep,
    principal: CustomerDep,
    user: UserDep,
    x_dcs_org: Annotated[str | None, Header(alias="X-DCS-Org")] = None,
) -> OrgContext:
    org_id = parse_org_header(x_dcs_org)
    async with state.db.org_tx(org_id, user.id) as session:
        row = (
            await session.execute(
                select(Membership.role, Org.tenant_id, Org.status)
                .join(Org, Org.id == Membership.org_id)
                .where(
                    Membership.org_id == org_id, Membership.user_id == user.id, Membership.status == "active"
                )
            )
        ).one_or_none()
    if row is None or row.status == "deleted":
        raise not_found()
    role: str = row.role
    if state.settings.mfa_enforce and state.policy.mfa_required(role) and not principal.has_mfa():
        raise mfa_required()
    context.org_id_var.set(str(org_id))
    context.tenant_id_var.set(row.tenant_id)
    return OrgContext(
        org_id=org_id,
        tenant_id=row.tenant_id,
        org_status=row.status,
        user=user,
        role=role,
        permissions=state.policy.permissions_for(role),
        principal=principal,
        actor=Actor("user", str(user.id), client_ip(request), request.headers.get("user-agent")),
    )


OrgDep = Annotated[OrgContext, Depends(org_context)]


def require(permission: str) -> Callable[..., Awaitable[OrgContext]]:
    """Dependency factory: the active org context, with ``permission`` enforced."""

    async def _dep(ctx: OrgDep, state: StateDep) -> OrgContext:
        state.policy.permissions[permission]
        if not ctx.has(permission):
            raise forbidden(permission=permission)
        return ctx

    _dep.__name__ = f"require_{permission.replace(':', '_')}"
    return _dep


def ensure_path_org(ctx: OrgContext, org_id: uuid.UUID) -> None:
    """Routes with an org ID in the path must match the active org (else 404, never another org's data)."""
    if org_id != ctx.org_id:
        raise not_found()


# ------------------------------------------------------------------------------------------- staff
@dataclass(frozen=True)
class StaffContext:
    principal: Principal
    roles: frozenset[str]
    permissions: frozenset[str]
    actor: Actor

    def has(self, permission: str) -> bool:
        return permission in self.permissions


async def staff_context(request: Request, state: StateDep, principal: PrincipalDep) -> StaffContext:
    if not principal.is_staff:
        raise forbidden("This route is for DCS staff.")
    roles = frozenset(r for r in principal.realm_roles if r in STAFF_ROLES)
    if not roles:
        raise forbidden("No staff role assigned.")
    if state.settings.mfa_enforce and not principal.has_mfa():
        raise mfa_required()
    perms: set[str] = set()
    for r in roles:
        perms |= state.policy.permissions_for(r)
    return StaffContext(
        principal=principal,
        roles=roles,
        permissions=frozenset(perms),
        actor=Actor("staff", principal.subject, client_ip(request), request.headers.get("user-agent")),
    )


StaffDep = Annotated[StaffContext, Depends(staff_context)]


def staff_require(permission: str) -> Callable[..., Awaitable[StaffContext]]:
    async def _dep(ctx: StaffDep, state: StateDep) -> StaffContext:
        state.policy.permissions[permission]
        if not ctx.has(permission):
            raise forbidden(permission=permission)
        return ctx

    _dep.__name__ = f"staff_require_{permission.replace(':', '_')}"
    return _dep
