"""RBAC policy matrix: every role × every permission against an explicit expected table (SPEC §13 P0 tests).

This table is the reviewed statement of the security boundary. If policies.yaml changes, this file must
change in the same commit, otherwise the matrix test fails.
"""

from __future__ import annotations

import pytest

from dcs_authz import CUSTOMER_ROLES, STAFF_ROLES, default_policy

ALL_CUSTOMER = {
    "org:read",
    "org:write",
    "org:delete",
    "members:read",
    "members:invite",
    "members:manage",
    "security:read",
    "security:write",
    "audit:read",
    "notifications:read",
    "flags:read",
    "billing:read",
    "billing:write",
    "sources:read",
    "sources:write",
    "studio:read",
    "mapping:read",
    "mapping:write",
    "mapping:approve",
    "er:review",
    "dq:review",
    "dq:waive",
    "pipeline:read",
    "pipeline:replay",
    "tools:read",
    "tools:run",
    "tools:manage",
    "insights:read",
    "actions:approve_basic",
    "actions:approve_elevated",
    "governance:read",
    "governance:write",
}
ALL_PLATFORM = {
    "platform:dashboard:read",
    "platform:tenants:read",
    "platform:tenants:write",
    "platform:tenants:deprovision",
    "platform:flags:read",
    "platform:flags:write",
    "platform:audit:read",
    "platform:security:read",
    "platform:breakglass:request",
    "platform:breakglass:approve",
}

EXPECTED: dict[str, set[str]] = {
    "owner": set(ALL_CUSTOMER),
    "admin": ALL_CUSTOMER - {"org:delete", "billing:write", "governance:write"},
    "data_manager": {
        "org:read",
        "notifications:read",
        "flags:read",
        "sources:read",
        "sources:write",
        "studio:read",
        "mapping:read",
        "mapping:write",
        "mapping:approve",
        "er:review",
        "dq:review",
        "dq:waive",
        "pipeline:read",
        "pipeline:replay",
        "tools:read",
        "insights:read",
    },
    "analyst": {
        "org:read",
        "notifications:read",
        "flags:read",
        "studio:read",
        "mapping:read",
        "pipeline:read",
        "tools:read",
        "tools:run",
        "insights:read",
        "actions:approve_basic",
    },
    "viewer": {"org:read", "notifications:read", "flags:read", "insights:read"},
    "billing": {"org:read", "notifications:read", "flags:read", "billing:read", "billing:write"},
    "staff_support": {
        "platform:dashboard:read",
        "platform:tenants:read",
        "platform:audit:read",
        "platform:breakglass:request",
    },
    "staff_ops": {
        "platform:dashboard:read",
        "platform:tenants:read",
        "platform:tenants:write",
        "platform:flags:read",
        "platform:flags:write",
        "platform:audit:read",
        "platform:security:read",
        "platform:breakglass:request",
    },
    "staff_admin": set(ALL_PLATFORM),
}

ROLES = [*CUSTOMER_ROLES, *STAFF_ROLES]
PERMISSIONS = sorted(ALL_CUSTOMER | ALL_PLATFORM)


def test_declared_permissions_match_matrix() -> None:
    assert set(default_policy().permissions) == ALL_CUSTOMER | ALL_PLATFORM


def test_declared_roles_match_matrix() -> None:
    assert set(default_policy().roles) == set(ROLES) == set(EXPECTED)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("permission", PERMISSIONS)
def test_matrix_cell(role: str, permission: str) -> None:
    assert default_policy().allows(role, permission) is (permission in EXPECTED[role])


@pytest.mark.parametrize("role", ROLES)
def test_permissions_for_equals_matrix_row(role: str) -> None:
    assert default_policy().permissions_for(role) == frozenset(EXPECTED[role])


def test_customer_roles_never_hold_platform_permissions() -> None:
    policy = default_policy()
    for role in CUSTOMER_ROLES:
        assert not any(p.startswith("platform:") for p in policy.permissions_for(role))


def test_staff_roles_never_hold_customer_permissions() -> None:
    policy = default_policy()
    for role in STAFF_ROLES:
        assert all(p.startswith("platform:") for p in policy.permissions_for(role))


@pytest.mark.parametrize(
    ("role", "required"),
    [
        ("owner", True),
        ("admin", True),
        ("data_manager", False),
        ("analyst", False),
        ("viewer", False),
        ("billing", False),
        ("staff_support", True),
        ("staff_ops", True),
        ("staff_admin", True),
    ],
)
def test_mfa_required(role: str, required: bool) -> None:
    assert default_policy().mfa_required(role) is required


@pytest.mark.parametrize(
    ("actor", "target", "allowed"),
    [
        ("owner", "owner", True),
        ("owner", "billing", True),
        ("admin", "owner", False),  # no privilege escalation
        ("admin", "admin", True),
        ("admin", "viewer", True),
        ("data_manager", "viewer", False),
        ("analyst", "viewer", False),
        ("viewer", "viewer", False),
        ("billing", "viewer", False),
        ("staff_admin", "owner", False),
        (None, "viewer", False),
        ("owner", "nope", False),
    ],
)
def test_can_assign(actor: str | None, target: str, allowed: bool) -> None:
    assert default_policy().can_assign(actor, target) is allowed
