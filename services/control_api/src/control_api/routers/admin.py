"""Staff console API (``/v1/admin/*``): M-01 dashboard, M-02/M-03 tenants, M-12 audit & security, M-13 flags.

Staff see tenant **metadata** only. Every staff action that touches a tenant is written to that tenant's audit
chain, so the customer sees it in G-04 (SPEC §8.3).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from control_api import audit
from control_api.deps import StaffContext, StaffDep, StateDep, staff_require
from control_api.models import (
    AppUser,
    AuditEvent,
    AuditVerificationRun,
    FeatureFlag,
    Membership,
    Org,
    TenantDb,
    TenantKey,
)
from control_api.routers.activity import audit_out
from control_api.routers.orgs import org_out
from control_api.schemas import (
    AuditEventOut,
    DashboardOut,
    DeprovisionRequest,
    FlagRow,
    FlagUpsert,
    Page,
    StaffMeOut,
    TenantDetail,
    TenantRow,
    VerificationRunOut,
    WorkflowStarted,
)
from control_api.workflows.inputs import (
    AUDIT_VERIFY_WORKFLOW,
    DEPROVISION_WORKFLOW,
    PROVISION_WORKFLOW,
    DeprovisionInput,
    ProvisionInput,
)
from dcs_common.audit import PLATFORM_CHAIN
from dcs_common.ids import workflow_id
from dcs_common.problem import PROBLEM_RESPONSES, ProblemError, conflict, not_found

FlagScope = Literal["global", "plan", "org"]

router = APIRouter(prefix="/v1/admin", tags=["admin"], responses=PROBLEM_RESPONSES)


AuditRead = Annotated[StaffContext, Depends(staff_require("platform:audit:read"))]
DashboardRead = Annotated[StaffContext, Depends(staff_require("platform:dashboard:read"))]
FlagsRead = Annotated[StaffContext, Depends(staff_require("platform:flags:read"))]
FlagsWrite = Annotated[StaffContext, Depends(staff_require("platform:flags:write"))]
SecurityRead = Annotated[StaffContext, Depends(staff_require("platform:security:read"))]
TenantsDeprovision = Annotated[StaffContext, Depends(staff_require("platform:tenants:deprovision"))]
TenantsRead = Annotated[StaffContext, Depends(staff_require("platform:tenants:read"))]
TenantsWrite = Annotated[StaffContext, Depends(staff_require("platform:tenants:write"))]


@router.get("/me", response_model=StaffMeOut, summary="Current staff identity, roles and permissions")
async def staff_me(ctx: StaffDep) -> StaffMeOut:
    p = ctx.principal
    return StaffMeOut(
        subject=p.subject,
        email=p.email,
        name=p.name,
        roles=sorted(ctx.roles),
        permissions=sorted(ctx.permissions),
        session_mfa=p.has_mfa(),
    )


@router.get("/dashboard", response_model=DashboardOut, summary="Platform dashboard (M-01)")
async def dashboard(state: StateDep, ctx: DashboardRead) -> DashboardOut:
    async with state.db.platform_tx() as s:
        by_status: dict[str, int] = {}
        for row in await s.execute(select(Org.status, func.count()).group_by(Org.status)):
            by_status[row[0]] = row[1]
        by_region: dict[str, int] = {}
        for row in await s.execute(select(Org.region, func.count()).group_by(Org.region)):
            by_region[row[0]] = row[1]
        users = await s.scalar(select(func.count()).select_from(AppUser)) or 0
        latest = (
            select(AuditVerificationRun.chain, func.max(AuditVerificationRun.id).label("id"))
            .group_by(AuditVerificationRun.chain)
            .subquery()
        )
        runs = (
            await s.scalars(select(AuditVerificationRun).join(latest, AuditVerificationRun.id == latest.c.id))
        ).all()
    return DashboardOut(
        tenants_by_status=by_status,
        tenants_by_region=by_region,
        users=users,
        audit_chains_failing=sum(1 for r in runs if not r.ok),
        last_verification_at=max((r.ran_at for r in runs), default=None),
    )


@router.get("/tenants", response_model=Page[TenantRow], summary="Tenants list (M-02)")
async def list_tenants(
    state: StateDep,
    ctx: TenantsRead,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query(max_length=20)] = None,
    region: Annotated[str | None, Query(max_length=20)] = None,
    cursor: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[TenantRow]:
    stmt = select(Org, TenantDb.status).outerjoin(TenantDb, TenantDb.org_id == Org.id)
    if q:
        like = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(Org.name.ilike(like) | Org.slug.ilike(like) | Org.tenant_id.ilike(like))
    if status:
        stmt = stmt.where(Org.status == status)
    if region:
        stmt = stmt.where(Org.region == region)
    if cursor:
        stmt = stmt.where(Org.id < cursor)
    async with state.db.platform_tx() as s:
        rows = (await s.execute(stmt.order_by(Org.id.desc()).limit(limit + 1))).all()
    items = [
        TenantRow(
            org_id=o.id,
            tenant_id=o.tenant_id,
            name=o.name,
            slug=o.slug,
            region=o.region,
            status=o.status,
            plan_id=o.plan_id,
            db_status=db_status,
            created_at=o.created_at,
        )
        for o, db_status in rows[:limit]
    ]
    return Page(items=items, next_cursor=str(rows[limit - 1][0].id) if len(rows) > limit else None)


@router.get("/tenants/{org_id}", response_model=TenantDetail, summary="Tenant detail (M-03)")
async def tenant_detail(org_id: uuid.UUID, state: StateDep, ctx: TenantsRead) -> TenantDetail:
    async with state.db.platform_tx() as s:
        org = await s.get(Org, org_id)
        if org is None:
            raise not_found()
        db = await s.get(TenantDb, org_id)
        key = await s.get(TenantKey, org_id)
        members = (
            await s.scalar(
                select(func.count())
                .select_from(Membership)
                .where(Membership.org_id == org_id, Membership.status == "active")
            )
            or 0
        )
        owners = (
            await s.scalars(
                select(AppUser.email)
                .join(Membership, Membership.user_id == AppUser.id)
                .where(Membership.org_id == org_id, Membership.role == "owner", Membership.status == "active")
            )
        ).all()
        recent = (
            await s.scalars(
                select(AuditEvent).where(AuditEvent.org_id == org_id).order_by(AuditEvent.id.desc()).limit(20)
            )
        ).all()
        await audit.emit(
            s,
            actor=ctx.actor,
            action="staff.tenant.viewed",
            org_id=org_id,
            target_type="org",
            target_id=str(org_id),
            details={"scope": "metadata"},
        )
    return TenantDetail(
        org=org_out(org),
        db={"cluster": db.cluster, "db_name": db.db_name, "status": db.status, "cbm_version": db.cbm_version}
        if db
        else None,
        key={
            "status": key.status,
            "created_at": key.created_at,
            "deletion_scheduled_at": key.deletion_scheduled_at,
            "provider": "aws-kms" if key.kms_key_arn.startswith("arn:") else "local",
        }
        if key
        else None,
        member_count=members,
        owners=list(owners),
        recent_audit=[audit_out(e) for e in recent],
    )


@router.post(
    "/tenants/{org_id}/deprovision",
    status_code=202,
    response_model=WorkflowStarted,
    summary="Deprovision a tenant: drop DB, delete prefixes, schedule key deletion",
)
async def deprovision(
    org_id: uuid.UUID,
    body: DeprovisionRequest,
    state: StateDep,
    ctx: TenantsDeprovision,
) -> WorkflowStarted:
    pending_days = body.pending_days or await state.config.get_int("chassis.deprovision_default_pending_days")
    async with state.db.platform_tx() as s:
        org = await s.get(Org, org_id, with_for_update=True)
        if org is None or org.status == "deleted":
            raise not_found()
        if body.confirm_slug != org.slug:
            raise ProblemError(422, slug="confirmation-mismatch", detail="Type the tenant slug to confirm.")
        if org.status == "deprovisioning":
            raise conflict("Deprovisioning is already running.")
        org.status = "deprovisioning"
        tenant_id = org.tenant_id
        await audit.emit(
            s,
            actor=ctx.actor,
            action="tenant.deprovision.requested",
            org_id=org_id,
            target_type="org",
            target_id=str(org_id),
            details={"reason": body.reason, "pending_days": pending_days},
        )
    wf = workflow_id("deprovision", tenant_id, "v1")
    await state.workflows.start(
        DEPROVISION_WORKFLOW,
        DeprovisionInput(str(org_id), tenant_id, ctx.principal.subject, body.reason, pending_days),
        workflow_id=wf,
    )
    return WorkflowStarted(workflow_id=wf)


@router.post(
    "/tenants/{org_id}/retry-provisioning",
    status_code=202,
    response_model=WorkflowStarted,
    summary="Retry a failed or stuck provisioning",
)
async def retry_provisioning(org_id: uuid.UUID, state: StateDep, ctx: TenantsWrite) -> WorkflowStarted:
    async with state.db.platform_tx() as s:
        org = await s.get(Org, org_id, with_for_update=True)
        if org is None:
            raise not_found()
        if org.status not in ("provisioning", "failed"):
            raise conflict(f"Tenant is {org.status}; nothing to retry.")
        org.status = "provisioning"
        tenant_id, created_by = org.tenant_id, str(org.created_by or "")
        await audit.emit(
            s,
            actor=ctx.actor,
            action="tenant.provision.retried",
            org_id=org_id,
            target_type="org",
            target_id=str(org_id),
        )
    wf = workflow_id("provision", tenant_id, "v1")
    await state.workflows.start(
        PROVISION_WORKFLOW,
        ProvisionInput(str(org_id), tenant_id, created_by),
        workflow_id=wf,
        allow_retry_failed=True,
    )
    return WorkflowStarted(workflow_id=wf)


# ------------------------------------------------------------------------------- audit & security
@router.get("/audit", response_model=Page[AuditEventOut], summary="Platform-wide audit (M-12)")
async def platform_audit(
    state: StateDep,
    ctx: AuditRead,
    org_id: uuid.UUID | None = None,
    actor_type: Annotated[str | None, Query(pattern="^(user|staff|system|api_key)$")] = None,
    platform_only: bool = False,
    cursor: Annotated[str | None, Query(pattern=r"^\d+$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[AuditEventOut]:
    stmt = select(AuditEvent)
    if platform_only:
        stmt = stmt.where(AuditEvent.org_id.is_(None))
    elif org_id:
        stmt = stmt.where(AuditEvent.org_id == org_id)
    if actor_type:
        stmt = stmt.where(AuditEvent.actor_type == actor_type)
    if cursor:
        stmt = stmt.where(AuditEvent.id < int(cursor))
    async with state.db.platform_tx() as s:
        rows = (await s.scalars(stmt.order_by(AuditEvent.id.desc()).limit(limit + 1))).all()
    return Page(
        items=[audit_out(e) for e in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.get(
    "/audit/verification", response_model=list[VerificationRunOut], summary="Latest chain verification"
)
async def verification_status(state: StateDep, ctx: SecurityRead) -> list[VerificationRunOut]:
    latest = (
        select(AuditVerificationRun.chain, func.max(AuditVerificationRun.id).label("id"))
        .group_by(AuditVerificationRun.chain)
        .subquery()
    )
    async with state.db.platform_tx() as s:
        runs = (
            await s.scalars(
                select(AuditVerificationRun)
                .join(latest, AuditVerificationRun.id == latest.c.id)
                .order_by(AuditVerificationRun.ok, AuditVerificationRun.ran_at.desc())
            )
        ).all()
    return [
        VerificationRunOut(
            chain=r.chain,
            ran_at=r.ran_at,
            ok=r.ok,
            checked=r.checked,
            first_bad_id=r.first_bad_id,
            reason=r.reason,
        )
        for r in runs
    ]


@router.post(
    "/audit/verify", status_code=202, response_model=WorkflowStarted, summary="Run chain verification now"
)
async def verify_now(state: StateDep, ctx: SecurityRead) -> WorkflowStarted:
    wf = workflow_id("audit-verify", "platform", datetime.now(UTC).strftime("%Y%m%dT%H%M%S"))
    async with state.db.platform_tx() as s:
        await audit.emit(
            s,
            actor=ctx.actor,
            action="staff.audit.verify_requested",
            org_id=None,
            target_type="workflow",
            target_id=wf,
        )
    await state.workflows.start(AUDIT_VERIFY_WORKFLOW, None, workflow_id=wf)
    return WorkflowStarted(workflow_id=wf)


# ------------------------------------------------------------------------------------------ flags
@router.get("/flags", response_model=list[FlagRow], summary="Feature flags (M-13)")
async def list_flags(state: StateDep, ctx: FlagsRead) -> list[FlagRow]:
    async with state.db.unscoped_tx() as s:
        rows = (await s.scalars(select(FeatureFlag).order_by(FeatureFlag.key, FeatureFlag.scope))).all()
    return [
        FlagRow(
            key=r.key,
            scope=cast(FlagScope, r.scope),
            scope_id=r.scope_id,
            value=r.value,
            updated_by=r.updated_by,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.put("/flags", response_model=FlagRow, summary="Create or update a flag")
async def upsert_flag(body: FlagUpsert, state: StateDep, ctx: FlagsWrite) -> FlagRow:
    if (body.scope == "global") != (body.scope_id == ""):
        raise ProblemError(422, detail="Global flags have no scope_id; plan/org flags need one.")
    now = datetime.now(UTC)
    stmt = insert(FeatureFlag).values(
        key=body.key,
        scope=body.scope,
        scope_id=body.scope_id,
        value=body.value,
        updated_by=ctx.principal.subject,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["key", "scope", "scope_id"],
        set_={"value": body.value, "updated_by": ctx.principal.subject, "updated_at": now},
    )
    async with state.db.platform_tx() as s:
        await s.execute(stmt)
        target_org = uuid.UUID(body.scope_id) if body.scope == "org" else None
        await audit.emit(
            s,
            actor=ctx.actor,
            action="staff.flag.set",
            org_id=target_org,
            target_type="flag",
            target_id=f"{body.key}@{body.scope}:{body.scope_id}",
            details={"value": body.value},
        )
    return FlagRow(
        key=body.key,
        scope=body.scope,
        scope_id=body.scope_id,
        value=body.value,
        updated_by=ctx.principal.subject,
        updated_at=now,
    )


@router.delete("/flags/{key}", status_code=204, summary="Delete a flag override")
async def delete_flag(
    key: str,
    state: StateDep,
    ctx: FlagsWrite,
    scope: Annotated[str, Query(pattern="^(global|plan|org)$")] = "global",
    scope_id: str = "",
) -> Response:
    async with state.db.platform_tx() as s:
        result = await s.execute(
            delete(FeatureFlag).where(
                FeatureFlag.key == key, FeatureFlag.scope == scope, FeatureFlag.scope_id == scope_id
            )
        )
        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise not_found()
        await audit.emit(
            s,
            actor=ctx.actor,
            action="staff.flag.deleted",
            org_id=None,
            target_type="flag",
            target_id=f"{key}@{scope}:{scope_id}",
        )
    return Response(status_code=204)


__all__ = ["PLATFORM_CHAIN", "router"]
