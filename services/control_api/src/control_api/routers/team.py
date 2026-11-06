"""Team & roles (G-02): members, invites, role changes, removal; invite preview + accept (A-05).

Security rules (SPEC §8.3, OPEN_QUESTIONS Q4):
* an actor can grant, change or remove only roles listed in its ``can_assign`` (Admin cannot touch Owners);
* nobody changes their own role or removes themselves here;
* the last active Owner cannot be demoted or removed;
* invites are single-use, expire, and must be accepted by a verified login with the invited e-mail.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_api import audit
from control_api.deps import (
    CustomerDep,
    OrgContext,
    StateDep,
    UserDep,
    ensure_path_org,
    require,
)
from control_api.mailer import Mail
from control_api.models import AppUser, Invite, Membership, Org
from control_api.notifications import notify
from control_api.schemas import (
    CustomerRole,
    InviteCreate,
    InviteOut,
    InvitePreview,
    MemberOut,
    MembershipPatch,
    MembershipSummary,
    TeamOut,
)
from control_api.state import AppState
from dcs_common.logging import mask_email
from dcs_common.problem import PROBLEM_RESPONSES, ProblemError, conflict, forbidden, not_found

router = APIRouter(prefix="/v1", tags=["team"], responses=PROBLEM_RESPONSES)

MembersRead = Annotated[OrgContext, Depends(require("members:read"))]
MembersInvite = Annotated[OrgContext, Depends(require("members:invite"))]
MembersManage = Annotated[OrgContext, Depends(require("members:manage"))]


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _member_out(m: Membership, u: AppUser) -> MemberOut:
    return MemberOut(
        id=m.id,
        user_id=u.id,
        email=u.email,
        name=u.name,
        role=m.role,  # type: ignore[arg-type]
        status=m.status,
        created_at=m.created_at,
    )


def _invite_out(i: Invite) -> InviteOut:
    return InviteOut(
        id=i.id,
        email=i.email,
        role=cast(CustomerRole, i.role),
        status=i.status,
        expires_at=i.expires_at,
        created_at=i.created_at,
    )


@router.get("/orgs/{org_id}/members", response_model=TeamOut, summary="Members and pending invites")
async def list_members(org_id: uuid.UUID, state: StateDep, ctx: MembersRead) -> TeamOut:
    ensure_path_org(ctx, org_id)
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        members = (
            await s.execute(
                select(Membership, AppUser)
                .join(AppUser, AppUser.id == Membership.user_id)
                .where(Membership.org_id == org_id, Membership.status == "active")
                .order_by(Membership.created_at)
            )
        ).all()
        invites = (
            await s.scalars(
                select(Invite)
                .where(Invite.org_id == org_id, Invite.status == "pending")
                .order_by(Invite.created_at)
            )
        ).all()
    return TeamOut(members=[_member_out(m, u) for m, u in members], invites=[_invite_out(i) for i in invites])


@router.post("/orgs/{org_id}/invites", status_code=201, response_model=InviteOut, summary="Invite a user")
async def create_invite(
    org_id: uuid.UUID, body: InviteCreate, state: StateDep, ctx: MembersInvite
) -> InviteOut:
    ensure_path_org(ctx, org_id)
    if not state.policy.can_assign(ctx.role, body.role):
        raise forbidden(f"Your role cannot grant the {body.role} role.")
    token = secrets.token_urlsafe(32)
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        already = await s.scalar(
            select(Membership.id)
            .join(AppUser, AppUser.id == Membership.user_id)
            .where(Membership.org_id == org_id, Membership.status == "active", AppUser.email == body.email)
        )
        if already is not None:
            raise conflict("This person is already a member.")
        for old in (
            await s.scalars(
                select(Invite).where(
                    Invite.org_id == org_id, Invite.email == body.email, Invite.status == "pending"
                )
            )
        ).all():
            old.status = "revoked"
        org = await s.get(Org, org_id)
        assert org is not None  # noqa: S101 - membership guarantees the org exists
        invite = Invite(
            org_id=org_id,
            email=body.email,
            role=body.role,
            token_hash=token_hash(token),
            status="pending",
            invited_by=ctx.user.id,
            expires_at=datetime.now(UTC) + timedelta(days=state.settings.invite_ttl_days),
        )
        s.add(invite)
        await s.flush()
        await audit.emit(
            s,
            actor=ctx.actor,
            action="member.invited",
            org_id=org_id,
            target_type="invite",
            target_id=str(invite.id),
            details={"role": body.role, "email": mask_email(body.email)},
        )
        await s.refresh(invite)
        out = _invite_out(invite)
        org_name = org.name
    link = f"{state.settings.web_base_url.rstrip('/')}/auth/invite/{token}"
    await state.mailer.send(
        Mail(
            to=body.email,
            subject=f"You're invited to {org_name} on DCS-PIS",
            text=(
                f"{ctx.user.name or ctx.user.email} invited you to join {org_name} as {body.role}.\n\n"
                f"Accept the invitation: {link}\n\nThe link expires in {state.settings.invite_ttl_days} days."
            ),
        )
    )
    return out


@router.delete("/orgs/{org_id}/invites/{invite_id}", status_code=204, summary="Revoke a pending invite")
async def revoke_invite(
    org_id: uuid.UUID, invite_id: uuid.UUID, state: StateDep, ctx: MembersInvite
) -> Response:
    ensure_path_org(ctx, org_id)
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        invite = await s.get(Invite, invite_id, with_for_update=True)
        if invite is None or invite.org_id != ctx.org_id or invite.status != "pending":
            raise not_found()
        if not state.policy.can_assign(ctx.role, invite.role):
            raise forbidden(f"Your role cannot manage {invite.role} invites.")
        invite.status = "revoked"
        await audit.emit(
            s,
            actor=ctx.actor,
            action="member.invite_revoked",
            org_id=ctx.org_id,
            target_type="invite",
            target_id=str(invite_id),
        )
    return Response(status_code=204)


async def _load_membership(s: AsyncSession, ctx: OrgContext, membership_id: uuid.UUID) -> Membership:
    m = await s.get(Membership, membership_id, with_for_update=True)
    if m is None or m.org_id != ctx.org_id or m.status != "active":
        raise not_found()
    return m


async def _guard_change(
    s: AsyncSession, state: AppState, ctx: OrgContext, m: Membership, new_role: str | None
) -> None:
    if m.user_id == ctx.user.id:
        raise forbidden("You cannot change your own membership.")
    if not state.policy.can_assign(ctx.role, m.role):
        raise forbidden(f"Your role cannot manage members with the {m.role} role.")
    if new_role is not None and not state.policy.can_assign(ctx.role, new_role):
        raise forbidden(f"Your role cannot grant the {new_role} role.")
    if m.role == "owner" and new_role != "owner":
        owners = await s.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.org_id == ctx.org_id, Membership.role == "owner", Membership.status == "active")
        )
        if (owners or 0) <= 1:
            raise conflict("An organisation must keep at least one owner.")


@router.patch("/memberships/{membership_id}", response_model=MemberOut, summary="Change a member's role")
async def change_role(
    membership_id: uuid.UUID, body: MembershipPatch, state: StateDep, ctx: MembersManage
) -> MemberOut:
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        m = await _load_membership(s, ctx, membership_id)
        await _guard_change(s, state, ctx, m, body.role)
        old = m.role
        if old != body.role:
            m.role = body.role
            m.updated_at = datetime.now(UTC)
            await audit.emit(
                s,
                actor=ctx.actor,
                action="member.role_changed",
                org_id=ctx.org_id,
                target_type="membership",
                target_id=str(m.id),
                details={"from": old, "to": body.role},
            )
            await notify(
                s,
                state.publisher,
                state.mailer,
                org_id=ctx.org_id,
                user_ids=[m.user_id],
                event_type="member.role_changed",
                payload={"message": f"Your role is now {body.role}.", "role": body.role},
            )
        user = await s.get(AppUser, m.user_id)
        assert user is not None  # noqa: S101
        await s.flush()
        return _member_out(m, user)


@router.delete("/memberships/{membership_id}", status_code=204, summary="Remove a member")
async def remove_member(membership_id: uuid.UUID, state: StateDep, ctx: MembersManage) -> Response:
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        m = await _load_membership(s, ctx, membership_id)
        await _guard_change(s, state, ctx, m, None)
        m.status = "removed"
        m.updated_at = datetime.now(UTC)
        await audit.emit(
            s,
            actor=ctx.actor,
            action="member.removed",
            org_id=ctx.org_id,
            target_type="membership",
            target_id=str(m.id),
            details={"role": m.role},
        )
    return Response(status_code=204)


# --------------------------------------------------------------------------------- invite acceptance
async def _find_invite(state: StateDep, token: str) -> Invite:
    if not 20 <= len(token) <= 100:
        raise not_found()
    # The invitee is not a member yet, so the lookup by token hash runs in platform scope. Only the hash of
    # an unguessable 256-bit token can match; nothing else is read.
    async with state.db.platform_tx() as s:
        invite = await s.scalar(select(Invite).where(Invite.token_hash == token_hash(token)))
    if invite is None or invite.status != "pending":
        raise not_found("This invitation is not valid. Ask for a new one.")
    return invite


@router.get("/invites/{token}", response_model=InvitePreview, summary="Public invite preview (no auth)")
async def preview_invite(token: str, state: StateDep) -> InvitePreview:
    invite = await _find_invite(state, token)
    async with state.db.platform_tx() as s:
        org = await s.get(Org, invite.org_id)
    if org is None or org.status == "deleted":
        raise not_found()
    expired = invite.expires_at <= datetime.now(UTC)
    return InvitePreview(
        org_name=org.name,
        role=cast(CustomerRole, invite.role),
        email_hint=mask_email(invite.email),
        status="expired" if expired else "pending",
        expires_at=invite.expires_at,
    )


@router.post("/invites/{token}/accept", response_model=MembershipSummary, summary="Accept an invitation")
async def accept_invite(
    token: str, state: StateDep, principal: CustomerDep, user: UserDep
) -> MembershipSummary:
    invite = await _find_invite(state, token)
    if invite.expires_at <= datetime.now(UTC):
        raise ProblemError(
            410, slug="invite-expired", detail="This invitation has expired. Ask for a new one."
        )
    if state.settings.require_verified_email and not principal.email_verified:
        raise ProblemError(403, slug="email-unverified", detail="Verify your e-mail address first.")
    if user.email.casefold() != invite.email.casefold():
        async with state.db.org_tx(invite.org_id, None) as s:
            await audit.emit(
                s,
                actor=audit.Actor("user", str(user.id)),
                action="member.invite_email_mismatch",
                org_id=invite.org_id,
                target_type="invite",
                target_id=str(invite.id),
            )
        raise forbidden("This invitation was sent to a different e-mail address.")

    async with state.db.org_tx(invite.org_id, user.id) as s:
        inv = await s.get(Invite, invite.id, with_for_update=True)
        if inv is None or inv.status != "pending":
            raise not_found()
        org = await s.get(Org, inv.org_id)
        if org is None or org.status == "deleted":
            raise not_found()
        m = await s.scalar(
            select(Membership).where(Membership.org_id == inv.org_id, Membership.user_id == user.id)
        )
        if m is None:
            m = Membership(
                org_id=inv.org_id, user_id=user.id, role=inv.role, status="active", invited_by=inv.invited_by
            )
            s.add(m)
        elif m.status != "active":
            m.status, m.role, m.updated_at = "active", inv.role, datetime.now(UTC)
        else:
            raise conflict("You are already a member of this organisation.")
        inv.status, inv.accepted_by, inv.accepted_at = "accepted", user.id, datetime.now(UTC)
        await s.flush()
        await audit.emit(
            s,
            actor=audit.Actor("user", str(user.id)),
            action="member.joined",
            org_id=inv.org_id,
            target_type="membership",
            target_id=str(m.id),
            details={"role": m.role, "invite_id": str(inv.id)},
        )
        if inv.invited_by:
            await notify(
                s,
                state.publisher,
                state.mailer,
                org_id=inv.org_id,
                user_ids=[inv.invited_by],
                event_type="member.joined",
                payload={"message": f"{user.name or mask_email(user.email)} joined as {m.role}."},
            )
        return MembershipSummary(
            membership_id=m.id,
            org_id=org.id,
            org_name=org.name,
            org_slug=org.slug,
            org_status=org.status,
            tenant_id=org.tenant_id,
            region=org.region,
            role=m.role,  # type: ignore[arg-type]
            permissions=sorted(state.policy.permissions_for(m.role)),
            mfa_required=state.policy.mfa_required(m.role),
        )
