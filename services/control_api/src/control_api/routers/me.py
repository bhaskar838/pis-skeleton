from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from control_api.deps import CustomerDep, StateDep, UserDep
from control_api.models import Membership, Org
from control_api.schemas import MembershipSummary, MeOut, UserOut
from dcs_common.problem import PROBLEM_RESPONSES

router = APIRouter(prefix="/v1", tags=["me"], responses=PROBLEM_RESPONSES)


@router.get("/me", response_model=MeOut, summary="Current user, session MFA state and memberships")
async def get_me(state: StateDep, principal: CustomerDep, user: UserDep) -> MeOut:
    async with state.db.user_tx(user.id) as session:
        rows = (
            await session.execute(
                select(Membership, Org)
                .join(Org, Org.id == Membership.org_id)
                .where(Membership.user_id == user.id, Membership.status == "active", Org.status != "deleted")
                .order_by(Org.name)
            )
        ).all()
    memberships = [
        MembershipSummary(
            membership_id=m.id,
            org_id=o.id,
            org_name=o.name,
            org_slug=o.slug,
            org_status=o.status,
            tenant_id=o.tenant_id,
            region=o.region,
            role=m.role,  # type: ignore[arg-type]
            permissions=sorted(state.policy.permissions_for(m.role)),
            mfa_required=state.policy.mfa_required(m.role),
        )
        for m, o in rows
    ]
    return MeOut(
        user=UserOut(id=user.id, email=user.email, name=user.name),
        session_mfa=principal.has_mfa(),
        email_verified=principal.email_verified,
        memberships=memberships,
    )
