"""RBAC policy engine (SPEC §8.3)."""

from dcs_authz.engine import (
    CUSTOMER_ROLES,
    STAFF_ROLES,
    PermissionDeniedError,
    Policy,
    PolicyError,
    RoleDef,
    default_policy,
)

__all__ = [
    "CUSTOMER_ROLES",
    "STAFF_ROLES",
    "PermissionDeniedError",
    "Policy",
    "PolicyError",
    "RoleDef",
    "default_policy",
]
