"""Load and evaluate ``policies.yaml``.

Rules enforced at load time (a broken policy file fails fast, never silently grants):
- every permission referenced by a role must be declared;
- customer roles may only hold customer permissions, platform roles only ``platform:*`` permissions;
- ``"*"`` expands to every permission of the role's scope, minus ``exclude``;
- ``can_assign`` may only name roles of the same scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import yaml

Scope = Literal["customer", "platform"]
PLATFORM_PREFIX = "platform:"

CUSTOMER_ROLES: tuple[str, ...] = ("owner", "admin", "data_manager", "analyst", "viewer", "billing")
STAFF_ROLES: tuple[str, ...] = ("staff_support", "staff_ops", "staff_admin")


class PolicyError(ValueError):
    """The policy file is invalid."""


class PermissionDeniedError(Exception):
    def __init__(self, role: str | None, permission: str) -> None:
        self.role = role
        self.permission = permission
        super().__init__(f"role {role!r} lacks permission {permission!r}")


@dataclass(frozen=True)
class RoleDef:
    name: str
    scope: Scope
    permissions: frozenset[str]
    mfa_required: bool
    can_assign: frozenset[str]


def _scope_of(permission: str) -> Scope:
    return "platform" if permission.startswith(PLATFORM_PREFIX) else "customer"


class Policy:
    def __init__(self, permissions: dict[str, str], roles: dict[str, RoleDef], version: int) -> None:
        self.permissions = permissions
        self.roles = roles
        self.version = version

    # ------------------------------------------------------------------ loading
    @classmethod
    def from_mapping(cls, doc: dict[str, Any]) -> Policy:
        if not isinstance(doc, dict):
            raise PolicyError("policy document must be a mapping")
        raw_perms = doc.get("permissions")
        raw_roles = doc.get("roles")
        if not isinstance(raw_perms, dict) or not raw_perms:
            raise PolicyError("'permissions' must be a non-empty mapping")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise PolicyError("'roles' must be a non-empty mapping")
        permissions = {str(k): str(v) for k, v in raw_perms.items()}

        roles: dict[str, RoleDef] = {}
        for name, spec in raw_roles.items():
            if not isinstance(spec, dict):
                raise PolicyError(f"role {name!r} must be a mapping")
            scope = spec.get("scope")
            if scope not in ("customer", "platform"):
                raise PolicyError(f"role {name!r}: scope must be 'customer' or 'platform'")
            listed = [str(p) for p in spec.get("permissions", [])]
            excluded = {str(p) for p in spec.get("exclude", [])}
            for p in [*(x for x in listed if x != "*"), *excluded]:
                if p not in permissions:
                    raise PolicyError(f"role {name!r}: unknown permission {p!r}")
                if _scope_of(p) != scope:
                    raise PolicyError(f"role {name!r}: permission {p!r} is outside scope {scope!r}")
            granted = (
                {p for p in permissions if _scope_of(p) == scope} if "*" in listed else set(listed)
            ) - excluded
            roles[str(name)] = RoleDef(
                name=str(name),
                scope=scope,
                permissions=frozenset(granted),
                mfa_required=bool(spec.get("mfa_required", False)),
                can_assign=frozenset(str(r) for r in spec.get("can_assign", [])),
            )
        for role in roles.values():
            for target in role.can_assign:
                if target not in roles:
                    raise PolicyError(f"role {role.name!r}: can_assign names unknown role {target!r}")
                if roles[target].scope != role.scope:
                    raise PolicyError(f"role {role.name!r}: cannot assign role {target!r} of another scope")
        return cls(permissions, roles, int(doc.get("version", 1)))

    @classmethod
    def load(cls, path: Path | None = None) -> Policy:
        if path is None:
            text = resources.files("dcs_authz").joinpath("policies.yaml").read_text(encoding="utf-8")
        else:
            text = path.read_text(encoding="utf-8")
        return cls.from_mapping(yaml.safe_load(text))

    # --------------------------------------------------------------- evaluation
    def role(self, name: str) -> RoleDef:
        try:
            return self.roles[name]
        except KeyError:
            raise PolicyError(f"unknown role {name!r}") from None

    def allows(self, role: str | None, permission: str) -> bool:
        if permission not in self.permissions:
            raise PolicyError(f"unknown permission {permission!r}")
        if role is None or role not in self.roles:
            return False
        return permission in self.roles[role].permissions

    def allows_any(self, roles: frozenset[str] | set[str], permission: str) -> bool:
        return any(self.allows(r, permission) for r in roles)

    def require(self, role: str | None, permission: str) -> None:
        if not self.allows(role, permission):
            raise PermissionDeniedError(role, permission)

    def permissions_for(self, role: str | None) -> frozenset[str]:
        if role is None or role not in self.roles:
            return frozenset()
        return self.roles[role].permissions

    def mfa_required(self, role: str | None) -> bool:
        return role is not None and role in self.roles and self.roles[role].mfa_required

    def can_assign(self, actor_role: str | None, target_role: str) -> bool:
        if actor_role is None or actor_role not in self.roles or target_role not in self.roles:
            return False
        return target_role in self.roles[actor_role].can_assign

    def roles_in_scope(self, scope: Scope) -> list[str]:
        return [r.name for r in self.roles.values() if r.scope == scope]


@lru_cache(maxsize=1)
def default_policy() -> Policy:
    return Policy.load()
