"""Org creation (sign-up, A-02) and the organisation profile (G-01)."""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import func, select

from control_api import audit, idempotency
from control_api.audit import Actor
from control_api.deps import CustomerDep, OrgContext, StateDep, UserDep, client_ip, ensure_path_org, require
from control_api.flags import effective_flags
from control_api.models import Membership, Org, TenantDb
from control_api.regions import region_for_country
from control_api.schemas import OrgCreate, OrgOut, OrgProfilePatch
from control_api.workflows.inputs import PROVISION_WORKFLOW, ProvisionInput
from dcs_cbm import CBM_VERSION
from dcs_common.ids import new_tenant_id, uuid7, workflow_id
from dcs_common.problem import PROBLEM_RESPONSES, ProblemError

router = APIRouter(prefix="/v1", tags=["orgs"], responses=PROBLEM_RESPONSES)
log = logging.getLogger(__name__)


def org_out(o: Org) -> OrgOut:
    return OrgOut(
        id=o.id,
        tenant_id=o.tenant_id,
        name=o.name,
        slug=o.slug,
        country=o.country,
        region=o.region,
        status=o.status,
        plan_id=o.plan_id,
        business_profile=o.business_profile or {},
        profile_version=o.profile_version,
        created_at=o.created_at,
    )


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"
    return f"{base}-{secrets.token_hex(2)}"


@router.post(
    "/orgs", status_code=201, response_model=OrgOut, summary="Create an organisation and provision it"
)
async def create_org(
    body: OrgCreate,
    request: Request,
    response: Response,
    state: StateDep,
    principal: CustomerDep,
    user: UserDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> OrgOut | Response:
    key = idempotency.validate_key(idempotency_key)
    route = "POST /v1/orgs"
    if state.settings.require_verified_email and not principal.email_verified:
        raise ProblemError(
            403, slug="email-unverified", detail="Verify your e-mail address before creating an organisation."
        )
    try:
        region = region_for_country(body.country)
    except ValueError as exc:
        raise ProblemError(422, detail=str(exc)) from None

    async with state.db.unscoped_tx() as session:
        flags = await effective_flags(session, None, None)
    if not flags.get("system.signup_enabled", True):
        raise ProblemError(503, slug="signup-disabled", detail="Sign-up is temporarily disabled.")

    async with state.db.user_tx(user.id) as session:
        if key:
            prior = await idempotency.lookup(session, str(user.id), route, key)
            if prior is not None:
                return Response(
                    content=OrgOut(**prior.response).model_dump_json(),
                    status_code=prior.status_code,
                    media_type="application/json",
                )
        created = await session.scalar(
            select(func.count()).select_from(Org).where(Org.created_by == user.id, Org.status != "deleted")
        )
        if (created or 0) >= state.settings.max_orgs_per_user:
            raise ProblemError(409, slug="org-limit", detail="You have reached the organisation limit.")

    org_id = uuid7()
    tenant_id = new_tenant_id()
    actor = Actor("user", str(user.id), client_ip(request), request.headers.get("user-agent"))
    async with state.db.org_tx(org_id, user.id) as session:
        org = Org(
            id=org_id,
            tenant_id=tenant_id,
            name=body.name,
            slug=slugify(body.name),
            country=body.country,
            region=region,
            status="provisioning",
            created_by=user.id,
            business_profile={},
        )
        session.add(org)
        await session.flush()
        session.add(Membership(org_id=org_id, user_id=user.id, role="owner", status="active"))
        session.add(
            TenantDb(
                org_id=org_id,
                cluster=state.settings.tenant_cluster,
                db_name=tenant_id,
                status="pending",
                cbm_version=None,
            )
        )
        await audit.emit(
            session,
            actor=actor,
            action="org.created",
            org_id=org_id,
            target_type="org",
            target_id=str(org_id),
            details={
                "region": region,
                "country": body.country,
                "tenant_id": tenant_id,
                "cbm_target": CBM_VERSION,
            },
        )
        await session.flush()
        await session.refresh(org)
        out = org_out(org)
        if key:
            idempotency.store(session, str(user.id), route, key, 201, out.model_dump(mode="json"))

    wf_id = workflow_id("provision", tenant_id, "v1")
    try:
        await state.workflows.start(
            PROVISION_WORKFLOW, ProvisionInput(str(org_id), tenant_id, str(user.id)), workflow_id=wf_id
        )
    except Exception:
        # The org row exists with status=provisioning; staff can retry from M-03.
        log.exception("could not start provisioning workflow", extra={"workflow": wf_id})
        async with state.db.org_tx(org_id, user.id) as session:
            await audit.emit(
                session,
                actor=Actor.system("control-api"),
                action="tenant.provision.start_failed",
                org_id=org_id,
                target_type="workflow",
                target_id=wf_id,
            )
    response.headers["Location"] = f"/v1/orgs/{org_id}"
    return out


@router.get("/orgs/{org_id}", response_model=OrgOut, summary="Get the active organisation")
async def get_org(
    org_id: uuid.UUID, state: StateDep, ctx: Annotated[OrgContext, Depends(require("org:read"))]
) -> OrgOut:
    ensure_path_org(ctx, org_id)
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as session:
        org = await session.get(Org, org_id)
    if org is None:
        raise ProblemError(404)
    return org_out(org)


@router.patch("/orgs/{org_id}/profile", response_model=OrgOut, summary="Edit name and business profile")
async def patch_profile(
    org_id: uuid.UUID,
    body: OrgProfilePatch,
    state: StateDep,
    ctx: Annotated[OrgContext, Depends(require("org:write"))],
) -> OrgOut:
    ensure_path_org(ctx, org_id)
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as session:
        org = await session.get(Org, org_id, with_for_update=True)
        if org is None:
            raise ProblemError(404)
        changed: list[str] = []
        if body.name is not None and body.name != org.name:
            org.name = body.name.strip()
            changed.append("name")
        if body.business_profile is not None:
            new_profile = body.business_profile.model_dump(exclude_none=True)
            old_profile = dict(org.business_profile or {})
            diff = sorted(
                k for k in set(new_profile) | set(old_profile) if new_profile.get(k) != old_profile.get(k)
            )
            if diff:
                changed.extend(f"business_profile.{k}" for k in diff)
                org.business_profile = new_profile
                org.profile_version += 1  # re-triggers assessment from Phase 3
        if changed:
            await audit.emit(
                session,
                actor=ctx.actor,
                action="org.profile.updated",
                org_id=org_id,
                target_type="org",
                target_id=str(org_id),
                details={"fields": sorted(set(changed)), "profile_version": org.profile_version},
            )
        await session.flush()
        await session.refresh(org)
        return org_out(org)
