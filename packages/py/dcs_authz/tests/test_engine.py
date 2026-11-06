from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dcs_authz import PermissionDeniedError, Policy, PolicyError, default_policy

BASE: dict[str, Any] = {
    "version": 3,
    "permissions": {"a:read": "A", "a:write": "B", "platform:x": "X"},
    "roles": {
        "r1": {"scope": "customer", "permissions": ["a:read"]},
        "r2": {"scope": "customer", "permissions": ["*"], "exclude": ["a:write"], "can_assign": ["r1"]},
        "s1": {"scope": "platform", "permissions": ["*"], "mfa_required": True},
    },
}


def _policy(**overrides: Any) -> Policy:
    doc = {**BASE, **overrides}
    return Policy.from_mapping(doc)


def test_wildcard_expands_to_scope_minus_exclude() -> None:
    p = _policy()
    assert p.permissions_for("r2") == frozenset({"a:read"})
    assert p.permissions_for("s1") == frozenset({"platform:x"})
    assert p.version == 3


def test_unknown_role_and_none_are_denied() -> None:
    p = _policy()
    assert p.allows(None, "a:read") is False
    assert p.allows("ghost", "a:read") is False
    assert p.permissions_for(None) == frozenset()
    assert p.permissions_for("ghost") == frozenset()
    assert p.mfa_required(None) is False
    assert p.mfa_required("ghost") is False


def test_unknown_permission_raises_instead_of_denying_silently() -> None:
    with pytest.raises(PolicyError):
        _policy().allows("r1", "typo:perm")


def test_require() -> None:
    p = _policy()
    p.require("r1", "a:read")
    with pytest.raises(PermissionDeniedError) as exc:
        p.require("r1", "a:write")
    assert exc.value.role == "r1"
    assert exc.value.permission == "a:write"


def test_allows_any() -> None:
    p = _policy()
    assert p.allows_any({"r1", "s1"}, "platform:x") is True
    assert p.allows_any(set(), "a:read") is False


def test_role_lookup() -> None:
    p = _policy()
    assert p.role("r1").scope == "customer"
    with pytest.raises(PolicyError):
        p.role("ghost")


def test_roles_in_scope() -> None:
    assert _policy().roles_in_scope("platform") == ["s1"]


@pytest.mark.parametrize(
    "doc",
    [
        [],
        {"permissions": {}, "roles": {"r": {"scope": "customer"}}},
        {"permissions": {"a:read": "A"}, "roles": {}},
        {"permissions": {"a:read": "A"}, "roles": {"r": "not-a-mapping"}},
        {"permissions": {"a:read": "A"}, "roles": {"r": {"scope": "galaxy"}}},
        {"permissions": {"a:read": "A"}, "roles": {"r": {"scope": "customer", "permissions": ["b:read"]}}},
        {"permissions": {"a:read": "A"}, "roles": {"r": {"scope": "customer", "exclude": ["b:read"]}}},
        {
            "permissions": {"platform:x": "X"},
            "roles": {"r": {"scope": "customer", "permissions": ["platform:x"]}},
        },
        {"permissions": {"a:read": "A"}, "roles": {"r": {"scope": "platform", "permissions": ["a:read"]}}},
        {"permissions": {"a:read": "A"}, "roles": {"r": {"scope": "customer", "can_assign": ["ghost"]}}},
        {
            "permissions": {"a:read": "A", "platform:x": "X"},
            "roles": {"r": {"scope": "customer", "can_assign": ["s"]}, "s": {"scope": "platform"}},
        },
    ],
)
def test_invalid_policies_fail_fast(doc: Any) -> None:
    with pytest.raises(PolicyError):
        Policy.from_mapping(doc)


def test_load_from_path(tmp_path: Path) -> None:
    f = tmp_path / "p.yaml"
    f.write_text(
        "permissions: {x:read: X}\nroles: {r: {scope: customer, permissions: [x:read]}}\n", encoding="utf-8"
    )
    assert Policy.load(f).allows("r", "x:read")


def test_default_policy_is_cached() -> None:
    assert default_policy() is default_policy()
